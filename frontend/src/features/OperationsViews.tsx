import {
  ArrowUpRight,
  BookOpen,
  CheckCheck,
  ClipboardCheck,
  Clock3,
  Inbox,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { Metrics, Operations, QueueTicket } from "../types";
import { dateTime, Empty, SectionHeading, StateBadge, words } from "./shared";
export function ActivityList({
  data,
  onTicket,
}: {
  data: Operations;
  onTicket: (id: string) => void;
}) {
  return data.activity.length ? (
    <div className="activity-list">
      {data.activity.map((event) => (
        <div className="activity-row" key={event.id}>
          <span className="event-dot" />
          <div>
            <strong>{event.title}</strong>
            <p>{event.detail}</p>
            {event.ticket_id && (
              <button
                className="text-action"
                onClick={() => onTicket(event.ticket_id!)}
              >
                Open ticket <ArrowUpRight size={12} />
              </button>
            )}
          </div>
          <time>{dateTime(event.created_at)}</time>
        </div>
      ))}
    </div>
  ) : (
    <Empty title="Your team's work starts here">
      Ticket changes, investigations and reviews will appear in this activity
      feed.
    </Empty>
  );
}
function duration(minutes: number) {
  if (minutes < 1) return "<1 min";
  if (minutes < 90) return Math.round(minutes) + " min";
  if (minutes < 60 * 48) return (minutes / 60).toFixed(1) + " h";
  return (minutes / 1440).toFixed(1) + " d";
}

function TeamMetrics({ metrics }: { metrics: Metrics }) {
  const items = [
    {
      label: "Approval rate",
      value:
        metrics.approval_rate == null
          ? "—"
          : Math.round(metrics.approval_rate * 100) + "%",
      detail: `${metrics.reviews} review decision${metrics.reviews === 1 ? "" : "s"}`,
    },
    {
      label: "Median time to first draft",
      value:
        metrics.median_first_draft_minutes == null
          ? "—"
          : duration(metrics.median_first_draft_minutes),
      detail: `${metrics.drafted_tickets} drafted ticket${metrics.drafted_tickets === 1 ? "" : "s"}`,
    },
    {
      label: "Median time to resolution",
      value:
        metrics.median_resolution_hours == null
          ? "—"
          : duration(metrics.median_resolution_hours * 60),
      detail: `${metrics.resolved_tickets} resolved · measured to last update`,
    },
  ];
  return (
    <section className="team-metrics" aria-label="Team performance">
      {items.map((item) => (
        <div key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
          <small>{item.detail}</small>
        </div>
      ))}
    </section>
  );
}

export function Overview({
  data,
  onTicket,
  onQueue,
  onKnowledge,
}: {
  data: Operations;
  onTicket: (ticket: QueueTicket) => void;
  onQueue: (review?: boolean) => void;
  onKnowledge: () => void;
}) {
  const stats = [
    {
      label: "Active tickets",
      value: data.counts.open + data.counts.in_progress,
      detail: `${data.counts.open} open · ${data.counts.in_progress} in progress`,
      icon: Inbox,
      action: () => onQueue(),
    },
    {
      label: "Awaiting review",
      value: data.counts.awaiting_review,
      detail: "Drafts ready for a human decision",
      icon: ClipboardCheck,
      action: () => onQueue(true),
    },
    {
      label: "Waiting for context",
      value: data.counts.waiting,
      detail: "Tickets marked as waiting",
      icon: Clock3,
      action: () => onQueue(),
    },
    {
      label: "Resolved tickets",
      value: data.counts.resolved,
      detail: "Explicitly resolved by your team",
      icon: CheckCheck,
      action: () => onQueue(),
    },
  ];
  const max = Math.max(
    1,
    ...data.trends.flatMap((day) => [day.tickets, day.investigations]),
  );
  return (
    <>
      <div className="metric-grid">
        {stats.map((stat) => (
          <Card key={stat.label} className="metric-card">
            <CardContent>
              <div className="metric-top">
                <span>{stat.label}</span>
                <stat.icon size={17} />
              </div>
              <button className="metric-number" onClick={stat.action}>
                {stat.value}
                <ArrowUpRight size={19} />
              </button>
              <p>{stat.detail}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      {data.metrics && <TeamMetrics metrics={data.metrics} />}
      <div className="overview-grid">
        <Card className="trend-panel">
          <CardContent>
            <SectionHeading
              title="Workspace activity"
              detail="Tickets and investigations · last 7 UTC days"
            />
            <div className="chart-legend">
              <span>
                <i className="legend-ticket" />
                Tickets created
              </span>
              <span>
                <i className="legend-run" />
                Investigations
              </span>
            </div>
            <div
              className="trend-chart"
              role="img"
              aria-label={data.trends
                .map(
                  (day) =>
                    `${day.date}: ${day.tickets} tickets, ${day.investigations} investigations`,
                )
                .join("; ")}
            >
              {data.trends.map((day) => (
                <div className="chart-day" key={day.date}>
                  <div className="chart-bars">
                    <svg
                      viewBox="0 0 60 140"
                      preserveAspectRatio="none"
                      aria-hidden="true"
                    >
                      <rect
                        x="9"
                        y={140 - (day.tickets / max) * 126}
                        width="17"
                        height={(day.tickets / max) * 126 || 2}
                        rx="3"
                        fill="#73e2bc"
                      />
                      <rect
                        x="32"
                        y={140 - (day.investigations / max) * 126}
                        width="17"
                        height={(day.investigations / max) * 126 || 2}
                        rx="3"
                        fill="#516879"
                      />
                    </svg>
                  </div>
                  <span>
                    {new Date(day.date + "T00:00:00Z").toLocaleDateString([], {
                      weekday: "short",
                      timeZone: "UTC",
                    })}
                  </span>
                  <small>
                    {day.tickets} / {day.investigations}
                  </small>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <SectionHeading
              title="Workspace health"
              detail="Configuration and operational signals"
            />
            <div className="health-item">
              <span>
                <BookOpen size={17} />
                Searchable documents
              </span>
              <strong>{data.counts.knowledge_documents}</strong>
            </div>
            <div className="health-item">
              <span>
                <ShieldCheck size={17} />
                Execution mode
              </span>
              <StateBadge value={data.mode === "fixture" ? "demo" : "live"} />
            </div>
            <div className="health-item">
              <span>Failed investigations</span>
              <strong>{data.counts.failed_investigations}</strong>
            </div>
            <p className="muted small">
              {data.mode === "fixture"
                ? "Demo data and deterministic responses. Add your own documentation to test retrieval."
                : "Live responses use your workspace knowledge. Account and service integrations are not connected."}
            </p>
            <Button variant="outline" onClick={onKnowledge}>
              Manage knowledge <ArrowUpRight size={15} />
            </Button>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardContent>
          <SectionHeading
            title="Recent tickets"
            detail="Latest work across your workspace"
            action={
              <Button variant="ghost" onClick={() => onQueue()}>
                View all tickets <ArrowUpRight size={15} />
              </Button>
            }
          />
          {data.recent_tickets.length ? (
            <div className="ticket-table">
              <div className="ticket-table-head">
                <span>Ticket</span>
                <span>Status</span>
                <span>Priority</span>
                <span>Owner</span>
              </div>
              {data.recent_tickets.map((ticket) => (
                <button
                  className="ticket-table-row"
                  key={ticket.id}
                  onClick={() => onTicket(ticket)}
                >
                  <span>
                    <strong>{ticket.subject}</strong>
                    <small>
                      {ticket.id.slice(0, 8)} · {dateTime(ticket.created_at)}
                    </small>
                  </span>
                  <StateBadge value={ticket.status} />
                  <StateBadge value={ticket.priority} />
                  <span className="muted">
                    {ticket.assignee || "Unassigned"}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <Empty title="No tickets yet">
              Create your first ticket to build a searchable history of support
              work.
            </Empty>
          )}
        </CardContent>
      </Card>
    </>
  );
}
export function WorkspaceView({ data }: { data: Operations }) {
  return (
    <div className="workspace-grid">
      <Card>
        <CardContent>
          <SectionHeading
            title="Workspace configuration"
            detail="Settings supplied by your server administrator"
          />
          <dl className="settings-list">
            {[
              ["Workspace", data.workspace_id],
              ["Your identity", data.reviewer_id],
              ["Your role", data.role],
              [
                "Model",
                data.mode === "fixture"
                  ? "Deterministic fixture engine"
                  : data.model,
              ],
              ["Tools", data.tool_mode],
              ["Data retention", `${data.retention_days} days`],
              [
                "Investigation timeout",
                `${data.limits.timeout_seconds} seconds`,
              ],
              ["Model rounds", data.limits.max_rounds],
              ["Tool calls per investigation", data.limits.max_tool_calls],
              [
                "Investigations per hour",
                data.limits.max_investigations_per_hour,
              ],
            ].map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{words(String(value))}</dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
      <Card>
        <CardContent>
          <SectionHeading
            title="Team members"
            detail="Configured identities in this workspace"
          />
          <div className="members-list">
            {data.members.map((member) => (
              <div key={member.reviewer_id}>
                <span className="avatar">
                  {member.reviewer_id.slice(0, 2).toUpperCase()}
                </span>
                <strong>{member.reviewer_id}</strong>
                <StateBadge value={member.role} />
              </div>
            ))}
          </div>
          <p className="muted small">
            An administrator manages access on the server. Credentials are never
            displayed here.
          </p>
        </CardContent>
      </Card>
      <Card className="readiness-panel">
        <CardContent>
          <SectionHeading
            title="Readiness checks"
            detail="What is available now and what needs configuration"
          />
          {data.readiness.map((check) => (
            <div className="readiness-row" key={check.id}>
              <ShieldCheck size={18} />
              <div>
                <strong>{check.label}</strong>
                <p>{check.detail}</p>
              </div>
              <StateBadge value={check.status} />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
