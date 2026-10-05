import { useEffect, useState } from "react";
import {
  ArrowUpRight,
  Circle,
  CircleCheck,
  CircleDashed,
  Inbox,
  Radio,
  Terminal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Api, Operations, QueueTicket } from "../types";
import type { AgentRunner } from "./engineering-types";
import {
  KIND_ICON,
  STAGES,
  type Mission,
  type WorkItem,
} from "./MissionControl";
import { dateTime, StateBadge } from "./shared";
import "./dashboard.css";

const FILTERS = [
  ["all", "All", () => true],
  [
    "reviews",
    "Reviews",
    (i: WorkItem) =>
      ["review_run", "review_draft", "changes_requested"].includes(i.kind),
  ],
  [
    "failures",
    "Failures",
    (i: WorkItem) => ["failed_run", "stuck_run"].includes(i.kind),
  ],
  ["owners", "Unassigned", (i: WorkItem) => i.kind === "unassigned"],
] as const;

const PROVIDER_NAMES: Record<string, string> = {
  codex: "Codex",
  claude_code: "Claude Code",
  antigravity: "Antigravity",
  custom: "External",
};

const READINESS_ICON = {
  ready: CircleCheck,
  demo: CircleDashed,
  pending: Circle,
};

function duration(minutes: number | null | undefined) {
  if (minutes == null) return "—";
  if (minutes < 1) return "<1 min";
  if (minutes < 90) return Math.round(minutes) + " min";
  if (minutes < 2880) return (minutes / 60).toFixed(1) + " h";
  return (minutes / 1440).toFixed(1) + " d";
}

function age(since: string | null) {
  if (!since) return "";
  const minutes = (Date.now() - new Date(since).getTime()) / 60000;
  return minutes < 60
    ? Math.max(1, Math.round(minutes)) + "m"
    : minutes < 2880
      ? Math.round(minutes / 60) + "h"
      : Math.round(minutes / 1440) + "d";
}

export function Dashboard({
  api,
  data,
  onTicket,
  onOpenTicket,
  onOpenRun,
  onNavigate,
}: {
  api: Api;
  data: Operations;
  onTicket: (ticket: QueueTicket) => void;
  onOpenTicket: (id: string) => void;
  onOpenRun: (id: string) => void;
  onNavigate: (
    view: "workspace" | "reviews" | "agents" | "mission" | "settings",
  ) => void;
}) {
  const [mission, setMission] = useState<Mission | null>(null);
  const [runners, setRunners] = useState<AgentRunner[]>([]);
  const [filter, setFilter] = useState<(typeof FILTERS)[number][0]>("all");

  useEffect(() => {
    const load = () =>
      Promise.all([
        api<Mission>("/mission").then(setMission),
        api<{ items: AgentRunner[] }>("/agents/runners").then((r) =>
          setRunners(r.items),
        ),
      ]).catch(() => undefined);
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, []);

  const queue = mission?.work_queue ?? [];
  const pipeline = mission?.pipeline ?? {};
  const toReview = pipeline.awaiting_review ?? 0;
  const failed = pipeline.failed ?? 0;
  const active = data.counts.open + data.counts.in_progress;
  const online = runners.filter((r) => r.online);
  const shown = queue.filter(FILTERS.find(([id]) => id === filter)![2]);
  const summary = [
    `${active} open ticket${active === 1 ? "" : "s"}`,
    data.counts.awaiting_review &&
      `${data.counts.awaiting_review} draft${data.counts.awaiting_review === 1 ? "" : "s"} to decide`,
    toReview &&
      `${toReview} agent result${toReview === 1 ? "" : "s"} to review`,
    failed && `${failed} failed run${failed === 1 ? "" : "s"}`,
  ].filter(Boolean);

  const kpis = [
    {
      label: "Open tickets",
      value: String(active),
      detail: `${data.counts.waiting} waiting for context`,
      go: () => onNavigate("workspace"),
    },
    {
      label: "Drafts to decide",
      value: String(data.counts.awaiting_review),
      detail: "Investigation drafts",
      go: () => onNavigate("reviews"),
      tone: data.counts.awaiting_review ? "warn" : "",
    },
    {
      label: "Agent results to review",
      value: mission ? String(toReview) : "—",
      detail: failed ? `${failed} failed` : "No failures",
      go: () => onNavigate("mission"),
      tone: toReview ? "warn" : "",
    },
    {
      label: "Approval rate",
      value:
        data.metrics?.approval_rate == null
          ? "—"
          : Math.round(data.metrics.approval_rate * 100) + "%",
      detail: `${data.metrics?.reviews ?? 0} decisions`,
      go: () => onNavigate("reviews"),
    },
    {
      label: "Time to first draft",
      value: duration(data.metrics?.median_first_draft_minutes),
      detail: `median · ${data.metrics?.drafted_tickets ?? 0} tickets`,
      go: () => onNavigate("workspace"),
    },
  ];

  return (
    <div className="dash">
      <div className="dash-status">
        <p>
          <span className={"dash-status-dot" + (queue.length ? " busy" : "")} />
          {summary.join(" · ")}
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onNavigate("agents")}
        >
          <Terminal size={14} />
          Queue agent run
        </Button>
      </div>

      <section className="dash-kpis" aria-label="Key numbers">
        {kpis.map((kpi) => (
          <button
            key={kpi.label}
            className={"dash-kpi " + (kpi.tone || "")}
            onClick={kpi.go}
          >
            <span>{kpi.label}</span>
            <strong>{kpi.value}</strong>
            <small>{kpi.detail}</small>
          </button>
        ))}
      </section>

      <div className="dash-row">
        <section className="dash-panel dash-main" aria-label="Needs attention">
          <header>
            <div>
              <h2>Needs attention</h2>
              <p>Waiting on a person, oldest first</p>
            </div>
            <div
              className="dash-chips"
              role="group"
              aria-label="Filter attention items"
            >
              {FILTERS.map(([id, label, test]) => (
                <button
                  key={id}
                  className={filter === id ? "active" : ""}
                  aria-pressed={filter === id}
                  onClick={() => setFilter(id)}
                >
                  {label}
                  <span>{queue.filter(test).length}</span>
                </button>
              ))}
            </div>
          </header>
          {!mission ? (
            <p className="dash-empty">Loading…</p>
          ) : shown.length ? (
            <ul className="dash-queue">
              {shown.slice(0, 8).map((item) => {
                const Icon = KIND_ICON[item.kind] || Inbox;
                return (
                  <li key={item.kind + item.ref.id}>
                    <button
                      className={"kind-" + item.kind}
                      onClick={() =>
                        item.ref.type === "run"
                          ? onOpenRun(item.ref.id)
                          : onOpenTicket(item.ref.id)
                      }
                    >
                      <Icon size={16} />
                      <span className="dash-queue-text">
                        <strong>{item.title}</strong>
                        <span>{item.detail}</span>
                      </span>
                      <time title={item.since ? dateTime(item.since) : ""}>
                        {age(item.since)}
                      </time>
                    </button>
                  </li>
                );
              })}
              {shown.length > 8 && (
                <li>
                  <button
                    className="dash-more"
                    onClick={() => onNavigate("mission")}
                  >
                    {shown.length - 8} more in Mission control{" "}
                    <ArrowUpRight size={13} />
                  </button>
                </li>
              )}
            </ul>
          ) : (
            <p className="dash-empty">Nothing here. You're all caught up.</p>
          )}
        </section>

        <section className="dash-panel" aria-label="Agents">
          <header>
            <div>
              <h2>Agents</h2>
              <p className={online.length ? "dash-online" : ""}>
                <Radio size={12} />
                {online.length
                  ? `${online.length} runner${online.length === 1 ? "" : "s"} online`
                  : "No runner online"}
              </p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onNavigate("mission")}
            >
              Open <ArrowUpRight size={13} />
            </Button>
          </header>
          <ol className="dash-pipeline">
            {STAGES.map(([key, label]) => (
              <li
                key={key}
                className={
                  "stage-" +
                  key +
                  ((pipeline[key] ?? 0) > 0 ? " has-items" : "")
                }
              >
                <i aria-hidden="true" />
                <span>{label}</span>
                <strong>{pipeline[key] ?? 0}</strong>
              </li>
            ))}
          </ol>
          {!!mission &&
            !!Object.keys(mission.reliability.by_provider).length && (
              <ul className="dash-providers" aria-label="Runs by agent">
                {Object.entries(mission.reliability.by_provider).map(
                  ([provider, counts]) => (
                    <li key={provider}>
                      <span>{PROVIDER_NAMES[provider] || provider}</span>
                      <span className="dash-provider-bar" aria-hidden="true">
                        <i
                          style={{
                            width: `${((counts.completed ?? 0) / counts.runs) * 100}%`,
                          }}
                        />
                        <i
                          className="failed"
                          style={{
                            width: `${((counts.failed ?? 0) / counts.runs) * 100}%`,
                          }}
                        />
                      </span>
                      <small>
                        {counts.runs} run{counts.runs === 1 ? "" : "s"}
                        {counts.failed ? ` · ${counts.failed} failed` : ""}
                      </small>
                    </li>
                  ),
                )}
              </ul>
            )}
          <div className="dash-agent-foot">
            <span>Success rate</span>
            <strong>
              {mission?.reliability.success_rate == null
                ? "—"
                : Math.round(mission.reliability.success_rate * 100) + "%"}
            </strong>
            <small>{mission?.reliability.finished ?? 0} finished runs</small>
          </div>
        </section>
      </div>

      <div className="dash-row">
        <ActivityChart trends={data.trends} />
        <section className="dash-panel" aria-label="Readiness">
          <header>
            <div>
              <h2>Readiness</h2>
              <p>What is live, demo, or still to configure</p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onNavigate("settings")}
            >
              Configure <ArrowUpRight size={13} />
            </Button>
          </header>
          <ul className="dash-ready">
            {data.readiness.map((item) => {
              const Icon =
                READINESS_ICON[item.status as keyof typeof READINESS_ICON] ||
                Circle;
              return (
                <li
                  key={item.id}
                  className={"ready-" + item.status}
                  title={item.detail}
                >
                  <Icon size={15} />
                  <span>{item.label}</span>
                  <StateBadge value={item.status} />
                </li>
              );
            })}
          </ul>
        </section>
      </div>

      <div className="dash-row">
        <section className="dash-panel dash-main" aria-label="Recent tickets">
          <header>
            <div>
              <h2>Recent tickets</h2>
              <p>Latest updates across the workspace</p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onNavigate("workspace")}
            >
              All tickets <ArrowUpRight size={13} />
            </Button>
          </header>
          {data.recent_tickets.length ? (
            <ul className="dash-tickets">
              {data.recent_tickets.slice(0, 5).map((ticket) => (
                <li key={ticket.id}>
                  <button onClick={() => onTicket(ticket)}>
                    <span className="dash-queue-text">
                      <strong>{ticket.subject}</strong>
                      <span>
                        {ticket.assignee || "Unassigned"} ·{" "}
                        {dateTime(ticket.updated_at || ticket.created_at)}
                      </span>
                    </span>
                    <StateBadge value={ticket.status} />
                    {ticket.priority !== "normal" && (
                      <StateBadge value={ticket.priority} />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="dash-empty">No tickets yet.</p>
          )}
        </section>
        <section className="dash-panel" aria-label="GitHub activity">
          <header>
            <div>
              <h2>GitHub activity</h2>
              <p>Pushes, PRs, issues, failed checks</p>
            </div>
          </header>
          {mission?.inbox.length ? (
            <ul className="dash-feed">
              {mission.inbox.slice(0, 6).map((event) => (
                <li key={event.id}>
                  <strong>{event.title}</strong>
                  <span>{event.detail}</span>
                  <time>{age(event.created_at)}</time>
                </li>
              ))}
            </ul>
          ) : (
            <p className="dash-empty">
              No events yet. Add the repository webhook to stream activity here.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}

function ActivityChart({ trends }: { trends: Operations["trends"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(
    1,
    ...trends.flatMap((d) => [d.tickets, d.investigations]),
  );
  const label = (date: string) =>
    new Date(date + "T00:00:00Z").toLocaleDateString([], {
      weekday: "short",
      timeZone: "UTC",
    });
  const total = trends.reduce(
    (sum, d) => sum + d.tickets + d.investigations,
    0,
  );
  return (
    <section className="dash-panel dash-main" aria-label="Activity">
      <header>
        <div>
          <h2>Activity</h2>
          <p>Last 7 days (UTC) · {total} events</p>
        </div>
        <div className="dash-legend">
          <span>
            <i className="s1" />
            Tickets created
          </span>
          <span>
            <i className="s2" />
            Investigations
          </span>
        </div>
      </header>
      <div className="dash-chart" onMouseLeave={() => setHover(null)}>
        <div className="dash-chart-axis" aria-hidden="true">
          <span>{max}</span>
          <span>0</span>
        </div>
        <div className="dash-chart-plot" aria-hidden="true">
          {trends.map((day, index) => (
            <div
              key={day.date}
              className={"dash-chart-day" + (hover === index ? " hover" : "")}
              onMouseEnter={() => setHover(index)}
            >
              <div className="dash-bars">
                <span
                  className="s1"
                  style={{ height: `${(day.tickets / max) * 100}%` }}
                />
                <span
                  className="s2"
                  style={{ height: `${(day.investigations / max) * 100}%` }}
                />
              </div>
              <small>{label(day.date)}</small>
              {hover === index && (
                <div className="dash-tooltip" role="presentation">
                  <strong>
                    {label(day.date)} · {day.date}
                  </strong>
                  <span>
                    <i className="s1" />
                    Tickets {day.tickets}
                  </span>
                  <span>
                    <i className="s2" />
                    Investigations {day.investigations}
                  </span>
                  {!!(day.approved || day.rejected) && (
                    <span>
                      Reviews {day.approved} approved · {day.rejected} rejected
                    </span>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
        <table className="sr-only">
          <caption>Tickets and investigations per day</caption>
          <thead>
            <tr>
              <th>Day</th>
              <th>Tickets created</th>
              <th>Investigations</th>
            </tr>
          </thead>
          <tbody>
            {trends.map((day) => (
              <tr key={day.date}>
                <td>{day.date}</td>
                <td>{day.tickets}</td>
                <td>{day.investigations}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
