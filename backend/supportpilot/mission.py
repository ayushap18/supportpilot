"""Mission Control: what needs a person, computed only from stored workspace data."""

from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select

from supportpilot.agent_storage import AgentRunRow
from supportpilot.github_storage import GitHubRepositoryRow
from supportpilot.knowledge_storage import KnowledgeDocumentRow
from supportpilot.operations import queue_items
from supportpilot.storage import ActivityRow, InvestigationRow

STUCK_AFTER = timedelta(minutes=15)


def stage(run):
    if run["status"] != "completed":
        return run["status"]  # queued, running, failed, cancelled
    return (run.get("review") or {}).get("decision") or "awaiting_review"


def build_mission_router(database, identity):
    router = APIRouter(prefix="/api", tags=["mission"])

    @router.get("/mission")
    def mission(caller=Depends(identity)):
        workspace = caller["workspace_id"]
        now = datetime.now(UTC)
        with database.session() as session:
            runs = [
                r.payload
                for r in session.scalars(
                    select(AgentRunRow).where(AgentRunRow.workspace_id == workspace)
                )
            ]
            tickets = queue_items(session, workspace)
            activity = [
                r.payload
                for r in session.scalars(
                    select(ActivityRow).where(ActivityRow.workspace_id == workspace)
                )
            ]
            docs = session.scalars(
                select(KnowledgeDocumentRow).where(
                    KnowledgeDocumentRow.workspace_id == workspace,
                    KnowledgeDocumentRow.archived.is_(False),
                )
            ).all()
            repos = {
                r.payload["full_name"]: r.snapshot
                for r in session.scalars(
                    select(GitHubRepositoryRow).where(GitHubRepositoryRow.workspace_id == workspace)
                )
            }
            # ponytail: last 200 investigations by insertion; add an index-backed query at scale.
            investigations = [
                r.payload
                for r in session.scalars(
                    select(InvestigationRow)
                    .where(InvestigationRow.workspace_id == workspace)
                    .order_by(InvestigationRow.created_at.desc())
                    .limit(200)
                )
            ]

        def at(value):
            return datetime.fromisoformat(str(value)).astimezone(UTC)

        stages = Counter(stage(run) for run in runs)
        work = []

        def add(kind, title, detail, since, ref_type, ref_id):
            work.append(
                dict(
                    kind=kind,
                    title=title,
                    detail=detail,
                    since=since,
                    ref={"type": ref_type, "id": ref_id},
                )
            )

        for run in runs:
            task = run["task"].splitlines()[0][:120]
            current = stage(run)
            if current == "awaiting_review":
                add(
                    "review_run",
                    "Agent result to review",
                    task,
                    run["completed_at"],
                    "run",
                    run["id"],
                )
            elif current == "changes_requested":
                add(
                    "changes_requested",
                    "Changes requested",
                    task,
                    run["completed_at"],
                    "run",
                    run["id"],
                )
            elif current == "failed":
                add(
                    "failed_run",
                    "Agent run failed",
                    run.get("error") or task,
                    run["completed_at"],
                    "run",
                    run["id"],
                )
            elif current == "queued" and now - at(run["created_at"]) > STUCK_AFTER:
                add("stuck_run", "Waiting for a runner", task, run["created_at"], "run", run["id"])
        for ticket in tickets:
            since = ticket["updated_at"] or ticket["created_at"]
            if ticket["review_status"] == "pending":
                add(
                    "review_draft",
                    "Draft awaiting decision",
                    ticket["subject"],
                    since,
                    "ticket",
                    ticket["id"],
                )
            elif ticket["status"] in ("open", "in_progress") and not ticket.get("assignee"):
                add(
                    "unassigned", "Needs an owner", ticket["subject"], since, "ticket", ticket["id"]
                )
        work.sort(key=lambda item: item["since"] or "")

        finished = [r for r in runs if r["status"] in ("completed", "failed")]
        completed = sum(r["status"] == "completed" for r in finished)
        costs = [r["usage"]["cost_usd"] for r in runs if r["usage"].get("cost_usd") is not None]
        providers = {}
        for run in runs:
            entry = providers.setdefault(run["provider"], Counter())
            entry["runs"] += 1
            entry[run["status"]] += 1

        cited = Counter(
            evidence_id.split(":")[1]
            for inv in investigations
            for evidence_id in ((inv.get("draft") or {}).get("evidence_ids") or [])
            if evidence_id.count(":") >= 2
        )
        knowledge = []
        for doc in docs:
            item = dict(
                id=doc.id,
                title=doc.title,
                source_path=doc.source_path,
                updated_at=doc.updated_at.isoformat(),
                citations=cited[doc.id],
                status="local",
                indexed_at=None,
            )
            if doc.source_path.startswith("github:"):
                owner, name, path = doc.source_path.removeprefix("github:").split("/", 2)
                snapshot = repos.get(owner + "/" + name, {})
                latest = {d["path"]: d["sha"] for d in snapshot.get("docs", [])}
                indexed = snapshot.get("indexed", {}).get(path) or {}
                item["indexed_at"] = indexed.get("indexed_at")
                if not snapshot.get("tree_sha"):
                    item["status"] = "unknown"
                elif path not in latest:
                    item["status"] = "removed_upstream"
                elif not indexed.get("sha"):
                    item["status"] = "unknown"
                else:
                    item["status"] = (
                        "current" if latest[path] == indexed["sha"] else "changed_upstream"
                    )
            knowledge.append(item)

        return dict(
            pipeline={
                key: stages[key]
                for key in (
                    "queued",
                    "running",
                    "awaiting_review",
                    "accepted",
                    "changes_requested",
                    "failed",
                    "cancelled",
                )
            },
            work_queue=work[:50],
            reliability=dict(
                runs=len(runs),
                finished=len(finished),
                success_rate=completed / len(finished) if finished else None,
                token_coverage=sum(r["usage"].get("input_tokens") is not None for r in finished)
                / len(finished)
                if finished
                else None,
                reported_cost_usd=sum(costs) if costs else None,
                cost_coverage=len(costs),
                stuck=sum(item["kind"] == "stuck_run" for item in work),
                by_provider={k: dict(v) for k, v in providers.items()},
            ),
            inbox=sorted(
                (a for a in activity if a.get("kind") == "github"),
                key=lambda a: a["created_at"],
                reverse=True,
            )[:30],
            knowledge=sorted(
                knowledge,
                key=lambda d: (
                    d["status"] not in ("changed_upstream", "removed_upstream"),
                    d["title"],
                ),
            ),
        )

    return router
