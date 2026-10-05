from datetime import UTC, datetime, timedelta

from supportpilot.agent_storage import AgentRunRow
from supportpilot.github_storage import GitHubIssueRow, GitHubOAuthRow
from supportpilot.retention import purge_expired
from supportpilot.storage import Database, TicketRow


def test_retention_removes_captured_ticket_context_and_expired_oauth(settings):
    database = Database(settings.database_url)
    database.initialize()
    now = datetime.now(UTC)
    with database.session() as session:
        session.add(
            TicketRow(
                id="old",
                workspace_id="demo",
                payload={"created_at": (now - timedelta(days=31)).isoformat()},
            )
        )
        session.add(
            AgentRunRow(
                id="linked-run",
                workspace_id="demo",
                status="completed",
                payload={
                    "created_at": now.isoformat(),
                    "ticket_id": "old",
                    "ticket_context": {"description": "expired private details"},
                },
            )
        )
        session.add(
            AgentRunRow(
                id="keep",
                workspace_id="demo",
                status="queued",
                payload={"created_at": now.isoformat(), "ticket_id": None},
            )
        )
        session.add(
            GitHubIssueRow(
                id="link",
                workspace_id="demo",
                repository_id="repo",
                ticket_id="old",
                payload={"title": "old title"},
            )
        )
        session.add(
            GitHubOAuthRow(
                state="expired",
                workspace_id="demo",
                reviewer_id="alice",
                binding="hashed",
                verifier="encrypted",
                expires_at=now - timedelta(minutes=1),
            )
        )
        session.commit()
    assert purge_expired(database, 30) == 1
    with database.session() as session:
        assert session.get(AgentRunRow, "linked-run") is None
        assert session.get(AgentRunRow, "keep") is not None
        assert session.get(GitHubIssueRow, "link") is None
        assert session.get(GitHubOAuthRow, "expired") is None
    database.engine.dispose()
