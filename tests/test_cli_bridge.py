import json
import subprocess
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
    reports, logs = [], []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=proposal)
        body = json.loads(request.content)
        if request.url.path.endswith("/claim"):
            return httpx.Response(200, json={**proposal, "lease": "x" * 40})
        if request.url.path.endswith("/log"):
            logs.extend(body["lines"])
            return httpx.Response(200, json={"lines": len(logs)})
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

    def fake_execute(args, task, cwd, timeout, on_output=None):
        assert "Webhook broken" in task and "workspace-write" in args
        assert cwd != repository
        on_output(b'{"type":"item.started","item":{"type":"command_execution","command":"ls"}}\n')
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
    assert logs[0].startswith("Claimed by ")
    assert "item.started: ls" in logs
    assert logs[-1] == "Finished with exit code 0"
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


def test_denied_headless_actions_are_named():
    output = json.dumps(
        {
            "event": "result",
            "result": {
                "status": "SUCCESS",
                "response": "",
                "denied_actions": [{"action": "command", "display_name": "RunCommand"}],
            },
        }
    )
    assert bridge.parse_output("antigravity", output)[0] == ""
    assert bridge.denied_actions(output) == ["RunCommand"]
    assert bridge.denied_actions('{"type":"turn.completed"}') == []


def test_watch_runs_eligible_queue_items_once(tmp_path, monkeypatch):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "remote", "add", "origin", "https://github.com/team/app"],
        check=True,
    )
    queue = [
        {
            "id": "r-other",
            "status": "queued",
            "provider": "codex",
            "repository_full_name": "team/other",
        },
        {"id": "r-edit", "status": "queued", "provider": "antigravity"},
        {"id": "r-done", "status": "completed", "provider": "codex"},
        {"id": "r-ok", "status": "queued", "provider": "codex", "repository_full_name": "team/app"},
    ]
    beats = []

    def handler(request):
        if request.url.path.endswith("/heartbeat"):
            beats.append(json.loads(request.content))
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"items": queue})

    real_client = httpx.Client
    monkeypatch.setenv("SUPPORTPILOT_WORKSPACE_TOKEN", "token")
    monkeypatch.setattr(
        bridge.httpx,
        "Client",
        lambda **kw: real_client(**kw, transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/bin/" + name)
    started = []
    monkeypatch.setattr(
        bridge,
        "run_bridge",
        lambda run_id, root, edits, timeout, push, **kw: started.append((run_id, edits, push)),
    )
    assert bridge.watch(repository, once=True) == 0
    # Read-only runner: other repositories and edit-requiring runs are skipped.
    assert started == [("r-ok", False, False)]
    assert beats[0]["repository_full_name"] == "team/app" and beats[0]["allow_edits"] is False
    started.clear()
    assert bridge.watch(repository, allow_edits=True, push=True, once=True) == 0
    assert started == [("r-ok", False, False), ("r-edit", True, True)]


def test_watch_stops_on_rejected_token(tmp_path, monkeypatch, capsys):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    real_client = httpx.Client
    monkeypatch.setenv("SUPPORTPILOT_WORKSPACE_TOKEN", "wrong")
    monkeypatch.setattr(
        bridge.httpx,
        "Client",
        lambda **kw: real_client(
            **kw, transport=httpx.MockTransport(lambda request: httpx.Response(401))
        ),
    )
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/bin/" + name)
    assert bridge.watch(repository) == 1  # Stops instead of retrying forever.
    assert "token rejected (HTTP 401)" in capsys.readouterr().out


def test_login_saves_token_privately_and_watch_finds_it(tmp_path, monkeypatch, capsys):
    import stat

    monkeypatch.setenv("SUPPORTPILOT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("SUPPORTPILOT_WORKSPACE_TOKEN", raising=False)
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "remote", "add", "origin", "https://github.com/team/app"],
        check=True,
    )
    tokens = {"sp_good": {"workspace_id": "gh-1", "label": "team/app"}}
    seen = []

    def handler(request):
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        seen.append(token)
        if token not in tokens:
            return httpx.Response(401)
        if request.url.path == "/api/session":
            return httpx.Response(200, json=tokens[token])
        if request.url.path.endswith("/heartbeat"):
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"items": []})

    real_client = httpx.Client
    monkeypatch.setattr(
        bridge.httpx,
        "Client",
        lambda **kw: real_client(**kw, transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/bin/" + name)
    with pytest.raises(ValueError, match="No saved token"):
        bridge.watch(repository, once=True)

    monkeypatch.setattr("getpass.getpass", lambda prompt: "sp_bad")
    assert bridge.login(repository) == 1 and not bridge.credentials_file().exists()

    monkeypatch.setattr("getpass.getpass", lambda prompt: " sp_good\n")
    assert bridge.login(repository) == 0
    mode = stat.S_IMODE(bridge.credentials_file().stat().st_mode)
    assert mode == 0o600 and "sp_good" not in capsys.readouterr().out

    seen.clear()
    assert bridge.watch(repository, once=True) == 0
    assert set(seen) == {"sp_good"}  # The saved token was used, no prompt needed.

    other = tmp_path / "other"
    other.mkdir()
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    subprocess.run(
        ["git", "-C", str(other), "remote", "add", "origin", "https://github.com/team/site"],
        check=True,
    )
    assert bridge.login(other) == 1  # Token for team/app refused for team/site.
    bridge.logout(repository)
    assert bridge.stored_tokens("http://127.0.0.1:8000") == {}


def red_green_run(tmp_path, monkeypatch, agent):
    """A codex fix run on a ticket, with a stub agent; returns the submitted report."""
    repository = tmp_path / "repo"
    repository.mkdir()
    for args in (["init"], ["config", "user.name", "T"], ["config", "user.email", "t@e.com"]):
        bridge.git(repository, *args)
    (repository / "app.py").write_text("def add(a, b):\n    return a - b\n")
    bridge.git(repository, "add", ".")
    bridge.git(repository, "commit", "-m", "Initial")
    proposal = {"id": str(uuid4()), "status": "queued", "provider": "codex",
                "task": "Fix the ticket", "ticket_context": {"subject": "add() bug"}}  # fmt: skip
    reports = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=proposal)
        if request.url.path.endswith("/claim"):
            return httpx.Response(200, json={**proposal, "lease": "x" * 40})
        if request.url.path.endswith("/complete"):
            reports.append(json.loads(request.content))
        return httpx.Response(200, json={"status": "completed", "lines": 1})

    real_client = httpx.Client
    monkeypatch.setenv("SUPPORTPILOT_WORKSPACE_TOKEN", "token")
    monkeypatch.setattr(
        bridge.httpx,
        "Client",
        lambda **kw: real_client(**kw, transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/fake/" + name)
    monkeypatch.setattr(bridge.tempfile, "mkdtemp", lambda **kw: str(tmp_path / "run"))
    real_execute = bridge.execute

    def fake_execute(args, task, cwd, timeout, on_output=None, env=None):
        if args[:2] == ["codex", "sandbox"]:  # The runner's test command, in the agent sandbox.
            assert set(env) <= {"PATH", "TMPDIR", "LANG", "HOME"} and "-P" in args
            return real_execute(args[args.index("--") + 1 :], task, cwd, timeout)
        agent(task, cwd)
        done = {"type": "item.completed", "item": {"type": "agent_message", "text": "Done"}}
        return 0, json.dumps(done) + '\n{"type":"turn.completed"}'

    monkeypatch.setattr(bridge, "execute", fake_execute)
    # The test command comes from the checkout's .supportpilot.toml, never from the server.
    (repository / ".supportpilot.toml").write_text(
        f'[tests]\ncommand = "{sys.executable} -m pytest -q -p no:cacheprovider"\n'
    )
    bridge.run_bridge(proposal["id"], repository, allow_edits=True)
    return reports[0]


def test_red_before_green_fix_run(tmp_path, monkeypatch):
    def agent(task, cwd):
        if task.startswith("Phase 1"):
            (cwd / "tests").mkdir()
            (cwd / "tests" / "test_add.py").write_text(
                "from app import add\n\ndef test_add():\n    assert add(2, 2) == 4\n"
            )
        else:
            assert "Phase 2 of 2" in task
            (cwd / "app.py").write_text("def add(a, b):\n    return a + b\n")

    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")  # Same-size edits within a second.
    report = red_green_run(tmp_path, monkeypatch, agent)
    assert report["error"] is None and report["exit_code"] == 0, report["result"]
    tests = [a for a in report["artifacts"] if a["kind"] == "test_report"]
    assert [a["label"] for a in tests] == ["baseline (HEAD)", "repro (red)", "fix (green)"]
    assert "1 failed" in tests[1]["detail"] and "1 passed" in tests[2]["detail"]


@pytest.mark.parametrize(
    "tamper",
    [
        "git add -A",  # Staged edits are invisible to a plain `git diff`.
        "git commit -qam fix",
        "git rm -qf tests/test_add.py",
    ],
)
def test_fix_phase_cannot_rewrite_the_reproduction(tmp_path, monkeypatch, tamper):
    def agent(task, cwd):
        if task.startswith("Phase 1"):
            (cwd / "tests").mkdir()
            (cwd / "tests" / "test_add.py").write_text(
                "from app import add\n\ndef test_add():\n    assert add(2, 2) == 4\n"
            )
        else:
            (cwd / "tests" / "test_add.py").write_text("def test_add():\n    assert True\n")
            subprocess.run(tamper.split(), cwd=cwd, check=True)

    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    report = red_green_run(tmp_path, monkeypatch, agent)
    assert report["error"] == "Fix phase edited tests or test config: tests/test_add.py"


def test_fix_phase_cannot_deselect_the_reproduction(tmp_path, monkeypatch):
    def agent(task, cwd):
        if task.startswith("Phase 1"):
            (cwd / "tests").mkdir()
            (cwd / "tests" / "test_add.py").write_text(
                "from app import add\n\ndef test_add():\n    assert add(2, 2) == 4\n"
            )
        else:  # A root conftest.py is not a test path, but it can hide the failing test.
            (cwd / "conftest.py").write_text(
                "def pytest_collection_modifyitems(items):\n    items.clear()\n"
            )

    report = red_green_run(tmp_path, monkeypatch, agent)
    assert report["error"] == "Fix phase edited tests or test config: conftest.py"


def test_a_test_that_already_passes_is_not_a_reproduction(tmp_path, monkeypatch):
    def agent(task, cwd):
        (cwd / "tests").mkdir(exist_ok=True)
        (cwd / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n")

    report = red_green_run(tmp_path, monkeypatch, agent)
    assert report["error"].startswith("not_reproduced") and report["exit_code"] == 1
    assert "branch" in [a["kind"] for a in report["artifacts"]]


def test_reproduction_phase_may_only_touch_tests(tmp_path, monkeypatch):
    report = red_green_run(
        tmp_path, monkeypatch, lambda task, cwd: (cwd / "app.py").write_text("x = 1\n")
    )
    assert report["error"] == "not_reproduced: phase 1 changed non-test files: app.py"
    assert bridge.is_test_path("src/__tests__/a.ts") and bridge.is_test_path("pkg/x_test.go")
    assert not bridge.is_test_path("src/testing.py")
