export type Outcome = "resolved" | "needs_information" | "escalate";
export type TicketInput = {
  subject: string;
  description: string;
  product_version: "v1" | "v2" | null;
  account_id: string | null;
  log: string;
};
export type Ticket = TicketInput & {
  id: string;
  workspace_id: string;
  status: "open" | "in_progress" | "waiting" | "resolved";
  priority: "low" | "normal" | "high" | "urgent";
  assignee: string | null;
  revision: number;
  updated_at: string | null;
  created_at: string;
};
export type Evidence = {
  id: string;
  kind: "document" | "tool";
  title: string;
  excerpt: string;
  source_path: string | null;
  product_version: string | null;
};
export type Investigation = {
  id: string;
  ticket_id: string;
  ticket_revision: number;
  state: "queued" | "running" | "awaiting_review" | "failed";
  draft_revision: number;
  created_at: string;
  mode: "fixture" | "live";
  latency_ms: number;
  draft: {
    outcome: Outcome;
    response: string;
    missing_information: string[];
    evidence_ids: string[];
  } | null;
  evidence: Evidence[];
  trace: {
    stage: string;
    summary: string;
    duration_ms: number;
    tool_arguments: Record<string, unknown> | null;
    tool_result: unknown;
  }[];
  usage: {
    model_rounds: number;
    tool_calls: number;
    input_tokens: number;
    output_tokens: number;
    estimated_cost_usd: number | null;
  };
  error: string | null;
};
export type Review = {
  id: string;
  decision: "approve" | "reject";
  note: string;
  reviewer_id: string;
  created_at: string;
  draft_revision: number;
};

export type QueueTicket = Ticket & {
  latest_investigation_id: string | null;
  latest_outcome: Outcome | null;
  review_status: "none" | "pending" | "approved" | "rejected" | "stale";
  investigation_state: string | null;
};
export type Note = {
  id: string;
  body: string;
  author_id: string;
  created_at: string;
};
export type KnowledgeDocument = {
  id: string;
  title: string;
  body: string;
  product_version: "v1" | "v2" | "any";
  source_path: string;
  revision: number;
  origin: "seed" | "workspace";
  chunk_count: number;
  updated_at: string | null;
  archived: boolean;
};
export type Metrics = {
  approval_rate: number | null;
  reviews: number;
  median_first_draft_minutes: number | null;
  drafted_tickets: number;
  median_resolution_hours: number | null;
  resolved_tickets: number;
};
export type Operations = {
  metrics?: Metrics;
  workspace_id: string;
  reviewer_id: string;
  role: "admin" | "agent";
  mode: "fixture" | "live";
  model: string;
  tool_mode: "synthetic" | "disabled";
  retention_days: number;
  limits: {
    max_rounds: number;
    max_tool_calls: number;
    timeout_seconds: number;
    max_investigations_per_hour: number;
  };
  counts: {
    tickets: number;
    open: number;
    in_progress: number;
    waiting: number;
    resolved: number;
    awaiting_review: number;
    failed_investigations: number;
    knowledge_documents: number;
  };
  trends: {
    date: string;
    tickets: number;
    investigations: number;
    approved: number;
    rejected: number;
    failed: number;
  }[];
  outcomes: { outcome: string; count: number }[];
  activity: {
    id: string;
    kind: string;
    title: string;
    detail: string;
    ticket_id: string | null;
    created_at: string;
  }[];
  recent_tickets: QueueTicket[];
  members: { reviewer_id: string; role: string }[];
  readiness: {
    id: string;
    label: string;
    status: "ready" | "pending" | "demo";
    detail: string;
  }[];
};
export type Api = <T>(
  path: string,
  options?: RequestInit,
  credential?: string,
) => Promise<T>;
