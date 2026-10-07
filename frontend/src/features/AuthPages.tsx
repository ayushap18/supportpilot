import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ArrowRight,
  BookOpen,
  Check,
  ClipboardCheck,
  Copy,
  FileText,
  GitBranch,
  KeyRound,
  Layers3,
  LoaderCircle,
  Lock,
  RotateCcw,
  Search,
  ShieldCheck,
  Terminal,
  TriangleAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type AuthPage = "home" | "signup" | "signin" | "regenerate" | "token";
type Invite = {
  id: string;
  workspace_id: string;
  repository: string | null;
  role: string;
  invited_by: string;
};
type Session = {
  login: string | null;
  can_regenerate: boolean;
  invites: Invite[];
  workspaces: { workspace_id: string; repository: string; role: string }[];
};
type Repo = {
  id: number;
  full_name: string;
  private: boolean;
  description: string | null;
};
type Issued = {
  token: string;
  repository: string;
  role: string;
  regenerated: boolean;
};

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch("/api/auth" + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string" ? data.detail : "Request failed.",
    );
  return data;
}

export function usePage(): [AuthPage, (page: AuthPage) => void] {
  const read = (): AuthPage => {
    const hash = window.location.hash.slice(1);
    return ["signup", "signin", "regenerate", "token"].includes(hash)
      ? (hash as AuthPage)
      : "home";
  };
  const [page, setPage] = useState<AuthPage>(read);
  useEffect(() => {
    const sync = () => {
      setPage(read());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  return [
    page,
    (next) => {
      setPage(next);
      if (read() !== next) window.location.hash = next === "home" ? "" : next;
    },
  ];
}

const GitHubMark = ({ size = 16 }: { size?: number }) => (
  <svg
    viewBox="0 0 16 16"
    width={size}
    height={size}
    aria-hidden="true"
    fill="currentColor"
  >
    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
  </svg>
);

const Brand = () => (
  <a className="brand" href="#" aria-label="SupportPilot home">
    <span className="brand-mark">
      <Layers3 size={18} />
    </span>
    SupportPilot
  </a>
);

const FEATURES = [
  {
    icon: FileText,
    title: "Cited drafts",
    text: "Every investigation retrieves version-aware docs and links the exact sources behind each answer.",
  },
  {
    icon: GitBranch,
    title: "Repository context",
    text: "Commits, issues, contributors, and docs from the repository you choose, synced as bounded snapshots.",
  },
  {
    icon: Terminal,
    title: "Coding agents",
    text: "Hand a ticket to Codex, Claude Code, or Antigravity through a local bridge. Results and usage come back here.",
  },
  {
    icon: ClipboardCheck,
    title: "Human review",
    text: "Nothing reaches a customer automatically. Approve or reject the exact draft revision.",
  },
  {
    icon: BookOpen,
    title: "Knowledge base",
    text: "Upload Markdown or import repository docs. Versioned, searchable, and archivable.",
  },
  {
    icon: ShieldCheck,
    title: "Scoped access",
    text: "Workspaces are tied to repositories you can push to. Tokens are stored only as hashes.",
  },
];

const STORY = {
  signup: {
    chip: "Create a workspace",
    title: "Start with a repository.",
    text: "Verify with GitHub, choose the repository your team supports, and get a workspace token in under a minute.",
    steps: [
      "Verify with GitHub",
      "Choose a repository",
      "Save your workspace token",
    ],
  },
  signin: {
    chip: "Welcome back",
    title: "Resolve with evidence.",
    text: "Verify with GitHub, choose your workspace, then enter its token to open the dashboard.",
    steps: ["Verify with GitHub", "Choose your workspace", "Enter its token"],
  },
  regenerate: {
    chip: "Recover access",
    title: "Lost your token?",
    text: "Re-authorize with GitHub to prove it is you. Then pick the workspace whose token you want to replace.",
    steps: [
      "Re-authorize with GitHub",
      "Choose the workspace",
      "Save the new token",
    ],
  },
  token: {
    chip: "Server token",
    title: "Resolve with evidence.",
    text: "Connect with a token configured on the server by an administrator.",
    steps: ["Paste the token", "Open the dashboard"],
  },
};

export function AuthPages({
  page,
  go,
  github,
  mode,
  error,
  busy,
  onToken,
  remember,
  onRemember,
}: {
  page: AuthPage;
  go: (page: AuthPage) => void;
  github: boolean;
  mode: "fixture" | "live";
  error: string;
  busy: boolean;
  onToken: (token: string) => Promise<void>;
  remember: boolean;
  onRemember: (remember: boolean) => void;
}) {
  if (page === "home") return <Landing go={go} mode={mode} />;
  const story = STORY[page];
  return (
    <div className="auth-shell">
      <section className="auth-story" aria-label="About SupportPilot">
        <Brand />
        <div className="auth-copy">
          <span className="auth-chip">
            <span className="status-dot" />
            {story.chip}
          </span>
          <h1>{story.title}</h1>
          <p>{story.text}</p>
          <ol className="auth-steps">
            {story.steps.map((step, i) => (
              <li key={step}>
                <span>{i + 1}</span>
                {step}
              </li>
            ))}
          </ol>
        </div>
        <span className="auth-foot">
          <ShieldCheck size={14} /> Tokens are stored only as hashes and shown
          once.
        </span>
      </section>
      <section className="auth-panel">
        <div className="auth-form">
          {error && <InlineError message={error} />}
          {page === "token" ? (
            <TokenOnly busy={busy} onToken={onToken} go={go} />
          ) : (
            <GitHubFlow
              key={page}
              page={page}
              github={github}
              busy={busy}
              onToken={onToken}
              go={go}
            />
          )}
          <label className="checkbox-row remember-row">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => onRemember(e.target.checked)}
            />
            <span>
              Keep me signed in on this device
              <small>Off: you stay signed in until this tab closes.</small>
            </span>
          </label>
        </div>
      </section>
    </div>
  );
}

const TOUR = [
  {
    id: "dashboard",
    label: "Dashboard",
    title: "What needs you, at a glance",
    text: "Open tickets, drafts to decide, agent results to review, and failures, each one click from the work.",
    src: "/tour-dashboard.jpg",
    alt: "SupportPilot overview dashboard with key numbers, a needs-attention queue, the agent pipeline, and an activity chart",
  },
  {
    id: "mission",
    label: "Mission control",
    title: "Every agent run, from queue to review",
    text: "A live pipeline, a work queue ordered by age, agent reliability by provider, and a review desk with test evidence.",
    src: "/tour-mission.jpg",
    alt: "Mission control showing the agent pipeline, work queue, and agent reliability",
  },
  {
    id: "agents",
    label: "Agent runs",
    title: "Runs you can trace",
    text: "Queued, started, finished, reviewed. Live logs while an agent works, results and token usage when it is done.",
    src: "/tour-agents.jpg",
    alt: "Agent run history and run details with a timeline from queued to reviewed",
  },
];

const AGENTS = [
  {
    name: "Claude Code",
    role: "Analysis and live investigations",
    text: "Runs with tools disabled for investigations, and restricted read-only tools for repository analysis.",
  },
  {
    name: "Codex",
    role: "Analysis and edits",
    text: "Read-only sandbox by default. With edits allowed, it works in a dedicated git worktree and can open a draft PR.",
  },
  {
    name: "Antigravity",
    role: "Edits in a worktree",
    text: "Headless and sandboxed in its own worktree. Blocked tool permissions are reported, never silently bypassed.",
  },
];

const TRUST = [
  {
    icon: KeyRound,
    title: "No API keys required",
    text: "Use the Claude Code, Codex, or Antigravity subscription you already have. Keys for the Claude or OpenAI API work too.",
  },
  {
    icon: Terminal,
    title: "Code stays on your machine",
    text: "The server never runs repository code. A runner you start locally executes agent work in your own checkout.",
  },
  {
    icon: ClipboardCheck,
    title: "A person always decides",
    text: "Drafts and agent results wait for review. Nothing is sent to customers or merged automatically.",
  },
  {
    icon: Lock,
    title: "Credentials handled carefully",
    text: "Workspace tokens are stored as hashes and shown once. GitHub tokens are encrypted. Secrets are redacted from logs and drafts.",
  },
];

const FAQ = [
  [
    "Do I need an OpenAI or Anthropic API key?",
    "No. In live mode SupportPilot can run each investigation through your logged-in Claude Code, Codex, or Antigravity CLI. API keys are optional.",
  ],
  [
    "What does SupportPilot read from GitHub?",
    "Only repositories you choose: commits, issues, contributors, docs, and GitHub Actions results. Issues labelled “support” can become tickets, and “incident” issues inform investigations.",
  ],
  [
    "Can an agent change my code?",
    "Only if you start a runner with --allow-edits. Edits happen in a separate git worktree on its own branch. Pushing and opening a draft PR are separate, explicit steps, and merging is always yours.",
  ],
  [
    "What happens if I lose my workspace token?",
    "Sign in, choose “Forgot your token?”, and re-authorize with GitHub. A new token replaces the old one immediately.",
  ],
  [
    "Can my team share a workspace?",
    "Yes. Admins invite teammates by GitHub username; each person accepts with their own GitHub account and gets their own token.",
  ],
] as const;

function Landing({ go, mode }: { go: (page: AuthPage) => void; mode: string }) {
  const [tab, setTab] = useState(TOUR[0].id);
  const active = TOUR.find((item) => item.id === tab)!;
  const nav = [
    ["product", "Product"],
    ["agents", "Agents"],
    ["security", "Security"],
    ["faq", "FAQ"],
  ];
  return (
    <div className="landing">
      <header className="landing-nav">
        <Brand />
        <nav aria-label="Sections">
          {nav.map(([id, label]) => (
            <a key={id} href={"#" + id} onClick={(e) => scrollTo(e, id)}>
              {label}
            </a>
          ))}
          <a
            href="https://github.com/ayushap18/supportpilot"
            target="_blank"
            rel="noreferrer"
          >
            GitHub
          </a>
        </nav>
        <div className="landing-actions">
          <Button variant="ghost" size="sm" onClick={() => go("signin")}>
            Sign in
          </Button>
          <Button size="sm" className="primary" onClick={() => go("signup")}>
            Sign up
          </Button>
        </div>
      </header>

      <section className="hero">
        <span className="auth-chip">
          <span className="status-dot" />
          {mode === "fixture"
            ? "Demo mode · deterministic fixtures"
            : "Live · runs on the agents you already use"}
        </span>
        <h1>
          Support answers,{" "}
          <br />
          backed by evidence.
        </h1>
        <p>
          SupportPilot investigates tickets against your docs and your GitHub
          repository, hands code work to Claude Code, Codex, or Antigravity, and
          keeps every decision with your team.
        </p>
        <div className="hero-actions">
          <Button className="primary hero-cta" onClick={() => go("signup")}>
            <GitHubMark />
            Sign up with GitHub
          </Button>
          <Button
            variant="outline"
            className="hero-secondary"
            onClick={() => go("signin")}
          >
            Sign in
            <ArrowRight size={16} />
          </Button>
        </div>
        <p className="hero-note">
          No API keys · Code stays on your machine · Human review built in
        </p>
        <ul className="works-with" aria-label="Works with">
          <li>
            <GitHubMark /> GitHub
          </li>
          {AGENTS.map((agent) => (
            <li key={agent.name}>
              <Terminal size={15} /> {agent.name}
            </li>
          ))}
        </ul>
      </section>

      <section
        className="landing-section tour"
        id="product"
        aria-labelledby="tour-title"
      >
        <span className="section-kicker">Product</span>
        <h2 id="tour-title">One workspace from ticket to reviewed fix.</h2>
        <div className="tour-tabs" role="tablist" aria-label="Product tour">
          {TOUR.map((item) => (
            <button
              key={item.id}
              role="tab"
              id={"tour-tab-" + item.id}
              aria-selected={tab === item.id}
              aria-controls="tour-panel"
              className={tab === item.id ? "active" : ""}
              onClick={() => setTab(item.id)}
            >
              <strong>{item.label}</strong>
              <span>{item.title}</span>
            </button>
          ))}
        </div>
        <div
          className="tour-panel"
          role="tabpanel"
          id="tour-panel"
          aria-labelledby={"tour-tab-" + active.id}
        >
          <p>{active.text}</p>
          <div className="hero-frame">
            <img
              key={active.id}
              src={active.src}
              alt={active.alt}
              loading="lazy"
            />
          </div>
        </div>
      </section>

      <section
        className="landing-section"
        id="features"
        aria-labelledby="features-title"
      >
        <span className="section-kicker">Features</span>
        <h2 id="features-title">
          Everything between a ticket and a reviewed answer.
        </h2>
        <div className="feature-grid">
          {FEATURES.map((f) => (
            <article key={f.title} className="feature-card">
              <f.icon size={18} />
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section
        className="landing-section"
        id="agents"
        aria-labelledby="agents-title"
      >
        <span className="section-kicker">Bring your own agents</span>
        <h2 id="agents-title">
          Use the coding agents your team already pays for.
        </h2>
        <div className="agent-grid">
          {AGENTS.map((agent) => (
            <article key={agent.name} className="agent-card">
              <span className="agent-icon">
                <Terminal size={18} />
              </span>
              <h3>{agent.name}</h3>
              <span className="agent-role">{agent.role}</span>
              <p>{agent.text}</p>
            </article>
          ))}
        </div>
        <pre className="agent-command" aria-label="Start a runner">
          <code>
            <span className="prompt">$</span> python -m supportpilot.cli_bridge
            login --repository .{"\n"}
            <span className="prompt">$</span> python -m supportpilot.cli_bridge
            watch --repository . --allow-edits{"\n"}
            <span className="muted-line">
              Watching for queued runs · providers: codex, claude_code,
              antigravity
            </span>
          </code>
        </pre>
      </section>

      <section className="landing-section" id="how" aria-labelledby="how-title">
        <span className="section-kicker">How it works</span>
        <h2 id="how-title">From GitHub to your dashboard in three steps.</h2>
        <div className="how-grid">
          {[
            [
              "Sign up with GitHub",
              "Authorize SupportPilot. Only repositories you can push to are listed.",
            ],
            [
              "Choose a repository",
              "A workspace is created and connected to that repository.",
            ],
            [
              "Start a runner",
              "Save your token once with login, then watch. Queued agent runs start on your machine.",
            ],
          ].map(([title, text], i) => (
            <div className="how-step" key={title}>
              <span>{String(i + 1).padStart(2, "0")}</span>
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
          ))}
        </div>
      </section>

      <section
        className="landing-section"
        id="security"
        aria-labelledby="security-title"
      >
        <span className="section-kicker">Security</span>
        <h2 id="security-title">
          Built to be trusted with your code and your customers.
        </h2>
        <div className="trust-grid">
          {TRUST.map((item) => (
            <div key={item.title} className="trust-item">
              <item.icon size={18} />
              <div>
                <h3>{item.title}</h3>
                <p>{item.text}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section
        className="landing-section faq"
        id="faq"
        aria-labelledby="faq-title"
      >
        <span className="section-kicker">FAQ</span>
        <h2 id="faq-title">Questions teams ask first.</h2>
        <div className="faq-list">
          {FAQ.map(([question, answer]) => (
            <details key={question}>
              <summary>{question}</summary>
              <p>{answer}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="landing-cta">
        <h2>Give your support team evidence, and your agents a review desk.</h2>
        <div className="hero-actions">
          <Button className="primary hero-cta" onClick={() => go("signup")}>
            <GitHubMark />
            Get started
          </Button>
          <Button variant="ghost" onClick={() => go("signin")}>
            I already have a workspace
          </Button>
        </div>
      </section>

      <footer className="landing-footer">
        <div className="footer-brand">
          <Brand />
          <p>Evidence grounded. Human reviewed.</p>
        </div>
        <nav aria-label="Footer">
          <div>
            <strong>Product</strong>
            <a href="#product" onClick={(e) => scrollTo(e, "product")}>
              Tour
            </a>
            <a href="#features" onClick={(e) => scrollTo(e, "features")}>
              Features
            </a>
            <a href="#agents" onClick={(e) => scrollTo(e, "agents")}>
              Agents
            </a>
          </div>
          <div>
            <strong>Trust</strong>
            <a href="#security" onClick={(e) => scrollTo(e, "security")}>
              Security
            </a>
            <a href="#faq" onClick={(e) => scrollTo(e, "faq")}>
              FAQ
            </a>
          </div>
          <div>
            <strong>Project</strong>
            <a
              href="https://github.com/ayushap18/supportpilot"
              target="_blank"
              rel="noreferrer"
            >
              Source on GitHub
            </a>
            <a
              href="#signin"
              onClick={(e) => {
                e.preventDefault();
                go("signin");
              }}
            >
              Sign in
            </a>
          </div>
        </nav>
        <span className="footer-copy">
          © {new Date().getFullYear()} SupportPilot
        </span>
      </footer>
    </div>
  );
}

function scrollTo(event: React.MouseEvent, id: string) {
  event.preventDefault();
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
}

function StepHeading({ title, detail }: { title: string; detail: ReactNode }) {
  return (
    <>
      <h2>{title}</h2>
      <p>{detail}</p>
    </>
  );
}

const githubStart = (intent: "signin" | "signup" | "regenerate") =>
  "/api/auth/github/start?intent=" + intent;

function GitHubFlow({
  page,
  github,
  busy,
  onToken,
  go,
}: {
  page: "signin" | "signup" | "regenerate";
  github: boolean;
  busy: boolean;
  onToken: (token: string) => Promise<void>;
  go: (page: AuthPage) => void;
}) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [issued, setIssued] = useState<Issued | null>(null);
  const [chosen, setChosen] = useState("");
  const [entry, setEntry] = useState("");
  const [working, setWorking] = useState("");

  async function refresh() {
    const data = await call<Session>("/session");
    setSession(data.login ? data : null);
    setChosen((old) => old || data.workspaces[0]?.workspace_id || "");
  }
  useEffect(() => {
    refresh()
      .catch(() => setSession(null))
      .finally(() => setLoading(false));
  }, []);

  async function run(key: string, path: string, body?: object) {
    setWorking(key);
    setError("");
    try {
      setIssued(
        await call<Issued>(path, {
          method: "POST",
          body: body ? JSON.stringify(body) : undefined,
        }),
      );
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking("");
    }
  }

  async function verify(event: FormEvent) {
    event.preventDefault();
    const token = entry.trim();
    setWorking("verify");
    setError("");
    try {
      await call("/verify", {
        method: "POST",
        body: JSON.stringify({ token, workspace_id: chosen || null }),
      });
      await onToken(token);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking("");
    }
  }

  async function signOut() {
    await call("/session", { method: "DELETE" }).catch(() => undefined);
    setSession(null);
    setIssued(null);
  }

  if (loading)
    return (
      <p className="picker-hint">
        <LoaderCircle size={14} className="spin" /> Checking your session…
      </p>
    );

  const authorize = (title: string, detail: string) => (
    <>
      <StepHeading title={title} detail={detail} />
      {github ? (
        <a className="github-button" href={githubStart(page)}>
          <GitHubMark />
          {page === "regenerate"
            ? "Re-authorize with GitHub"
            : "Continue with GitHub"}
        </a>
      ) : (
        <p className="github-unavailable">
          <GitHubMark /> GitHub sign-in needs an OAuth App on the server. See
          docs/GITHUB_SETUP.md.
        </p>
      )}
      <SwitchLinks page={page} go={go} />
    </>
  );

  if (!session)
    return page === "signup"
      ? authorize(
          "Create your workspace",
          "Step 1 of 3 · Verify your identity with GitHub.",
        )
      : page === "signin"
        ? authorize(
            "Sign in to SupportPilot",
            "Step 1 of 3 · Verify your identity with GitHub.",
          )
        : authorize(
            "Regenerate a workspace token",
            "For your security, regenerating always needs a fresh GitHub authorization.",
          );

  if (page === "regenerate" && !session.can_regenerate)
    return authorize(
      "Re-authorize to continue",
      `Signed in as @${session.login}, but regenerating needs a fresh GitHub authorization (valid for 10 minutes).`,
    );

  const identity = (
    <div className="github-identity">
      <GitHubMark />
      <span>
        Verified as <strong>@{session.login}</strong>
      </span>
      <Button variant="ghost" size="sm" onClick={signOut}>
        Sign out
      </Button>
    </div>
  );

  if (issued)
    return (
      <div className="token-reveal" role="status">
        <span className="token-reveal-icon">
          <KeyRound size={18} />
        </span>
        <h3>{issued.regenerated ? "Token regenerated" : "Workspace ready"}</h3>
        <p>
          <strong>{issued.repository}</strong> ·{" "}
          {issued.role === "admin" ? "admin" : "member"} access.{" "}
          {issued.regenerated && "Your previous token no longer works. "}
          Copy this token now. It is shown only once.
        </p>
        <CopyToken token={issued.token} />
        <small>
          Lost it later? Use “Forgot your token?” on the sign-in page.
        </small>
        <Button
          className="primary"
          disabled={busy}
          onClick={() => onToken(issued.token)}
        >
          {busy ? (
            <LoaderCircle size={16} className="spin" />
          ) : (
            <ArrowRight size={16} />
          )}
          Continue to dashboard
        </Button>
      </div>
    );

  const invitations = (
    <Invitations
      invites={session.invites || []}
      working={working}
      onAccept={(invite) => run(invite.id, `/invites/${invite.id}/accept`)}
    />
  );

  if (page === "signup")
    return (
      <>
        <StepHeading
          title="Choose a repository"
          detail="Step 2 of 3 · A workspace is created for the repository you select."
        />
        {identity}
        {error && <InlineError message={error} />}
        {invitations}
        <RepoPicker
          joined={new Set(session.workspaces.map((w) => w.repository))}
          working={working}
          onPick={(full_name) => run(full_name, "/workspaces", { full_name })}
        />
        <SwitchLinks page={page} go={go} />
      </>
    );

  if (!session.workspaces.length)
    return (
      <>
        <StepHeading
          title="No workspaces yet"
          detail={`@${session.login} has not created or joined a workspace.`}
        />
        {identity}
        {error && <InlineError message={error} />}
        {invitations}
        <Button className="primary" onClick={() => go("signup")}>
          <ArrowRight size={16} />
          Create a workspace
        </Button>
      </>
    );

  if (page === "regenerate")
    return (
      <>
        <StepHeading
          title="Choose a workspace"
          detail="Step 2 of 3 · The new token replaces the old one immediately."
        />
        {identity}
        {error && <InlineError message={error} />}
        <div className="repo-list" aria-label="Your workspaces">
          {session.workspaces.map((w) => (
            <div className="repo-row" key={w.workspace_id}>
              <GitBranch size={15} />
              <div>
                <strong>{w.repository}</strong>
                <span>{w.role === "admin" ? "Admin" : "Member"} access</span>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="danger-outline"
                disabled={!!working}
                aria-label={"Regenerate token for " + w.repository}
                onClick={() =>
                  run(
                    w.workspace_id,
                    `/workspaces/${w.workspace_id}/regenerate`,
                  )
                }
              >
                {working === w.workspace_id ? (
                  <LoaderCircle size={14} className="spin" />
                ) : (
                  <RotateCcw size={14} />
                )}
                Regenerate
              </Button>
            </div>
          ))}
        </div>
        <div className="switch-links">
          <button type="button" onClick={() => go("signin")}>
            Back to sign in
          </button>
        </div>
      </>
    );

  return (
    <>
      <StepHeading
        title="Choose your workspace"
        detail="Step 2 of 3 · Then enter the token you saved for it."
      />
      {identity}
      {error && <InlineError message={error} />}
      {invitations}
      <div
        className="repo-list workspace-choice"
        role="radiogroup"
        aria-label="Your workspaces"
      >
        {session.workspaces.map((w) => (
          <label className="repo-row" key={w.workspace_id}>
            <input
              type="radio"
              name="workspace"
              value={w.workspace_id}
              checked={chosen === w.workspace_id}
              onChange={() => setChosen(w.workspace_id)}
            />
            <div>
              <strong>{w.repository}</strong>
              <span>{w.role === "admin" ? "Admin" : "Member"} access</span>
            </div>
          </label>
        ))}
      </div>
      <form onSubmit={verify} className="token-step">
        <label htmlFor="workspace-token">Workspace token</label>
        <div className="token-field">
          <KeyRound size={16} />
          <Input
            id="workspace-token"
            type="password"
            autoComplete="off"
            required
            minLength={24}
            value={entry}
            onChange={(e) => setEntry(e.target.value)}
            placeholder="sp_••••••••••••••••••••••••"
          />
        </div>
        <Button className="primary" disabled={!!working || busy}>
          {working === "verify" || busy ? (
            <LoaderCircle size={16} className="spin" />
          ) : (
            <ArrowRight size={16} />
          )}
          Sign in
        </Button>
      </form>
      <div className="switch-links">
        <a href={githubStart("regenerate")}>Forgot your token?</a>
        <button type="button" onClick={() => go("signup")}>
          Create another workspace
        </button>
      </div>
    </>
  );
}

function Invitations({
  invites,
  working,
  onAccept,
}: {
  invites: Invite[];
  working: string;
  onAccept: (invite: Invite) => void;
}) {
  if (!invites.length) return null;
  return (
    <section className="invitations" aria-label="Invitations">
      <h3>You're invited</h3>
      {invites.map((invite) => (
        <div className="repo-row" key={invite.id}>
          <GitBranch size={15} />
          <div>
            <strong>{invite.repository || invite.workspace_id}</strong>
            <span>
              {invite.role === "admin" ? "Admin" : "Member"} access · invited by{" "}
              {invite.invited_by}
            </span>
          </div>
          <Button
            size="sm"
            disabled={!!working}
            aria-label={
              "Accept invitation to " +
              (invite.repository || invite.workspace_id)
            }
            onClick={() => onAccept(invite)}
          >
            {working === invite.id ? (
              <LoaderCircle size={14} className="spin" />
            ) : (
              "Accept"
            )}
          </Button>
        </div>
      ))}
    </section>
  );
}

function RepoPicker({
  joined,
  working,
  onPick,
}: {
  joined: Set<string>;
  working: string;
  onPick: (fullName: string) => void;
}) {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [page, setPage] = useState(1);
  const [more, setMore] = useState(false);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function load(next: number) {
    setLoading(true);
    try {
      const data = await call<{ items: Repo[]; has_more: boolean }>(
        "/repos?page=" + next,
      );
      setRepos((old) => (next === 1 ? data.items : [...old, ...data.items]));
      setPage(next);
      setMore(data.has_more);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load(1);
  }, []);

  const shown = repos.filter((r) =>
    r.full_name.toLowerCase().includes(filter.trim().toLowerCase()),
  );
  return (
    <div className="github-picker">
      {error && <InlineError message={error} />}
      <div className="picker-search">
        <Search size={14} />
        <Input
          aria-label="Filter repositories"
          placeholder="Filter repositories…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      <div className="repo-list">
        {shown.map((r) => {
          const member = joined.has(r.full_name);
          return (
            <div className="repo-row" key={r.id}>
              {r.private ? <Lock size={15} /> : <GitBranch size={15} />}
              <div>
                <strong>{r.full_name}</strong>
                {member ? (
                  <span>You already have this workspace · sign in instead</span>
                ) : (
                  r.description && <span>{r.description}</span>
                )}
              </div>
              {member ? (
                <span className="joined-badge">
                  <Check size={13} /> Joined
                </span>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!!working}
                  aria-label={"Select " + r.full_name}
                  onClick={() => onPick(r.full_name)}
                >
                  {working === r.full_name ? (
                    <LoaderCircle size={14} className="spin" />
                  ) : (
                    "Select"
                  )}
                </Button>
              )}
            </div>
          );
        })}
        {loading && (
          <p className="picker-hint padded">
            <LoaderCircle size={14} className="spin" /> Loading repositories…
          </p>
        )}
        {!shown.length && !loading && (
          <p className="picker-hint padded">
            No matching repositories you can push to.
          </p>
        )}
      </div>
      {more && (
        <Button
          variant="ghost"
          size="sm"
          disabled={loading}
          onClick={() => load(page + 1)}
        >
          Load more
        </Button>
      )}
    </div>
  );
}

function CopyToken({ token }: { token: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="token-value">
      <code aria-label="Workspace token value">{token}</code>
      <Button
        variant="outline"
        size="sm"
        onClick={async () => {
          await navigator.clipboard.writeText(token).catch(() => undefined);
          setCopied(true);
        }}
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
        {copied ? "Copied" : "Copy"}
      </Button>
    </div>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="alert error" role="alert">
      <TriangleAlert size={16} />
      {message}
    </div>
  );
}

function SwitchLinks({
  page,
  go,
}: {
  page: "signin" | "signup" | "regenerate";
  go: (p: AuthPage) => void;
}) {
  return (
    <div className="switch-links">
      {page === "regenerate" ? (
        <button type="button" onClick={() => go("signin")}>
          Back to sign in
        </button>
      ) : page === "signup" ? (
        <button type="button" onClick={() => go("signin")}>
          Already have a workspace? Sign in
        </button>
      ) : (
        <button type="button" onClick={() => go("signup")}>
          New here? Sign up
        </button>
      )}
      <button type="button" onClick={() => go("token")}>
        Use a server-issued token
      </button>
    </div>
  );
}

function TokenOnly({
  busy,
  onToken,
  go,
}: {
  busy: boolean;
  onToken: (token: string) => Promise<void>;
  go: (page: AuthPage) => void;
}) {
  const [entry, setEntry] = useState("");
  return (
    <>
      <StepHeading
        title="Connect with a workspace token"
        detail="For tokens configured on the server by an administrator."
      />
      <form
        className="token-step"
        onSubmit={async (e) => {
          e.preventDefault();
          await onToken(entry.trim());
        }}
      >
        <label htmlFor="workspace-token">Workspace token</label>
        <div className="token-field">
          <KeyRound size={16} />
          <Input
            id="workspace-token"
            type="password"
            autoComplete="off"
            required
            minLength={24}
            value={entry}
            onChange={(e) => setEntry(e.target.value)}
            placeholder="Paste your workspace token"
          />
        </div>
        <Button className="primary" disabled={busy}>
          {busy ? (
            <LoaderCircle size={16} className="spin" />
          ) : (
            <ArrowRight size={16} />
          )}
          Connect workspace
        </Button>
        <small>
          Saved for this tab. Tick “Keep me signed in” to remember it on this
          device.
        </small>
      </form>
      <div className="switch-links">
        <button type="button" onClick={() => go("signin")}>
          Sign in with GitHub instead
        </button>
      </div>
    </>
  );
}
