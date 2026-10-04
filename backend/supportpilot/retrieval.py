import hashlib
import json
import math
import re

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, String, Text, delete, func, select
from sqlalchemy.orm import Mapped, mapped_column

from supportpilot.knowledge_storage import KnowledgeDocumentRow
from supportpilot.schemas import Evidence
from supportpilot.storage import Base

DIMENSIONS = 1536
STOP_WORDS = {"the", "a", "an", "to", "we", "our", "is", "my", "what", "how", "it", "and"}


def terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_-]+", text.lower())) - STOP_WORDS


def fixture_embedding(text: str) -> list[float]:
    """Reproducible lexical feature hashing; deliberately not a semantic embedding."""
    vector = [0.0] * DIMENSIONS
    for word in terms(text):
        index = int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], "big") % DIMENSIONS
        vector[index] += 1
    norm = math.sqrt(sum(value * value for value in vector)) or 1
    return [value / norm for value in vector]


class ChunkRow(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(String, index=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[str] = mapped_column(String, index=True)
    revision: Mapped[str] = mapped_column(String)
    signature: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    source_path: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(Vector(DIMENSIONS).with_variant(JSON(), "sqlite"))


class Retrieval:
    def __init__(self, database, settings, provider):
        self.database = database
        self.settings = settings
        self.provider = provider

    async def ingest(self):
        # Fixture documents belong only in the explicit demonstration mode.
        documents = (
            json.loads((self.settings.data_dir / "documents.json").read_text())
            if self.settings.mode == "fixture"
            else []
        )
        with self.database.session() as session:
            documents.extend(
                row.document()
                for row in session.scalars(
                    select(KnowledgeDocumentRow).where(KnowledgeDocumentRow.archived.is_(False))
                ).all()
            )
            active = {(doc["workspace_id"], doc["id"]) for doc in documents}
            for row in session.scalars(select(ChunkRow)).all():
                if (row.workspace_id, row.document_id) not in active:
                    session.delete(row)
            session.commit()
        for doc in documents:
            signature = self.document_signature(doc)
            with self.database.session() as session:
                current = session.scalar(select(ChunkRow).where(*self.document_scope(doc)))
                if current and current.signature == signature:
                    continue
            prepared = await self.prepare_document(doc)
            with self.database.session() as session:
                self.write_document(session, doc, prepared)
                session.commit()

    def document_signature(self, doc):
        return hashlib.sha256(
            json.dumps(
                {
                    "document": doc,
                    "embedding": self.provider.embedding_signature,
                    "chunk_size": 800,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()

    @staticmethod
    def document_scope(doc):
        return (
            ChunkRow.document_id == doc["id"],
            ChunkRow.workspace_id == doc["workspace_id"],
        )

    async def prepare_document(self, doc):
        # Preparation happens before a mutation transaction, keeping the old index available.
        chunks = [doc["body"][start : start + 800] for start in range(0, len(doc["body"]), 800)]
        embeddings = await self.provider.embed(chunks)
        if len(embeddings) != len(chunks):
            raise ValueError("Incomplete document embeddings")
        return self.document_signature(doc), chunks, embeddings

    def write_document(self, session, doc, prepared):
        signature, chunks, embeddings = prepared
        session.execute(delete(ChunkRow).where(*self.document_scope(doc)))
        for index, (body, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
            session.add(
                ChunkRow(
                    id=f"{doc['workspace_id']}:{doc['id']}:{doc['revision']}:{index}",
                    document_id=doc["id"],
                    workspace_id=doc["workspace_id"],
                    version=doc["product_version"],
                    revision=str(doc["revision"]),
                    signature=signature,
                    title=doc["title"],
                    source_path=doc["source_path"],
                    body=body,
                    embedding=embedding,
                )
            )

    async def search(self, query: str, workspace: str, version: str | None, limit=6):
        query = query[:8000]
        embedding = (await self.provider.embed([query]))[0]
        filters = [ChunkRow.workspace_id == workspace]
        if version:
            filters.append(ChunkRow.version.in_([version, "any"]))
        with self.database.session() as session:
            if self.database.engine.dialect.name == "postgresql":
                vector = (
                    select(ChunkRow)
                    .where(*filters)
                    .order_by(ChunkRow.embedding.cosine_distance(embedding))
                    .limit(limit * 2)
                )
                lexical = (
                    select(ChunkRow)
                    .where(*filters)
                    .order_by(
                        func.ts_rank_cd(
                            func.to_tsvector("english", ChunkRow.body),
                            func.plainto_tsquery("english", query),
                        ).desc()
                    )
                    .limit(limit * 2)
                )
                rankings = [session.scalars(vector).all(), session.scalars(lexical).all()]
            else:
                rows = session.scalars(select(ChunkRow).where(*filters)).all()
                rankings = [
                    sorted(
                        rows,
                        key=lambda row: sum(
                            a * b for a, b in zip(row.embedding, embedding, strict=True)
                        ),
                        reverse=True,
                    ),
                    sorted(rows, key=lambda row: len(terms(query) & terms(row.body)), reverse=True),
                ]
            scores, candidates = {}, {}
            for ranking in rankings:
                for rank, row in enumerate(ranking):
                    candidates[row.id] = row
                    scores[row.id] = scores.get(row.id, 0) + 1 / (60 + rank + 1)
            selected = sorted(scores, key=lambda key: (-scores[key], key))[:limit]
            return [
                Evidence(
                    id=key,
                    kind="document",
                    title=candidates[key].title,
                    excerpt=candidates[key].body,
                    source_path=candidates[key].source_path,
                    product_version=candidates[key].version,
                )
                for key in selected
            ]
