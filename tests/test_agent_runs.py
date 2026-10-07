"""Agent proposals and leases never execute server-side commands."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete
from supportpilot.agent_runs import build_agent_router
from supportpilot.agent_storage import AgentRunRow
from supportpilot.storage import Base, Database, TicketRow

WORKSPACE = "agent-tests-" + uuid4().hex
OTHER_WORKSPACE = WORKSPACE + "-other"


@pytest.fixture(params=["sqlite", "postgres"])
def agents(settings, request):
    if request.param == "postgres":
        url = os.getenv("SUPPORTPILOT_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("PostgreSQL integration runs in CI")
        settings.database_url = url
    database = Database(settings.database_url)
    database.initialize()
    app = FastAPI()

    def identity(authorization: str = Header()):
        if authorization not in {"admin", "second", "agent", "other"}:
            raise HTTPException(401)
        return {
            "workspace_id": OTHER_WORKSPACE if authorization == "other" else WORKSPACE,
            "reviewer_id": authorization,
            "role": "agent" if authorization == "agent" else "admin",
        }

    app.include_router(build_agent_router(database, identity, settings))
    with TestClient(app) as client:
        client.headers["Authorization"] = "admin"
        yield client, database
    with database.engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            if "workspace_id" in table.c:
                connection.execute(
                    delete(table).where(table.c.workspace_id.in_([WORKSPACE, OTHER_WORKSPACE]))
                )
    database.engine.dispose()


def create(client, **values):
    response = client.post(
        "/api/agents/runs",
        json={"provider": "codex", "task": "Investigate the repository documentation", **values},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_claim_completion_and_actual_usage(agents):
    client, database = agents
    run = create(client)
    path = "/api/agents/runs/" + run["id"]
    assert client.get("/api/agents/runs").json()["usage"]["cost_usd"] is None
    claim = client.post(path + "/claim", json={"runner_id": "laptop"}).json()
    assert claim["status"] == "running"
    assert "lease" not in client.get(path).json()
    with database.session() as session:
        row = session.get(AgentRunRow, run["id"])
        assert claim["lease"] not in str(row.payload)
        assert row.lease_hash != claim["lease"]
    assert client.post(path + "/claim", json={"runner_id": "another"}).status_code == 409
    report = {
        "lease": claim["lease"],
        "result": "Checked source. password=privatevalue",
        "exit_code": 0,
        "usage": {"input_tokens": 40, "output_tokens": 7, "cost_usd": 0.125},
    }
    assert (
        client.post(
            path + "/complete", json=report, headers={"Authorization": "second"}
        ).status_code
        == 403
    )
    assert client.post(path + "/complete", json={**report, "lease": "x" * 40}).status_code == 403
    result = client.post(path + "/complete", json=report)
    assert result.status_code == 200, result.text
    assert "privatevalue" not in result.text
    assert result.json()["status"] == "completed"
    assert client.post(path + "/complete", json=report).status_code == 409
    usage = client.get("/api/agents/runs").json()["usage"]
    assert usage == {
        "runs": 1,
        "input_tokens": 40,
        "output_tokens": 7,
        "cost_usd": 0.125,
        "reported_cost_runs": 1,
        "unreported_cost_runs": 0,
        "reported_input_tokens_runs": 1,
        "reported_output_tokens_runs": 1,
    }


def test_scope_role_cancellation_and_ticket_snapshot(agents):
    client, database = agents
    with database.session() as session:
        session.add(
            TicketRow(
                id="ticket",
                workspace_id=WORKSPACE,
                payload={"subject": "Bug", "description": "Broken flow", "revision": 2},
            )
        )
        session.add(TicketRow(id="private", workspace_id=OTHER_WORKSPACE, payload={}))
        session.commit()
    run = create(client, ticket_id="ticket", repository_full_name="owner/repo")
    assert run["ticket_context"]["revision"] == 2
    path = "/api/agents/runs/" + run["id"]
    other = {"Authorization": "other"}
    assert client.get(path, headers=other).status_code == 404
    assert client.get("/api/agents/runs", headers=other).json()["items"] == []
    for suffix in ("/cancel", "/claim", "/expire"):
        assert (
            client.post(
                path + suffix, headers={"Authorization": "agent"}, json={"runner_id": "test"}
            ).status_code
            == 403
        )
    invalid = client.post(
        "/api/agents/runs",
        json={"provider": "codex", "task": "Inspect code now", "ticket_id": "private"},
    )
    assert invalid.status_code == 404
    assert client.post(path + "/cancel").json()["status"] == "cancelled"
    assert client.post(path + "/claim", json={"runner_id": "test"}).status_code == 409
    assert client.post(path + "/cancel").status_code == 409
    providers = client.get("/api/agents/providers").json()["items"]
    assert {p["id"] for p in providers} == {"codex", "claude_code", "antigravity", "custom"}


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": -1},
        {"output_tokens": True},
        {"cost_usd": -1},
        {"cost_usd": "NaN"},
        {"input_tokens": 10**11},
        {"arbitrary": 3},
    ],
)
def test_invalid_usage_rejected(agents, usage):
    client, _ = agents
    run = create(client)
    path = "/api/agents/runs/" + run["id"]
    lease = client.post(path + "/claim", json={"runner_id": "test"}).json()["lease"]
    response = client.post(
        path + "/complete", json={"lease": lease, "result": "done", "exit_code": 0, "usage": usage}
    )
    assert response.status_code == 422
    assert client.get(path).json()["status"] == "running"


def test_expiry_does_not_retry_or_pretend_to_stop_process(agents):
    client, database = agents
    run = create(client)
    path = "/api/agents/runs/" + run["id"]
    lease = client.post(path + "/claim", json={"runner_id": "test"}).json()["lease"]
    assert client.post(path + "/expire").status_code == 409
    with database.session() as session:
        row = session.get(AgentRunRow, run["id"])
        row.payload = {
            **row.payload,
            "lease_expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        }
        session.commit()
    assert client.post(path + "/complete", json={"lease": lease, "exit_code": 0}).status_code == 409
    response = client.post(path + "/expire")
    assert response.json()["status"] == "failed"
    assert "unknown" in response.json()["error"]
    assert client.post(path + "/claim", json={"runner_id": "test"}).status_code == 409


def test_runner_heartbeat_and_live_log(agents):
    client, _ = agents
    beat = {"runner_id": "laptop", "providers": ["codex"], "allow_edits": True}
    assert client.post("/api/agents/runners/heartbeat", json=beat).status_code == 200
    runners = client.get("/api/agents/runners").json()["items"]
    assert runners[0]["online"] and runners[0]["providers"] == ["codex"]
    agent = {"Authorization": "agent"}
    assert client.post("/api/agents/runners/heartbeat", json=beat, headers=agent).status_code == 403
    assert client.get("/api/agents/runners", headers={"Authorization": "other"}).json() == {
        "items": []
    }

    run = create(client, allow_edits=True)
    assert run["allow_edits"] is True and run["log"] == []
    path = "/api/agents/runs/" + run["id"]
    lease = client.post(path + "/claim", json={"runner_id": "laptop"}).json()["lease"]
    lines = {"lease": lease, "lines": ["command: ls", "token=ghp_" + "a" * 36]}
    assert client.post(path + "/log", json=lines).status_code == 200
    log = client.get(path).json()["log"]
    assert log[0] == "command: ls" and "ghp_" not in log[1]
    forged = {"lease": "x" * 40, "lines": ["spoofed"]}
    assert client.post(path + "/log", json=forged).status_code == 403
    second = {"Authorization": "second"}
    assert client.post(path + "/log", json=lines, headers=second).status_code == 403


def test_providers_give_a_runnable_bridge_command(agents):
    import os
    import shlex

    client, _ = agents
    import shutil

    command = client.get("/api/agents/providers").json()["bridge"]
    executable = shutil.which(shlex.split(command)[0]) or shlex.split(command)[0]
    assert os.access(executable, os.X_OK)
    assert command == "supportpilot" or command.endswith("-m supportpilot.cli_bridge")
