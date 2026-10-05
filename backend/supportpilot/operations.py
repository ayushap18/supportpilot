"""Workspace-scoped ticket operations and persisted operational reporting."""

from collections import Counter
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update

from supportpilot.accounts import members
from supportpilot.agent_storage import AgentRunRow
from supportpilot.redaction import redact
from supportpilot.retrieval import ChunkRow
from supportpilot.schemas import Note, NoteCreate, Ticket, TicketPatch
from supportpilot.storage import ActivityRow, InvestigationRow, NoteRow, ReviewRow, TicketRow


def record_activity(session, workspace_id, ticket_id, kind, title, detail):
    payload = dict(
        id=str(uuid4()),
        kind=kind,
        title=title,
        detail=detail,
        ticket_id=ticket_id,
        created_at=datetime.now(UTC).isoformat(),
    )
    session.add(
        ActivityRow(
            id=payload["id"], workspace_id=workspace_id, ticket_id=ticket_id, payload=payload
        )
    )


def queue_items(session, workspace_id):
    tickets = session.scalars(select(TicketRow).where(TicketRow.workspace_id == workspace_id)).all()
    investigations = session.scalars(
        select(InvestigationRow)
        .where(InvestigationRow.workspace_id == workspace_id)
        .order_by(InvestigationRow.created_at)
    ).all()
    latest = {row.ticket_id: row.payload for row in investigations}
    reviewed = {
        row.investigation_id: row.payload
        for row in session.scalars(
            select(ReviewRow).where(ReviewRow.workspace_id == workspace_id)
        ).all()
    }
    items = []
    for row in tickets:
        ticket = Ticket.model_validate(row.payload)
        inv = latest.get(row.id)
        review_status = "none"
        if inv and inv.get("draft") and inv["state"] == "awaiting_review":
            if inv.get("ticket_revision", 1) != ticket.revision:
                review_status = "stale"
            elif inv["id"] in reviewed:
                review_status = (
                    "approved" if reviewed[inv["id"]]["decision"] == "approve" else "rejected"
                )
            else:
                review_status = "pending"
        items.append(
            {
                **ticket.model_dump(mode="json"),
                "latest_investigation_id": inv["id"] if inv else None,
                "latest_outcome": inv["draft"]["outcome"] if inv and inv.get("draft") else None,
                "review_status": review_status,
                "investigation_state": inv["state"] if inv else None,
            }
        )
    return sorted(items, key=lambda item: item["updated_at"] or item["created_at"], reverse=True)


def model_label(settings):
    if settings.llm_provider == "cli":
        names = {"claude_code": "Claude Code", "codex": "Codex", "antigravity": "Antigravity"}
        return f"local {names[settings.cli_agent]} CLI on your subscription (no API key)"
    if settings.llm_provider == "anthropic":
        return f"Claude API ({settings.anthropic_model})"
    return f"OpenAI API ({settings.model})"


def team_metrics(items, investigations, reviews):
    """Outcome metrics from recorded data only; None when nothing has been measured yet."""

    def at(value):
        return datetime.fromisoformat(str(value)).astimezone(UTC)

    created = {item["id"]: at(item["created_at"]) for item in items}
    first_draft = {}
    for inv in investigations:
        if inv.get("draft") and inv["ticket_id"] in created:
            stamp = at(inv["created_at"])
            first_draft[inv["ticket_id"]] = min(first_draft.get(inv["ticket_id"], stamp), stamp)
    draft_minutes = [
        max(0.0, (stamp - created[ticket]).total_seconds() / 60)
        for ticket, stamp in first_draft.items()
    ]
    resolution_hours = [
        max(0.0, (at(item["updated_at"]) - created[item["id"]]).total_seconds() / 3600)
        for item in items
        if item["status"] == "resolved" and item.get("updated_at")
    ]
    decisions = [review["decision"] for review in reviews]
    return dict(
        approval_rate=decisions.count("approve") / len(decisions) if decisions else None,
        reviews=len(decisions),
        median_first_draft_minutes=median(draft_minutes) if draft_minutes else None,
        drafted_tickets=len(draft_minutes),
        median_resolution_hours=median(resolution_hours) if resolution_hours else None,
        resolved_tickets=len(resolution_hours),
    )


def build_operations_router(database, identity, settings):
    router = APIRouter(prefix="/api")

    def require_ticket(session, ticket_id, caller):
        row = session.scalar(
            select(TicketRow)
            .where(TicketRow.id == ticket_id, TicketRow.workspace_id == caller["workspace_id"])
            .with_for_update()
        )
        if row is None:
            raise HTTPException(404, "Ticket not found")
        return row

    @router.patch("/tickets/{ticket_id}", response_model=Ticket)
    def edit_ticket(ticket_id: str, payload: TicketPatch, caller: dict = Depends(identity)):
        changes = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
        if changes.get("assignee") is not None and changes["assignee"] not in members(
            database, settings, caller["workspace_id"]
        ):
            raise HTTPException(422, "Assignee must be a member of this workspace")
        for key in ("subject", "description", "log"):
            if key in changes:
                changes[key] = redact(changes[key])
        with database.session() as session:
            row = require_ticket(session, ticket_id, caller)
            current = Ticket.model_validate(row.payload)
            if current.revision != payload.expected_revision:
                raise HTTPException(409, "Ticket changed; refresh before saving")
            changes = {
                key: value for key, value in changes.items() if getattr(current, key) != value
            }
            if not changes:
                return current
            revised = current.model_copy(
                update={
                    **changes,
                    "revision": current.revision + 1,
                    "updated_at": datetime.now(UTC),
                }
            )
            result = session.execute(
                update(TicketRow)
                .where(
                    TicketRow.id == ticket_id,
                    TicketRow.workspace_id == caller["workspace_id"],
                    func.coalesce(TicketRow.payload["revision"].as_integer(), 1)
                    == payload.expected_revision,
                )
                .values(payload=revised.model_dump(mode="json"))
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                raise HTTPException(409, "Ticket changed; refresh before saving")
            record_activity(
                session,
                caller["workspace_id"],
                ticket_id,
                "ticket_updated",
                "Ticket updated",
                f"{caller['reviewer_id']} changed {', '.join(sorted(changes))}",
            )
            session.commit()
            return revised

    @router.get("/tickets/{ticket_id}/notes", response_model=list[Note])
    def list_notes(ticket_id: str, caller: dict = Depends(identity)):
        with database.session() as session:
            require_ticket(session, ticket_id, caller)
            rows = session.scalars(
                select(NoteRow).where(
                    NoteRow.ticket_id == ticket_id, NoteRow.workspace_id == caller["workspace_id"]
                )
            ).all()
            return sorted(
                [Note.model_validate(row.payload) for row in rows], key=lambda note: note.created_at
            )

    @router.post("/tickets/{ticket_id}/notes", response_model=Note, status_code=201)
    def add_note(ticket_id: str, payload: NoteCreate, caller: dict = Depends(identity)):
        with database.session() as session:
            require_ticket(session, ticket_id, caller)
            note = Note(
                id=str(uuid4()),
                body=redact(payload.body.strip()),
                author_id=caller["reviewer_id"],
                created_at=datetime.now(UTC),
            )
            session.add(
                NoteRow(
                    id=note.id,
                    ticket_id=ticket_id,
                    workspace_id=caller["workspace_id"],
                    payload=note.model_dump(mode="json"),
                )
            )
            record_activity(
                session,
                caller["workspace_id"],
                ticket_id,
                "note_added",
                "Internal note added",
                caller["reviewer_id"],
            )
            session.commit()
            return note

    @router.get("/queue")
    def queue(
        search: str = Query(default="", max_length=200),
        status: Literal["all", "open", "in_progress", "waiting", "resolved"] = "all",
        priority: Literal["all", "low", "normal", "high", "urgent"] = "all",
        review: Literal["all", "pending"] = "all",
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=25, ge=1, le=100),
        caller: dict = Depends(identity),
    ):
        with database.session() as session:
            items = queue_items(session, caller["workspace_id"])
        items = [
            item
            for item in items
            if (status == "all" or item["status"] == status)
            and (priority == "all" or item["priority"] == priority)
            and (review == "all" or item["review_status"] == "pending")
            and search.casefold().strip()
            in " ".join(
                [
                    item["id"],
                    item["subject"],
                    item["description"],
                    item["account_id"] or "",
                    item["assignee"] or "",
                ]
            ).casefold()
        ]
        return dict(
            items=items[(page - 1) * page_size : page * page_size],
            total=len(items),
            page=page,
            page_size=page_size,
        )

    @router.get("/operations")
    def operations(caller: dict = Depends(identity)):
        workspace_id = caller["workspace_id"]
        with database.session() as session:
            items = queue_items(session, workspace_id)
            investigations = [
                row.payload
                for row in session.scalars(
                    select(InvestigationRow).where(InvestigationRow.workspace_id == workspace_id)
                ).all()
            ]
            reviews = [
                row.payload
                for row in session.scalars(
                    select(ReviewRow).where(ReviewRow.workspace_id == workspace_id)
                ).all()
            ]
            changes = [
                row.payload
                for row in session.scalars(
                    select(ActivityRow).where(ActivityRow.workspace_id == workspace_id)
                ).all()
            ]
            documents = session.scalar(
                select(func.count(func.distinct(ChunkRow.document_id))).where(
                    ChunkRow.workspace_id == workspace_id
                )
            )
        counts = dict(
            tickets=len(items),
            **{
                status: sum(item["status"] == status for item in items)
                for status in ("open", "in_progress", "waiting", "resolved")
            },
            awaiting_review=sum(item["review_status"] == "pending" for item in items),
            failed_investigations=sum(inv["state"] == "failed" for inv in investigations),
            knowledge_documents=documents or 0,
        )
        metrics = team_metrics(items, investigations, reviews)
        today = datetime.now(UTC).date()
        trends = {
            str(today - timedelta(days=offset)): dict(
                date=str(today - timedelta(days=offset)),
                tickets=0,
                investigations=0,
                approved=0,
                rejected=0,
                failed=0,
            )
            for offset in range(6, -1, -1)
        }
        activity = list(changes)

        def increment(timestamp, field):
            date = str(datetime.fromisoformat(timestamp).astimezone(UTC).date())
            if date in trends:
                trends[date][field] += 1

        for item in items:
            increment(item["created_at"], "tickets")
            activity.append(
                dict(
                    id="created-" + item["id"],
                    kind="ticket_created",
                    title="Ticket created",
                    detail=item["subject"],
                    ticket_id=item["id"],
                    created_at=item["created_at"],
                )
            )
        for inv in investigations:
            increment(inv["created_at"], "investigations")
            if inv["state"] == "failed":
                increment(inv["created_at"], "failed")
            activity.append(
                dict(
                    id="investigation-" + inv["id"],
                    kind="investigation",
                    title="Investigation " + inv["state"].replace("_", " "),
                    detail=inv["mode"] + " mode",
                    ticket_id=inv["ticket_id"],
                    created_at=inv["created_at"],
                )
            )
        lookup = {inv["id"]: inv for inv in investigations}
        for review in reviews:
            decision = "approved" if review["decision"] == "approve" else "rejected"
            increment(review["created_at"], decision)
            activity.append(
                dict(
                    id="review-" + review["id"],
                    kind="review",
                    title="Draft " + decision,
                    detail=review["reviewer_id"],
                    ticket_id=lookup.get(review["investigation_id"], {}).get("ticket_id"),
                    created_at=review["created_at"],
                )
            )
        outcomes = Counter(inv["draft"]["outcome"] for inv in investigations if inv.get("draft"))
        team = members(database, settings, workspace_id)
        with database.session() as session:
            completed_runs = session.scalar(
                select(func.count())
                .select_from(AgentRunRow)
                .where(
                    AgentRunRow.workspace_id == workspace_id,
                    AgentRunRow.status == "completed",
                )
            )
        github_login = bool(
            settings.github_client_id and settings.github_client_secret.get_secret_value()
        )
        return dict(
            workspace_id=workspace_id,
            reviewer_id=caller["reviewer_id"],
            role=caller["role"],
            mode=settings.mode,
            model=settings.model if settings.mode == "fixture" else model_label(settings),
            tool_mode="synthetic"
            if settings.mode == "fixture"
            else {"github": "github"}.get(settings.integrations, "disabled"),
            retention_days=settings.retention_days,
            limits={
                key: getattr(settings, key)
                for key in (
                    "max_rounds",
                    "max_tool_calls",
                    "timeout_seconds",
                    "max_investigations_per_hour",
                )
            },
            counts=counts,
            trends=list(trends.values()),
            outcomes=[dict(outcome=key, count=value) for key, value in sorted(outcomes.items())],
            activity=sorted(activity, key=lambda event: event["created_at"], reverse=True)[:50],
            recent_tickets=items[:6],
            members=sorted(team.values(), key=lambda member: member["reviewer_id"]),
            metrics=metrics,
            readiness=[
                dict(
                    id="workflow",
                    label="Workspace workflow",
                    status="ready",
                    detail="Ticket triage, notes, evidence, and human review are available.",
                ),
                dict(
                    id="model",
                    label="Model provider",
                    status="demo" if settings.mode == "fixture" else "ready",
                    detail="Deterministic fixture responses; no live model calls."
                    if settings.mode == "fixture"
                    else f"Live: {model_label(settings)}.",
                ),
                dict(
                    id="tools",
                    label="Account and service integrations",
                    status="demo"
                    if settings.mode == "fixture"
                    else "ready"
                    if settings.integrations == "github"
                    else "pending",
                    detail="Synthetic tool results for demo scenarios."
                    if settings.mode == "fixture"
                    else "GitHub: service health from Actions runs, incidents from issues labelled "
                    "'incident'. Account lookups are not connected."
                    if settings.integrations == "github"
                    else "No integrations connected; account and service checks go to a human.",
                ),
                dict(
                    id="identity",
                    label="Team identity",
                    status="ready" if github_login else "pending",
                    detail="GitHub sign-in with per-repository workspaces; tokens are hashed "
                    "and regenerable after re-authorization."
                    if github_login
                    else "Static workspace tokens only; configure a GitHub OAuth App for sign-in.",
                ),
                dict(
                    id="agents",
                    label="Coding agents",
                    status="ready" if completed_runs else "pending",
                    detail=f"{completed_runs} run(s) completed through the local bridge."
                    if completed_runs
                    else "Queue a run and execute it once with the local bridge to verify.",
                ),
                dict(
                    id="deployment",
                    label="Deployment and recovery",
                    status="pending",
                    detail="Verify hosting, backups, restore, and retention before rollout.",
                ),
            ],
        )

    return router
