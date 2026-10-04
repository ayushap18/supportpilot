from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from supportpilot.app import create_app
from supportpilot.config import Settings
from supportpilot.retention import purge_expired
from supportpilot.storage import InvestigationRow, TicketRow

from scripts.deploy_render import hook_url


def test_retention_keeps_fresh_tickets_and_removes_expired(client, headers, ticket_input):
    fresh = client.post("/api/tickets", headers=headers, json=ticket_input).json()
    expired = client.post("/api/tickets", headers=headers, json=ticket_input).json()
    database = client.app.state.database
    with database.session() as session:
        row = session.get(TicketRow, expired["id"])
        row.payload = {
            **row.payload,
            "created_at": (datetime.now(UTC) - timedelta(days=31)).isoformat(),
        }
        session.commit()
    assert purge_expired(database, 30) == 1
    assert client.get("/api/tickets/" + fresh["id"], headers=headers).status_code == 200
    assert client.get("/api/tickets/" + expired["id"], headers=headers).status_code == 404


def test_restart_recovers_interrupted_investigations(settings, headers, ticket_input):
    with TestClient(create_app(settings)) as first:
        ticket = first.post("/api/tickets", headers=headers, json=ticket_input).json()
        run = first.post(
            "/api/tickets/" + ticket["id"] + "/investigations",
            headers={**headers, "Idempotency-Key": "restart-test"},
        ).json()
        with first.app.state.database.session() as session:
            row = session.get(InvestigationRow, run["id"])
            row.payload = {**row.payload, "state": "running", "draft": None}
            session.commit()
    with TestClient(create_app(settings)) as restarted:
        recovered = restarted.get("/api/investigations/" + run["id"], headers=headers).json()
        assert recovered["state"] == "failed"
        assert "restart" in recovered["error"]


def test_security_headers_and_static_build(client):
    response = client.get("/api/config")
    assert response.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_deploy_hook_pins_commit_and_rejects_other_hosts():
    sha = "a" * 40
    parsed = urlsplit(hook_url("https://api.render.com/deploy/srv-test?key=example", sha))
    assert parse_qs(parsed.query) == {"key": ["example"], "ref": [sha]}
    with pytest.raises(ValueError):
        hook_url("https://attacker.invalid/deploy", sha)
    with pytest.raises(ValueError):
        hook_url("https://api.render.com/deploy", "main")


@pytest.mark.parametrize(
    "options",
    [
        {"retention_days": 0},
        {"max_rounds": 4},
        {"max_tool_calls": 6},
        {"input_usd_per_million": float("nan")},
        {"output_usd_per_million": -1},
        {"max_output_tokens": 50000},
    ],
)
def test_invalid_budget_configuration_is_rejected(options):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **options)
