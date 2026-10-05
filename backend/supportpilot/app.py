import json
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from supportpilot.accounts import build_accounts_router, token_identity
from supportpilot.agent_runs import build_agent_router
from supportpilot.config import Settings
from supportpilot.github import build_github_router
from supportpilot.knowledge import build_knowledge_router
from supportpilot.mission import build_mission_router
from supportpilot.notifications import notify
from supportpilot.operations import build_operations_router
from supportpilot.provider import Provider
from supportpilot.redaction import redact
from supportpilot.retention import purge_expired
from supportpilot.retrieval import Retrieval
from supportpilot.schemas import Investigation, Review, ReviewCreate, Ticket, TicketCreate
from supportpilot.storage import Database, InvestigationRow, ReviewRow, TicketRow
from supportpilot.tools import Tools
from supportpilot.workflow import investigate


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings.database_url)
    provider = Provider(settings)
    retrieval = Retrieval(database, settings, provider)
    tools = Tools(settings.data_dir)

    @asynccontextmanager
    async def lifespan(app):
        database.initialize()
        purge_expired(database, settings.retention_days)
        await retrieval.ingest()
        # The MVP runs one API worker. Interrupted requests are not silently re-executed.
        with database.session() as session:
            for row in session.scalars(select(InvestigationRow)).all():
                if row.payload["state"] in {"queued", "running"}:
                    row.payload = {
                        **row.payload,
                        "state": "failed",
                        "error": "Interrupted by a restart; retry with a new idempotency key",
                    }
            session.commit()
        yield
        await provider.close()
        database.engine.dispose()

    app = FastAPI(
        title="SupportPilot", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    app.state.settings = settings
    app.state.database = database
    app.state.provider = provider
    app.state.retrieval = retrieval
    app.state.tools = tools
    bearer = HTTPBearer(auto_error=False)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "style-src-elem 'self' 'unsafe-inline'; "
            "style-src-attr 'unsafe-inline'; font-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def identity(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials is not None:
            for candidate in settings.identities():
                if secrets.compare_digest(credentials.credentials, candidate["token"]):
                    return candidate
            if found := token_identity(database, credentials.credentials):
                return found
        raise HTTPException(401, "A valid workspace token is required")

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        try:
            database.ready()
        except Exception as exc:
            raise HTTPException(503, "Database unavailable") from exc
        return {"status": "ok"}

    @app.get("/api/config")
    def config():
        return {
            "mode": settings.mode,
            "product": "RelayDesk" if settings.mode == "fixture" else "Support workspace",
        }

    @app.get("/api/session")
    def session_identity(caller: dict = Depends(identity)):
        return {key: value for key, value in caller.items() if key != "token"}

    @app.get("/api/examples")
    def examples(caller: dict = Depends(identity)):
        if caller["workspace_id"] != "demo" or settings.mode != "fixture":
            return []
        cases = json.loads((settings.data_dir / "development.json").read_text())
        return [{"id": item["id"], "ticket": item["ticket"]} for item in cases]

    @app.post("/api/tickets", response_model=Ticket, status_code=201)
    def create_ticket(payload: TicketCreate, caller: dict = Depends(identity)):
        payload = payload.model_copy(
            update={
                "subject": redact(payload.subject),
                "description": redact(payload.description),
                "log": redact(payload.log),
            }
        )
        ticket = Ticket(
            **payload.model_dump(),
            id=str(uuid4()),
            workspace_id=caller["workspace_id"],
            created_at=datetime.now(UTC),
        )
        with database.session() as session:
            session.add(
                TicketRow(
                    id=ticket.id,
                    workspace_id=ticket.workspace_id,
                    payload=ticket.model_dump(mode="json"),
                )
            )
            session.commit()
        return ticket

    @app.get("/api/tickets", response_model=list[Ticket])
    def list_tickets(caller: dict = Depends(identity)):
        with database.session() as session:
            rows = session.scalars(
                select(TicketRow)
                .where(TicketRow.workspace_id == caller["workspace_id"])
                .order_by(TicketRow.payload["created_at"].as_string().desc())
                .limit(100)
            ).all()
            return [Ticket.model_validate(row.payload) for row in rows]

    @app.get("/api/tickets/{ticket_id}", response_model=Ticket)
    def get_ticket(ticket_id: str, caller: dict = Depends(identity)):
        with database.session() as session:
            row = session.get(TicketRow, ticket_id)
            if row is None or row.workspace_id != caller["workspace_id"]:
                raise HTTPException(404, "Ticket not found")
            return Ticket.model_validate(row.payload)

    @app.get("/api/tickets/{ticket_id}/investigations", response_model=list[Investigation])
    def ticket_investigations(ticket_id: str, caller: dict = Depends(identity)):
        with database.session() as session:
            ticket = session.get(TicketRow, ticket_id)
            if ticket is None or ticket.workspace_id != caller["workspace_id"]:
                raise HTTPException(404, "Ticket not found")
            rows = session.scalars(
                select(InvestigationRow)
                .where(InvestigationRow.ticket_id == ticket_id)
                .order_by(InvestigationRow.created_at.desc())
            ).all()
            return [Investigation.model_validate(row.payload) for row in rows]

    @app.post("/api/tickets/{ticket_id}/investigations", response_model=Investigation)
    async def start_investigation(
        ticket_id: str,
        background: BackgroundTasks,
        idempotency_key: str = Header(min_length=8, max_length=120),
        caller: dict = Depends(identity),
    ):
        with database.session() as session:
            if database.engine.dialect.name == "postgresql":
                session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:workspace))"),
                    {"workspace": caller["workspace_id"]},
                )
            ticket_row = session.get(TicketRow, ticket_id)
            if ticket_row is None or ticket_row.workspace_id != caller["workspace_id"]:
                raise HTTPException(404, "Ticket not found")
            ticket = Ticket.model_validate(ticket_row.payload)
            scope = (
                InvestigationRow.workspace_id == caller["workspace_id"],
                InvestigationRow.ticket_id == ticket_id,
                InvestigationRow.idempotency_key == idempotency_key,
            )
            existing = session.scalar(select(InvestigationRow).where(*scope))
            if existing:
                return Investigation.model_validate(existing.payload)
            recent = session.scalar(
                select(func.count())
                .select_from(InvestigationRow)
                .where(
                    InvestigationRow.workspace_id == caller["workspace_id"],
                    InvestigationRow.created_at >= datetime.now(UTC) - timedelta(hours=1),
                )
            )
            if recent >= settings.max_investigations_per_hour:
                raise HTTPException(429, "Workspace hourly investigation limit reached")
            investigation = Investigation(
                id=str(uuid4()),
                ticket_id=ticket_id,
                workspace_id=caller["workspace_id"],
                state="queued",
                ticket_revision=ticket.revision,
                created_at=datetime.now(UTC),
                mode=settings.mode,
            )
            session.add(
                InvestigationRow(
                    id=investigation.id,
                    ticket_id=ticket_id,
                    workspace_id=caller["workspace_id"],
                    idempotency_key=idempotency_key,
                    created_at=investigation.created_at,
                    payload=investigation.model_dump(mode="json"),
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(select(InvestigationRow).where(*scope))
                if existing is None:
                    raise
                return Investigation.model_validate(existing.payload)
        investigation = await investigate(
            ticket,
            investigation,
            retrieval,
            provider,
            settings,
            tools=tools,
            allow_tools=settings.mode == "fixture",
        )
        with database.session() as session:
            row = session.get(InvestigationRow, investigation.id)
            row.payload = investigation.model_dump(mode="json")
            session.commit()
        if investigation.state == "awaiting_review" and investigation.draft:
            background.add_task(
                notify,
                settings,
                f"SupportPilot · {caller.get('label') or caller['workspace_id']}: draft ready "
                f"for review ({investigation.draft.outcome.replace('_', ' ')}) for "
                f"“{ticket.subject}”.",
            )
        return investigation

    @app.get("/api/investigations/{investigation_id}", response_model=Investigation)
    def get_investigation(investigation_id: str, caller: dict = Depends(identity)):
        with database.session() as session:
            row = session.get(InvestigationRow, investigation_id)
            if row is None or row.workspace_id != caller["workspace_id"]:
                raise HTTPException(404, "Investigation not found")
            return Investigation.model_validate(row.payload)

    @app.get("/api/investigations/{investigation_id}/reviews", response_model=list[Review])
    def list_reviews(investigation_id: str, caller: dict = Depends(identity)):
        with database.session() as session:
            parent = session.get(InvestigationRow, investigation_id)
            if parent is None or parent.workspace_id != caller["workspace_id"]:
                raise HTTPException(404, "Investigation not found")
            return [
                Review.model_validate(row.payload)
                for row in session.scalars(
                    select(ReviewRow).where(ReviewRow.investigation_id == investigation_id)
                ).all()
            ]

    @app.post(
        "/api/investigations/{investigation_id}/reviews", response_model=Review, status_code=201
    )
    def create_review(
        investigation_id: str, payload: ReviewCreate, caller: dict = Depends(identity)
    ):
        with database.session() as session:
            # SQLite has no row-level FOR UPDATE. Serialize the short review transaction
            # so a concurrent ticket edit cannot slip between validation and approval.
            if database.engine.dialect.name == "sqlite":
                session.execute(text("BEGIN IMMEDIATE"))
            parent = session.scalar(
                select(InvestigationRow)
                .where(
                    InvestigationRow.id == investigation_id,
                    InvestigationRow.workspace_id == caller["workspace_id"],
                )
                .with_for_update()
            )
            if parent is None:
                raise HTTPException(404, "Investigation not found")
            investigation = Investigation.model_validate(parent.payload)
            if investigation.state != "awaiting_review" or investigation.draft is None:
                raise HTTPException(409, "No reviewable draft exists")
            ticket_row = session.scalar(
                select(TicketRow)
                .where(
                    TicketRow.id == investigation.ticket_id,
                    TicketRow.workspace_id == caller["workspace_id"],
                )
                .with_for_update()
            )
            if (
                ticket_row is None
                or Ticket.model_validate(ticket_row.payload).revision
                != investigation.ticket_revision
            ):
                raise HTTPException(
                    409,
                    "Ticket changed since this investigation; investigate again before reviewing",
                )
            if payload.draft_revision != investigation.draft_revision:
                raise HTTPException(409, "Stale draft revision")
            review = Review(
                **payload.model_dump(),
                id=str(uuid4()),
                investigation_id=investigation_id,
                reviewer_id=caller["reviewer_id"],
                created_at=datetime.now(UTC),
            )
            session.add(
                ReviewRow(
                    id=review.id,
                    investigation_id=investigation_id,
                    workspace_id=caller["workspace_id"],
                    draft_revision=payload.draft_revision,
                    payload=review.model_dump(mode="json"),
                )
            )
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise HTTPException(409, "This draft revision has already been reviewed") from exc
            return review

    app.include_router(build_accounts_router(database, settings, identity))
    app.include_router(build_github_router(database, retrieval, identity, settings))
    app.include_router(build_agent_router(database, identity, settings))
    app.include_router(build_mission_router(database, identity))
    app.include_router(build_operations_router(database, identity, settings))
    app.include_router(build_knowledge_router(database, retrieval, identity, settings))

    if settings.frontend_dir.exists():
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")

    return app
