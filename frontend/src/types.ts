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
