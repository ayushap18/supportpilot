# Local coding agents and reported usage

SupportPilot records proposed tasks, ownership, results, and usage. Creating a run does **not** execute code. An administrator must explicitly start the local bridge on a machine with the selected CLI installed and authenticated. The web server never executes commands supplied by tickets or browsers.

## Run a proposal

1. In **Agents**, select the provider, describe the task, and optionally associate a ticket and GitHub `owner/repository`. Review the task before starting it.
2. On macOS or Linux, install SupportPilot in a Python 3.12+ virtual environment (`pip install -e .`). Install and authenticate the selected provider's CLI separately.
3. Supply your workspace token through the local environment. Do not put it in command arguments, a repository file, or a task. Set `SUPPORTPILOT_API_URL` to your HTTPS deployment URL (local default: `http://127.0.0.1:8000`). Set `SUPPORTPILOT_WORKSPACE_TOKEN` privately through your shell or secret manager.
4. Copy the run UUID and invoke:

```sh
python -m supportpilot.cli_bridge run RUN_UUID --repository /absolute/path/to/repository
```

For Codex edits, explicitly add `--allow-edits`. Antigravity requires this flag because its headless mode permits workspace writes. The bridge creates a dedicated `supportpilot/RUN_UUID` branch and a fresh Git worktree from local `HEAD`, and prints its path. Uncommitted changes in the primary checkout are not copied. Worktrees remain on disk for review, including when runs fail; remove them manually after preserving any wanted changes.

```sh
python -m supportpilot.cli_bridge run RUN_UUID --repository /absolute/path/to/repository --allow-edits
```

The local repository root must match the command argument. When a repository is associated with the proposal, its `origin` must match the exact GitHub owner/name using an HTTPS or SSH GitHub remote. The bridge does not clone or fetch automatically. Use a trusted checkout at the intended commit.

## Run queued work automatically (`watch`)

Instead of one command per run, start a runner in your repository and leave it open:

```sh
python -m supportpilot.cli_bridge watch --repository /absolute/path/to/repository
```

- It sends a heartbeat every cycle (default 10 s, `--interval 3..300`), so **Agent runs** shows "Local runner online" with its providers, repository, and permissions.
- It executes queued runs oldest first. It skips runs linked to a different repository, providers whose CLI isn't installed, and edit runs when the runner wasn't started with `--allow-edits`. Edit permission is always granted on the machine, never from the browser.
- `--allow-edits` lets it execute edit runs (Codex with "Allow edits", and Antigravity) in a dedicated worktree. Add `--push` to commit and push the run's `supportpilot/RUN_UUID` branch after a successful edit run on a linked repository, using your local git credentials.
- `--once` processes the queue a single time, which is useful in scripts.

While a run executes, the bridge streams short, redacted progress lines (the last 300 are kept) that appear as a **Live log** in the run details. Progress is best effort; the final result is submitted either way.

## Open a draft pull request

When an edit run completes and its branch was pushed (`--push`), **Open draft PR** in the run details opens a *draft* pull request against the repository's default branch through the workspace's GitHub connection. The PR body contains the task and the redacted agent report. The PR link is stored as a run artifact; one PR per run. Nothing is merged.

## Provider boundaries

| Provider | Execution policy | Captured usage |
| --- | --- | --- |
| Codex | `exec --json --sandbox read-only` by default; `workspace-write` only with explicit edits. Ignores user config and exec policy rules. | Tokens reported by completed turns; no inferred cost. |
| Claude Code | Restricted headless invocation (`--bare` only when `ANTHROPIC_API_KEY` is set, since bare mode skips subscription login), plan mode, built-in `Read,Glob,Grep` only; MCP tools denied. Edits are currently unsupported by this adapter. | Reported tokens and `total_cost_usd` when supplied. |
| Antigravity (`agy`) | One stdin streaming task with `--sandbox`, explicit edits flag, dedicated worktree. No permission bypass flag. | Reported input/output/cache tokens; no inferred cost. |
| External report | An administrator manually claims and reports a run via API. No arbitrary executable registration. | Only supplied values. |

These adapters use current documented flags; older CLI versions may reject them. The bridge fails rather than retrying with broader permissions. No real paid CLI session is run by the automated tests. Configure and validate one controlled local run before relying on a provider in a team workflow.

A worktree isolates tracked edits from the primary checkout; it is not a container or a security boundary against malicious repository configuration. Provider sandbox/restricted policies still apply. Use trusted repositories and a dedicated account or disposable development environment for unfamiliar code. The bridge strips all `SUPPORTPILOT_` environment variables from child processes. Other credentials and local files may remain accessible under the provider's own policy. It does not claim to guarantee prompt-injection prevention.

## Review results

The bridge sends task text and the ticket's captured subject, description, log, product version, account ID, and revision through stdin. Treat ticket text as untrusted. Changing a ticket after creating a proposal does not silently alter that proposal's context.

Runs have `queued`, `running`, `completed`, `failed`, or `cancelled` states. **Completed means the CLI returned a supported successful result; it does not mean the ticket was solved or the generated code is correct.** A run never auto-resolves a ticket or pushes, merges, or opens a pull request through the bridge. Review the preserved worktree and provider's reported tests before publishing changes. Test descriptions in model output are reports, not independently verified CI evidence.

Results are bounded and redacted with SupportPilot's standard secret-pattern redactor. Redaction is best effort; do not submit secrets to agent tasks. Raw CLI diagnostic logs are not uploaded. Token totals show only explicitly reported values; missing totals and costs remain unknown. Coverage counts indicate how many runs supplied each metric. Reported costs are not verified invoices, subscription usage, credit balances, or quota access.

## Limits and recovery

The default execution timeout is 15 minutes; `--timeout` accepts 30–3600 seconds. Output is limited to 2 MB. Timeout, interruption, and output-limit failures terminate the local process group and attempt to submit a failed result. No automatic retry runs another paid request.

Claim leases are random, stored hashed, tied to the claiming workspace identity, and returned only once. Another admin cannot submit completion using a different identity. Duplicate claims/completions are rejected. A queued run can be cancelled in the UI. Running cancellation is deliberately not presented as remote process control: stop the bridge in its terminal instead.

If the bridge cannot submit its result (for example, network loss), the run remains claimed. Inspect and stop any surviving local process first. After the two-hour lease deadline, an admin can call `POST /api/agents/runs/{id}/expire` to mark it failed, then create a new proposal if appropriate. Expiry does not prove a remote process stopped. The old lease cannot complete an expired run.

## External reports

Use the same workspace identity for both calls. Keep the returned lease private:

- `POST /api/agents/runs/{id}/claim` with `{"runner_id":"your-runner"}`.
- `POST /api/agents/runs/{id}/complete` with `lease`, `result`, `exit_code`, optional `error`, optional `usage`, and optional `artifacts`.

Usage fields are optional `input_tokens`, `output_tokens`, `cached_input_tokens`, and `cost_usd`; omit values you cannot observe. Artifacts accept `kind` (`branch`, `pull_request`, `test_report`, or `patch`), `label`, and an optional HTTPS `url`. Result submissions record supplied evidence; they do not independently verify an external agent's actions or spending.

## Documentation used

- [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode): sandbox options, JSONL events, and config flags.
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference): restricted/bare modes and tool selection.
- [Claude Code headless usage](https://code.claude.com/docs/en/headless): programmatic output.
- [Antigravity headless mode](https://antigravity.google/docs/cli/headless/): stdin streaming, permissions, result envelope, and usage.
