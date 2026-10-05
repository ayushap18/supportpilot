"""Mission Control summarizes stored work; reviews and context packs stay traceable."""

from datetime import UTC, datetime, timedelta

from supportpilot.agent_storage import AgentRunRow


def test_mission_pipeline_queue_review_and_context(client, headers, ticket_input):
    doc = client.post(
        "/api/knowledge/documents",
        json={"title": "Retry policy", "body": "Webhook retries back off exponentially."},
        headers=headers,
    )
    assert doc.status_code == 201, doc.text
    doc_id = doc.json()["id"]
    ticket = client.post("/api/tickets", json=ticket_input, headers=headers).json()

    missing = {"provider": "codex", "task": "Investigate retries", "knowledge_ids": ["nope"]}
    assert client.post("/api/agents/runs", json=missing, headers=headers).status_code == 404
    body = {
        "provider": "codex",
        "task": "Investigate webhook retries\nDetails",
        "ticket_id": ticket["id"],
        "knowledge_ids": [doc_id],
    }
    run = client.post("/api/agents/runs", json=body, headers=headers).json()
    assert run["context_docs"][0]["title"] == "Retry policy"
    assert "exponentially" in run["context_docs"][0]["excerpt"]

    mission = client.get("/api/mission", headers=headers).json()
    assert mission["pipeline"]["queued"] == 1
    kinds = {item["kind"] for item in mission["work_queue"]}
    assert "unassigned" in kinds and "stuck_run" not in kinds
    assert mission["reliability"]["success_rate"] is None  # Nothing finished yet.
    assert {d["title"]: d["status"] for d in mission["knowledge"]}["Retry policy"] == "local"

    # Simulate a stale queued run and a completed one, as a runner would leave them.
    app_db = client.app.state.database
    with app_db.session() as session:
        row = session.get(AgentRunRow, run["id"])
        old = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        row.payload = {**row.payload, "created_at": old}
        session.commit()
    stuck = client.get("/api/mission", headers=headers).json()
    assert stuck["reliability"]["stuck"] == 1
    with app_db.session() as session:
        row = session.get(AgentRunRow, run["id"])
        row.status = "completed"
        row.payload = {
            **row.payload,
            "status": "completed",
            "completed_at": datetime.now(UTC).isoformat(),
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }
        session.commit()
    done = client.get("/api/mission", headers=headers).json()
    assert done["pipeline"]["awaiting_review"] == 1
    assert done["reliability"]["success_rate"] == 1.0
    assert done["reliability"]["token_coverage"] == 1.0
    assert done["reliability"]["by_provider"]["codex"]["completed"] == 1
    assert any(i["kind"] == "review_run" for i in done["work_queue"])

    review = {
        "decision": "accepted",
        "tests_before": "test_retry FAILED",
        "tests_after": "test_retry passed",
        "note": "Verified locally",
        "customer_confirmed": True,
    }
    path = f"/api/agents/runs/{run['id']}/review"
    reviewed = client.post(path, json=review, headers=headers).json()["review"]
    assert reviewed["customer_confirmed"] is True and reviewed["reviewer_id"] == "alice"
    after = client.get("/api/mission", headers=headers).json()
    assert after["pipeline"]["accepted"] == 1 and after["pipeline"]["awaiting_review"] == 0
    assert not any(i["kind"] == "review_run" for i in after["work_queue"])
    queued = client.post(
        "/api/agents/runs", json={"provider": "codex", "task": "Another task here"}, headers=headers
    ).json()
    blocked = client.post(f"/api/agents/runs/{queued['id']}/review", json=review, headers=headers)
    assert blocked.status_code == 409
