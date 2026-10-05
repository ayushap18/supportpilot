"""Keyless live mode (local CLI provider) and real GitHub-backed investigation tools."""

import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr
from supportpilot.config import Settings
from supportpilot.github_storage import GitHubRepositoryRow
from supportpilot.provider import Provider
from supportpilot.schemas import AccountArgs, HealthArgs, IncidentArgs, Ticket, ToolCall
from supportpilot.storage import Database
from supportpilot.tools import GitHubTools

STEP = {
    "summary": "Explain bearer auth",
    "tool_calls": [],
    "draft": {
        "outcome": "resolved",
        "response": "Use Authorization: Bearer <token>.",
        "missing_information": [],
        "evidence_ids": ["w:auth:1:0"],
    },
}
TICKET = Ticket(
    id="t",
    workspace_id="w",
    created_at="2026-10-06T00:00:00Z",
    subject="401 errors",
    description="API v2 returns 401 MISSING_BEARER.",
)


def outputs(agent, text):
    if agent == "claude_code":
        return json.dumps(
            {"type": "result", "is_error": False, "result": text, "usage": {"input_tokens": 7}}
        )
    if agent == "codex":
        return "\n".join(
            [
                json.dumps(
                    {"type": "item.completed", "item": {"type": "agent_message", "text": text}}
                ),
                json.dumps(
                    {"type": "turn.completed", "usage": {"input_tokens": 9, "output_tokens": 4}}
                ),
            ]
        )
    return json.dumps({"event": "result", "result": {"status": "SUCCESS", "response": text}})


@pytest.mark.parametrize("agent", ["claude_code", "codex", "antigravity"])
def test_cli_provider_runs_sandboxed_and_validates(settings, monkeypatch, agent):
    settings.mode, settings.llm_provider, settings.cli_agent = "live", "cli", agent
    settings.integrations = "off"
    provider = Provider(settings)
    assert provider.client is None and provider.cli == agent
    seen = {}
    reply = {"text": json.dumps(STEP)}

    class Process:
        returncode = 0

        async def communicate(self, data):
            seen["stdin"] = data.decode()
            return outputs(agent, reply["text"]).encode(), b""

    async def spawn(*args, **kwargs):
        seen["args"], seen["cwd"], seen["env"] = args, kwargs["cwd"], kwargs["env"]
        return Process()

    monkeypatch.setenv("SUPPORTPILOT_API_TOKENS_JSON", "secret")
    monkeypatch.setattr("supportpilot.provider.shutil.which", lambda name: "/bin/" + name)
    monkeypatch.setattr("supportpilot.provider.asyncio.create_subprocess_exec", spawn)
    step, usage = asyncio.run(provider.step(TICKET, [], []))
    assert step.draft.outcome == "resolved" and usage.model_rounds == 1
    assert "MISSING_BEARER" in seen["stdin"]
    assert "supportpilot-cli-" in seen["cwd"]  # Empty temporary directory, not a repository.
    assert not any(key.startswith("SUPPORTPILOT_") for key in seen["env"])
    args = seen["args"]
    if agent == "claude_code":
        assert args[:3] == ("claude", "--restricted", "--strict-mcp-config")
        assert args[args.index("--tools") + 1] == ""
    elif agent == "codex":
        assert "read-only" in args and "--output-schema" in args
    else:
        assert "--sandbox" in args and "Do not use any tools" in seen["stdin"]
    assert "No tools are connected." in (seen["stdin"] + " ".join(args))

    reply["text"] = json.dumps({**STEP, "draft": {"outcome": "resolved", "reply": "wrong key"}})
    with pytest.raises(ValueError, match="invalid investigation"):
        asyncio.run(provider.step(TICKET, [], []))


def test_live_mode_rejects_synthetic_integrations():
    assert Settings(_env_file=None, mode="live", llm_provider="cli").integrations == "off"
    assert Settings(_env_file=None).integrations == "synthetic"
    with pytest.raises(ValueError, match="synthetic"):
        Settings(_env_file=None, mode="live", llm_provider="cli", integrations="synthetic")


def test_github_tools_read_actions_and_incident_issues(settings, monkeypatch, tmp_path):
    database = Database("sqlite:///" + str(tmp_path / "tools.db"))
    database.initialize()
    settings.github_token = SecretStr("gh-token")
    with database.session() as session:
        session.add(
            GitHubRepositoryRow(
                id="r1",
                workspace_id="w",
                github_id="1",
                payload={"full_name": "team/app", "default_branch": "main"},
                snapshot={},
            )
        )
        session.commit()

    def handler(request):
        assert request.headers["authorization"] == "Bearer gh-token"
        if request.url.path.endswith("/actions/runs"):
            assert request.url.params["branch"] == "main"
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {"name": "CI", "status": "completed", "conclusion": "failure"},
                        {"name": "CI", "status": "completed", "conclusion": "success"},
                        {"name": "Deploy", "status": "completed", "conclusion": "success"},
                    ]
                },
            )
        assert request.url.params["labels"] == "incident"
        return httpx.Response(
            200,
            json=[
                {"number": 3, "title": "Webhook delivery outage", "body": "", "html_url": "u"},
                {"number": 4, "title": "Billing page slow", "body": "", "html_url": "u"},
                {"number": 5, "title": "Webhook PR", "pull_request": {}, "html_url": "u"},
            ],
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    tools = GitHubTools(database, settings)

    def run(name, arguments):
        return asyncio.run(tools.execute(ToolCall(name=name, arguments=arguments), "w"))

    health = run("get_service_health", HealthArgs(service_name="api"))
    assert health.status == "ok" and health.data["status"] == "degraded"  # Latest CI failed.
    assert {w["workflow"]: w["conclusion"] for w in health.data["workflows"]} == {
        "CI": "failure",
        "Deploy": "success",
    }
    incidents = run("search_known_incidents", IncidentArgs(query="webhook delivery"))
    assert [i["number"] for i in incidents.data["incidents"]] == [3]
    account = run("get_account_status", AccountArgs(account_id="acct_1"))
    assert account.status == "error" and "not connected" in account.data["message"]
    other = asyncio.run(
        tools.execute(
            ToolCall(name="get_service_health", arguments=HealthArgs(service_name="api")), "x"
        )
    )
    assert other.status == "unknown"  # A workspace without a repository gets no data.
