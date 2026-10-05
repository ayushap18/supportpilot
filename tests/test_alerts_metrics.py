"""Slack alerts are best effort; outcome metrics come only from recorded data."""

import httpx
from pydantic import SecretStr


def test_review_ready_alert_and_metrics(client, headers, ticket_input, settings, monkeypatch):
    sent = []

    def post(url, json, timeout):
        sent.append((url, json["text"]))
        if len(sent) > 1:
            raise httpx.ConnectError("Slack down")
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr("supportpilot.notifications.httpx.post", post)
    empty = client.get("/api/operations", headers=headers).json()["metrics"]
    assert empty["approval_rate"] is None and empty["median_first_draft_minutes"] is None

    ticket = client.post("/api/tickets", json=ticket_input, headers=headers).json()
    path = "/api/tickets/" + ticket["id"] + "/investigations"
    run = client.post(path, headers={**headers, "Idempotency-Key": "alert-one"}).json()
    assert run["state"] == "awaiting_review"
    assert sent == []  # No webhook configured: nothing is sent.

    settings.slack_webhook_url = SecretStr("https://hooks.slack.com/services/T/B/x")
    second = client.post(path, headers={**headers, "Idempotency-Key": "alert-two"})
    assert sent[0][0].startswith("https://hooks.slack.com/")
    assert "draft ready for review" in sent[0][1] and ticket_input["subject"] in sent[0][1]
    # A failing webhook never fails the investigation.
    third = client.post(path, headers={**headers, "Idempotency-Key": "alert-three"})
    assert third.status_code == 200 and len(sent) == 2

    review = {"draft_revision": 1, "decision": "approve"}
    assert client.post(
        f"/api/investigations/{second.json()['id']}/reviews", json=review, headers=headers
    ).status_code in (200, 201)
    metrics = client.get("/api/operations", headers=headers).json()["metrics"]
    assert metrics["approval_rate"] == 1.0 and metrics["reviews"] == 1
    assert metrics["drafted_tickets"] == 1 and metrics["median_first_draft_minutes"] >= 0
    assert metrics["resolved_tickets"] == 0 and metrics["median_resolution_hours"] is None


def test_slack_url_must_be_a_slack_webhook():
    import pytest
    from supportpilot.config import Settings

    with pytest.raises(ValueError, match="hooks.slack.com"):
        Settings(_env_file=None, slack_webhook_url="https://evil.example/hook")
