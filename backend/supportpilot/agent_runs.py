"""Explicit, workspace-scoped local execution tracking; never executes server commands."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update

from supportpilot.agent_storage import AgentRunnerRow, AgentRunRow
from supportpilot.knowledge_storage import KnowledgeDocumentRow
from supportpilot.notifications import notify
from supportpilot.redaction import redact
from supportpilot.storage import TicketRow

PROVIDERS = [
    dict(
        id="codex",
        name="Codex CLI",
        execution="local_cli",
        capabilities=["analysis", "isolated_worktree_edits"],
        usage_support="Reported tokens; cost unavailable unless explicitly reported.",
        setup="Install and authenticate Codex locally, then run the SupportPilot bridge.",
    ),
    dict(
        id="claude_code",
        name="Claude Code",
        execution="local_cli",
        capabilities=["analysis"],
        usage_support="Reported tokens and reported run cost.",
        setup="Install and authenticate Claude Code locally; bridge uses restricted read tools.",
    ),
    dict(
        id="antigravity",
        name="Antigravity CLI",
        execution="local_cli",
        capabilities=["isolated_worktree_edits"],
        usage_support="Reported tokens; provider quota and billing unavailable.",
        setup="Authenticate agy locally. Requires explicit --allow-edits in a dedicated worktree.",
    ),
    dict(
        id="custom",
        name="External agent report",
        execution="external_report",
        capabilities=["manual_report"],
        usage_support="Only explicitly supplied run usage.",
        setup="Claim a proposed run and submit the result through the authenticated API.",
    ),
]


class CreateRun(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    provider: Literal["codex", "claude_code", "antigravity", "custom"]
    task: str = Field(min_length=10, max_length=12000)
    repository_full_name: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=201
    )
    ticket_id: str | None = Field(default=None, max_length=100)
    model: str | None = Field(
        default=None, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$"
    )
    # Requests an isolated-worktree edit run; a runner only honors it if started with edits.
    allow_edits: bool = False
    # Context pack: knowledge documents snapshotted into the run for traceability.
    knowledge_ids: list[str] = Field(default_factory=list, max_length=5)


class ReviewRun(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    decision: Literal["accepted", "changes_requested"]
    note: str = Field(default="", max_length=2000)
    tests_before: str = Field(default="", max_length=2000)
    tests_after: str = Field(default="", max_length=2000)
    customer_confirmed: bool = False


class ClaimRun(BaseModel):
    runner_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")


class Usage(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    input_tokens: int | None = Field(default=None, ge=0, le=10**10, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, le=10**10, strict=True)
    cached_input_tokens: int | None = Field(default=None, ge=0, le=10**10, strict=True)
    cost_usd: float | None = Field(default=None, ge=0, le=10**6)


class Artifact(BaseModel):
    kind: Literal["branch", "pull_request", "test_report", "patch"]
    label: str = Field(min_length=1, max_length=300)
    url: str | None = Field(default=None, max_length=2000)

    @field_validator("url")
    @classmethod
    def safe_url(cls, value):
        if value and not value.startswith("https://"):
            raise ValueError("Artifact links must use HTTPS")
        return value


class RunLog(BaseModel):
    lease: str = Field(min_length=32, max_length=100)
    lines: list[str] = Field(min_length=1, max_length=50)


class Heartbeat(BaseModel):
    runner_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    providers: list[Literal["codex", "claude_code", "antigravity"]] = Field(max_length=3)
    repository_full_name: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=201
    )
    allow_edits: bool = False
    push: bool = False


LOG_LINES = 300
RUNNER_ONLINE = timedelta(seconds=45)


class CompleteRun(BaseModel):
    lease: str = Field(min_length=32, max_length=100)
    result: str = Field(default="", max_length=50000)
    usage: Usage = Field(default_factory=Usage)
    exit_code: int = Field(ge=-1000, le=1000)
    artifacts: list[Artifact] = Field(default_factory=list, max_length=20)
    error: str | None = Field(default=None, max_length=2000)


def now():
    return datetime.now(UTC).isoformat()


def build_agent_router(database, identity, settings):
    router = APIRouter(prefix="/api/agents", tags=["agents"])

    def admin(caller=Depends(identity)):
        if caller.get("role", "admin") != "admin":
            raise HTTPException(403, "Administrator role required")
        return caller

    def get_row(session, run_id, caller):
        row = session.get(AgentRunRow, run_id)
        if not row or row.workspace_id != caller["workspace_id"]:
            raise HTTPException(404, "Agent run not found")
        return row

    @router.get("/providers")
    def providers(caller=Depends(identity)):
        return {
            "items": PROVIDERS,
            "note": "Runs start only from your local bridge. Usage covers "
            "reported runs, not subscription limits, provider quotas, or verified billing.",
        }

    @router.get("/runs")
    def list_runs(caller=Depends(identity)):
        with database.session() as session:
            rows = session.scalars(
                select(AgentRunRow).where(AgentRunRow.workspace_id == caller["workspace_id"])
            ).all()
            items = sorted(
                [row.payload for row in rows], key=lambda r: r["created_at"], reverse=True
            )
        costs = [r["usage"]["cost_usd"] for r in items if r["usage"].get("cost_usd") is not None]
        totals = {}
        for key in ("input_tokens", "output_tokens"):
            reported = [r["usage"][key] for r in items if r["usage"].get(key) is not None]
            totals[key] = sum(reported) if reported else None
            totals["reported_" + key + "_runs"] = len(reported)
        return {
            "items": items,
            "usage": {
                "runs": len(items),
                **totals,
                "cost_usd": sum(costs) if costs else None,
                "reported_cost_runs": len(costs),
                "unreported_cost_runs": len(items) - len(costs),
            },
        }

    @router.post("/runs", status_code=201)
    def create_run(body: CreateRun, caller=Depends(admin)):
        payload = {
            **body.model_dump(),
            "id": str(uuid4()),
            "status": "queued",
            "task": redact(body.task),
            "created_at": now(),
            "started_at": None,
            "completed_at": None,
            "created_by": caller["reviewer_id"],
            "runner_id": None,
            "result": None,
            "usage": {},
            "exit_code": None,
            "artifacts": [],
            "error": None,
            "log": [],
        }
        with database.session() as session:
            docs = [session.get(KnowledgeDocumentRow, doc_id) for doc_id in body.knowledge_ids]
            if any(d is None or d.workspace_id != caller["workspace_id"] for d in docs):
                raise HTTPException(404, "Knowledge document not found")
            payload["context_docs"] = [
                {
                    "id": d.id,
                    "title": d.title,
                    "source_path": d.source_path,
                    "revision": d.revision,
                    "excerpt": d.body[:3000],
                }
                for d in docs
            ]
            if body.ticket_id:
                ticket = session.get(TicketRow, body.ticket_id)
                if not ticket or ticket.workspace_id != caller["workspace_id"]:
                    raise HTTPException(404, "Ticket not found")
                payload["ticket_context"] = {
                    key: ticket.payload.get(key)
                    for key in (
                        "subject",
                        "description",
                        "log",
                        "product_version",
                        "account_id",
                        "revision",
                    )
                }
            session.add(
                AgentRunRow(
                    id=payload["id"],
                    workspace_id=caller["workspace_id"],
                    status="queued",
                    payload=payload,
                )
            )
            session.commit()
        return payload

    @router.get("/runs/{run_id}")
    def get_run(run_id: str, caller=Depends(identity)):
        with database.session() as session:
            return get_row(session, run_id, caller).payload

    @router.post("/runs/{run_id}/claim")
    def claim(run_id: str, body: ClaimRun, caller=Depends(admin)):
        lease = secrets.token_urlsafe(32)
        with database.session() as session:
            row = get_row(session, run_id, caller)
            payload = {
                **row.payload,
                "status": "running",
                "runner_id": body.runner_id,
                "started_at": now(),
                "lease_expires_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
            }
            changed = session.execute(
                update(AgentRunRow)
                .where(AgentRunRow.id == run_id, AgentRunRow.status == "queued")
                .values(
                    status="running",
                    payload=payload,
                    claimed_by=caller["reviewer_id"],
                    lease_hash=hashlib.sha256(lease.encode()).hexdigest(),
                )
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "Run is already claimed or finished")
            session.commit()
        return {**payload, "lease": lease}

    def leased(session, run_id, caller, lease):
        digest = hashlib.sha256(lease.encode()).hexdigest()
        row = get_row(session, run_id, caller)
        if row.claimed_by != caller["reviewer_id"] or not secrets.compare_digest(
            row.lease_hash or "", digest
        ):
            raise HTTPException(403, "Run lease does not belong to this runner identity")
        return row, digest

    @router.post("/runs/{run_id}/log")
    def append_log(run_id: str, body: RunLog, caller=Depends(admin)):
        """Live progress from the bridge: short redacted lines, newest LOG_LINES kept."""
        with database.session() as session:
            row, digest = leased(session, run_id, caller, body.lease)
            if row.status != "running":
                raise HTTPException(409, "Run is not running")
            lines = [redact(line)[:500] for line in body.lines]
            payload = {**row.payload, "log": (row.payload.get("log", []) + lines)[-LOG_LINES:]}
            session.execute(
                update(AgentRunRow)
                .where(AgentRunRow.id == run_id, AgentRunRow.lease_hash == digest)
                .values(payload=payload)
            )
            session.commit()
        return {"lines": len(payload["log"])}

    @router.post("/runners/heartbeat")
    def heartbeat(body: Heartbeat, caller=Depends(admin)):
        key = caller["workspace_id"] + ":" + body.runner_id
        payload = {
            **body.model_dump(),
            "reviewer_id": caller["reviewer_id"],
            "last_seen": now(),
        }
        with database.session() as session:
            session.merge(
                AgentRunnerRow(id=key, workspace_id=caller["workspace_id"], payload=payload)
            )
            session.commit()
        return payload

    @router.get("/runners")
    def runners(caller=Depends(identity)):
        cutoff = datetime.now(UTC) - RUNNER_ONLINE
        with database.session() as session:
            rows = session.scalars(
                select(AgentRunnerRow).where(AgentRunnerRow.workspace_id == caller["workspace_id"])
            ).all()
            items = [
                {**r.payload, "online": datetime.fromisoformat(r.payload["last_seen"]) > cutoff}
                for r in rows
            ]
        return {"items": sorted(items, key=lambda r: r["last_seen"], reverse=True)}

    @router.post("/runs/{run_id}/complete")
    def complete(
        run_id: str, body: CompleteRun, background: BackgroundTasks, caller=Depends(admin)
    ):
        with database.session() as session:
            row, digest = leased(session, run_id, caller, body.lease)
            if datetime.fromisoformat(row.payload["lease_expires_at"]) < datetime.now(UTC):
                raise HTTPException(
                    409, "Run lease expired; use expire recovery and create a new run"
                )
            status = "completed" if body.exit_code == 0 and not body.error else "failed"
            payload = {
                **row.payload,
                "status": status,
                "completed_at": now(),
                "result": redact(body.result),
                "usage": body.usage.model_dump(exclude_none=True),
                "exit_code": body.exit_code,
                "error": redact(body.error) if body.error else None,
                "artifacts": [{**a.model_dump(), "label": redact(a.label)} for a in body.artifacts],
            }
            changed = session.execute(
                update(AgentRunRow)
                .where(
                    AgentRunRow.id == run_id,
                    AgentRunRow.status == "running",
                    AgentRunRow.lease_hash == digest,
                )
                .values(status=status, payload=payload)
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "Run already finished")
            session.commit()
        background.add_task(
            notify,
            settings,
            f"SupportPilot · {caller.get('label') or caller['workspace_id']}: "
            f"{payload['provider']} run {status}: {payload['task'].splitlines()[0][:120]}",
        )
        return payload

    @router.post("/runs/{run_id}/review")
    def review_run(run_id: str, body: ReviewRun, caller=Depends(admin)):
        """Fix verification: a person's verdict on a finished run, with test evidence."""
        with database.session() as session:
            row = get_row(session, run_id, caller)
            if row.status != "completed":
                raise HTTPException(409, "Only completed runs can be reviewed")
            payload = {
                **row.payload,
                "review": {
                    **body.model_dump(),
                    "note": redact(body.note),
                    "tests_before": redact(body.tests_before),
                    "tests_after": redact(body.tests_after),
                    "reviewer_id": caller["reviewer_id"],
                    "reviewed_at": now(),
                },
            }
            session.execute(
                update(AgentRunRow).where(AgentRunRow.id == run_id).values(payload=payload)
            )
            session.commit()
        return payload

    @router.post("/runs/{run_id}/cancel")
    def cancel(run_id: str, caller=Depends(admin)):
        with database.session() as session:
            row = get_row(session, run_id, caller)
            payload = {**row.payload, "status": "cancelled", "completed_at": now()}
            changed = session.execute(
                update(AgentRunRow)
                .where(AgentRunRow.id == run_id, AgentRunRow.status == "queued")
                .values(status="cancelled", payload=payload)
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "Only queued runs can be cancelled")
            session.commit()
        return payload

    @router.post("/runs/{run_id}/expire")
    def expire(run_id: str, caller=Depends(admin)):
        with database.session() as session:
            row = get_row(session, run_id, caller)
            deadline = row.payload.get("lease_expires_at")
            if (
                row.status != "running"
                or not deadline
                or datetime.fromisoformat(deadline) > datetime.now(UTC)
            ):
                raise HTTPException(409, "Only expired running leases can be recovered")
            payload = {
                **row.payload,
                "status": "failed",
                "completed_at": now(),
                "error": "Runner lease expired. Local process state is unknown; inspect it "
                "before starting another run.",
            }
            changed = session.execute(
                update(AgentRunRow)
                .where(AgentRunRow.id == run_id, AgentRunRow.status == "running")
                .values(status="failed", payload=payload)
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "Run already finished")
            session.commit()
        return payload

    return router
