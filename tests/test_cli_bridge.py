import json
import sys
from uuid import uuid4

import httpx
import pytest
from supportpilot import cli_bridge as bridge


def test_provider_arguments_and_repository_validation():
    with pytest.raises(ValueError):
        bridge.command("codex", model="--dangerously-skip-permissions")
    codex = bridge.command("codex")
    assert codex[codex.index("--sandbox") + 1] == "read-only"
    assert "workspace-write" in bridge.command("codex", allow_edits=True)
    claude = bridge.command("claude_code")
    assert "Read,Glob,Grep" in claude and "--restricted" in claude
    with pytest.raises(ValueError):
        bridge.command("claude_code", allow_edits=True)
    with pytest.raises(ValueError):
        bridge.command("antigravity")
    assert "--sandbox" in bridge.command("antigravity", allow_edits=True)
    with pytest.raises(ValueError):
        bridge.command("custom")
    for remote in (
        "git@github.com:Owner/Repo.git",
        "https://github.com/Owner/Repo",
        "ssh://git@github.com/Owner/Repo.git",
    ):
        assert bridge.github_repository(remote) == "owner/repo"
    assert bridge.github_repository("https://github.com.evil/owner/repo") is None
    assert bridge.github_repository("https://token@github.com/owner/repo") is None


def test_provider_usage_parsers_report_only_explicit_usage():
    events = [
        {"type": "item.completed", "item": {"type": "agent_message", "text": "Checked files"}},
        {"type": "turn.completed", "usage": {"input_tokens": 9, "output_tokens": 2}},
        {"type": "turn.completed", "usage": {"input_tokens": 5, "cached_input_tokens": 3}},
    ]
    text, usage = bridge.parse_output("codex", "\n".join(map(json.dumps, events)))
    assert text == "Checked files"
    assert usage == {"input_tokens": 14, "output_tokens": 2, "cached_input_tokens": 3}
    text, usage = bridge.parse_output(
        "claude_code",
        json.dumps(
            {
                "type": "result",
                "result": "OK",
                "usage": {"input_tokens": 10, "output_tokens": 3},
                "total_cost_usd": 0.01,
            }
        ),
    )
    assert usage["cost_usd"] == 0.01
    envelope = {
        "event": "result",
        "result": {
            "status": "SUCCESS",
            "response": "OK",
            "usage": {"input_tokens": 4, "output_tokens": 2, "cache_read_tokens": 1},
        },
    }
    assert bridge.parse_output("antigravity", json.dumps(envelope)) == (
        "OK",
        {"input_tokens": 4, "output_tokens": 2, "cached_input_tokens": 1},
    )
    assert bridge.parse_output("antigravity", '{"status":"ERROR","response":"Bad"}') == ("", {})
    assert bridge.parse_output("codex", "malformed output") == ("", {})
    assert bridge.parse_output(
        "claude_code", json.dumps({"type": "result", "is_error": True, "result": "Failed"})
    ) == ("", {})


def test_process_stdin_is_data_and_service_secrets_not_forwarded(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPPORTPILOT_WORKSPACE_TOKEN", "private-service-token")
    script = (
        "import sys,os; print(sys.stdin.read()); "
        "print('SUPPORTPILOT_WORKSPACE_TOKEN' in os.environ)"
    )
    task = "$(touch should-not-exist); `echo secret`" + "a" * 100000
    code, output = bridge.execute([sys.executable, "-c", script], task, tmp_path, timeout=3)
    assert code == 0 and task in output and output.endswith("False\n")
    assert not (tmp_path / "should-not-exist").exists()


def test_timeout_and_output_bounds(tmp_path, monkeypatch):
    with pytest.raises(TimeoutError):
        bridge.execute([sys.executable, "-c", "import time; time.sleep(10)"], "task", tmp_path, 0.1)
    monkeypatch.setattr(bridge, "OUTPUT_LIMIT", 100)
    with pytest.raises(RuntimeError):
        bridge.execute([sys.executable, "-c", "print('x'*1000)"], "task", tmp_path, 3)


def test_manual_bridge_claim_report_and_isolated_worktree(tmp_path, monkeypatch):
    repository = tmp_path / "repo"
    repository.mkdir()
    for args in (
        ["init"],
        ["config", "user.name", "Test"],
        ["config", "user.email", "t@example.com"],
    ):
        bridge.git(repository, *args)
    (repository / "README.md").write_text("Original content")
    bridge.git(repository, "add", "README.md")
    bridge.git(repository, "commit", "-m", "Initial")
    bridge.git(repository, "remote", "add", "origin", "https://github.com/owner/repo.git")
    run_id = str(uuid4())
    proposal = {
        "id": run_id,
        "status": "queued",
        "provider": "codex",
        "task": "Inspect and propose a fix",
        "repository_full_name": "owner/repo",
        "ticket_context": {"subject": "Webhook broken", "revision": 2},
    }
    reports = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=proposal)
        body = json.loads(request.content)
        if request.url.path.endswith("/claim"):
            return httpx.Response(200, json={**proposal, "lease": "x" * 40})
        reports.append(body)
        return httpx.Response(200, json={"status": "completed"})

    real_client = httpx.Client
    monkeypatch.setenv("SUPPORTPILOT_WORKSPACE_TOKEN", "token")
    monkeypatch.setattr(
        bridge.httpx,
        "Client",
        lambda **kw: real_client(**kw, transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/fake/" + name)
    monkeypatch.setattr(bridge.tempfile, "mkdtemp", lambda **kw: str(tmp_path / "run"))
    (tmp_path / "run").mkdir()

    def fake_execute(args, task, cwd, timeout):
        assert "Webhook broken" in task and "workspace-write" in args
        assert cwd != repository
        (cwd / "README.md").write_text("Proposed change")
        return 0, json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "Proposed change; no tests run"},
            }
        ) + '\n{"type":"turn.completed"}'

    monkeypatch.setattr(bridge, "execute", fake_execute)
    assert bridge.run_bridge(run_id, repository, allow_edits=True) == 0
    assert (repository / "README.md").read_text() == "Original content"
    assert reports[0]["artifacts"][0]["kind"] == "branch"
    assert reports[0]["usage"] == {}
    proposal["repository_full_name"] = "different/repo"
    with pytest.raises(ValueError, match="origin"):
        bridge.run_bridge(run_id, repository)


@pytest.mark.parametrize(
    "provider,output",
    [
        ("codex", '{"type":"item.completed","item":{"type":"agent_message","text":"OK"}}'),
        ("codex", '{"type":"turn.completed"}\n{"type":"turn.failed"}'),
        ("claude_code", '{"type":"result","is_error":true,"result":"Bad"}'),
        ("antigravity", '{"event":"result","result":{"status":"INTERRUPTED"}}'),
    ],
)
def test_final_text_or_zero_exit_does_not_override_provider_failure(provider, output):
    assert bridge.output_failed(provider, output)
