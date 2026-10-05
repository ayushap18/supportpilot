"""Sign in with GitHub → choose repository → workspace token, against a mocked GitHub."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from supportpilot.app import create_app

REPOS = {
    "team/app": {"id": 7, "push": True, "admin": True},
    "team/docs": {"id": 8, "push": True, "admin": False},
    "other/readonly": {"id": 9, "push": False, "admin": False},
}


def repo(name):
    meta = REPOS[name]
    return {
        "id": meta["id"],
        "full_name": name,
        "description": None,
        "private": True,
        "default_branch": "main",
        "html_url": "https://github.com/" + name,
        "permissions": {"push": meta["push"], "admin": meta["admin"]},
    }


@pytest.fixture
def app_client(settings, monkeypatch):
    settings.github_client_id = "client-id"
    settings.github_client_secret = SecretStr("client-secret")
    settings.integration_encryption_key = SecretStr(Fernet.generate_key().decode())

    who = {"login": "octocat"}

    def handler(request):
        path = request.url.path
        if path == "/login/oauth/access_token":
            assert b"code_verifier=" in request.content
            assert b"auth%2Fgithub%2Fcallback" in request.content
            return httpx.Response(200, json={"access_token": "gho-user", "scope": "repo"})
        assert request.headers["authorization"] == "Bearer gho-user"
        if path == "/user":
            return httpx.Response(200, json=who)
        if path == "/user/repos":
            return httpx.Response(200, json=[repo(n) for n in REPOS])
        if path.startswith("/repos/"):
            return httpx.Response(200, json=repo(path.removeprefix("/repos/")))
        raise AssertionError(path)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )
    with TestClient(create_app(settings), follow_redirects=False) as client:
        client.who = who
        yield client


def sign_in(client, intent="signup"):
    start = client.get("/api/auth/github/start", params={"intent": intent})
    query = parse_qs(urlparse(start.headers["location"]).query)
    assert ("prompt" in query) == (intent == "regenerate")
    state = query["state"][0]
    done = client.get("/api/auth/github/callback", params={"state": state, "code": "abc"})
    assert done.headers["location"] == "/#" + intent


def test_sign_up_sign_in_and_regenerate_flow(app_client):
    assert app_client.get("/api/auth/config").json() == {"github": True}
    assert app_client.get("/api/auth/session").json()["login"] is None
    sign_in(app_client, "signup")
    me = app_client.get("/api/auth/session").json()
    assert me == {"login": "octocat", "workspaces": [], "can_regenerate": False, "invites": []}

    names = [r["full_name"] for r in app_client.get("/api/auth/repos").json()["items"]]
    assert names == ["team/app", "team/docs"]  # read-only repositories are hidden

    issued = app_client.post("/api/auth/workspaces", json={"full_name": "team/app"}).json()
    assert issued["token"].startswith("sp_") and issued["role"] == "admin"
    first = {"Authorization": "Bearer " + issued["token"]}
    assert app_client.get("/api/session", headers=first).json() == {
        "workspace_id": "gh-7",
        "reviewer_id": "octocat",
        "role": "admin",
        "label": "team/app",
    }
    # The new workspace is already connected to GitHub with its repository selected.
    assert app_client.get("/api/github/status", headers=first).json()["login"] == "octocat"
    repos = app_client.get("/api/github/repositories", headers=first).json()["items"]
    assert [r["full_name"] for r in repos] == ["team/app"]
    members = app_client.get("/api/operations", headers=first).json()["members"]
    assert members == [{"reviewer_id": "octocat", "role": "admin"}]

    # Signing up again for the same repository never silently rotates the saved token.
    again = app_client.post("/api/auth/workspaces", json={"full_name": "team/app"})
    assert again.status_code == 409
    assert app_client.get("/api/session", headers=first).status_code == 200

    # A second repository is a second workspace with its own token.
    docs = app_client.post("/api/auth/workspaces", json={"full_name": "team/docs"}).json()
    assert docs["role"] == "agent" and docs["workspace_id"] == "gh-8"
    listed = app_client.get("/api/auth/session").json()["workspaces"]
    assert {w["repository"] for w in listed} == {"team/app", "team/docs"}
    denied = app_client.post("/api/auth/workspaces", json={"full_name": "other/readonly"})
    assert denied.status_code == 403

    # Sign-in: tokens are trimmed, and must match the user and the chosen workspace.
    padded = {"token": " " + issued["token"] + "\n", "workspace_id": "gh-7"}
    assert app_client.post("/api/auth/verify", json=padded).json()["workspace_id"] == "gh-7"
    wrong = {"token": issued["token"], "workspace_id": "gh-8"}
    assert app_client.post("/api/auth/verify", json=wrong).status_code == 403

    # A sign-in/sign-up session is not enough to rotate tokens.
    blocked = app_client.post("/api/auth/workspaces/gh-7/regenerate")
    assert blocked.status_code == 401

    sign_in(app_client, "regenerate")
    assert app_client.get("/api/auth/session").json()["can_regenerate"] is True
    rotated = app_client.post("/api/auth/workspaces/gh-7/regenerate").json()
    assert rotated["regenerated"] and rotated["token"] != issued["token"]
    assert app_client.get("/api/session", headers=first).status_code == 401
    second = {"Authorization": "Bearer " + rotated["token"]}
    assert app_client.get("/api/session", headers=second).status_code == 200
    assert app_client.post("/api/auth/workspaces/gh-unknown/regenerate").status_code == 404
    stale = app_client.post("/api/auth/verify", json={"token": issued["token"]})
    assert stale.status_code == 403

    app_client.delete("/api/auth/session")
    assert app_client.get("/api/auth/session").json()["login"] is None
    assert (
        app_client.post("/api/auth/workspaces", json={"full_name": "team/app"}).status_code == 401
    )


def test_regenerate_window_expires(app_client, monkeypatch):
    from supportpilot import accounts

    sign_in(app_client, "signup")
    app_client.post("/api/auth/workspaces", json={"full_name": "team/app"})
    monkeypatch.setattr(accounts, "REGENERATE_WINDOW", accounts.timedelta(0))
    sign_in(app_client, "regenerate")
    assert app_client.get("/api/auth/session").json()["can_regenerate"] is False
    assert app_client.post("/api/auth/workspaces/gh-7/regenerate").status_code == 401


def test_callback_rejects_mismatched_state(app_client):
    app_client.get("/api/auth/github/start")
    bad = app_client.get("/api/auth/github/callback", params={"state": "forged", "code": "abc"})
    assert bad.headers["location"] == "/?login=failed#signin"
    assert app_client.get("/api/auth/session").json()["login"] is None


def test_sign_in_unavailable_without_oauth_app(client):
    assert client.get("/api/auth/config").json() == {"github": False}
    response = client.get("/api/auth/github/start", follow_redirects=False)
    assert response.headers["location"] == "/?login=unavailable#signin"


def test_verify_rejects_token_of_another_user(app_client, headers):
    sign_in(app_client, "signin")
    # The static demo token belongs to reviewer "alice", not the GitHub user "octocat".
    token = headers["Authorization"].removeprefix("Bearer ")
    assert app_client.post("/api/auth/verify", json={"token": token}).status_code == 403


def test_admin_invites_github_user_who_joins_with_own_token(app_client):
    sign_in(app_client, "signup")
    owner = app_client.post("/api/auth/workspaces", json={"full_name": "team/app"}).json()
    admin = {"Authorization": "Bearer " + owner["token"]}
    invite = app_client.post("/api/auth/invites", json={"login": "Hubot"}, headers=admin)
    assert invite.status_code == 201 and invite.json()["repository"] == "team/app"
    assert invite.json()["login"] == "hubot" and invite.json()["role"] == "agent"
    duplicate = app_client.post("/api/auth/invites", json={"login": "hubot"}, headers=admin)
    assert duplicate.status_code == 409
    member = app_client.post("/api/auth/invites", json={"login": "octocat"}, headers=admin)
    assert member.status_code == 409  # Already a member.
    bad = app_client.post("/api/auth/invites", json={"login": "-bad name"}, headers=admin)
    assert bad.status_code == 422
    assert len(app_client.get("/api/auth/invites", headers=admin).json()["items"]) == 1

    # Octocat cannot accept an invitation addressed to someone else.
    invite_id = invite.json()["id"]
    assert app_client.post(f"/api/auth/invites/{invite_id}/accept").status_code == 404

    app_client.delete("/api/auth/session")
    app_client.who["login"] = "HUBOT"
    sign_in(app_client, "signin")
    pending = app_client.get("/api/auth/session").json()["invites"]
    assert [p["workspace_id"] for p in pending] == ["gh-7"]
    joined = app_client.post(f"/api/auth/invites/{invite_id}/accept").json()
    assert joined["role"] == "agent" and joined["workspace_id"] == "gh-7"
    me = app_client.get("/api/session", headers={"Authorization": "Bearer " + joined["token"]})
    assert me.json()["reviewer_id"] == "HUBOT" and me.json()["role"] == "agent"
    assert app_client.post(f"/api/auth/invites/{invite_id}/accept").status_code == 404
    team = app_client.get("/api/operations", headers=admin).json()["members"]
    assert {m["reviewer_id"] for m in team} == {"octocat", "HUBOT"}
    assert app_client.get("/api/auth/invites", headers=admin).json()["items"] == []

    # Members (agent role) cannot invite; admins can revoke pending invitations.
    agent = {"Authorization": "Bearer " + joined["token"]}
    assert (
        app_client.post("/api/auth/invites", json={"login": "x"}, headers=agent).status_code == 403
    )
    other = app_client.post("/api/auth/invites", json={"login": "someone"}, headers=admin).json()
    assert app_client.delete(f"/api/auth/invites/{other['id']}", headers=agent).status_code == 403
    assert app_client.delete(f"/api/auth/invites/{other['id']}", headers=admin).status_code == 200
