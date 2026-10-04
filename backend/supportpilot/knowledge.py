import asyncio
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, field_validator
from sqlalchemy import delete, func, select, text, update

from supportpilot.knowledge_storage import KnowledgeDocumentRow
from supportpilot.redaction import redact
from supportpilot.retrieval import ChunkRow
from supportpilot.schemas import Contract


class DocumentInput(Contract):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=20, max_length=30000)
    product_version: Literal["v1", "v2", "any"] = "any"
    source_path: str = Field(default="", max_length=200)

    @field_validator("title", "body", "source_path", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class DocumentUpdate(DocumentInput):
    expected_revision: int = Field(ge=1)


class RevisionInput(Contract):
    expected_revision: int = Field(ge=1)


class SearchInput(Contract):
    query: str = Field(min_length=2, max_length=2000)
    product_version: Literal["v1", "v2"] | None = None

    @field_validator("query", mode="before")
    @classmethod
    def trim_query(cls, value):
        return value.strip() if isinstance(value, str) else value


def document_response(row, chunk_count):
    return {
        "id": row.id,
        "title": row.title,
        "body": row.body,
        "product_version": row.product_version,
        "source_path": row.source_path,
        "revision": row.revision,
        "origin": "workspace",
        "chunk_count": chunk_count,
        "updated_at": (
            row.updated_at.replace(tzinfo=UTC)
            if row.updated_at.tzinfo is None
            else row.updated_at.astimezone(UTC)
        ),
        "archived": row.archived,
    }


def build_knowledge_router(database, retrieval, identity, settings):
    router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

    def admin(caller=Depends(identity)):
        if caller.get("role", "admin") != "admin":
            raise HTTPException(403, "Only workspace admins can change knowledge documents")
        return caller

    def get_document(session, document_id, workspace):
        row = session.scalar(
            select(KnowledgeDocumentRow).where(
                KnowledgeDocumentRow.id == document_id,
                KnowledgeDocumentRow.workspace_id == workspace,
            )
        )
        if row is None:
            # Seed IDs are never mutable; don't reveal documents in other workspaces.
            raise HTTPException(404, "Editable document not found")
        return row

    async def prepare(doc):
        try:
            async with asyncio.timeout(settings.timeout_seconds):
                return await retrieval.prepare_document(doc)
        except Exception as exc:
            raise HTTPException(
                503, "Document indexing unavailable. No changes were saved."
            ) from exc

    def contents(payload):
        return {
            "title": redact(payload.title),
            "body": redact(payload.body),
            "product_version": payload.product_version,
            "source_path": redact(payload.source_path),
        }

    def scope(row):
        return ChunkRow.document_id == row.id, ChunkRow.workspace_id == row.workspace_id

    @router.get("/documents")
    def list_documents(caller=Depends(identity)):
        with database.session() as session:
            rows = session.scalars(
                select(KnowledgeDocumentRow)
                .where(KnowledgeDocumentRow.workspace_id == caller["workspace_id"])
                .order_by(KnowledgeDocumentRow.updated_at.desc())
            ).all()
            chunks = session.scalars(
                select(ChunkRow).where(ChunkRow.workspace_id == caller["workspace_id"])
            ).all()
            groups = {}
            for chunk in chunks:
                groups.setdefault(chunk.document_id, []).append(chunk)
            items = [document_response(row, len(groups.get(row.id, []))) for row in rows]
            custom_ids = {row.id for row in rows}
            for document_id, parts in sorted(groups.items()):
                if document_id in custom_ids:
                    continue
                first = parts[0]
                items.append(
                    {
                        "id": document_id,
                        "title": first.title,
                        "body": "".join(
                            item.body
                            for item in sorted(parts, key=lambda p: int(p.id.rsplit(":", 1)[1]))
                        ),
                        "product_version": first.version,
                        "source_path": first.source_path,
                        "revision": int(first.revision) if first.revision.isdigit() else 1,
                        "origin": "seed",
                        "chunk_count": len(parts),
                        "updated_at": None,
                        "archived": False,
                    }
                )
            return {"items": items, "total": len(items)}

    @router.post("/documents", status_code=201)
    async def add_document(payload: DocumentInput, caller=Depends(admin)):
        row = KnowledgeDocumentRow(
            id="kb-" + str(uuid4()),
            workspace_id=caller["workspace_id"],
            **contents(payload),
            revision=1,
            archived=False,
            updated_at=datetime.now(UTC),
        )
        prepared = await prepare(row.document())
        with database.session() as session:
            if database.engine.dialect.name == "postgresql":
                session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:workspace))"),
                    {"workspace": caller["workspace_id"]},
                )
            count = session.scalar(
                select(func.count())
                .select_from(KnowledgeDocumentRow)
                .where(KnowledgeDocumentRow.workspace_id == caller["workspace_id"])
            )
            if count >= 100:
                raise HTTPException(
                    409, "Workspace document limit reached (100 including archives)"
                )
            session.add(row)
            retrieval.write_document(session, row.document(), prepared)
            session.commit()
            return document_response(row, len(prepared[1]))

    @router.patch("/documents/{document_id}")
    async def edit_document(document_id: str, payload: DocumentUpdate, caller=Depends(admin)):
        with database.session() as session:
            row = get_document(session, document_id, caller["workspace_id"])
            if row.revision != payload.expected_revision:
                raise HTTPException(409, "Document changed. Reload it before saving.")
            if row.archived:
                raise HTTPException(409, "Restore this document before editing")
            doc = {**row.document(), **contents(payload), "revision": str(row.revision + 1)}
        prepared = await prepare(doc)
        with database.session() as session:
            changed = session.execute(
                update(KnowledgeDocumentRow)
                .where(
                    KnowledgeDocumentRow.id == document_id,
                    KnowledgeDocumentRow.workspace_id == caller["workspace_id"],
                    KnowledgeDocumentRow.revision == payload.expected_revision,
                    KnowledgeDocumentRow.archived.is_(False),
                )
                .values(
                    **contents(payload),
                    revision=payload.expected_revision + 1,
                    updated_at=datetime.now(UTC),
                )
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "Document changed. Reload it before saving.")
            retrieval.write_document(session, doc, prepared)
            session.commit()
            return document_response(
                get_document(session, document_id, caller["workspace_id"]), len(prepared[1])
            )

    async def change_archive(document_id, expected_revision, archived, caller):
        with database.session() as session:
            row = get_document(session, document_id, caller["workspace_id"])
            if row.revision != expected_revision:
                raise HTTPException(409, "Document changed. Reload it before saving.")
            if row.archived == archived:
                raise HTTPException(409, "Document is already in the requested state")
            doc = {**row.document(), "revision": str(row.revision + 1)}
        prepared = None if archived else await prepare(doc)
        with database.session() as session:
            changed = session.execute(
                update(KnowledgeDocumentRow)
                .where(
                    KnowledgeDocumentRow.id == document_id,
                    KnowledgeDocumentRow.workspace_id == caller["workspace_id"],
                    KnowledgeDocumentRow.revision == expected_revision,
                )
                .values(
                    archived=archived, revision=expected_revision + 1, updated_at=datetime.now(UTC)
                )
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "Document changed. Reload it before saving.")
            row = get_document(session, document_id, caller["workspace_id"])
            if archived:
                session.execute(delete(ChunkRow).where(*scope(row)))
            else:
                retrieval.write_document(session, doc, prepared)
            session.commit()
            return document_response(row, 0 if archived else len(prepared[1]))

    @router.post("/documents/{document_id}/archive")
    async def archive_document(document_id: str, payload: RevisionInput, caller=Depends(admin)):
        return await change_archive(document_id, payload.expected_revision, True, caller)

    @router.post("/documents/{document_id}/restore")
    async def restore_document(document_id: str, payload: RevisionInput, caller=Depends(admin)):
        return await change_archive(document_id, payload.expected_revision, False, caller)

    @router.post("/search")
    async def search_documents(payload: SearchInput, caller=Depends(identity)):
        try:
            async with asyncio.timeout(settings.timeout_seconds):
                evidence = await retrieval.search(
                    redact(payload.query), caller["workspace_id"], payload.product_version
                )
        except Exception as exc:
            raise HTTPException(503, "Knowledge search unavailable. Please try again.") from exc
        return {"evidence": evidence}

    return router
