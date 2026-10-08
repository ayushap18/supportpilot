"""How often the pipeline agrees with human reviewers. Shared by replay evals and autonomy."""

AUTOPILOT_NOTE = "Auto-approved by supportpilot autopilot"


def human_review(review: dict) -> bool:
    """Bot approvals must never count as human agreement, or the bot grades itself.

    Rows stored before `reviewer_kind` existed are excluded, not trusted; the note prefix
    is only an extra guard.
    """
    return review.get("reviewer_kind") == "human" and not review.get("note", "").startswith(
        AUTOPILOT_NOTE
    )


def agrees(decision: str, reviewed_outcome: str, outcome: str | None) -> bool:
    """Approve: reach the approved outcome. Reject: do not repeat it. No draft never agrees."""
    return outcome is not None and (outcome == reviewed_outcome) == (decision == "approve")


def approval_agreement(rows) -> float | None:
    """Share of rows (dicts with an `agrees` flag) that agree with the human verdict."""
    rows = list(rows)
    return sum(bool(row["agrees"]) for row in rows) / len(rows) if rows else None
