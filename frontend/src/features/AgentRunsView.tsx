import { useEffect, useRef, useState } from "react";
import {
  Check,
  Copy,
  GitPullRequest,
  Plus,
  Radio,
  RefreshCw,
  Terminal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import type { Api, QueueTicket } from "../types";
import { dateTime, Empty, SectionHeading, StateBadge } from "./shared";
import { githubUrl } from "./engineering-types";
import type {
  AgentProvider,
  AgentRun,
  AgentRunner,
  AgentUsage,
  Repository,
} from "./engineering-types";
import "./engineering.css";
export function AgentRunsView({
  api,
  onError,
  admin,
}: {
  api: Api;
  admin: boolean;
  onError: (message: string) => void;
}) {
  const [providers, setProviders] = useState<AgentProvider[]>([]),
    [runs, setRuns] = useState<AgentRun[]>([]),
    [usage, setUsage] = useState<AgentUsage | null>(null),
    [repositories, setRepositories] = useState<Repository[]>([]),
    [tickets, setTickets] = useState<QueueTicket[]>([]),
    [selected, setSelected] = useState<AgentRun | null>(null),
    [busy, setBusy] = useState(""),
    [open, setOpen] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [copied, setCopied] = useState(""),
    [runners, setRunners] = useState<AgentRunner[]>([]),
    logEnd = useRef<HTMLDivElement | null>(null),
    [form, setForm] = useState({
      provider: "codex",
      task: "",
      repository_full_name: "",
      model: "",
      ticket_id: "",
      allow_edits: false,
    });
  async function load() {
    const data = await api<{ items: AgentRun[]; usage: AgentUsage }>(
      "/agents/runs",
    );
    setRuns(data.items);
    setUsage(data.usage);
    setRunners((await api<{ items: AgentRunner[] }>("/agents/runners")).items);
    setSelected((current) =>
      current
        ? data.items.find((run) => run.id === current.id) || current
        : null,
    );
  }
  useEffect(() => {
    Promise.all([
      load(),
      api<{ items: QueueTicket[] }>("/queue?page_size=100").then((data) =>
        setTickets(data.items),
      ),
      api<{ items: AgentProvider[] }>("/agents/providers").then((data) =>
        setProviders(data.items),
      ),
      api<{ items: Repository[] }>("/github/repositories").then((data) =>
        setRepositories(data.items),
      ),
    ])
      .catch((e) => onError(e.message))
      .finally(() => setLoading(false));
  }, []);
  const active = runs.some((run) => ["queued", "running"].includes(run.status));
  useEffect(() => {
    // Poll while work is pending so runner pickup and live logs appear without refreshing.
    if (!active) return;
    const timer = setInterval(() => load().catch(() => undefined), 3000);
    return () => clearInterval(timer);
  }, [active]);
  useEffect(() => {
    logEnd.current?.scrollIntoView({ block: "nearest" });
  }, [selected?.log?.length]);
  async function copy(text: string, key: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
    } catch {
      onError("Clipboard unavailable. Select and copy the command manually.");
    }
  }
  async function openPullRequest(run: AgentRun) {
    setBusy("pull");
    try {
      setSelected(
        await api<AgentRun>(`/github/agent-runs/${run.id}/pull-request`, {
          method: "POST",
        }),
      );
      await load();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function refresh() {
    setBusy("refresh");
    try {
      await load();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function create(event: React.FormEvent) {
    event.preventDefault();
    setBusy("create");
    setError("");
    try {
      const run = await api<AgentRun>("/agents/runs", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          repository_full_name: form.repository_full_name || null,
          model: form.model || null,
          ticket_id: form.ticket_id.trim() || null,
          allow_edits:
            form.provider === "antigravity" ||
            (form.provider === "codex" && form.allow_edits),
        }),
      });
      await load();
      setSelected(run);
      setOpen(false);
      setForm({ ...form, task: "" });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  const needsEdits = (run: AgentRun) =>
    run.allow_edits || run.provider === "antigravity";
  const command = selected
    ? `python -m supportpilot.cli_bridge run ${selected.id} --repository /absolute/path/to/repo${needsEdits(selected) ? " --allow-edits" : ""}`
    : "";
  const watchCommand =
    "python -m supportpilot.cli_bridge watch --repository /absolute/path/to/repo --allow-edits --push";
  const online = runners.filter((runner) => runner.online);
  const provider = providers.find((item) => item.id === form.provider);
  const pushedBranch = (run: AgentRun) =>
    (run.artifacts || []).some(
      (a) =>
        typeof a === "object" &&
        a.kind === "branch" &&
        String(a.label).endsWith("(pushed)"),
    );
  const hasPull = (run: AgentRun) =>
    (run.artifacts || []).some(
      (a) => typeof a === "object" && a.kind === "pull_request",
    );
  return (
    <div className="engineering-view">
      <Card>
        <CardContent>
          <SectionHeading
            title="Coding agents"
            detail="A shared run history for local CLI agents. You control where code executes."
            action={
              <Button
                onClick={() => {
                  setError("");
                  setOpen(true);
                }}
                disabled={loading || !admin}
              >
                <Plus size={16} />
                Queue agent run
              </Button>
            }
          />
          <div className="engineering-provider-grid">
            {providers.map((item) => (
              <div className="engineering-provider" key={item.id}>
                <span className="engineering-icon">
                  <Terminal size={19} />
                </span>
                <h3>{item.name}</h3>
                <StateBadge value={item.execution || "local_cli"} />
                <p>{item.setup}</p>
                <small>{item.usage_support}</small>
              </div>
            ))}
          </div>
          <div
            className={"runner-status " + (online.length ? "online" : "")}
            role="status"
          >
            <Radio size={18} />
            {online.length ? (
              <div>
                <strong>
                  {online.length === 1
                    ? "Local runner online"
                    : `${online.length} local runners online`}
                </strong>
                {online.map((runner) => (
                  <p key={runner.runner_id}>
                    {runner.runner_id} · {runner.providers.join(", ")} ·{" "}
                    {runner.repository_full_name || "any repository"} ·{" "}
                    {runner.allow_edits ? "edits allowed" : "read-only"}
                    {runner.push ? " · pushes branches" : ""}
                  </p>
                ))}
                <p>
                  Queued runs start automatically. Execution stays on that
                  machine.
                </p>
              </div>
            ) : (
              <div>
                <strong>No runner online</strong>
                <p>
                  Start a runner in your repository to execute queued runs
                  automatically. Set SUPPORTPILOT_API_URL and
                  SUPPORTPILOT_WORKSPACE_TOKEN in that shell first. Drop
                  --allow-edits for read-only analysis; --push lets edit runs
                  push their branch so you can open a draft PR.
                </p>
                <div className="engineering-command">
                  <code>{watchCommand}</code>
                  <Button
                    variant="ghost"
                    aria-label="Copy runner watch command"
                    onClick={() => copy(watchCommand, "watch")}
                  >
                    {copied === "watch" ? (
                      <Check size={15} />
                    ) : (
                      <Copy size={15} />
                    )}
                  </Button>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
      <div className="engineering-stats engineering-usage">
        <div>
          <span>Tracked runs</span>
          <strong>{usage?.runs ?? "—"}</strong>
        </div>
        <div>
          <span>Reported input tokens</span>
          <strong>{usage?.input_tokens?.toLocaleString() ?? "—"}</strong>
          <small>{usage?.reported_input_tokens_runs ?? 0} runs reported</small>
        </div>
        <div>
          <span>Reported output tokens</span>
          <strong>{usage?.output_tokens?.toLocaleString() ?? "—"}</strong>
          <small>{usage?.reported_output_tokens_runs ?? 0} runs reported</small>
        </div>
        <div>
          <span>Reported cost</span>
          <strong>
            {usage?.cost_usd == null
              ? "Unknown"
              : `$${usage.cost_usd.toFixed(4)}`}
          </strong>
          <small>
            {usage?.unreported_cost_runs ?? 0} runs without cost data
          </small>
        </div>
      </div>
      <p className="muted small">
        Usage covers runs recorded in this workspace. Missing telemetry is
        unknown; this is not your provider account's billing total or
        subscription allowance.
      </p>
      <div className="engineering-runs-grid">
        <Card>
          <CardContent>
            <SectionHeading
              title="Run history"
              detail="Updates automatically while runs are queued or running."
              action={
                <Button
                  aria-label="Refresh agent runs"
                  variant="ghost"
                  disabled={!!busy}
                  onClick={refresh}
                >
                  <RefreshCw size={15} />
                </Button>
              }
            />
            {loading ? (
              <p className="muted">Loading agent runs…</p>
            ) : runs.length ? (
              <div className="engineering-run-list">
                {runs.map((run) => (
                  <button
                    className={selected?.id === run.id ? "selected" : ""}
                    key={run.id}
                    onClick={() => {
                      setSelected(run);
                      setCopied("");
                    }}
                  >
                    <div>
                      <strong>
                        {providers.find((item) => item.id === run.provider)
                          ?.name || run.provider}
                      </strong>
                      <StateBadge value={run.status} />
                    </div>
                    <p>{run.task}</p>
                    <small>
                      {dateTime(run.created_at)}
                      {run.repository_full_name
                        ? ` · ${run.repository_full_name}`
                        : ""}
                    </small>
                  </button>
                ))}
              </div>
            ) : (
              <Empty title="Your first agent run">
                Queue a task for Codex, Claude Code, Antigravity, or another
                tool, then report the result from your local environment.
              </Empty>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            {selected ? (
              <>
                <SectionHeading
                  title="Run details"
                  detail={selected.id}
                  action={<StateBadge value={selected.status} />}
                />
                <p className="engineering-task">{selected.task}</p>
                <div className="engineering-run-meta">
                  <span>{selected.provider}</span>
                  <span>{selected.model || "CLI default model"}</span>
                  <span>
                    {selected.repository_full_name || "Local repository"}
                  </span>
                </div>
                {selected.ticket_id && (
                  <p className="muted small">
                    Linked ticket: {selected.ticket_id}
                  </p>
                )}
                {selected.status === "queued" && !!online.length && (
                  <p className="muted small">
                    Waiting for a runner to pick this up…
                  </p>
                )}
                {selected.status === "queued" && !online.length && (
                  <div className="engineering-callout">
                    <strong>Start this run locally</strong>
                    <p>
                      Set SUPPORTPILOT_API_URL and SUPPORTPILOT_WORKSPACE_TOKEN
                      in your shell. Keep your token out of commands and
                      screenshots.
                    </p>
                    {selected.provider !== "custom" && (
                      <div className="engineering-command">
                        <code>{command}</code>
                        <Button
                          variant="ghost"
                          aria-label="Copy runner command"
                          onClick={() => copy(command, "run")}
                        >
                          {copied === "run" ? (
                            <Check size={15} />
                          ) : (
                            <Copy size={15} />
                          )}
                        </Button>
                      </div>
                    )}
                    {selected.provider === "antigravity" && (
                      <p className="muted small">
                        Antigravity requires a dedicated clean worktree and the
                        explicit --allow-edits option.
                      </p>
                    )}
                    {selected.provider === "custom" && (
                      <p className="muted small">
                        For custom tools, claim this run and submit a result
                        through the authenticated API. See docs/AGENT_BRIDGE.md
                        for the external report workflow.
                      </p>
                    )}
                  </div>
                )}
                {!!selected.log?.length && (
                  <>
                    <h3 className="engineering-subtitle">
                      {selected.status === "running" && (
                        <span className="live-dot" aria-hidden="true" />
                      )}
                      {selected.status === "running" ? "Live log" : "Run log"}
                    </h3>
                    <div className="run-log" aria-label="Run log" role="log">
                      {selected.log.slice(-80).map((line, index) => (
                        <div key={index}>{line}</div>
                      ))}
                      <div ref={logEnd} />
                    </div>
                  </>
                )}
                {selected.result && (
                  <>
                    <h3 className="engineering-subtitle">Result</h3>
                    <pre className="engineering-pre">
                      {typeof selected.result === "string"
                        ? selected.result
                        : JSON.stringify(selected.result, null, 2)}
                    </pre>
                  </>
                )}
                {selected.error && (
                  <p role="alert" className="error-banner">
                    {selected.error}
                  </p>
                )}
                {!!selected.artifacts?.length && (
                  <>
                    <h3 className="engineering-subtitle">Artifacts</h3>
                    <div className="engineering-artifacts">
                      {selected.artifacts.map((artifact, index) => {
                        const item =
                          typeof artifact === "string"
                            ? { label: artifact }
                            : artifact;
                        const url = githubUrl(
                          typeof item.url === "string" ? item.url : undefined,
                        );
                        return (
                          <div className="engineering-artifact" key={index}>
                            <StateBadge
                              value={String(item.kind || "artifact")}
                            />
                            {url ? (
                              <a href={url} target="_blank" rel="noreferrer">
                                {String(item.label || "Open artifact")}
                              </a>
                            ) : (
                              <span>
                                {String(item.label || "Reported artifact")}
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}
                {admin &&
                  selected.status === "completed" &&
                  selected.repository_full_name &&
                  !hasPull(selected) &&
                  (pushedBranch(selected) ? (
                    <div className="engineering-actions">
                      <Button
                        disabled={!!busy}
                        onClick={() => openPullRequest(selected)}
                      >
                        <GitPullRequest size={15} />
                        {busy === "pull" ? "Opening…" : "Open draft PR"}
                      </Button>
                      <span className="muted small">
                        Opens a draft pull request on GitHub for review. Nothing
                        is merged.
                      </span>
                    </div>
                  ) : (
                    needsEdits(selected) && (
                      <p className="muted small">
                        To open a draft PR, run edit tasks with a runner started
                        with --allow-edits --push.
                      </p>
                    )
                  ))}
                <div className="engineering-run-meta">
                  <span>
                    Input: {selected.usage?.input_tokens ?? "unknown"}
                  </span>
                  <span>
                    Output: {selected.usage?.output_tokens ?? "unknown"}
                  </span>
                  <span>
                    Cost:{" "}
                    {selected.usage?.cost_usd == null
                      ? "unknown"
                      : `$${selected.usage.cost_usd.toFixed(4)}`}
                  </span>
                </div>
                {admin && selected.status === "queued" && (
                  <div className="engineering-actions">
                    <Button
                      variant="outline"
                      disabled={!!busy}
                      onClick={async () => {
                        setBusy("cancel");
                        try {
                          setSelected(
                            await api<AgentRun>(
                              `/agents/runs/${selected.id}/cancel`,
                              { method: "POST" },
                            ),
                          );
                          await load();
                        } catch (e) {
                          onError((e as Error).message);
                        } finally {
                          setBusy("");
                        }
                      }}
                    >
                      Cancel run
                    </Button>
                    <span className="muted small">
                      Only tasks that have not started can be cancelled.
                    </span>
                  </div>
                )}
              </>
            ) : (
              <Empty title="Select a run">
                Inspect the task, execution state, reported usage, and results
                here.
              </Empty>
            )}
          </CardContent>
        </Card>
      </div>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!busy) setOpen(value);
        }}
      >
        <DialogContent className="document-dialog">
          <DialogHeader>
            <DialogTitle>Queue an agent run</DialogTitle>
            <DialogDescription>
              Describe one bounded task. Execution starts only when you launch a
              local runner.
            </DialogDescription>
          </DialogHeader>
          <form className="stack-form" onSubmit={create}>
            {error && (
              <p className="error-banner" role="alert">
                {error}
              </p>
            )}
            <label>
              Agent provider
              <NativeSelect
                aria-label="Agent provider"
                value={form.provider}
                onChange={(e) => setForm({ ...form, provider: e.target.value })}
              >
                {providers.map((item) => (
                  <NativeSelectOption key={item.id} value={item.id}>
                    {item.name}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </label>
            <p className="muted small">{provider?.setup}</p>
            <label>
              Task
              <Textarea
                aria-label="Agent task"
                required
                minLength={10}
                maxLength={12000}
                rows={5}
                placeholder="Investigate issue #42, propose a focused fix, and run the relevant tests."
                value={form.task}
                onChange={(e) => setForm({ ...form, task: e.target.value })}
              />
            </label>
            <label>
              Repository
              <NativeSelect
                aria-label="Agent repository"
                value={form.repository_full_name}
                onChange={(e) =>
                  setForm({ ...form, repository_full_name: e.target.value })
                }
              >
                <NativeSelectOption value="">
                  Choose locally when running
                </NativeSelectOption>
                {repositories.map((repo) => (
                  <NativeSelectOption key={repo.id} value={repo.full_name}>
                    {repo.full_name}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </label>
            <div className="form-row">
              <label>
                Model (optional)
                <Input
                  maxLength={100}
                  placeholder="Use CLI default"
                  value={form.model}
                  onChange={(e) => setForm({ ...form, model: e.target.value })}
                />
              </label>
              <label>
                Linked ticket (optional)
                <NativeSelect
                  aria-label="Linked ticket"
                  value={form.ticket_id}
                  onChange={(e) =>
                    setForm({ ...form, ticket_id: e.target.value })
                  }
                >
                  <NativeSelectOption value="">
                    No linked ticket
                  </NativeSelectOption>
                  {tickets.map((ticket) => (
                    <NativeSelectOption key={ticket.id} value={ticket.id}>
                      {ticket.subject}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
                <span className="muted small">
                  Showing up to 100 recently updated tickets.
                </span>
              </label>
            </div>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.provider === "antigravity" || form.allow_edits}
                disabled={
                  form.provider === "antigravity" ||
                  form.provider === "claude_code" ||
                  form.provider === "custom"
                }
                onChange={(e) =>
                  setForm({ ...form, allow_edits: e.target.checked })
                }
              />
              <span>
                Allow edits in an isolated worktree
                <small>
                  {form.provider === "claude_code"
                    ? "Claude Code runs are analysis-only."
                    : form.provider === "antigravity"
                      ? "Antigravity always runs in an isolated worktree."
                      : "The runner must also be started with --allow-edits."}
                </small>
              </span>
            </label>
            <Button type="submit" disabled={!!busy}>
              {busy === "create" ? "Queuing…" : "Queue task"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
