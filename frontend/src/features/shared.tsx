import type { ReactNode } from "react";
import { Inbox } from "lucide-react";
import { Badge } from "@/components/ui/badge";
export const dateTime = (value: string) =>
  new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
export const words = (value: string) => value.replaceAll("_", " ");
export function StateBadge({ value }: { value: string }) {
  return (
    <Badge variant="outline" className={"state-badge state-" + value}>
      {words(value).replace(/\bcli\b/gi, "CLI")}
    </Badge>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty-block">
      <span className="empty-icon">
        <Inbox size={24} />
      </span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function SectionHeading({
  title,
  detail,
  action,
}: {
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-heading">
      <div>
        <h2>{title}</h2>
        {detail && <p>{detail}</p>}
      </div>
      {action}
    </div>
  );
}
