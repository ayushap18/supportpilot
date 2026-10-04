import asyncio

from supportpilot.schemas import Draft, ModelStep, Usage


def run_ticket(client, headers, payload, key="workflow-test-key"):
    ticket = client.post("/api/tickets", headers=headers, json=payload).json()
    return client.post(
        "/api/tickets/" + ticket["id"] + "/investigations",
        headers={**headers, "Idempotency-Key": key},
    ).json()


def test_grounded_draft(client, headers, ticket_input):
    result = run_ticket(client, headers, ticket_input)
    assert result["state"] == "awaiting_review"
    assert result["draft"]["outcome"] == "resolved"
    assert "Bearer" in result["draft"]["response"]
    assert set(result["draft"]["evidence_ids"]) <= {e["id"] for e in result["evidence"]}
    saved = client.get("/api/investigations/" + result["id"], headers=headers)
    assert saved.json() == result


def test_missing_version_and_unsupported_request(client, headers):
    missing = run_ticket(
        client,
        headers,
        {"subject": "Authentication fails", "description": "We receive 401 on our API request."},
    )
    assert missing["draft"]["outcome"] == "needs_information"
    assert missing["draft"]["missing_information"]
    unsupported = run_ticket(
        client,
        headers,
        {
            "subject": "Refund requested",
            "description": "Please refund my entire subscription invoice.",
        },
    )
    assert unsupported["draft"]["outcome"] == "escalate"


def test_invalid_citations_fail_closed(client, headers, ticket_input):
    async def invalid(*args, **kwargs):
        return ModelStep(
            summary="Draft",
            tool_calls=[],
            draft=Draft(
                outcome="resolved",
                response="Unsupported fix",
                missing_information=[],
                evidence_ids=["invented-source"],
            ),
        ), Usage(model_rounds=1)

    client.app.state.provider.step = invalid
    result = run_ticket(client, headers, ticket_input)
    assert result["state"] == "failed" and result["draft"] is None


def test_total_timeout(client, headers, ticket_input):
    async def slow(*args, **kwargs):
        await asyncio.sleep(1)

    client.app.state.settings.timeout_seconds = 0.01
    client.app.state.provider.step = slow
    result = run_ticket(client, headers, ticket_input)
    assert result["state"] == "failed"
    assert "time budget" in result["error"]
