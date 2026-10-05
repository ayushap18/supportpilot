import { ArrowUpRight, ShieldCheck } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { Operations } from "../types";
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
