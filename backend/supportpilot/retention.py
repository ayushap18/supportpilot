from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from supportpilot.agent_storage import AgentRunRow
from supportpilot.github_storage import GitHubIssueRow, GitHubOAuthRow
from supportpilot.storage import ActivityRow, InvestigationRow, NoteRow, ReviewRow, TicketRow


def purge_expired(database, days: int):
    """Remove expired ticket data on startup; product documents are retained."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    with database.session() as session:
        expired = [
            row.id
            for row in session.scalars(select(TicketRow)).all()
            if datetime.fromisoformat(row.payload["created_at"]) < cutoff
        ]
        expired_runs = [
            row.id
            for row in session.scalars(select(AgentRunRow)).all()
            if row.payload.get("ticket_id") in expired
            or datetime.fromisoformat(row.payload["created_at"]) < cutoff
        ]
        if expired_runs:
            session.execute(delete(AgentRunRow).where(AgentRunRow.id.in_(expired_runs)))
        session.execute(delete(GitHubOAuthRow).where(GitHubOAuthRow.expires_at < datetime.now(UTC)))
        if expired:
            investigations = session.scalars(
                select(InvestigationRow.id).where(InvestigationRow.ticket_id.in_(expired))
            ).all()
            session.execute(delete(ReviewRow).where(ReviewRow.investigation_id.in_(investigations)))
            session.execute(delete(InvestigationRow).where(InvestigationRow.ticket_id.in_(expired)))
            session.execute(delete(NoteRow).where(NoteRow.ticket_id.in_(expired)))
            session.execute(delete(ActivityRow).where(ActivityRow.ticket_id.in_(expired)))
            session.execute(delete(GitHubIssueRow).where(GitHubIssueRow.ticket_id.in_(expired)))
            session.execute(delete(TicketRow).where(TicketRow.id.in_(expired)))
        session.commit()
        return len(expired)
