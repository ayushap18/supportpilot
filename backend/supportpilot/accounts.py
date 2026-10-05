"""Sign in with GitHub, pick a repository, and receive a workspace token (shown once)."""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlencode
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import Field, field_validator
from sqlalchemy import DateTime, String, Text, UniqueConstraint, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from supportpilot.github import repo_summary, utc
from supportpilot.github_client import GitHubClient, exchange_code
from supportpilot.github_storage import GitHubConnectionRow, GitHubRepositoryRow
from supportpilot.schemas import Contract
from supportpilot.storage import Base

SESSION_COOKIE = "supportpilot_login"
STATE_COOKIE = "supportpilot_login_state"
SESSION_TTL = timedelta(minutes=30)
REGENERATE_WINDOW = timedelta(minutes=10)
Intent = Literal["signin", "signup", "regenerate"]


class WorkspaceTokenRow(Base):
    """One token per (workspace, GitHub user). Only its SHA-256 hash is stored."""

    __tablename__ = "workspace_tokens"
    __table_args__ = (UniqueConstraint("workspace_id", "reviewer_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    reviewer_id: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    repository: Mapped[str] = mapped_column(String)
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginSessionRow(Base):
    __tablename__ = "login_sessions"
    id_hash: Mapped[str] = mapped_column(String, primary_key=True)
    login: Mapped[str] = mapped_column(String)
    token: Mapped[str] = mapped_column(Text)
    # Why GitHub was authorized: "signin", "signup", or "regenerate" (the only one that may
    # rotate tokens, and only within REGENERATE_WINDOW of the authorization).
    intent: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VerifyToken(Contract):
    token: str = Field(min_length=24, max_length=200)
    workspace_id: str | None = Field(default=None, max_length=100)

    @field_validator("token")
    @classmethod
    def trim(cls, value):
        return value.strip()  # Copied tokens often carry a trailing newline.


class ChooseRepository(Contract):
    full_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=200)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def token_identity(database, token):
    with database.session() as session:
        row = session.scalar(
            select(WorkspaceTokenRow).where(WorkspaceTokenRow.token_hash == digest(token))
        )
        if row is None:
            return None
        return {
            "workspace_id": row.workspace_id,
            "reviewer_id": row.reviewer_id,
            "role": row.role,
            "label": row.repository,
        }


def members(database, settings, workspace_id):
    """Workspace members from static configuration plus GitHub-issued tokens."""
    found = {
        e["reviewer_id"]: {"reviewer_id": e["reviewer_id"], "role": e["role"]}
        for e in settings.identities()
        if e["workspace_id"] == workspace_id
    }
    with database.session() as session:
        for row in session.scalars(
            select(WorkspaceTokenRow).where(WorkspaceTokenRow.workspace_id == workspace_id)
        ):
            found.setdefault(row.reviewer_id, {"reviewer_id": row.reviewer_id, "role": row.role})
    return found


def build_accounts_router(database, settings):
    router = APIRouter(prefix="/api/auth", tags=["auth"])
    secure = settings.github_login_redirect_uri.startswith("https://")

    def configured():
        return bool(
            settings.github_client_id
            and settings.github_client_secret.get_secret_value()
            and settings.integration_encryption_key.get_secret_value()
        )

    def cipher():
        if not configured():
            raise HTTPException(503, "GitHub sign-in is not configured on this server")
        return Fernet(settings.integration_encryption_key.get_secret_value().encode())

    def current(request: Request):
        raw = request.cookies.get(SESSION_COOKIE, "")
        with database.session() as session:
            row = session.get(LoginSessionRow, digest(raw)) if raw else None
            if row is None or utc(row.expires_at) < datetime.now(UTC):
                raise HTTPException(401, "Verify with GitHub first")
            try:
                github_token = cipher().decrypt(row.token.encode()).decode()
            except InvalidToken as exc:
                raise HTTPException(401, "Session expired; verify with GitHub again") from exc
            return {
                "login": row.login,
                "github_token": github_token,
                "can_regenerate": row.intent == "regenerate"
                and utc(row.created_at) + REGENERATE_WINDOW > datetime.now(UTC),
            }

    def owned(login):
        with database.session() as session:
            return [
                {
                    "workspace_id": r.workspace_id,
                    "repository": r.repository,
                    "role": r.role,
                    "issued_at": r.created_at.isoformat(),
                }
                for r in session.scalars(
                    select(WorkspaceTokenRow)
                    .where(WorkspaceTokenRow.reviewer_id == login)
                    .order_by(WorkspaceTokenRow.created_at.desc())
                )
            ]

    async def writable(github_token, full_name):
        repo = await GitHubClient(github_token).get("/repos/" + full_name)
        permissions = repo.get("permissions") or {}
        if not permissions.get("push"):
            raise HTTPException(403, "You need write access to this repository")
        role = "admin" if permissions.get("admin") or permissions.get("maintain") else "agent"
        return repo, role

    def new_token(session, workspace_id, login, role, repository):
        token = "sp_" + secrets.token_urlsafe(32)
        session.add(
            WorkspaceTokenRow(
                id=str(uuid4()),
                workspace_id=workspace_id,
                reviewer_id=login,
                role=role,
                repository=repository,
                token_hash=digest(token),
                created_at=datetime.now(UTC),
            )
        )
        return token

    @router.get("/config")
    def config():
        return {"github": configured()}

    @router.get("/github/start")
    def start(intent: Intent = "signin"):
        back = "signin" if intent == "regenerate" else intent
        if not configured():
            return RedirectResponse("/?login=unavailable#" + back, status_code=303)
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        query = {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_login_redirect_uri,
            "scope": "repo read:user",
            "state": state,
            "code_challenge": challenge.rstrip(b"=").decode(),
            "code_challenge_method": "S256",
        }
        if intent == "regenerate":
            query["prompt"] = "select_account"  # Make re-authorization an explicit step.
        response = RedirectResponse(
            "https://github.com/login/oauth/authorize?" + urlencode(query), status_code=303
        )
        response.set_cookie(
            STATE_COOKIE,
            state + "." + intent + "." + verifier,
            max_age=600,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/api/auth/github/callback",
        )
        return response

    @router.get("/github/callback")
    async def callback(request: Request, state: str = "", code: str = ""):
        expected, _, rest = request.cookies.get(STATE_COOKIE, "").partition(".")
        intent, _, verifier = rest.partition(".")
        if intent not in ("signin", "signup", "regenerate"):
            intent = "signin"
        result = RedirectResponse(
            "/?login=failed#" + ("signin" if intent == "regenerate" else intent),
            status_code=303,
        )
        result.delete_cookie(STATE_COOKIE, path="/api/auth/github/callback")
        if not (expected and verifier and code and secrets.compare_digest(expected, state)):
            return result
        try:
            box = cipher()
            token = (
                await exchange_code(settings, code, verifier, settings.github_login_redirect_uri)
            )["access_token"]
            login = (await GitHubClient(token).get("/user"))["login"]
        except (HTTPException, KeyError, TypeError):
            return result
        raw = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        with database.session() as session:
            session.execute(delete(LoginSessionRow).where(LoginSessionRow.expires_at < now))
            old = request.cookies.get(SESSION_COOKIE, "")
            if old:
                session.execute(
                    delete(LoginSessionRow).where(LoginSessionRow.id_hash == digest(old))
                )
            session.add(
                LoginSessionRow(
                    id_hash=digest(raw),
                    login=login,
                    token=box.encrypt(token.encode()).decode(),
                    intent=intent,
                    created_at=now,
                    expires_at=now + SESSION_TTL,
                )
            )
            session.commit()
        result.headers["location"] = "/#" + intent
        result.set_cookie(
            SESSION_COOKIE,
            raw,
            max_age=int(SESSION_TTL.total_seconds()),
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/api/auth",
        )
        return result

    @router.get("/session")
    def session_info(request: Request):
        try:
            me = current(request)
        except HTTPException:
            return {"login": None, "workspaces": [], "can_regenerate": False}
        return {
            "login": me["login"],
            "workspaces": owned(me["login"]),
            "can_regenerate": me["can_regenerate"],
        }

    @router.delete("/session")
    def sign_out(request: Request):
        raw = request.cookies.get(SESSION_COOKIE, "")
        if raw:
            with database.session() as session:
                session.execute(
                    delete(LoginSessionRow).where(LoginSessionRow.id_hash == digest(raw))
                )
                session.commit()
        response = JSONResponse({"signed_out": True})
        response.delete_cookie(SESSION_COOKIE, path="/api/auth")
        return response

    @router.post("/verify")
    def verify(payload: VerifyToken, request: Request):
        """Sign-in step two: the token must belong to this GitHub user (and chosen workspace)."""
        login = current(request)["login"]
        found = token_identity(database, payload.token)
        if found is None or found["reviewer_id"] != login:
            raise HTTPException(403, f"This workspace token does not belong to @{login}")
        if payload.workspace_id and found["workspace_id"] != payload.workspace_id:
            raise HTTPException(403, f"This token is for {found['label']}, not the selected one")
        return found

    @router.get("/repos")
    async def repos(request: Request, page: int = Query(default=1, ge=1, le=100)):
        me = current(request)
        items, headers = await GitHubClient(me["github_token"]).request(
            "GET",
            "/user/repos",
            params={"per_page": 50, "page": page, "sort": "updated"},
        )
        return {
            "items": [
                {**repo_summary(i), "permissions": i.get("permissions", {})}
                for i in items
                if (i.get("permissions") or {}).get("push")
            ],
            "page": page,
            "has_more": 'rel="next"' in headers.get("link", ""),
        }

    @router.post("/workspaces", status_code=201)
    async def create(payload: ChooseRepository, request: Request):
        """Sign-up: create the repository's workspace and issue this user's first token."""
        me = current(request)
        repo, role = await writable(me["github_token"], payload.full_name)
        workspace_id = "gh-" + str(repo["id"])
        box = cipher()
        with database.session() as session:
            if session.scalar(
                select(WorkspaceTokenRow).where(
                    WorkspaceTokenRow.workspace_id == workspace_id,
                    WorkspaceTokenRow.reviewer_id == me["login"],
                )
            ):
                raise HTTPException(
                    409,
                    f"You already have a workspace for {repo['full_name']}. "
                    "Sign in, or use “Forgot your token?” to regenerate it.",
                )
            token = new_token(session, workspace_id, me["login"], role, repo["full_name"])
            # The first member connects the workspace's GitHub access and selects its repository.
            if session.get(GitHubConnectionRow, workspace_id) is None:
                session.add(
                    GitHubConnectionRow(
                        workspace_id=workspace_id,
                        token=box.encrypt(me["github_token"].encode()).decode(),
                        login=me["login"],
                        scopes="repo,read:user",
                    )
                )
            if not session.scalar(
                select(GitHubRepositoryRow).where(
                    GitHubRepositoryRow.workspace_id == workspace_id,
                    GitHubRepositoryRow.github_id == str(repo["id"]),
                )
            ):
                session.add(
                    GitHubRepositoryRow(
                        id=str(uuid4()),
                        workspace_id=workspace_id,
                        github_id=str(repo["id"]),
                        payload=repo_summary(repo),
                        snapshot={},
                    )
                )
            try:
                session.commit()
            except IntegrityError as exc:
                raise HTTPException(409, "Workspace was created concurrently; sign in") from exc
        return {
            "token": token,
            "workspace_id": workspace_id,
            "repository": repo["full_name"],
            "role": role,
            "regenerated": False,
        }

    @router.post("/workspaces/{workspace_id}/regenerate", status_code=201)
    async def regenerate(workspace_id: str, request: Request):
        """Rotate a lost token. Requires a fresh GitHub authorization made for this purpose."""
        me = current(request)
        if not me["can_regenerate"]:
            raise HTTPException(401, "Verify with GitHub again to regenerate a token")
        with database.session() as session:
            row = session.scalar(
                select(WorkspaceTokenRow).where(
                    WorkspaceTokenRow.workspace_id == workspace_id,
                    WorkspaceTokenRow.reviewer_id == me["login"],
                )
            )
            if row is None:
                raise HTTPException(404, "Workspace not found for this GitHub account")
            repository = row.repository
        # Access may have been revoked on GitHub since the workspace was created.
        repo, role = await writable(me["github_token"], repository)
        with database.session() as session:
            session.execute(
                delete(WorkspaceTokenRow).where(
                    WorkspaceTokenRow.workspace_id == workspace_id,
                    WorkspaceTokenRow.reviewer_id == me["login"],
                )
            )
            token = new_token(session, workspace_id, me["login"], role, repo["full_name"])
            session.commit()
        return {
            "token": token,
            "workspace_id": workspace_id,
            "repository": repo["full_name"],
            "role": role,
            "regenerated": True,
        }

    return router
