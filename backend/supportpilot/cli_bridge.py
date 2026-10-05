"""Manual local CLI runner. Server proposals never select shell commands."""

import argparse
import json
import os
import re
import selectors
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import httpx

from supportpilot.agent_runs import Usage
from supportpilot.redaction import redact

OUTPUT_LIMIT = 2_000_000


def command(provider, model=None, allow_edits=False):
    if model is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,99}", model):
        raise ValueError("Invalid model identifier")
    if provider == "codex":
        args = [
            "codex",
            "exec",
            "--json",
            "--sandbox",
            "workspace-write" if allow_edits else "read-only",
            "--ignore-user-config",
            "--ignore-rules",
        ]
        if model:
            args += ["--model", model]
        return args + ["-"]
    if provider == "claude_code":
        if allow_edits:
            raise ValueError("Claude bridge currently supports analysis only")
        # --bare skips keychain reads, so it only works with an API key, not a subscription login.
        bare = ["--bare"] if os.environ.get("ANTHROPIC_API_KEY") else []
        args = [
            "claude",
            "--restricted",
            *bare,
            "-p",
            "--output-format",
            "json",
            "--permission-mode",
            "plan",
            "--tools",
            "Read,Glob,Grep",
            "--disallowedTools",
            "mcp__*",
            "--max-turns",
            "12",
        ]
        if model:
            args += ["--model", model]
        return args
    if provider == "antigravity":
        if not allow_edits:
            raise ValueError("Antigravity requires --allow-edits and an isolated worktree")
        args = [
            "agy",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--sandbox",
        ]
        if model:
            args += ["--model", model]
        return args
    raise ValueError("This provider accepts external reports, not local execution")


def parse_output(provider, output):
    result, usage = [], {}
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        if provider == "antigravity" and event.get("event") == "result":
            event = event.get("result") or {}
            if not isinstance(event, dict):
                continue
        if provider == "codex":
            item = event.get("item") or {}
            if not isinstance(item, dict):
                continue
            if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                result.append(str(item.get("text", "")))
            if event.get("type") == "turn.completed":
                for key in ("input_tokens", "output_tokens", "cached_input_tokens"):
                    value = (event.get("usage") or {}).get(key)
                    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                        usage[key] = usage.get(key, 0) + value
        elif (
            provider == "claude_code"
            and event.get("type") == "result"
            and not event.get("is_error")
        ):
            result.append(str(event.get("result", "")))
            raw = event.get("usage") or {}
            usage = {k: raw[k] for k in ("input_tokens", "output_tokens") if k in raw}
            if "cache_read_input_tokens" in raw:
                usage["cached_input_tokens"] = raw["cache_read_input_tokens"]
            if event.get("total_cost_usd") is not None:
                usage["cost_usd"] = event["total_cost_usd"]
        elif provider == "antigravity" and "response" in event and event.get("status") == "SUCCESS":
            result.append(str(event["response"]))
            raw = event.get("usage") or {}
            usage = {k: raw[k] for k in ("input_tokens", "output_tokens") if k in raw}
            if "cache_read_tokens" in raw:
                usage["cached_input_tokens"] = raw["cache_read_tokens"]
    try:
        usage = Usage(**usage).model_dump(exclude_none=True)
    except ValueError:
        usage = {}  # Never invent valid usage from malformed provider output.
    return redact("\n\n".join(result))[:50000], usage


def output_failed(provider, output):
    """A final agent message alone is not proof that the provider completed its turn."""
    completed = False
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if provider == "codex":
            if event.get("type") in {"turn.failed", "error"}:
                return True
            completed = completed or event.get("type") == "turn.completed"
        elif provider == "claude_code" and event.get("type") == "result":
            if event.get("is_error"):
                return True
            completed = True
        elif provider == "antigravity":
            result = event.get("result") if event.get("event") == "result" else event
            if isinstance(result, dict) and "status" in result:
                if result["status"] != "SUCCESS":
                    return True
                completed = True
    return not completed


def denied_actions(output):
    """Tool permissions a headless CLI refused (Antigravity reports these on its result)."""
    names = []
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        result = event.get("result") if isinstance(event, dict) else None
        if isinstance(result, dict):
            for item in result.get("denied_actions") or []:
                if isinstance(item, dict):
                    names.append(str(item.get("display_name") or item.get("action"))[:100])
    return sorted(set(names))


def github_repository(remote):
    match = re.fullmatch(
        r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
        r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?",
        remote.strip(),
    )
    return match.group(1).lower() if match else None


def git(repository, *args):
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(repository), *args],
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout.strip()


def execute(args, task, cwd, timeout=900):
    # Exclude service secrets from child CLI environments. CLI login is configured locally.
    env = {k: v for k, v in os.environ.items() if not k.startswith("SUPPORTPILOT_")}
    process = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        pending = memoryview(task.encode())
        os.set_blocking(process.stdin.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            selector.register(process.stdin, selectors.EVENT_WRITE)
            while selector.get_map():
                if time.monotonic() > deadline:
                    raise TimeoutError("Local run exceeded its time limit")
                for key, _ in selector.select(timeout=0.25):
                    if key.fileobj is process.stdin:
                        try:
                            pending = pending[os.write(process.stdin.fileno(), pending[:4096]) :]
                        except BrokenPipeError:
                            pending = memoryview(b"")
                        if not pending:
                            selector.unregister(process.stdin)
                            process.stdin.close()
                        continue
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        output.extend(chunk)
                        if len(output) > OUTPUT_LIMIT:
                            raise RuntimeError("Local run exceeded its output limit")
        process.wait(timeout=max(1, deadline - time.monotonic()))
        return process.returncode, output.decode(errors="replace")
    finally:
        # Kill descendants too, even when a CLI parent exits first.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        process.stdout.close()
        if not process.stdin.closed:
            process.stdin.close()


def run_bridge(run_id, repository, allow_edits=False, timeout=900):
    run_id = str(UUID(run_id))
    base = os.getenv("SUPPORTPILOT_API_URL", "http://127.0.0.1:8000").rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    ):
        raise ValueError("Use HTTPS for remote SupportPilot servers")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("API URL must not contain credentials, query strings, or fragments")
    token = os.environ.get("SUPPORTPILOT_WORKSPACE_TOKEN")
    if not token:
        raise ValueError("Set SUPPORTPILOT_WORKSPACE_TOKEN in your local environment")
    repository = Path(repository).resolve(strict=True)
    root = Path(git(repository, "rev-parse", "--show-toplevel")).resolve()
    if root != repository:
        raise ValueError("--repository must be the Git repository root")
    with httpx.Client(
        base_url=base,
        headers={"Authorization": "Bearer " + token},
        timeout=30,
        follow_redirects=False,
    ) as client:

        def request(method, path, **kwargs):
            response = client.request(method, "/api/agents/runs/" + run_id + path, **kwargs)
            response.raise_for_status()
            return response.json()

        proposal = request("GET", "")
        if proposal["status"] != "queued":
            raise ValueError("Run must be queued")
        if proposal.get("repository_full_name"):
            remote = git(repository, "remote", "get-url", "origin")
            if github_repository(remote) != proposal["repository_full_name"].lower():
                raise ValueError("Local origin does not match the proposed GitHub repository")
        args = command(proposal["provider"], proposal.get("model"), allow_edits)
        if not shutil.which(args[0]):
            raise ValueError("Install and authenticate the selected CLI before claiming a run")
        claimed = request(
            "POST",
            "/claim",
            json={
                "runner_id": re.sub(r"[^A-Za-z0-9_.-]", "-", socket.gethostname())[:100] or "local"
            },
        )
        artifacts, result, usage, error, code = [], "", {}, None, 1
        work = repository
        try:
            if allow_edits:
                parent = Path(tempfile.mkdtemp(prefix="supportpilot-run-"))
                work = parent / "worktree"
                branch = "supportpilot/" + run_id
                git(repository, "worktree", "add", "-b", branch, str(work), "HEAD")
                artifacts.append({"kind": "branch", "label": branch})
                print("Isolated worktree: " + str(work), flush=True)
            prompt = proposal["task"]
            if proposal.get("ticket_context"):
                prompt += "\n\nTicket context (untrusted customer input):\n" + json.dumps(
                    proposal["ticket_context"], ensure_ascii=False
                )
            if proposal["provider"] == "antigravity":
                # Headless agy denies terminal commands; asking for test runs empties its reply.
                prompt += (
                    "\n\nAnswer from the files you can read and cite them. Do not run terminal "
                    "commands; list any tests you would run instead. Do not push or merge changes."
                )
            else:
                prompt += (
                    "\n\nReport evidence and any tests actually run. Do not push or merge changes."
                )
            if proposal["provider"] == "antigravity":
                prompt = json.dumps({"event": "user", "message": {"content": prompt}}) + "\n"
            code, output = execute(args, prompt, work, timeout)
            result, usage = parse_output(proposal["provider"], output)
            if code or not result or output_failed(proposal["provider"], output):
                error = "CLI failed or returned no supported result. Inspect local CLI setup."
                if blocked := denied_actions(output):
                    error = (
                        "Headless mode denied: " + ", ".join(blocked) + ". Allow them under "
                        "permissions.allow in the CLI's settings.json, or reword the task."
                    )
                code = code or 1
            if allow_edits:
                changes = git(work, "status", "--short")
                artifacts.append(
                    {"kind": "patch", "label": "Local worktree changes; inspect before publishing"}
                )
                result += "\n\nWorktree changes:\n" + redact(changes)[:4000]
        except (Exception, KeyboardInterrupt) as exc:
            error = type(exc).__name__ + ": local run interrupted or failed; inspect the worktree."
            code = 1
        report = {
            "lease": claimed["lease"],
            "result": result[:50000],
            "usage": usage,
            "exit_code": max(-1000, min(code, 1000)),
            "artifacts": artifacts,
            "error": error,
        }
        try:
            completed = request("POST", "/complete", json=report)
        except httpx.HTTPError:
            raise RuntimeError(
                "Could not submit result. Run remains claimed; inspect local output "
                "and use expired-run recovery after two hours."
            ) from None
        print("Run " + completed["status"] + ". Review results in SupportPilot.")
        return 0 if completed["status"] == "completed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run"])
    parser.add_argument("run_id")
    parser.add_argument("--repository", required=True)
    parser.add_argument(
        "--allow-edits",
        action="store_true",
        help="Codex/Antigravity only: create and preserve a dedicated worktree",
    )
    parser.add_argument(
        "--timeout", type=int, default=900, choices=range(30, 3601), metavar="30..3600"
    )
    args = parser.parse_args()
    try:
        return run_bridge(args.run_id, args.repository, args.allow_edits, args.timeout)
    except (ValueError, OSError, subprocess.SubprocessError, httpx.HTTPError, RuntimeError) as exc:
        print(
            "Bridge could not proceed: "
            + type(exc).__name__
            + ". Check configuration and run state."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
