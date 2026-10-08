"""Earned autonomy: autopilot may approve a kind of draft only after humans agreed with it."""

import math

from sqlalchemy import select

from supportpilot.agreement import human_review
from supportpilot.storage import InvestigationRow, ReviewRow


def bucket(investigation: dict) -> str:
    """Kind of draft: outcome · citation band · tool statuses · mode (and live provider)."""
    draft = investigation.get("draft") or {}
    cites = len(draft.get("evidence_ids") or [])
    statuses = sorted(
        {
            e["tool_result"]["status"]
            for e in investigation.get("trace") or []
            if e.get("tool_result")
        }
    )
    tools = "tools " + "/".join(statuses) if statuses else "no tools"
    mode = "/".join(filter(None, [investigation.get("mode"), investigation.get("provider")]))
    band = "2+ citations" if cites >= 2 else f"{cites} citation{'s' * (cites != 1)}"
    return " · ".join([draft.get("outcome", "no draft"), band, tools, mode])


def wilson_lower_bound(agreed: int, n: int, z: float = 1.96) -> float:
    if not n:
        return 0.0
    p = agreed / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - margin) / (1 + z * z / n)


def ladder(session, workspace_id, settings) -> list[dict]:
    """Per bucket: human agreement, its Wilson lower bound, and AUTO or SHADOW.

    AUTO needs enough human reviews, a lower bound at the bar, and a latest human verdict that
    approved: one rejection drops the bucket to SHADOW until humans approve again.
    """
    # ponytail: full scan of the workspace's reviews; keep a per-bucket tally when this is slow.
    reviews = sorted(
        (
            r.payload
            for r in session.scalars(
                select(ReviewRow).where(ReviewRow.workspace_id == workspace_id)
            )
            if human_review(r.payload)
        ),
        key=lambda review: review["created_at"],
    )
    ids = {review["investigation_id"] for review in reviews}
    investigations = {
        r.id: r.payload
        for r in session.scalars(select(InvestigationRow).where(InvestigationRow.id.in_(ids)))
    }
    tally = {}
    for review in reviews:
        if inv := investigations.get(review["investigation_id"]):
            entry = tally.setdefault(bucket(inv), {"agreed": 0, "n": 0})
            entry["n"] += 1
            entry["agreed"] += review["decision"] == "approve"
            entry["last"] = review["decision"]
    rows = []
    for key, entry in tally.items():
        bound = wilson_lower_bound(entry["agreed"], entry["n"])
        promoted = (
            entry["n"] >= settings.autonomy_min_n
            and bound >= settings.autonomy_min_lb
            and entry["last"] == "approve"
        )
        rows.append(
            dict(
                key=key,
                agreed=entry["agreed"],
                n=entry["n"],
                lower_bound=round(bound, 3),
                state="auto" if promoted else "shadow",
            )
        )
    return sorted(rows, key=lambda row: (row["state"] != "auto", -row["n"], row["key"]))


def states(session, workspace_id, settings) -> dict[str, str]:
    return {row["key"]: row["state"] for row in ladder(session, workspace_id, settings)}


def policy(session, workspace_id, settings) -> dict:
    return dict(
        enabled=workspace_id in settings.autonomy_workspaces,
        min_n=settings.autonomy_min_n,
        min_lower_bound=settings.autonomy_min_lb,
        buckets=ladder(session, workspace_id, settings),
    )
