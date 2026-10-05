export type Repository = {
  id: string | number;
  full_name: string;
  description?: string | null;
  private?: boolean;
  default_branch?: string;
  html_url?: string;
  updated_at?: string;
};
export type GitHubStatus = {
  configured: boolean;
  connected: boolean;
  login?: string;
  scopes?: string[] | string;
  missing?: string[];
};
export type CommitDetail = {
  sha: string;
  message: string;
  html_url?: string;
  stats: { total: number; additions: number; deletions: number };
  files: {
    filename: string;
    status: string;
    additions: number;
    deletions: number;
    patch: string | null;
    patch_truncated: boolean;
    patch_available: boolean;
  }[];
  limits: { files_truncated: boolean; upstream_may_have_more: boolean };
};
export type Snapshot = {
  activity?: {
    id: string;
    type: string;
    actor: string;
    created_at: string;
    summary: string;
  }[];
  repo: Repository;
  commits: {
    sha: string;
    message: string;
    author?: string;
    date?: string;
    html_url?: string;
  }[];
  issues: {
    number: number;
    title: string;
    state: string;
    html_url?: string;
    author?: string;
  }[];
  contributors: { login: string; contributions: number; html_url?: string }[];
  files: (string | { path: string })[];
  docs: { path: string; content?: string; size?: number }[];
  analysis: string | Record<string, unknown>;
  limits?: Record<string, unknown>;
};
export type AgentProvider = {
  id: string;
  name: string;
  execution?: string;
  capabilities?: string[];
  usage_support?: string;
  setup?: string;
};
export type AgentRun = {
  id: string;
  provider: string;
  task: string;
  status: string;
  model?: string | null;
  repository_full_name?: string | null;
  ticket_id?: string | null;
  created_at: string;
  updated_at?: string;
  result?: string | Record<string, unknown> | null;
  error?: string | null;
  artifacts?: (string | Record<string, unknown>)[];
  usage?: {
    input_tokens?: number | null;
    output_tokens?: number | null;
    cost_usd?: number | null;
  };
};
export type AgentUsage = {
  runs: number;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  reported_input_tokens_runs?: number;
  reported_output_tokens_runs?: number;
  reported_cost_runs: number;
  unreported_cost_runs: number;
};
export function githubUrl(value?: string) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "github.com"
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}
