"""Replay evals: human reviews become frozen, deterministic regression cases."""

import asyncio

from supportpilot.agreement import AUTOPILOT_NOTE
from test_workflow import run_ticket

from evals import from_reviews


def review(client, headers, payload, decision, note="", key="replay-key", kind="human"):
    inv = run_ticket(client, headers, payload, key=key)
    client.post(
        f"/api/investigations/{inv['id']}/reviews",
        headers=headers,
        json={
            "draft_revision": inv["draft_revision"],
            "decision": decision,
            "note": note,
            "reviewer_kind": kind,
        },
    ).raise_for_status()
    return inv


def test_reviews_replay_with_recorded_tools_and_gate(
    client, headers, settings, tmp_path, monkeypatch
):
    monkeypatch.setattr(from_reviews, "RUNS", tmp_path)
    account = {
        "subject": "Account rate limit",
        "description": "We get 429 RATE_LIMIT. What is our limit? token=supersecretvalue",
        "product_version": "v2",
        "account_id": "acct_pro",
    }
    auth = {
        "subject": "API v2 rejects my API key",
        "description": "API v2 returns 401 MISSING_BEARER with X-API-Key.",
        "product_version": "v2",
    }
    review(client, headers, account, "approve", key="replay-a")
    review(client, headers, auth, "reject", key="replay-b")
    review(
        client,
        headers,
        {**auth, "subject": "Auth again"},
        "approve",
        AUTOPILOT_NOTE,
        key="replay-c",
    )
    # A policy review with an ordinary note is still not a human verdict.
    review(
        client, headers, {**auth, "subject": "Auth thrice"}, "approve", "ok", "replay-d", "policy"
    )

    database = client.app.state.database
    cases = from_reviews.export_cases(database)
    assert [case["decision"] for case in cases] == ["reject", "approve"]  # Bot review excluded.
    assert "supersecretvalue" not in str(cases)
    assert cases[1]["replay"]["tool_results"][0]["result"]["status"] == "ok"

    # Live tools are gone: the account answer must come from the recorded result.
    client.app.state.tools.errors["get_account_status"] = True
    report, failure = asyncio.run(from_reviews.run(database, settings, fail_below="last"))
    rows = {row["decision"]: row for row in report["cases"]}
    assert rows["approve"]["agrees"] and rows["approve"]["actual_outcome"] == "resolved"
    assert not rows["reject"]["agrees"]  # Replay repeats the outcome the human rejected.
    assert report["summary"]["approval_agreement"] == 0.5 and failure is None

    report, failure = asyncio.run(from_reviews.run(database, settings, fail_below=0.9))
    assert failure and report["flipped"] == [] and not report["passed"]
    assert len(list(tmp_path.glob("*.json"))) == 2
    # The failed run is saved but never becomes the `last` baseline.
    assert from_reviews.latest_run()["passed"]
