"""Workspace-scoped GitHub OAuth and explicitly selected repository snapshots."""

import asyncio
import base64
import hashlib
import secrets
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import Field
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError

from supportpilot.github_client import GitHubClient, exchange_code
from supportpilot.github_storage import (
    GitHubConnectionRow,
    GitHubIssueRow,
    GitHubOAuthRow,
    GitHubRepositoryRow,
)
from supportpilot.knowledge_storage import KnowledgeDocumentRow
from supportpilot.redaction import redact
from supportpilot.schemas import Contract
from supportpilot.storage import TicketRow


class SelectRepository(Contract):
    full_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=200)


class CreateIssue(Contract):
    ticket_id: str = Field(min_length=1, max_length=100)


def repo_summary(item):
    return {
        key: item.get(key)
        for key in (
            "id",
            "full_name",
            "description",
            "private",
            "default_branch",
            "html_url",
        )
    }


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def build_github_router(database, retrieval, identity, settings):
    router = APIRouter(prefix="/api/github", tags=["github"])

    def admin(caller=Depends(identity)):
        if caller.get("role", "admin") != "admin":
            raise HTTPException(403, "Only workspace admins can manage GitHub integrations")
        return caller

    def missing():
        values = {
            "GITHUB_CLIENT_ID": settings.github_client_id,
            "GITHUB_CLIENT_SECRET": settings.github_client_secret.get_secret_value(),
            "GITHUB_REDIRECT_URI": settings.github_redirect_uri,
            "INTEGRATION_ENCRYPTION_KEY": settings.integration_encryption_key.get_secret_value(),
        }
        return [name for name, value in values.items() if not value]

    def cipher():
        if missing():
            raise HTTPException(503, "GitHub OAuth is not configured on this server")
        try:
            return Fernet(settings.integration_encryption_key.get_secret_value().encode())
        except ValueError as exc:
            raise HTTPException(503, "Integration encryption configuration is invalid") from exc

    def client_for(caller):
        with database.session() as session:
            row = session.get(GitHubConnectionRow, caller["workspace_id"])
            if row is None:
                raise HTTPException(409, "Connect GitHub first")
            try:
                return GitHubClient(cipher().decrypt(row.token.encode()).decode())
            except InvalidToken as exc:
                raise HTTPException(
                    503, "GitHub credentials cannot be decrypted; reconnect"
                ) from exc

    def get_repo(session, repository_id, caller):
        row = session.get(GitHubRepositoryRow, repository_id)
        if row is None or row.workspace_id != caller["workspace_id"]:
            raise HTTPException(404, "Repository not found")
        return row

    @router.get("/status")
    def status(caller=Depends(identity)):
        with database.session() as session:
            row = session.get(GitHubConnectionRow, caller["workspace_id"])
            return {
                "configured": not missing(),
                "connected": row is not None,
                "login": row.login if row else None,
                "scopes": row.scopes.split(",") if row else [],
                "missing": missing() if caller.get("role", "admin") == "admin" else [],
            }

    @router.post("/connect")
    def connect(response: Response, caller=Depends(admin)):
        box = cipher()
        state, binding, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        with database.session() as session:
            session.execute(
                delete(GitHubOAuthRow).where(
                    GitHubOAuthRow.expires_at < datetime.now(UTC),
                )
            )
            session.add(
                GitHubOAuthRow(
                    state=state,
                    workspace_id=caller["workspace_id"],
                    reviewer_id=caller["reviewer_id"],
                    binding=hashlib.sha256(binding.encode()).hexdigest(),
                    verifier=box.encrypt(verifier.encode()).decode(),
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                )
            )
            session.commit()
        response.set_cookie(
            "supportpilot_github_oauth",
            binding,
            max_age=600,
            httponly=True,
            secure=settings.github_redirect_uri.startswith("https://"),
            samesite="lax",
            path="/api/github/callback",
        )
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        return {
            "authorize_url": "https://github.com/login/oauth/authorize?"
            + urlencode(
                {
                    "client_id": settings.github_client_id,
                    "redirect_uri": settings.github_redirect_uri,
                    "scope": "repo read:user",
                    "state": state,
                    "code_challenge": challenge.rstrip(b"=").decode(),
                    "code_challenge_method": "S256",
                }
            )
        }

    @router.get("/callback")
    async def callback(request: Request, state: str = "", code: str = "", error: str = ""):
        result = RedirectResponse("/?github=authorization_failed", status_code=303)
        result.delete_cookie("supportpilot_github_oauth", path="/api/github/callback")
        binding = request.cookies.get("supportpilot_github_oauth", "")
        with database.session() as session:
            row = session.get(GitHubOAuthRow, state)
            if (
                not row
                or not binding
                or not secrets.compare_digest(
                    row.binding,
                    hashlib.sha256(binding.encode()).hexdigest(),
                )
                or utc(row.expires_at) < datetime.now(UTC)
            ):
                return result
            workspace, reviewer, verifier = row.workspace_id, row.reviewer_id, row.verifier
            # Atomic consume prevents replay even when two callbacks arrive together.
            consumed = session.execute(delete(GitHubOAuthRow).where(GitHubOAuthRow.state == state))
            session.commit()
            if consumed.rowcount != 1 or error or not code:
                return result
        if not any(
            i["workspace_id"] == workspace
            and i["reviewer_id"] == reviewer
            and i.get("role", "admin") == "admin"
            for i in settings.identities()
        ):
            return result
        try:
            box = cipher()
            token = await exchange_code(settings, code, box.decrypt(verifier.encode()).decode())
            user = await GitHubClient(token["access_token"]).get("/user")
            with database.session() as session:
                old = session.get(GitHubConnectionRow, workspace)
                if old and old.login != user["login"]:
                    # Cached private data must not survive switching the connected account.
                    session.execute(
                        delete(GitHubRepositoryRow).where(
                            GitHubRepositoryRow.workspace_id == workspace
                        )
                    )
                    session.execute(
                        delete(GitHubIssueRow).where(GitHubIssueRow.workspace_id == workspace)
                    )
                session.merge(
                    GitHubConnectionRow(
                        workspace_id=workspace,
                        token=box.encrypt(token["access_token"].encode()).decode(),
                        login=user["login"],
                        scopes=token.get("scope", ""),
                    )
                )
                session.commit()
            result.headers["location"] = "/?github=connected"
        except (HTTPException, InvalidToken, KeyError):
            pass
        return result

    @router.delete("/connection")
    def disconnect(caller=Depends(admin)):
        with database.session() as session:
            for model in (GitHubOAuthRow, GitHubIssueRow, GitHubRepositoryRow, GitHubConnectionRow):
                session.execute(delete(model).where(model.workspace_id == caller["workspace_id"]))
            session.commit()
        return {"disconnected": True, "knowledge_retained": True}

    @router.get("/repos")
    async def available_repos(page: int = Query(default=1, ge=1, le=100), caller=Depends(admin)):
        items, headers = await client_for(caller).request(
            "GET",
            "/user/repos",
            params={
                "per_page": 30,
                "page": page,
                "sort": "updated",
                "affiliation": "owner,collaborator,organization_member",
            },
        )
        return {
            "items": [repo_summary(item) for item in items],
            "page": page,
            "has_more": 'rel="next"' in headers.get("link", ""),
        }

    @router.post("/repos/select", status_code=201)
    async def select_repo(payload: SelectRepository, caller=Depends(admin)):
        item = repo_summary(await client_for(caller).get("/repos/" + payload.full_name))
        with database.session() as session:
            existing = session.scalar(
                select(GitHubRepositoryRow).where(
                    GitHubRepositoryRow.workspace_id == caller["workspace_id"],
                    GitHubRepositoryRow.github_id == str(item["id"]),
                )
            )
            if existing:
                return {**existing.payload, "id": existing.id, "github_id": existing.github_id}
            count = session.scalar(
                select(func.count())
                .select_from(GitHubRepositoryRow)
                .where(GitHubRepositoryRow.workspace_id == caller["workspace_id"])
            )
            if count >= 25:
                raise HTTPException(409, "Selected repository limit reached (25)")
            row = GitHubRepositoryRow(
                id=str(uuid4()),
                workspace_id=caller["workspace_id"],
                github_id=str(item["id"]),
                payload=item,
                snapshot={},
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError as exc:
                raise HTTPException(409, "Repository was selected concurrently; reload") from exc
            return {**row.payload, "id": row.id, "github_id": row.github_id}

    @router.get("/repositories")
    def repositories(caller=Depends(identity)):
        with database.session() as session:
            rows = session.scalars(
                select(GitHubRepositoryRow).where(
                    GitHubRepositoryRow.workspace_id == caller["workspace_id"]
                )
            )
            return {
                "items": [
                    {
                        **r.payload,
                        "id": r.id,
                        "github_id": r.github_id,
                        "synced_at": r.snapshot.get("synced_at"),
                    }
                    for r in rows
                ]
            }

    @router.get("/repositories/{repository_id}")
    def repository(repository_id: str, caller=Depends(identity)):
        with database.session() as session:
            row = get_repo(session, repository_id, caller)
            links = session.scalars(
                select(GitHubIssueRow).where(
                    GitHubIssueRow.repository_id == row.id,
                    GitHubIssueRow.workspace_id == caller["workspace_id"],
                )
            )
            return {
                **row.snapshot,
                "repo": {**row.payload, "id": row.id, "github_id": row.github_id},
                "linked_issues": [r.payload for r in links],
            }

    @router.post("/repositories/{repository_id}/sync")
    async def sync(repository_id: str, caller=Depends(admin)):
        github = client_for(caller)
        with database.session() as session:
            row = get_repo(session, repository_id, caller)
            name = row.payload["full_name"]
        base = "/repos/" + name
        metadata = await github.get(base)
        branch = metadata.get("default_branch", "main")
        try:
            commits, issues, contributors, tree, events = await asyncio.gather(
                github.get(base + "/commits", {"per_page": 30, "sha": branch}),
                github.get(base + "/issues", {"per_page": 30, "state": "all", "sort": "updated"}),
                github.get(base + "/contributors", {"per_page": 30}),
                github.get(base + "/git/trees/" + quote(branch, safe=""), {"recursive": "1"}),
                github.get(base + "/events", {"per_page": 30}),
            )
        except HTTPException as exc:
            if metadata.get("size") == 0 and exc.status_code in (404, 502):
                commits, issues, contributors, tree, events = [], [], [], {"tree": []}, []
            else:
                raise
        files = [item for item in tree.get("tree", []) if item.get("type") == "blob"]
        docs = [
            item
            for item in files
            if item["path"].lower() in ("readme.md", "readme.txt")
            or (item["path"].startswith("docs/") and item["path"].lower().endswith((".md", ".txt")))
        ]
        paths = {item["path"] for item in files}
        snapshot = {
            "synced_at": datetime.now(UTC).isoformat(),
            "branch": branch,
            "tree_sha": tree.get("sha"),
            "activity": [
                {
                    "id": e["id"],
                    "type": e["type"],
                    "actor": (e.get("actor") or {}).get("login"),
                    "created_at": e.get("created_at"),
                    "summary": e["type"].removesuffix("Event"),
                }
                for e in events[:30]
            ],
            "commits": [
                {
                    "sha": c["sha"],
                    "message": redact(c["commit"]["message"][:2000]),
                    "author": (c.get("author") or {}).get("login")
                    or c["commit"].get("author", {}).get("name"),
                    "date": c["commit"].get("author", {}).get("date"),
                    "html_url": c.get("html_url"),
                }
                for c in commits[:30]
            ],
            "issues": [
                {
                    "number": i["number"],
                    "title": redact(i["title"]),
                    "state": i["state"],
                    "html_url": i.get("html_url"),
                    "updated_at": i.get("updated_at"),
                    "author": (i.get("user") or {}).get("login"),
                    "is_pull_request": "pull_request" in i,
                }
                for i in issues[:30]
            ],
            "contributors": [
                {
                    "login": c.get("login"),
                    "contributions": c.get("contributions"),
                    "html_url": c.get("html_url"),
                }
                for c in contributors[:30]
            ],
            "files": [
                {"path": f["path"], "size": f.get("size"), "sha": f["sha"]} for f in files[:500]
            ],
            "docs": [
                {"path": f["path"], "size": f.get("size", 0), "sha": f["sha"]} for f in docs[:20]
            ],
            "analysis": {
                "kind": "inventory",
                "summary": (
                    "Bounded repository inventory; not a security audit "
                    "or an assessment of contributor performance."
                ),
                "has_readme": any(p.lower().startswith("readme.") for p in paths),
                "has_tests": any(p.startswith(("tests/", "test/")) or ".test." in p for p in paths),
                "has_ci": any(p.startswith(".github/workflows/") for p in paths),
                "has_docs": bool(docs),
                "observed_file_count": len(files),
            },
            "limits": {
                "activity": 30,
                "activity_may_have_more": len(events) >= 30,
                "commits": 30,
                "issues": 30,
                "contributors": 30,
                "files": 500,
                "docs": 20,
                "tree_truncated": bool(tree.get("truncated")),
                "files_truncated": len(files) > 500,
                "docs_truncated": len(docs) > 20,
                "commits_may_have_more": len(commits) >= 30,
                "issues_may_have_more": len(issues) >= 30,
                "contributors_may_have_more": len(contributors) >= 30,
            },
        }
        with database.session() as session:
            row = get_repo(session, repository_id, caller)
            row.payload, row.snapshot = repo_summary(metadata), snapshot
            session.commit()
        return repository(repository_id, caller)

    @router.post("/repositories/{repository_id}/import-docs")
    async def import_docs(repository_id: str, caller=Depends(admin)):
        github = client_for(caller)
        with database.session() as session:
            repo = get_repo(session, repository_id, caller)
            name, snapshot, github_id = repo.payload["full_name"], repo.snapshot, repo.github_id
        if not snapshot.get("tree_sha"):
            raise HTTPException(409, "Sync this repository before importing documentation")
        imported, skipped, errors = [], [], []
        deadline = time.monotonic() + settings.timeout_seconds
        for item in snapshot.get("docs", [])[:20]:
            path = item["path"]
            if time.monotonic() >= deadline:
                errors.append({"path": path, "reason": "Import time budget exhausted; retry later"})
                continue
            if item.get("size", 0) > 30000:
                skipped.append({"path": path, "reason": "File exceeds 30 KB"})
                continue
            document_id = (
                "gh-"
                + hashlib.sha256(
                    f"{caller['workspace_id']}:{github_id}:{path}".encode()
                ).hexdigest()[:32]
            )
            with database.session() as session:
                previous = session.get(KnowledgeDocumentRow, document_id)
                if previous and previous.archived:
                    skipped.append({"path": path, "reason": "Document is archived"})
                    continue
                expected = previous.revision if previous else None
                old_body = previous.body if previous else None
            try:
                async with asyncio.timeout(max(0.001, deadline - time.monotonic())):
                    blob = await github.get("/repos/" + name + "/git/blobs/" + item["sha"])
                if blob.get("encoding") != "base64" or blob.get("size", 0) > 30000:
                    skipped.append({"path": path, "reason": "Unsupported or oversized content"})
                    continue
                raw = base64.b64decode(blob["content"], validate=False)
                if len(raw) > 30000:
                    skipped.append({"path": path, "reason": "File exceeds 30 KB"})
                    continue
                body = redact(raw.decode("utf-8").strip())
                if len(body) < 20 or body == old_body:
                    skipped.append({"path": path, "reason": "Unchanged or too short"})
                    continue
                doc = {
                    "id": document_id,
                    "workspace_id": caller["workspace_id"],
                    "title": redact(path)[:200],
                    "body": body,
                    "product_version": "any",
                    "source_path": f"github:{name}/{path}"[:200],
                    "revision": str((expected or 0) + 1),
                }
                async with asyncio.timeout(max(0.001, deadline - time.monotonic())):
                    prepared = await retrieval.prepare_document(doc)
                with database.session() as session:
                    if expected is None:
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
                            raise HTTPException(409, "Workspace document limit reached")
                        session.add(
                            KnowledgeDocumentRow(
                                **{k: v for k, v in doc.items() if k != "revision"},
                                revision=1,
                                archived=False,
                                updated_at=datetime.now(UTC),
                            )
                        )
                        session.flush()
                    else:
                        changed = session.execute(
                            update(KnowledgeDocumentRow)
                            .where(
                                KnowledgeDocumentRow.id == document_id,
                                KnowledgeDocumentRow.workspace_id == caller["workspace_id"],
                                KnowledgeDocumentRow.revision == expected,
                                KnowledgeDocumentRow.archived.is_(False),
                            )
                            .values(
                                title=doc["title"],
                                body=doc["body"],
                                source_path=doc["source_path"],
                                revision=expected + 1,
                                updated_at=datetime.now(UTC),
                            )
                        )
                        if changed.rowcount != 1:
                            raise HTTPException(409, "Document changed during import")
                    retrieval.write_document(session, doc, prepared)
                    session.commit()
                imported.append({"path": path, "document_id": document_id})
            except (
                Exception
            ):  # Per-document failures preserve existing knowledge and permit reporting.
                errors.append(
                    {"path": path, "reason": "Import failed; previous document preserved"}
                )
        return {"imported": imported, "skipped": skipped, "errors": errors}

    @router.post("/repositories/{repository_id}/issues")
    async def create_issue(repository_id: str, payload: CreateIssue, caller=Depends(admin)):
        github = client_for(caller)
        with database.session() as session:
            repo = get_repo(session, repository_id, caller)
            name = repo.payload["full_name"]
            ticket = session.get(TicketRow, payload.ticket_id)
            if ticket is None or ticket.workspace_id != caller["workspace_id"]:
                raise HTTPException(404, "Ticket not found")
            ticket_data = dict(ticket.payload)
            link = session.scalar(
                select(GitHubIssueRow).where(
                    GitHubIssueRow.workspace_id == caller["workspace_id"],
                    GitHubIssueRow.repository_id == repository_id,
                    GitHubIssueRow.ticket_id == payload.ticket_id,
                )
            )
            if link and link.payload.get("state") == "created":
                return link.payload
            existing = link is not None
            link_id = link.id if link else str(uuid4())
            marker = "<!-- supportpilot:" + link_id + " -->"
            if not link:
                session.add(
                    GitHubIssueRow(
                        id=link_id,
                        workspace_id=caller["workspace_id"],
                        repository_id=repository_id,
                        ticket_id=payload.ticket_id,
                        payload={
                            "state": "pending",
                            "ticket_id": payload.ticket_id,
                            "created_at": datetime.now(UTC).isoformat(),
                        },
                    )
                )
                try:
                    session.commit()
                except IntegrityError as exc:
                    raise HTTPException(409, "Issue creation already started; reload") from exc
        if existing:
            # Never repeat an uncertain external write. Scan a bounded window for our marker.
            candidates = await github.get(
                "/repos/" + name + "/issues",
                {
                    "per_page": 100,
                    "state": "all",
                    "sort": "created",
                    "direction": "desc",
                },
            )
            issue = next((i for i in candidates if marker in (i.get("body") or "")), None)
            if issue is None:
                raise HTTPException(
                    409,
                    (
                        "Issue creation outcome is uncertain. Check GitHub before retrying; "
                        "automatic duplicate creation is blocked."
                    ),
                )
        else:
            body = redact(ticket_data["description"])
            body += "\n\n---\nCreated from SupportPilot ticket `" + payload.ticket_id + "`."
            body += "\nOnly the ticket subject and description were published.\n" + marker
            try:
                issue, _ = await github.request(
                    "POST",
                    "/repos/" + name + "/issues",
                    body={
                        "title": redact(ticket_data["subject"]),
                        "body": body,
                    },
                )
            except HTTPException as exc:
                # The durable pending record deliberately remains for reconciliation.
                raise HTTPException(
                    409,
                    (
                        "GitHub issue creation was not confirmed. Check the repository; "
                        "retrying here only checks for the existing issue."
                    ),
                ) from exc
        result = {
            "state": "created",
            "ticket_id": payload.ticket_id,
            "number": issue["number"],
            "html_url": issue["html_url"],
            "title": issue["title"],
            "repository_id": repository_id,
        }
        with database.session() as session:
            link = session.get(GitHubIssueRow, link_id)
            if link is None:
                raise HTTPException(409, "Integration changed; inspect GitHub for the issue")
            link.payload = result
            session.commit()
        return result

    @router.get("/repositories/{repository_id}/commits/{sha}")
    async def commit_detail(repository_id: str, sha: str, caller=Depends(identity)):
        if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha.lower()):
            raise HTTPException(422, "A full 40-character commit SHA is required")
        with database.session() as session:
            repo = get_repo(session, repository_id, caller)
            name = repo.payload["full_name"]
        github = client_for(caller)
        commit = await github.get("/repos/" + name + "/commits/" + sha)
        files = commit.get("files", [])
        return {
            "sha": commit["sha"],
            "message": redact(commit["commit"]["message"][:4000]),
            "html_url": commit.get("html_url"),
            "stats": commit.get("stats", {}),
            "files": [
                {
                    "filename": f["filename"],
                    "status": f.get("status"),
                    "additions": f.get("additions", 0),
                    "deletions": f.get("deletions", 0),
                    "patch": redact(f.get("patch", "")[:12000]),
                    "patch_truncated": len(f.get("patch", "")) > 12000,
                    "patch_available": "patch" in f,
                }
                for f in files[:40]
            ],
            "limits": {
                "files": 40,
                "patch_characters": 12000,
                "files_truncated": len(files) > 40,
                "upstream_may_have_more": len(files) >= 300,
            },
        }

    return router
