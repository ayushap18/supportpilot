"""Replay evals: human approve/reject decisions become deterministic regression cases.

Each case freezes the reviewed investigation's retrieved evidence and recorded tool results,
so only the model step (prompt, provider, model) can change the result between runs.
"""

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from supportpilot.agreement import agrees, approval_agreement, human_review
from supportpilot.config import ROOT
from supportpilot.provider import PROMPT_VERSION, Provider
from supportpilot.redaction import redact
from supportpilot.schemas import Evidence, Investigation, Ticket, ToolResult
from supportpilot.storage import InvestigationRow, ReviewRow, TicketRow
from supportpilot.workflow import investigate

from evals.run import measure, summarize

RUNS = ROOT / "evals" / "runs" / "reviews"
TICKET_FIELDS = ("subject", "description", "product_version", "account_id", "log")


def scrub(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


def export_cases(database, limit=None):
    """Newest human reviews first, in the development.json case shape plus a `replay` block."""
    with database.session() as session:
        reviews = [row.payload for row in session.scalars(select(ReviewRow))]
        reviews.sort(key=lambda review: review["created_at"], reverse=True)
        cases = []
        for review in reviews:
            if limit is not None and len(cases) >= limit:
                break
            if not human_review(review):
                continue
            row = session.get(InvestigationRow, review["investigation_id"])
            investigation = Investigation.model_validate(row.payload) if row else None
            ticket_row = investigation and session.get(TicketRow, investigation.ticket_id)
            # Only replay the exact ticket text and draft the human actually judged.
            if (
                not ticket_row
                or investigation.draft is None
                or investigation.draft_revision != review["draft_revision"]
                or ticket_row.payload.get("revision", 1) != investigation.ticket_revision
            ):
                continue
            draft = investigation.draft
            approved = review["decision"] == "approve"
            # ponytail: near-duplicate tickets are not deduplicated; add it past a few hundred.
            cases.append(
                scrub(
                    {
                        "id": "review-" + review["id"][:8],
                        "category": "review",
                        "decision": review["decision"],
                        "ticket": {
                            key: ticket_row.payload[key]
                            for key in TICKET_FIELDS
                            if key in ticket_row.payload
                        },
                        "expected_outcome": draft.outcome,
                        "required_evidence_ids": [
                            item.split(":")[1]
                            for item in draft.evidence_ids
                            if approved and item.startswith("document:")
                        ],
                        "required_facts": [],
                        "required_tools": [],
                        "replay": {
                            "evidence": [
                                item.model_dump()
                                for item in investigation.evidence
                                if item.kind != "tool"
                            ],
                            "tool_results": [
                                {
                                    "arguments": event.tool_arguments,
                                    "result": event.tool_result.model_dump(),
                                }
                                for event in investigation.trace
                                if event.tool_result
                            ],
                        },
                    }
                )
            )
        return cases


class FrozenRetrieval:
    """Returns the evidence the reviewed investigation saw instead of searching again."""

    def __init__(self, evidence):
        self.evidence = evidence

    async def search(self, *args, **kwargs):
        return [Evidence.model_validate(item) for item in self.evidence]


class ReplayTools:
    """Recorded tool results matched on (name, arguments); unrecorded calls fail honestly."""

    def __init__(self, recorded):
        self.recorded = recorded

    async def execute(self, call, workspace):
        arguments = call.arguments.model_dump()
        for item in self.recorded:
            if item["result"]["name"] == call.name and item["arguments"] == arguments:
                return ToolResult.model_validate(item["result"])
        return ToolResult(
            name=call.name, status="error", data={"message": "No recorded result for this call"}
        )


async def replay(cases, settings):
    provider = Provider(settings)
    rows = []
    try:
        for case in cases:
            ticket = Ticket(
                **case["ticket"],
                id=str(uuid4()),
                workspace_id="replay",
                created_at=datetime.now(UTC),
            )
            investigation = Investigation(
                id=str(uuid4()),
                ticket_id=ticket.id,
                workspace_id="replay",
                state="queued",
                created_at=datetime.now(UTC),
                mode=settings.mode,
            )
            result = await investigate(
                ticket,
                investigation,
                FrozenRetrieval(case["replay"]["evidence"]),
                provider,
                settings,
                tools=ReplayTools(case["replay"]["tool_results"]),
            )
            row = measure(case, result)
            row["decision"] = case["decision"]
            row["agrees"] = agrees(
                case["decision"], case["expected_outcome"], row["actual_outcome"]
            )
            rows.append(row)
    finally:
        await provider.close()
    return {**summarize(rows), "approval_agreement": approval_agreement(rows)}, rows


def latest_run():
    """Newest passing run, so a regression never becomes the next baseline."""
    for path in sorted(RUNS.glob("*.json"), reverse=True):
        report = json.loads(path.read_text())
        if report.get("passed"):
            return report
    return None


def flips(previous, rows):
    """Cases that agreed with the human last run and disagree now."""
    before = {row["case_id"]: row["agrees"] for row in previous["cases"]}
    return [row for row in rows if before.get(row["case_id"]) and not row["agrees"]]


async def run(database, settings, limit=None, fail_below=None):
    """Export, replay, save, and gate. Returns (report, failure message or None)."""
    cases = export_cases(database, limit)
    if not cases:
        raise SystemExit("No human reviews to replay yet. Approve or reject a draft first.")
    previous = latest_run()
    summary, rows = await replay(cases, settings)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "mode": settings.mode,
        "prompt_version": PROMPT_VERSION,
        "summary": summary,
        "flipped": [row["case_id"] for row in flips(previous, rows)] if previous else [],
        "cases": rows,
    }
    floor = None
    if fail_below == "last":
        floor = previous and previous["summary"]["approval_agreement"]
    elif fail_below is not None:
        floor = float(fail_below)
    failure = None
    if floor is not None and summary["approval_agreement"] < floor:
        failure = f"Approval agreement {summary['approval_agreement']:.0%} is below {floor:.0%}"
    report["passed"] = failure is None
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json")).write_text(
        json.dumps(report, indent=2) + "\n"
    )
    return report, failure
