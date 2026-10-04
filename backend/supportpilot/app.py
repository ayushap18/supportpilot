import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from supportpilot.config import Settings
from supportpilot.provider import Provider
from supportpilot.retrieval import Retrieval
from supportpilot.schemas import Investigation, Ticket, TicketCreate
from supportpilot.storage import Database, InvestigationRow, TicketRow
from supportpilot.workflow import investigate


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings.database_url)
    provider = Provider(settings)
    retrieval = Retrieval(database, settings, provider)

    @asynccontextmanager
    async def lifespan(app):
        database.initialize()
        await retrieval.ingest()
        yield
        await provider.close()
        database.engine.dispose()

    app = FastAPI(title="SupportPilot", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.database = database
    app.state.provider = provider
    app.state.retrieval = retrieval
    bearer = HTTPBearer(auto_error=False)

    def identity(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials is not None:
            for candidate in settings.identities():
                if secrets.compare_digest(credentials.credentials, candidate["token"]):
                    return candidate
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
        return {"mode": settings.mode, "product": "RelayDesk"}

    @app.post("/api/tickets", response_model=Ticket, status_code=201)
    def create_ticket(payload: TicketCreate, caller: dict = Depends(identity)):
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
                select(TicketRow).where(TicketRow.workspace_id == caller["workspace_id"])
            ).all()
            return [Ticket.model_validate(row.payload) for row in rows]

    @app.get("/api/tickets/{ticket_id}", response_model=Ticket)
    def get_ticket(ticket_id: str, caller: dict = Depends(identity)):
        with database.session() as session:
            row = session.get(TicketRow, ticket_id)
            if row is None or row.workspace_id != caller["workspace_id"]:
                raise HTTPException(404, "Ticket not found")
            return Ticket.model_validate(row.payload)

    @app.post("/api/tickets/{ticket_id}/investigations", response_model=Investigation)
    async def start_investigation(
        ticket_id: str,
        idempotency_key: str = Header(min_length=8, max_length=120),
        caller: dict = Depends(identity),
    ):
        with database.session() as session:
            ticket = session.get(TicketRow, ticket_id)
            if ticket is None or ticket.workspace_id != caller["workspace_id"]:
                raise HTTPException(404, "Ticket not found")
            ticket_contract = Ticket.model_validate(ticket.payload)
            existing = session.scalar(
                select(InvestigationRow).where(
                    InvestigationRow.workspace_id == caller["workspace_id"],
                    InvestigationRow.ticket_id == ticket_id,
                    InvestigationRow.idempotency_key == idempotency_key,
                )
            )
            if existing:
                return Investigation.model_validate(existing.payload)
            investigation = Investigation(
                id=str(uuid4()),
                ticket_id=ticket_id,
                workspace_id=caller["workspace_id"],
                state="queued",
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
            session.commit()
        investigation = await investigate(
            ticket_contract,
            investigation,
            retrieval,
            provider,
            settings,
        )
        with database.session() as session:
            row = session.get(InvestigationRow, investigation.id)
            row.payload = investigation.model_dump(mode="json")
            session.commit()
        return investigation

    @app.get("/api/investigations/{investigation_id}", response_model=Investigation)
    def get_investigation(investigation_id: str, caller: dict = Depends(identity)):
        with database.session() as session:
            row = session.get(InvestigationRow, investigation_id)
            if row is None or row.workspace_id != caller["workspace_id"]:
                raise HTTPException(404, "Investigation not found")
            return Investigation.model_validate(row.payload)

    return app
