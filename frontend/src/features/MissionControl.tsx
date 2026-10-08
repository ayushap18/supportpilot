import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  CircleDot,
  ClipboardCheck,
  ExternalLink,
  GitPullRequest,
  Inbox,
  LoaderCircle,
  Radio,
  Timer,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { Api } from "../types";
import type { AgentRun } from "./engineering-types";
import { dateTime, Empty, SectionHeading, StateBadge } from "./shared";
import "./mission.css";

export type WorkItem = {
  kind: string;
  title: string;
  detail: string;
  since: string | null;
  ref: { type: "run" | "ticket"; id: string };
};
export type Lane = {
  ticket_id: string;
  subject: string;
  status: string;
  steps: string[];
  run_id: string | null;
  run_status: string | null;
  pr_url: string | null;
  fix_merged_at: string | null;
  customer_confirmed: boolean;
  log_tail: string[];
};
export type Mission = {
  lanes: Lane[];
  pipeline: Record<string, number>;
  work_queue: WorkItem[];
  reliability: {
    runs: number;
    finished: number;
    success_rate: number | null;
    token_coverage: number | null;
    reported_cost_usd: number | null;
    cost_coverage: number;
    stuck: number;
    by_provider: Record<string, Record<string, number>>;
  };
  inbox: { id: string; title: string; detail: string; created_at: string }[];
  autonomy: {
    enabled: boolean;
    min_n: number;
    min_lower_bound: number;
    buckets: {
      key: string;
      agreed: number;
      n: number;
      lower_bound: number;
      state: "auto" | "shadow";
    }[];
  };
  knowledge: {
    id: string;
    title: string;
    source_path: string;
    status: string;
    citations: number;
    indexed_at: string | null;
    updated_at: string;
  }[];
};
type PullStatus = {
  number: number;
  html_url: string;
  state: string;
  draft: boolean;
  changed_files: number;
  additions: number;
  deletions: number;
  reviews: { login: string; state: string }[];
  checks: {
    name: string;
    status: string;
    conclusion: string | null;
    html_url: string;
  }[];
};

export const STAGES = [
  ["queued", "Queued"],
  ["running", "Running"],
  ["awaiting_review", "Needs review"],
  ["accepted", "Accepted"],
  ["changes_requested", "Changes requested"],
  ["failed", "Failed"],
] as const;
const PROVIDERS: Record<string, string> = {
  codex: "Codex",
  claude_code: "Claude Code",
  antigravity: "Antigravity",
  custom: "External",
};
export const KIND_ICON: Record<string, typeof Inbox> = {
  review_run: ClipboardCheck,
  review_draft: ClipboardCheck,
  failed_run: XCircle,
  stuck_run: Timer,
  changes_requested: AlertTriangle,
  unassigned: CircleDot,
};
const LANE_STEPS = [
  ["created", "Created"],
  ["investigated", "Investigated"],
  ["escalated", "Escalated"],
  ["claimed", "Runner claimed"],
  ["red", "Red"],
  ["green", "Green"],
  ["pr", "PR opened"],
  ["merged", "Merged"],
] as const;
const percent = (value: number | null) =>
  value == null ? "—" : Math.round(value * 100) + "%";

export function MissionControl({
  api,
  admin,
  onError,
  onOpenRun,
  onOpenTicket,
}: {
  api: Api;
  admin: boolean;
  onError: (message: string) => void;
  onOpenRun: (id: string) => void;
  onOpenTicket: (id: string) => void;
}) {
  const [mission, setMission] = useState<Mission | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);

  async function load() {
    const [summary, list] = await Promise.all([
      api<Mission>("/mission"),
      api<{ items: AgentRun[] }>("/agents/runs"),
    ]);
    setMission(summary);
    setRuns(list.items);
  }
  useEffect(() => {
    load().catch((e) => onError(e.message));
    // ponytail: 5 s polling; switch to server-sent events if lanes need sub-second updates.
    const timer = setInterval(() => load().catch(() => undefined), 5000);
    return () => clearInterval(timer);
  }, []);

  if (!mission) return <p className="muted">Loading mission control…</p>;
  const running = mission.pipeline.running > 0;
  const desk = runs.filter((run) => run.status === "completed" && !run.review);
  const open = (item: WorkItem) =>
    item.ref.type === "run"
      ? onOpenRun(item.ref.id)
      : onOpenTicket(item.ref.id);

  return (
    <div className="mission">
      <section
        className={"mission-pipeline" + (running ? " live" : "")}
        aria-label="Agent pipeline"
      >
        <div className="mission-pipeline-head">
          <span className="mission-orb" aria-hidden="true" />
          <div>
            <strong>
              {running
                ? `${mission.pipeline.running} agent${mission.pipeline.running === 1 ? "" : "s"} working`
                : "No agent is running"}
            </strong>
            <span>
              Ticket → context pack → agent → local run → results → human review
              → GitHub
            </span>
          </div>
        </div>
        <ol className="mission-stages">
          {STAGES.map(([key, label]) => (
            <li
              key={key}
              className={
                "stage-" + key + (mission.pipeline[key] ? " has-items" : "")
              }
            >
              <strong>{mission.pipeline[key] ?? 0}</strong>
              <span>{label}</span>
            </li>
          ))}
        </ol>
      </section>

      <Card>
        <CardContent>
          <SectionHeading
            title="Flight board"
            detail="Each ticket from complaint to merged fix. A merge never resolves a ticket or messages the customer; the lane turns green only when the customer confirms."
          />
          {mission.lanes.length ? (
            <div className="flight-board" role="list">
              {mission.lanes.map((lane) => {
                const tone = lane.customer_confirmed
                  ? " confirmed"
                  : lane.fix_merged_at
                    ? " merged"
                    : "";
                return (
                  <div
                    key={lane.ticket_id}
                    className={"flight-lane" + tone}
                    role="listitem"
                  >
                    <button
                      className="flight-ticket"
                      onClick={() => onOpenTicket(lane.ticket_id)}
                    >
                      <strong>{lane.subject}</strong>
                      <span>
                        {lane.customer_confirmed
                          ? "Customer confirmed the fix"
                          : lane.fix_merged_at
                            ? "Fix merged, awaiting customer confirmation"
                            : lane.status.replace("_", " ")}
                      </span>
                    </button>
                    {LANE_STEPS.map(([key, label]) => {
                      const live =
                        key === "claimed" && lane.run_status === "running";
                      return (
                        <div
                          key={key}
                          className={
                            "flight-step" +
                            (lane.steps.includes(key) ? " done" : "") +
                            (live ? " live" : "")
                          }
                          tabIndex={
                            live && lane.log_tail.length ? 0 : undefined
                          }
                        >
                          <span className="flight-dot" aria-hidden="true" />
                          {key === "pr" && lane.pr_url ? (
                            <a
                              href={lane.pr_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {label}
                            </a>
                          ) : (
                            <small>{label}</small>
                          )}
                          {live && !!lane.log_tail.length && (
                            <pre className="flight-log" role="tooltip">
                              {lane.log_tail.join("\n")}
                            </pre>
                          )}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          ) : (
            <Empty title="No tickets yet">
              Lanes appear as tickets arrive and move toward a merged fix.
            </Empty>
          )}
        </CardContent>
      </Card>

      <div className="mission-grid">
        <Card className="mission-queue">
          <CardContent>
            <SectionHeading
              title="Work queue"
              detail="Everything waiting on an owner, a runner, or a reviewer — oldest first."
            />
            {mission.work_queue.length ? (
              <ul className="mission-list">
                {mission.work_queue.map((item) => {
                  const Icon = KIND_ICON[item.kind] || Inbox;
                  return (
                    <li key={item.kind + item.ref.id}>
                      <button
                        className={"mission-item kind-" + item.kind}
                        onClick={() => open(item)}
                      >
                        <Icon size={16} />
                        <div>
                          <strong>{item.title}</strong>
                          <span>{item.detail}</span>
                        </div>
                        {item.since && <time>{dateTime(item.since)}</time>}
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <Empty title="Nothing is waiting on you">
                New drafts, agent results, and failures appear here.
              </Empty>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <SectionHeading
              title="Agent reliability"
              detail="From recorded runs only. Missing telemetry is unknown, not zero."
            />
            <div className="mission-stats">
              <div>
                <span>Success rate</span>
                <strong>{percent(mission.reliability.success_rate)}</strong>
                <small>{mission.reliability.finished} finished runs</small>
              </div>
              <div>
                <span>Token coverage</span>
                <strong>{percent(mission.reliability.token_coverage)}</strong>
                <small>finished runs reporting tokens</small>
              </div>
              <div>
                <span>Reported cost</span>
                <strong>
                  {mission.reliability.reported_cost_usd == null
                    ? "Unknown"
                    : "$" + mission.reliability.reported_cost_usd.toFixed(2)}
                </strong>
                <small>
                  {mission.reliability.cost_coverage} runs reported cost
                </small>
              </div>
              <div className={mission.reliability.stuck ? "warn" : ""}>
                <span>Waiting too long</span>
                <strong>{mission.reliability.stuck}</strong>
                <small>queued over 15 minutes</small>
              </div>
            </div>
            {!!Object.keys(mission.reliability.by_provider).length && (
              <table className="mission-table">
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>Runs</th>
                    <th>Completed</th>
                    <th>Failed</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(mission.reliability.by_provider).map(
                    ([provider, counts]) => (
                      <tr key={provider}>
                        <td>{PROVIDERS[provider] || provider}</td>
                        <td>{counts.runs ?? 0}</td>
                        <td>{counts.completed ?? 0}</td>
                        <td>{counts.failed ?? 0}</td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent>
          <SectionHeading
            title="Review desk"
            detail="Finished agent work waiting for a person. A completed run is not a solved issue."
          />
          {desk.length ? (
            <div className="mission-desk">
              {desk.map((run) => (
                <ReviewCard
                  key={run.id}
                  run={run}
                  api={api}
                  admin={admin}
                  onError={onError}
                  onDone={() => load().catch(() => undefined)}
                  onOpen={() => onOpenRun(run.id)}
                />
              ))}
            </div>
          ) : (
            <Empty title="Review desk is clear">
              Completed runs appear here until someone accepts them or requests
              changes.
            </Empty>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <SectionHeading
            title="Autonomy ladder"
            detail={`Autopilot approves a kind of draft only after ${mission.autonomy.min_n}+ human reviews with a ${percent(mission.autonomy.min_lower_bound)} agreement lower bound. One rejection drops it back to shadow. ${mission.autonomy.enabled ? "On for this workspace." : "Off for this workspace: shadow scoring only."}`}
          />
          {mission.autonomy.buckets.length ? (
            <table className="mission-table">
              <thead>
                <tr>
                  <th>Kind of draft</th>
                  <th>Humans agreed</th>
                  <th>Lower bound</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {mission.autonomy.buckets.map((b) => (
                  <tr key={b.key}>
                    <td>{b.key}</td>
                    <td>
                      {b.agreed}/{b.n}
                    </td>
                    <td>{percent(b.lower_bound)}</td>
                    <td>
                      <StateBadge value={b.state} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty title="No human reviews yet">
              Approve or reject drafts to start scoring each kind of draft.
              Autopilot approvals never count.
            </Empty>
          )}
        </CardContent>
      </Card>

      <div className="mission-grid">
        <Card>
          <CardContent>
            <SectionHeading
              title="Live activity"
              detail="Pushes, pull requests, issues, and failed checks from the GitHub webhook, plus autonomy demotions."
              action={<Radio size={16} className="mission-live-icon" />}
            />
            {mission.inbox.length ? (
              <ul className="mission-feed">
                {mission.inbox.map((event) => (
                  <li key={event.id}>
                    <Activity size={14} />
                    <div>
                      <strong>{event.title}</strong>
                      <span>{event.detail}</span>
                    </div>
                    <time>{dateTime(event.created_at)}</time>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty title="No GitHub events yet">
                Add the repository webhook (Issues, Pushes, Pull requests,
                Workflow runs) to stream activity here. See
                docs/GITHUB_SETUP.md.
              </Empty>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <SectionHeading
              title="Knowledge freshness"
              detail="Imported docs compared with the latest repository snapshot, and how often answers cite them."
            />
            {mission.knowledge.length ? (
              <ul className="mission-feed">
                {mission.knowledge.map((doc) => (
                  <li key={doc.id}>
                    <BookOpen size={14} />
                    <div>
                      <strong>{doc.title}</strong>
                      <span>
                        {doc.citations} citation{doc.citations === 1 ? "" : "s"}{" "}
                        · indexed {dateTime(doc.indexed_at || doc.updated_at)}
                      </span>
                    </div>
                    <StateBadge value={doc.status} />
                  </li>
                ))}
              </ul>
            ) : (
              <Empty title="No knowledge yet">
                Import repository docs or upload Markdown in Knowledge.
              </Empty>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// The runner's red/green test reports, so nobody pastes test output by hand.
function testSummary(run: AgentRun, label: string) {
  const report = (run.artifacts || []).find(
    (a) =>
      typeof a === "object" && a.kind === "test_report" && a.label === label,
  ) as Record<string, unknown> | undefined;
  const last = String(report?.detail || "")
    .trim()
    .split("\n")
    .pop();
  return last ? `${label}: ${last}`.slice(0, 2000) : "";
}

function ReviewCard({
  run,
  api,
  admin,
  onError,
  onDone,
  onOpen,
}: {
  run: AgentRun;
  api: Api;
  admin: boolean;
  onError: (message: string) => void;
  onDone: () => void;
  onOpen: () => void;
}) {
  const [form, setForm] = useState({
    tests_before: testSummary(run, "repro (red)"),
    tests_after: testSummary(run, "fix (green)"),
    note: "",
    customer_confirmed: false,
  });
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const hasPull = (run.artifacts || []).some(
    (a) => typeof a === "object" && a.kind === "pull_request",
  );
  async function decide(decision: "accepted" | "changes_requested") {
    setBusy(true);
    try {
      await api(`/agents/runs/${run.id}/review`, {
        method: "POST",
        body: JSON.stringify({ ...form, decision }),
      });
      onDone();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="mission-review">
      <header>
        <div>
          <strong>{run.task.split("\n")[0]}</strong>
          <span>
            {PROVIDERS[run.provider] || run.provider} ·{" "}
            {run.repository_full_name || "local repository"}
            {run.ticket_id ? " · linked ticket" : ""}
          </span>
        </div>
        <div className="mission-actions">
          <Button variant="ghost" size="sm" onClick={onOpen}>
            Open run
          </Button>
          {admin && !open && (
            <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
              Review
            </Button>
          )}
        </div>
      </header>
      {hasPull && <PullRequestPanel api={api} runId={run.id} />}
      {admin && open && (
        <div className="mission-verify">
          <label>
            Tests before
            <Input
              placeholder="e.g. test_retry FAILED"
              value={form.tests_before}
              onChange={(e) =>
                setForm({ ...form, tests_before: e.target.value })
              }
            />
          </label>
          <label>
            Tests after
            <Input
              placeholder="e.g. 42 passed"
              value={form.tests_after}
              onChange={(e) =>
                setForm({ ...form, tests_after: e.target.value })
              }
            />
          </label>
          <label className="span-2">
            Reviewer note
            <Textarea
              rows={2}
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
          </label>
          <label className="checkbox-row span-2">
            <input
              type="checkbox"
              checked={form.customer_confirmed}
              onChange={(e) =>
                setForm({ ...form, customer_confirmed: e.target.checked })
              }
            />
            <span>Customer confirmed the fix</span>
          </label>
          <div className="mission-actions span-2">
            <Button
              className="primary"
              disabled={busy}
              onClick={() => decide("accepted")}
            >
              <CheckCircle2 size={15} />
              Accept
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => decide("changes_requested")}
            >
              Request changes
            </Button>
          </div>
        </div>
      )}
    </article>
  );
}

export function PullRequestPanel({ api, runId }: { api: Api; runId: string }) {
  const [pull, setPull] = useState<PullStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function load() {
    setLoading(true);
    setError("");
    try {
      setPull(
        await api<PullStatus>(`/github/agent-runs/${runId}/pull-request`),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  if (!pull)
    return (
      <div className="pr-panel">
        <Button variant="outline" size="sm" disabled={loading} onClick={load}>
          {loading ? (
            <LoaderCircle size={14} className="spin" />
          ) : (
            <GitPullRequest size={14} />
          )}
          Load PR and CI status
        </Button>
        {error && <span className="muted small">{error}</span>}
      </div>
    );
  return (
    <div className="pr-panel loaded" aria-label="Pull request status">
      <a href={pull.html_url} target="_blank" rel="noreferrer">
        <GitPullRequest size={14} /> PR #{pull.number}
        <ExternalLink size={12} />
      </a>
      <StateBadge
        value={pull.draft && pull.state === "open" ? "draft" : pull.state}
      />
      <span className="muted small">
        {pull.changed_files} file{pull.changed_files === 1 ? "" : "s"} · +
        {pull.additions} −{pull.deletions}
      </span>
      {pull.reviews.map((review) => (
        <StateBadge key={review.login} value={review.state.toLowerCase()} />
      ))}
      {pull.checks.length ? (
        pull.checks.map((check, index) => (
          <a
            key={index}
            className={"pr-check " + (check.conclusion || check.status)}
            href={check.html_url}
            target="_blank"
            rel="noreferrer"
          >
            {check.name}: {check.conclusion || check.status}
          </a>
        ))
      ) : (
        <span className="muted small">No workflow runs on this commit</span>
      )}
      <Button variant="ghost" size="sm" onClick={load} disabled={loading}>
        Refresh
      </Button>
    </div>
  );
}
