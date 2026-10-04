from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from supportpilot.storage import InvestigationRow, ReviewRow, TicketRow


def purge_expired(database, days: int):
    """Remove expired ticket data on startup; product documents are retained."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    with database.session() as session:
        expired = [
            row.id
            for row in session.scalars(select(TicketRow)).all()
            if datetime.fromisoformat(row.payload["created_at"]) < cutoff
        ]
        if expired:
            investigations = session.scalars(
                select(InvestigationRow.id).where(InvestigationRow.ticket_id.in_(expired))
            ).all()
            session.execute(delete(ReviewRow).where(ReviewRow.investigation_id.in_(investigations)))
            session.execute(delete(InvestigationRow).where(InvestigationRow.ticket_id.in_(expired)))
            session.execute(delete(TicketRow).where(TicketRow.id.in_(expired)))
            session.commit()
        return len(expired)
