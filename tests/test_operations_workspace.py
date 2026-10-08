from datetime import UTC, datetime, timedelta
from uuid import uuid4

from conftest import OTHER_TOKEN
from supportpilot.schemas import Ticket
from supportpilot.storage import TicketRow


def test_queue_totals_beyond_legacy_cap_and_utc_trends(client, headers, ticket_input):
    database = client.app.state.database
    with database.session() as session:
        for index in range(105):
            ticket = Ticket(
                **ticket_input,
                id=str(uuid4()),
                workspace_id="demo",
                created_at=datetime.now(UTC) - timedelta(days=1 if index < 5 else 0),
                status="waiting" if index < 5 else "open",
            )
            session.add(
                TicketRow(id=ticket.id, workspace_id="demo", payload=ticket.model_dump(mode="json"))
            )
        session.commit()
    assert len(client.get("/api/tickets", headers=headers).json()) == 100
    queue = client.get("/api/queue?page=5&page_size=25", headers=headers).json()
    assert queue["total"] == 105 and len(queue["items"]) == 5
    operations = client.get("/api/operations", headers=headers).json()
    assert operations["counts"]["tickets"] == 105
    assert operations["counts"]["waiting"] == 5
    assert len(operations["trends"]) == 7
    assert operations["trends"][-1]["tickets"] == 100
    assert operations["trends"][-2]["tickets"] == 5
    assert operations["trends"][0]["tickets"] == 0
    assert operations["members"] == [{"reviewer_id": "alice", "role": "admin"}]
    assert operations["tool_mode"] == "synthetic"


def test_ticket_edits_notes_scope_and_revision(client, headers, ticket_input):
    ticket = client.post("/api/tickets", headers=headers, json=ticket_input).json()
    path = "/api/tickets/" + ticket["id"]
    other = {"Authorization": "Bearer " + OTHER_TOKEN}
    assert (
        client.patch(
            path, headers=other, json={"expected_revision": 1, "priority": "urgent"}
        ).status_code
        == 404
    )
    assert client.get(path + "/notes", headers=other).status_code == 404
    assert (
        client.post(
            path + "/notes", headers=other, json={"body": "Cross workspace note"}
        ).status_code
        == 404
    )
    assert (
        client.patch(
            path, headers=headers, json={"expected_revision": 1, "assignee": "bob"}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            path, headers=headers, json={"expected_revision": 1, "subject": None}
        ).status_code
        == 422
    )
    changed = client.patch(
        path,
        headers=headers,
        json={
            "expected_revision": 1,
            "priority": "urgent",
            "status": "in_progress",
            "assignee": "alice",
        },
    ).json()
    assert changed["revision"] == 2
    assert (
        client.patch(
            path, headers=headers, json={"expected_revision": 1, "status": "resolved"}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            path, headers=headers, json={"expected_revision": 2, "status": "in_progress"}
        ).json()["revision"]
        == 2
    )
    assert client.post(path + "/notes", headers=headers, json={"body": "   "}).status_code == 422
    note = client.post(path + "/notes", headers=headers, json={"body": "Need customer logs"}).json()
    assert note["author_id"] == "alice"
    assert client.get(path + "/notes", headers=headers).json() == [note]
    queue = client.get(
        "/api/queue?priority=urgent&status=in_progress&search=migration", headers=headers
    ).json()
    assert queue["total"] == 1
    assert client.get("/api/queue?priority=low", headers=headers).json()["total"] == 0
    activity = client.get("/api/operations", headers=headers).json()["activity"]
    assert {event["kind"] for event in activity} >= {
        "ticket_created",
        "ticket_updated",
        "note_added",
    }


def test_latest_investigation_and_stale_review(client, headers, ticket_input):
    ticket = client.post("/api/tickets", headers=headers, json=ticket_input).json()
    path = "/api/tickets/" + ticket["id"]
    inv = client.post(
        path + "/investigations", headers={**headers, "Idempotency-Key": "operation-first"}
    ).json()
    assert inv["ticket_revision"] == 1
    assert client.get("/api/queue?review=pending", headers=headers).json()["total"] == 1
    client.patch(path, headers=headers, json={"expected_revision": 1, "status": "in_progress"})
    assert client.get("/api/queue?review=pending", headers=headers).json()["total"] == 0
    assert client.get("/api/queue", headers=headers).json()["items"][0]["review_status"] == "stale"
    assert (
        client.post(
            "/api/investigations/" + inv["id"] + "/reviews",
            headers=headers,
            json={"draft_revision": 1, "decision": "approve"},
        ).status_code
        == 409
    )
    latest = client.post(
        path + "/investigations", headers={**headers, "Idempotency-Key": "operation-second"}
    ).json()
    assert latest["ticket_revision"] == 2
    assert (
        client.post(
            "/api/investigations/" + latest["id"] + "/reviews",
            headers=headers,
            json={"draft_revision": 1, "decision": "approve"},
        ).status_code
        == 201
    )
    queue = client.get("/api/queue", headers=headers).json()["items"][0]
    assert queue["review_status"] == "approved" and queue["status"] == "in_progress"
    operations = client.get("/api/operations", headers=headers).json()
    assert operations["counts"]["awaiting_review"] == 0
    assert operations["trends"][-1]["investigations"] == 2
    assert operations["trends"][-1]["approved"] == 1


def test_mid_investigation_edit_cannot_approve_old_context(
    client, headers, ticket_input, monkeypatch
):
    import supportpilot.app as app_module

    original = app_module.investigate

    async def edit_during_investigation(ticket, investigation, *args, **kwargs):
        with client.app.state.database.session() as session:
            row = session.get(TicketRow, ticket.id)
            row.payload = {**row.payload, "revision": 2, "description": "Changed customer context."}
            session.commit()
        return await original(ticket, investigation, *args, **kwargs)

    monkeypatch.setattr(app_module, "investigate", edit_during_investigation)
    ticket = client.post("/api/tickets", headers=headers, json=ticket_input).json()
    inv = client.post(
        "/api/tickets/" + ticket["id"] + "/investigations",
        headers={**headers, "Idempotency-Key": "mid-investigation-edit"},
    ).json()
    assert inv["ticket_revision"] == 1
    assert (
        client.post(
            "/api/investigations/" + inv["id"] + "/reviews",
            headers=headers,
            json={"draft_revision": 1, "decision": "approve"},
        ).status_code
        == 409
    )


def test_live_application_disables_synthetic_tools(client, headers, ticket_input, monkeypatch):
    import supportpilot.app as app_module

    observed = []

    async def observe_invocation(ticket, investigation, *args, **kwargs):
        observed.append(kwargs["allow_tools"])
        investigation.state = "failed"
        investigation.error = "Stubbed live provider for route contract test"
        return investigation

    monkeypatch.setattr(app_module, "investigate", observe_invocation)
    client.app.state.settings.mode = "live"
    ticket = client.post("/api/tickets", headers=headers, json=ticket_input).json()
    result = client.post(
        "/api/tickets/" + ticket["id"] + "/investigations",
        headers={**headers, "Idempotency-Key": "live-disables-tools"},
    )
    assert result.status_code == 200 and observed == [False]
    assert client.get("/api/examples", headers=headers).json() == []
    assert client.get("/api/operations", headers=headers).json()["tool_mode"] == "disabled"


def test_review_decision_survives_later_ticket_edits(client, headers, ticket_input):
    ticket = client.post("/api/tickets", headers=headers, json=ticket_input).json()
    inv = client.post(
        "/api/tickets/" + ticket["id"] + "/investigations",
        headers={**headers, "Idempotency-Key": "review-then-resolve"},
    ).json()
    client.post(
        f"/api/investigations/{inv['id']}/reviews",
        headers=headers,
        json={"draft_revision": 1, "decision": "approve"},
    )
    client.patch(
        "/api/tickets/" + ticket["id"],
        headers=headers,
        json={"expected_revision": ticket["revision"], "status": "resolved"},
    )
    item = client.get("/api/queue", headers=headers).json()["items"][0]
    assert item["status"] == "resolved" and item["review_status"] == "approved"
