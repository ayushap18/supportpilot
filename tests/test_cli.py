"""The supportpilot CLI: table layout and one autopilot cycle against a fake API."""

from types import SimpleNamespace

from supportpilot import cli


def test_table_aligns_colored_cells(capsys, monkeypatch):
    monkeypatch.setattr(cli.S, "on", True)
    cli.table(["ID", "STATUS", "SUBJECT"], [("a", cli.tone("open"), "x"), ("bbb", "done", "y")])
    first, second = capsys.readouterr().out.splitlines()[1:]
    # The last column starts at the same visible offset despite the color codes in row one.
    assert cli.visible(first[: first.rindex("x")]) == cli.visible(second[: second.rindex("y")])


def test_autopilot_cycle_investigates_approves_fixes_and_opens_prs(monkeypatch):
    tickets = [
        {"id": "aaa111", "subject": "New", "status": "open", "investigation_state": None,
         "review_status": "none", "latest_outcome": None, "latest_investigation_id": None,
         "revision": 1},
        {"id": "bbb222", "subject": "Resolved draft", "status": "open",
         "investigation_state": "awaiting_review", "review_status": "pending",
         "latest_outcome": "resolved", "latest_investigation_id": "inv-b", "revision": 3},
        {"id": "ccc333", "subject": "Escalated", "status": "open",
         "investigation_state": "awaiting_review", "review_status": "pending",
         "latest_outcome": "escalate", "latest_investigation_id": "inv-c", "revision": 1},
    ]  # fmt: skip
    runs = [
        {"id": "run-pushed", "status": "completed", "ticket_id": "zzz",
         "artifacts": [{"kind": "branch", "label": "supportpilot/run-pushed (pushed)"}]},
    ]  # fmt: skip
    calls = []

    def api(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/queue":
            return {"items": tickets}
        if path.startswith("/investigations/inv-"):
            outcome = "resolved" if path.endswith("inv-b") else "escalate"
            ids = ["w:doc:1:0"] if outcome == "resolved" else []
            return {"id": path.rsplit("/", 1)[1], "draft_revision": 1,
                    "draft": {"outcome": outcome, "evidence_ids": ids}}  # fmt: skip
        if path.endswith("/investigations") and method == "POST":
            return {"state": "awaiting_review", "draft": {"outcome": "needs_information"}}
        if path == "/agents/runs" and method == "GET":
            return {"items": runs}
        if path == "/agents/runs" and method == "POST":
            runs.append({"id": "run-fix", "status": "queued", "ticket_id": "ccc333",
                         "artifacts": []})  # fmt: skip
            return runs[-1]
        if path.endswith("/pull-request"):
            return {"artifacts": [{"kind": "pull_request", "url": "https://github.com/t/a/pull/9"}]}
        return {}

    watched = []
    monkeypatch.setattr(cli.bridge, "watch", lambda repo, **k: watched.append((repo, k)))
    args = SimpleNamespace(no_approve=False, no_fix=False, agent="codex", max_per_cycle=3,
                           timeout=900, repository="/repo")  # fmt: skip
    cli.autopilot_cycle(api, args, "team/app")

    investigated = [c for c in calls if c[1] == "/tickets/aaa111/investigations"]
    assert investigated[0][2]["headers"]["Idempotency-Key"] == "autopilot-aaa111"
    reviews = [c for c in calls if c[1].endswith("/reviews")]
    assert [c[1] for c in reviews] == ["/investigations/inv-b/reviews"]  # Escalation not approved.
    assert reviews[0][2]["json"]["decision"] == "approve"
    patch = next(c for c in calls if c[0] == "PATCH")
    assert patch[1] == "/tickets/bbb222" and patch[2]["json"]["status"] == "resolved"
    fix = next(c for c in calls if c[0] == "POST" and c[1] == "/agents/runs")
    assert fix[2]["json"]["ticket_id"] == "ccc333" and fix[2]["json"]["allow_edits"] is True
    assert watched == [("/repo", {"allow_edits": True, "push": True, "timeout": 900, "once": True})]
    assert ("POST", "/github/agent-runs/run-pushed/pull-request", {}) in calls

    calls.clear()
    cli.autopilot_cycle(api, args, "team/app")  # A second cycle never queues a duplicate fix.
    assert not [c for c in calls if c[0] == "POST" and c[1] == "/agents/runs"]
