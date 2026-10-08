"""GitHub integration acceptance: mock HTTP, real DB and retrieval, no external writes."""

import asyncio
import base64
import json
import os
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select
from supportpilot.github import build_github_router
from supportpilot.github_storage import GitHubConnectionRow, GitHubIssueRow, GitHubOAuthRow
from supportpilot.knowledge_storage import KnowledgeDocumentRow
from supportpilot.mission import build_mission_router, lane
from supportpilot.operations import queue_items
from supportpilot.provider import Provider
from supportpilot.retrieval import ChunkRow, Retrieval
from supportpilot.storage import Base, Database, InvestigationRow, TicketRow

WORKSPACE = "github-tests-" + uuid4().hex
OTHER_WORKSPACE = WORKSPACE + "-other"

REPO = {
    "id": 42,
    "full_name": "team/project",
    "description": "Example",
    "private": True,
    "default_branch": "main",
    "html_url": "https://github.com/team/project",
}
DOC = "# Troubleshooting\nRestart the worker to resolve this example failure."


@pytest.fixture(params=["sqlite", "postgres"])
def github(settings, monkeypatch, request):
    if request.param == "postgres":
        url = os.getenv("SUPPORTPILOT_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("PostgreSQL integration runs in CI")
        settings.database_url = url
    identities = settings.identities()
    for entry in identities:
        entry["workspace_id"] = WORKSPACE if entry["workspace_id"] == "demo" else OTHER_WORKSPACE
    settings.api_tokens_json = SecretStr(json.dumps(identities))
    settings.github_client_id = "client-id"
    settings.github_client_secret = SecretStr("client-secret")
    settings.integration_encryption_key = SecretStr(Fernet.generate_key().decode())
    database = Database(settings.database_url)
    database.initialize()
    provider = Provider(settings)
    retrieval = Retrieval(database, settings, provider)
    calls = []
    remote_issues = []
    state = {"issue_failure": False, "doc": DOC, "extra_docs": False}

    def handler(request):
        calls.append(request)
        path = request.url.path
        if path == "/login/oauth/access_token":
            assert request.url.host == "github.com"
            return httpx.Response(
                200, json={"access_token": "github-secret-token", "scope": "repo,read:user"}
            )
        assert request.url.host == "api.github.com"
        assert request.headers["authorization"] == "Bearer github-secret-token"
        if path == "/user":
            return httpx.Response(200, json={"login": "octocat"})
        if path == "/user/repos":
            return httpx.Response(
                200,
                json=[REPO],
                headers={"link": '<https://api.github.com/user/repos?page=2>; rel="next"'},
            )
        if path == "/repos/team/project":
            return httpx.Response(200, json=REPO)
        if "/commits/" in path:
            return httpx.Response(
                200,
                json={
                    "sha": "a" * 40,
                    "commit": {"message": "Fix timeout"},
                    "html_url": "https://github.com/team/project/commit/" + "a" * 40,
                    "stats": {"additions": 2, "deletions": 1, "total": 3},
                    "files": [
                        {
                            "filename": f"file{i}.py",
                            "status": "modified",
                            "additions": 2,
                            "deletions": 1,
                            "patch": "+ token=private-secret-value\n" + "x" * 13000,
                        }
                        for i in range(45)
                    ]
                    + [{"filename": "binary.png"}],
                },
            )
        if path.endswith("/commits"):
            return httpx.Response(
                200,
                json=[
                    {
                        "sha": "abc",
                        "commit": {
                            "message": "Fix timeout",
                            "author": {"name": "Jane", "date": "2026-10-04T00:00:00Z"},
                        },
                        "author": {"login": "jane"},
                        "html_url": "https://github.com/team/project/commit/abc",
                    }
                ],
            )
        if path.endswith("/events"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "event-1",
                        "type": "PushEvent",
                        "actor": {"login": "jane"},
                        "created_at": "2026-10-04T00:00:00Z",
                    }
                ],
            )
        if path.endswith("/contributors"):
            return httpx.Response(
                200,
                json=[{"login": "jane", "contributions": 8, "html_url": "https://github.com/jane"}],
            )
        if "/git/trees/" in path:
            files = [
                {
                    "type": "blob",
                    "path": "docs/guide.md",
                    "sha": state.get("doc_sha", "doc-sha"),
                    "size": len(state["doc"]),
                }
            ]
            if state["extra_docs"]:
                files.extend(
                    {"type": "blob", "path": f"docs/guide-{i}.md", "sha": "doc-sha", "size": 30001}
                    for i in range(30)
                )
            return httpx.Response(
                200, json={"sha": "tree-sha", "tree": files, "truncated": state["extra_docs"]}
            )
        if "/git/blobs/" in path:
            return httpx.Response(
                200,
                json={
                    "encoding": "base64",
                    "size": len(state["doc"]),
                    "content": base64.b64encode(state["doc"].encode()).decode(),
                },
            )
        if path.endswith("/pulls/5/reviews"):
            return httpx.Response(
                200,
                json=[
                    {"user": {"login": "rev"}, "state": "CHANGES_REQUESTED"},
                    {"user": {"login": "rev"}, "state": "APPROVED"},
                    {"user": {"login": "bot"}, "state": "COMMENTED"},
                ],
            )
        if path.endswith("/pulls/5"):
            return httpx.Response(
                200,
                json={
                    "number": 5,
                    "html_url": "https://github.com/team/project/pull/5",
                    "state": "open",
                    "merged": False,
                    "draft": True,
                    "changed_files": 1,
                    "additions": 3,
                    "deletions": 0,
                    "head": {"sha": "headsha"},
                },
            )
        if path.endswith("/actions/runs"):
            assert request.url.params["head_sha"] == "headsha"
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {
                            "name": "CI",
                            "status": "completed",
                            "conclusion": "failure",
                            "html_url": "https://github.com/team/project/actions/runs/1",
                        }
                    ]
                },
            )
        if path.endswith("/pulls") and request.method == "POST":
            data = json.loads(request.content)
            state["pulls"] = state.get("pulls", []) + [data]
            return httpx.Response(
                201, json={"number": 5, "html_url": "https://github.com/team/project/pull/5"}
            )
        if path.endswith("/issues") and request.method == "GET":
            return httpx.Response(200, json=remote_issues + state.get("support_issues", []))
        if path.endswith("/issues") and request.method == "POST":
            data = json.loads(request.content)
            issue = {
                "number": 17,
                "title": data["title"],
                "body": data["body"],
                "html_url": "https://github.com/team/project/issues/17",
                "state": "open",
            }
            remote_issues.append(issue)
            if state["issue_failure"]:
                raise httpx.ReadTimeout("Uncertain after publication")
            return httpx.Response(201, json=issue)
        raise AssertionError(f"Unexpected request {request.method} {path}")

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )

    def identity(authorization: str = Header(default="")):
        if authorization == "Bearer admin":
            return {"workspace_id": WORKSPACE, "reviewer_id": "alice", "role": "admin"}
        if authorization == "Bearer agent":
            return {"workspace_id": WORKSPACE, "reviewer_id": "agent", "role": "agent"}
        if authorization == "Bearer other":
            return {"workspace_id": OTHER_WORKSPACE, "reviewer_id": "bob", "role": "admin"}
        raise HTTPException(401, "Unauthorized")

    app = FastAPI()
    app.include_router(build_github_router(database, retrieval, identity, settings))
    app.include_router(build_mission_router(database, identity, settings))
    with TestClient(app) as client:
        yield client, database, calls, state, retrieval
    with database.engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            if "workspace_id" in table.c:
                connection.execute(
                    delete(table).where(table.c.workspace_id.in_([WORKSPACE, OTHER_WORKSPACE]))
                )
    database.engine.dispose()


def admin():
    return {"Authorization": "Bearer admin"}


def connect(github):
    client, database, _, _, _ = github
    result = client.post("/api/github/connect", headers=admin())
    assert result.status_code == 200
    params = parse_qs(urlparse(result.json()["authorize_url"]).query)
    result = client.get(
        "/api/github/callback",
        params={"state": params["state"][0], "code": "code"},
        follow_redirects=False,
    )
    assert result.headers["location"] == "/?github=connected"
    with database.session() as session:
        assert session.get(GitHubConnectionRow, WORKSPACE).token != "github-secret-token"
    return params


def select_repo(github):
    connect(github)
    client = github[0]
    response = client.post(
        "/api/github/repos/select", headers=admin(), json={"full_name": "team/project"}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_oauth_pkce_cookie_binding_single_use_and_encryption(github):
    client, database, calls, _, _ = github
    response = client.post("/api/github/connect", headers=admin())
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    params = parse_qs(urlparse(response.json()["authorize_url"]).query)
    assert params["code_challenge_method"] == ["S256"]
    state = params["state"][0]
    cookies = list(client.cookies.jar)
    client.cookies.clear()
    invalid = client.get(
        "/api/github/callback", params={"state": state, "code": "code"}, follow_redirects=False
    )
    assert invalid.headers["location"] == "/?github=authorization_failed"
    assert not calls
    for cookie in cookies:
        client.cookies.jar.set_cookie(cookie)
    result = client.get(
        "/api/github/callback", params={"state": state, "code": "code"}, follow_redirects=False
    )
    assert result.headers["location"] == "/?github=connected"
    assert b"code_verifier=" in calls[0].content
    assert len(calls) == 2
    result = client.get(
        "/api/github/callback", params={"state": state, "code": "code"}, follow_redirects=False
    )
    assert result.headers["location"] == "/?github=authorization_failed"
    assert len(calls) == 2
    with database.session() as session:
        assert session.get(GitHubOAuthRow, state) is None
        assert "github-secret-token" not in session.get(GitHubConnectionRow, WORKSPACE).token
    status = client.get("/api/github/status", headers=admin()).json()
    assert status == {
        "configured": True,
        "connected": True,
        "login": "octocat",
        "scopes": ["repo", "read:user"],
        "missing": [],
        "method": "oauth",
    }


def test_oauth_expiry_and_authorization(github):
    client, database, calls, _, _ = github
    assert client.post("/api/github/connect").status_code == 401
    assert (
        client.post("/api/github/connect", headers={"Authorization": "Bearer agent"}).status_code
        == 403
    )
    response = client.post("/api/github/connect", headers=admin())
    state = parse_qs(urlparse(response.json()["authorize_url"]).query)["state"][0]
    with database.session() as session:
        session.get(GitHubOAuthRow, state).expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    response = client.get(
        "/api/github/callback", params={"state": state, "code": "code"}, follow_redirects=False
    )
    assert response.headers["location"].endswith("authorization_failed")
    assert not calls


def test_repository_scope_sync_limits_and_idempotent_selection(github):
    client, _, _, state, _ = github
    repository_id = select_repo(github)
    available = client.get("/api/github/repos", headers=admin()).json()
    assert available["has_more"] and available["items"][0]["id"] == 42
    again = client.post(
        "/api/github/repos/select", headers=admin(), json={"full_name": "team/project"}
    ).json()
    assert again["id"] == repository_id
    base = "/api/github/repositories/" + repository_id
    assert client.get(base, headers={"Authorization": "Bearer other"}).status_code == 404
    assert client.post(base + "/sync", headers={"Authorization": "Bearer agent"}).status_code == 403
    state["extra_docs"] = True
    result = client.post(base + "/sync", headers=admin())
    assert result.status_code == 200, result.text
    result = result.json()
    assert result["commits"][0]["author"] == "jane"
    assert result["contributors"][0]["contributions"] == 8
    assert result["activity"][0]["actor"] == "jane"
    assert result["analysis"]["kind"] == "inventory"
    assert result["limits"]["tree_truncated"] and result["limits"]["docs_truncated"]
    assert len(result["docs"]) == 20
    assert client.get(base, headers={"Authorization": "Bearer agent"}).status_code == 200


def test_document_import_idempotence_archive_and_revision(github):
    client, database, _, state, _ = github
    repository_id = select_repo(github)
    base = "/api/github/repositories/" + repository_id
    assert client.post(base + "/import-docs", headers=admin()).status_code == 409
    assert client.post(base + "/sync", headers=admin()).status_code == 200
    first = client.post(base + "/import-docs", headers=admin()).json()
    document_id = first["imported"][0]["document_id"]
    again = client.post(base + "/import-docs", headers=admin()).json()
    assert not again["imported"] and len(again["skipped"]) == 1
    state["doc"] += "\nThen verify the health endpoint."
    result = client.post(base + "/import-docs", headers=admin()).json()
    assert result["imported"][0]["document_id"] == document_id
    with database.session() as session:
        row = session.get(KnowledgeDocumentRow, document_id)
        assert row.revision == 2 and "health endpoint" in row.body
        assert (
            session.scalar(select(ChunkRow).where(ChunkRow.document_id == document_id)).workspace_id
            == WORKSPACE
        )
        row.archived = True
        session.commit()
    result = client.post(base + "/import-docs", headers=admin()).json()
    assert result["skipped"][0]["reason"] == "Document is archived"
    assert (
        client.post(base + "/import-docs", headers={"Authorization": "Bearer agent"}).status_code
        == 403
    )
    assert client.delete("/api/github/connection", headers=admin()).json()["knowledge_retained"]
    assert client.get(base, headers=admin()).status_code == 404
    with database.session() as session:
        assert session.get(KnowledgeDocumentRow, document_id) is not None


@pytest.mark.parametrize("uncertain", [False, True])
def test_issue_creation_explicit_idempotent_reconciliation(github, uncertain):
    client, database, calls, state, _ = github
    repository_id = select_repo(github)
    with database.session() as session:
        session.add(
            TicketRow(
                id="ticket1",
                workspace_id=WORKSPACE,
                payload={
                    "subject": "Webhook failure",
                    "description": "The webhook does not deliver after updating.",
                    "log_excerpt": "PRIVATE LOG MUST NOT BE PUBLISHED",
                },
            )
        )
        session.add(
            TicketRow(
                id="private",
                workspace_id=OTHER_WORKSPACE,
                payload={"subject": "Secret", "description": "Private ticket"},
            )
        )
        session.commit()
    endpoint = "/api/github/repositories/" + repository_id + "/issues"
    assert (
        client.post(
            endpoint, headers={"Authorization": "Bearer agent"}, json={"ticket_id": "ticket1"}
        ).status_code
        == 403
    )
    assert client.post(endpoint, headers=admin(), json={"ticket_id": "private"}).status_code == 404
    state["issue_failure"] = uncertain
    response = client.post(endpoint, headers=admin(), json={"ticket_id": "ticket1"})
    assert response.status_code == (409 if uncertain else 200), response.text
    response = client.post(endpoint, headers=admin(), json={"ticket_id": "ticket1"})
    assert response.status_code == 200, response.text
    assert response.json()["number"] == 17
    posts = [call for call in calls if call.method == "POST" and call.url.path.endswith("/issues")]
    assert len(posts) == 1
    assert b"PRIVATE LOG" not in posts[0].content
    with database.session() as session:
        assert len(session.scalars(select(GitHubIssueRow)).all()) == 1


def test_import_embedding_failure_preserves_previous_index(github, monkeypatch):
    client, database, _, state, retrieval = github
    repository_id = select_repo(github)
    base = "/api/github/repositories/" + repository_id
    client.post(base + "/sync", headers=admin())
    document_id = client.post(base + "/import-docs", headers=admin()).json()["imported"][0][
        "document_id"
    ]
    state["doc"] += " Another troubleshooting step."

    async def unavailable(doc):
        raise RuntimeError("Provider unavailable with private internal details")

    monkeypatch.setattr(retrieval, "prepare_document", unavailable)
    response = client.post(base + "/import-docs", headers=admin())
    assert response.status_code == 200
    assert len(response.json()["errors"]) == 1
    assert "private internal" not in response.text
    with database.session() as session:
        assert session.get(KnowledgeDocumentRow, document_id).revision == 1
        assert session.get(KnowledgeDocumentRow, document_id).body == DOC
        assert (
            session.scalar(select(ChunkRow).where(ChunkRow.document_id == document_id)).body == DOC
        )


def test_import_timeout_reports_and_preserves_database(github, monkeypatch):
    client, database, _, _, retrieval = github
    repository_id = select_repo(github)
    base = "/api/github/repositories/" + repository_id
    client.post(base + "/sync", headers=admin())
    retrieval.settings.timeout_seconds = 0.005

    async def slow(doc):
        await asyncio.sleep(1)

    monkeypatch.setattr(retrieval, "prepare_document", slow)
    response = client.post(base + "/import-docs", headers=admin())
    assert response.status_code == 200
    assert len(response.json()["errors"]) == 1
    with database.session() as session:
        assert not session.scalars(select(KnowledgeDocumentRow)).all()


def test_document_identity_survives_reconnect(github):
    client, database, _, _, _ = github
    first = select_repo(github)
    base = "/api/github/repositories/" + first
    client.post(base + "/sync", headers=admin())
    document_id = client.post(base + "/import-docs", headers=admin()).json()["imported"][0][
        "document_id"
    ]
    client.delete("/api/github/connection", headers=admin())
    second = select_repo(github)
    assert first != second
    base = "/api/github/repositories/" + second
    client.post(base + "/sync", headers=admin())
    response = client.post(base + "/import-docs", headers=admin()).json()
    assert not response["imported"]
    assert response["skipped"][0]["reason"] == "Unchanged or too short"
    with database.session() as session:
        assert session.scalars(select(KnowledgeDocumentRow.id)).all() == [document_id]


def test_commit_diff_is_bounded_redacted_and_scoped(github):
    client = github[0]
    repository_id = select_repo(github)
    base = "/api/github/repositories/" + repository_id + "/commits/"
    assert client.get(base + "main", headers=admin()).status_code == 422
    assert client.get(base + "a" * 40, headers={"Authorization": "Bearer other"}).status_code == 404
    response = client.get(base + "a" * 40, headers={"Authorization": "Bearer agent"})
    assert response.status_code == 200
    result = response.json()
    assert result["limits"]["files_truncated"]
    assert len(result["files"]) == 40
    assert result["files"][0]["patch_truncated"]
    assert "private-secret-value" not in response.text
    assert len(result["files"][0]["patch"]) <= 12000


def test_server_token_connects_without_oauth(github, settings):
    _, database, _, _, retrieval = github
    settings.github_token = SecretStr("github-secret-token")
    settings.github_client_id = ""
    settings.integration_encryption_key = SecretStr("")
    app = FastAPI()
    app.include_router(
        build_github_router(
            database,
            retrieval,
            lambda: {"workspace_id": WORKSPACE, "reviewer_id": "alice", "role": "admin"},
            settings,
        )
    )
    with TestClient(app) as client:
        status = client.get("/api/github/status").json()
        assert status["connected"] and status["login"] == "octocat"
        assert status["method"] == "token" and status["missing"] == []
        assert client.get("/api/github/repos").json()["items"][0]["full_name"] == "team/project"


def test_agent_run_opens_draft_pull_request_explicitly(github):
    from supportpilot.agent_storage import AgentRunRow

    client, database, _, state, _ = github
    connect(github)
    run_id = str(uuid4())
    payload = {
        "id": run_id,
        "status": "completed",
        "provider": "codex",
        "task": "Fix the webhook retry bug where deliveries stop after the v2 signature "
        "migration completes\nMore detail",
        "repository_full_name": "team/project",
        "result": "Changed retry.py; token=ghp_" + "a" * 36,
        "artifacts": [{"kind": "branch", "label": "supportpilot/" + run_id, "url": None}],
    }
    with database.session() as session:
        session.add(
            AgentRunRow(id=run_id, workspace_id=WORKSPACE, status="completed", payload=payload)
        )
        session.commit()
    path = f"/api/github/agent-runs/{run_id}/pull-request"
    # The branch was never pushed, so there is nothing to open a PR from.
    assert client.post(path, headers=admin()).status_code == 409
    with database.session() as session:
        row = session.get(AgentRunRow, run_id)
        row.payload = {
            **payload,
            "artifacts": [{"kind": "branch", "label": f"supportpilot/{run_id} (pushed)"}],
        }
        session.commit()
    assert client.post(path, headers={"Authorization": "Bearer agent"}).status_code == 403
    assert client.post(path, headers={"Authorization": "Bearer other"}).status_code == 404
    opened = client.post(path, headers=admin())
    assert opened.status_code == 201, opened.text
    pull = state["pulls"][0]
    assert pull["draft"] is True and pull["head"] == "supportpilot/" + run_id
    assert pull["base"] == "main"
    # Long task lines are cut at a word boundary, never mid-word.
    assert pull["title"] == (
        "SupportPilot: Fix the webhook retry bug where deliveries stop after the v2 signature…"
    )
    assert "ghp_" not in pull["body"]
    assert opened.json()["artifacts"][-1]["url"] == "https://github.com/team/project/pull/5"
    assert client.post(path, headers=admin()).status_code == 409  # Only once per run.


def test_pr_ci_panel_live_inbox_and_knowledge_freshness(github, settings):
    import hashlib
    import hmac

    from supportpilot.agent_storage import AgentRunRow

    client, database, _, state, _ = github
    connect(github)
    repo_id = select_repo(github)
    base = "/api/github/repositories/" + repo_id
    client.post(base + "/sync", headers=admin())
    assert client.post(base + "/import-docs", headers=admin()).json()["imported"]
    fresh = client.get("/api/mission", headers=admin()).json()["knowledge"]
    assert [(d["title"], d["status"]) for d in fresh] == [("docs/guide.md", "current")]
    state["doc_sha"] = "new-sha"
    client.post(base + "/sync", headers=admin())  # The record of what was indexed survives.
    changed = client.get("/api/mission", headers=admin()).json()["knowledge"][0]
    assert changed["status"] == "changed_upstream" and changed["indexed_at"]

    run_id = str(uuid4())
    with database.session() as session:
        session.add(
            AgentRunRow(
                id=run_id,
                workspace_id=WORKSPACE,
                status="completed",
                payload={
                    "id": run_id,
                    "status": "completed",
                    "provider": "codex",
                    "task": "Fix it",
                    "created_at": "2026-10-05T00:00:00+00:00",
                    "completed_at": "2026-10-05T00:05:00+00:00",
                    "usage": {},
                    "repository_full_name": "team/project",
                    "artifacts": [
                        {"kind": "pull_request", "url": "https://github.com/team/project/pull/5"}
                    ],
                },
            )
        )
        session.commit()
    panel = client.get(f"/api/github/agent-runs/{run_id}/pull-request", headers=admin()).json()
    assert panel["state"] == "open" and panel["draft"] and panel["changed_files"] == 1
    assert panel["reviews"] == [{"login": "rev", "state": "APPROVED"}]  # Latest verdict wins.
    assert panel["checks"][0]["conclusion"] == "failure"
    other = {"Authorization": "Bearer other"}
    assert (
        client.get(f"/api/github/agent-runs/{run_id}/pull-request", headers=other).status_code
        == 404
    )

    settings.github_webhook_secret = SecretStr("s")

    def send(event, payload):
        body = json.dumps({**payload, "repository": REPO}).encode()
        signature = "sha256=" + hmac.new(b"s", body, hashlib.sha256).hexdigest()
        client.post(
            "/api/github/webhook",
            content=body,
            headers={"x-github-event": event, "x-hub-signature-256": signature},
        )

    send(
        "pull_request",
        {"action": "closed", "pull_request": {"number": 5, "title": "Fix", "merged": True}},
    )
    send(
        "workflow_run",
        {
            "action": "completed",
            "workflow_run": {"name": "CI", "conclusion": "failure", "head_branch": "main"},
        },
    )
    send(
        "workflow_run",
        {"action": "completed", "workflow_run": {"name": "CI", "conclusion": "success"}},
    )
    send("push", {"ref": "refs/heads/main", "commits": [{}, {}], "pusher": {"name": "jane"}})
    inbox = client.get("/api/mission", headers=admin()).json()["inbox"]
    titles = {item["title"] for item in inbox}
    assert titles == {"PR #5 merged", "Check failed: CI", "Push to main"}


def test_merged_pr_stamps_ticket_and_lane_needs_customer_confirmation(github, settings):
    import hashlib
    import hmac

    from supportpilot.agent_storage import AgentRunRow

    client, database, _, _, _ = github
    select_repo(github)
    pr_url = "https://github.com/team/project/pull/9"
    ticket_id, run_id = str(uuid4()), str(uuid4())
    with database.session() as session:
        session.add(
            TicketRow(
                id=ticket_id,
                workspace_id=WORKSPACE,
                payload={
                    "id": ticket_id,
                    "workspace_id": WORKSPACE,
                    "subject": "Retries stop",
                    "description": "Webhook retries stop after an upgrade.",
                    "created_at": "2026-10-05T00:00:00+00:00",
                },
            )
        )
        run = {
            "id": run_id,
            "ticket_id": ticket_id,
            "status": "completed",
            "provider": "codex",
            "task": "Fix it",
            "created_at": "2026-10-05T00:00:00+00:00",
            "started_at": "2026-10-05T00:01:00+00:00",
            "completed_at": "2026-10-05T00:05:00+00:00",
            "usage": {},
            "log": [f"line {n}" for n in range(12)],
            "artifacts": [
                {"kind": "test_report", "label": "repro (red)"},
                {"kind": "test_report", "label": "fix (green)"},
                {"kind": "pull_request", "label": "Draft PR #9", "url": pr_url},
            ],
        }
        session.add(AgentRunRow(id=run_id, workspace_id=WORKSPACE, status="completed", payload=run))
        draft = {"outcome": "answer", "evidence_ids": []}
        inv = {"id": "inv-1", "state": "awaiting_review", "draft": draft, "ticket_revision": 1}
        session.add(
            InvestigationRow(
                id="inv-1",
                ticket_id=ticket_id,
                workspace_id=WORKSPACE,
                idempotency_key="k",
                created_at=datetime.now(UTC),
                payload=inv,
            )
        )
        session.commit()
    settings.github_webhook_secret = SecretStr("s")
    pull = {"number": 9, "merged": True, "html_url": pr_url, "merged_at": "2026-10-06T00:00:00Z"}
    body = json.dumps({"action": "closed", "pull_request": pull, "repository": REPO}).encode()
    signature = "sha256=" + hmac.new(b"s", body, hashlib.sha256).hexdigest()
    sent = client.post(
        "/api/github/webhook",
        content=body,
        headers={"x-github-event": "pull_request", "x-hub-signature-256": signature},
    )
    assert sent.status_code == 200, sent.text
    with database.session() as session:
        ticket = session.get(TicketRow, ticket_id).payload
        queued = next(t for t in queue_items(session, WORKSPACE) if t["id"] == ticket_id)
    # A merge stamp is metadata: the revision holds, so the pending draft stays approvable.
    assert ticket["fix_merged_at"].startswith("2026-10-06") and ticket["revision"] == 1
    assert queued["review_status"] == "pending"
    assert ticket["status"] == "open"  # resolve_on_merge is off by default.
    lane = next(
        item
        for item in client.get("/api/mission", headers=admin()).json()["lanes"]
        if item["ticket_id"] == ticket_id
    )
    assert lane["steps"][-4:] == ["red", "green", "pr", "merged"]
    assert lane["customer_confirmed"] is False and lane["log_tail"][-1] == "line 11"
    assert len(lane["log_tail"]) == 8

    settings.resolve_on_merge_workspaces = [WORKSPACE]
    with database.session() as session:
        row = session.get(AgentRunRow, run_id)
        row.payload = {**run, "review": {"customer_confirmed": True}}
        session.commit()
    client.post(
        "/api/github/webhook",
        content=body,
        headers={"x-github-event": "pull_request", "x-hub-signature-256": signature},
    )
    with database.session() as session:
        assert session.get(TicketRow, ticket_id).payload["status"] == "resolved"
    lanes = client.get("/api/mission", headers=admin()).json()["lanes"]
    assert next(i for i in lanes if i["ticket_id"] == ticket_id)["customer_confirmed"] is True


def test_lane_red_needs_reproduction_and_green_needs_merge():
    ticket = {"id": "t", "subject": "s", "status": "open", "latest_investigation_id": None}
    ticket["latest_outcome"] = None
    run = {
        "id": "r",
        "status": "failed",
        "error": "not_reproduced: the new test already passes",
        "started_at": "2026-10-05T00:01:00+00:00",
        "review": {"customer_confirmed": True},
        "artifacts": [{"kind": "test_report", "label": "repro (red)"}],
    }
    unmerged = lane(ticket, run)
    assert "red" not in unmerged["steps"] and unmerged["customer_confirmed"] is False
