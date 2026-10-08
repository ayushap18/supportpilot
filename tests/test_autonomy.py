"""Earned autonomy: human agreement promotes a kind of draft to AUTO; one rejection demotes it."""

from fastapi.testclient import TestClient
from supportpilot.app import create_app
from supportpilot.policy import wilson_lower_bound
from test_workflow import run_ticket


def review(client, headers, inv, decision, kind="human"):
    return client.post(
        f"/api/investigations/{inv['id']}/reviews",
        headers=headers,
        json={"draft_revision": inv["draft_revision"], "decision": decision, "reviewer_kind": kind},
    )


def test_human_reviews_promote_and_one_rejection_demotes(settings, headers, ticket_input):
    assert wilson_lower_bound(20, 20) < 0.9 < wilson_lower_bound(40, 40)
    settings = settings.model_copy(
        update={"autonomy_workspaces": ["demo"], "autonomy_min_n": 3, "autonomy_min_lb": 0.4}
    )
    with TestClient(create_app(settings)) as client:
        run = iter(range(100))

        def draft():
            return run_ticket(client, headers, ticket_input, key=f"autonomy-{next(run)}")

        # The server refuses policy approvals until the bucket has earned AUTO.
        assert review(client, headers, draft(), "approve", kind="policy").status_code == 403

        for _ in range(3):
            inv = draft()
            assert inv["shadow_decision"] == "hold"
            review(client, headers, inv, "approve").raise_for_status()
        policy = client.get("/api/policy", headers=headers).json()
        assert policy["enabled"] is True
        [ladder] = policy["buckets"]
        assert (ladder["agreed"], ladder["n"], ladder["state"]) == (3, 3, "auto")
        assert ladder["key"].startswith("resolved · ")

        # The autopilot approves in AUTO; its own approval never counts as agreement.
        inv = draft()
        assert inv["shadow_decision"] == "approve"
        assert review(client, headers, inv, "approve", kind="policy").status_code == 201
        ticket = client.get(f"/api/tickets/{inv['ticket_id']}", headers=headers).json()
        client.patch(  # As the autopilot does after approving a resolved draft.
            f"/api/tickets/{inv['ticket_id']}",
            headers=headers,
            json={"expected_revision": ticket["revision"], "status": "resolved"},
        ).raise_for_status()
        [ladder] = client.get("/api/policy", headers=headers).json()["buckets"]
        assert (ladder["agreed"], ladder["n"], ladder["state"]) == (3, 3, "auto")

        # A human overrules that policy approval: the bucket drops to SHADOW at once.
        assert review(client, headers, inv, "reject").status_code == 201
        assert [
            r["reviewer_kind"]
            for r in client.get(f"/api/investigations/{inv['id']}/reviews", headers=headers).json()
        ] == ["human"]
        assert review(client, headers, inv, "approve").status_code == 409
        [ladder] = client.get("/api/policy", headers=headers).json()["buckets"]
        assert (ladder["agreed"], ladder["n"], ladder["state"]) == (3, 4, "shadow")
        mission = client.get("/api/mission", headers=headers).json()
        assert mission["autonomy"]["buckets"] == [ladder]
        assert mission["inbox"][0]["kind"] == "autonomy_demoted"
        assert review(client, headers, draft(), "approve", kind="policy").status_code == 403

        # A rejection while already SHADOW is no second demotion.
        review(client, headers, draft(), "reject").raise_for_status()
        mission = client.get("/api/mission", headers=headers).json()
        assert [i["kind"] for i in mission["inbox"]].count("autonomy_demoted") == 1

        # Off by default for every other workspace.
        other = {"Authorization": "Bearer test-other-token-at-least-24-characters"}
        assert client.get("/api/policy", headers=other).json()["enabled"] is False
