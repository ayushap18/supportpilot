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
type Session = {
  login: string | null;
  can_regenerate: boolean;
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
}: {
  page: AuthPage;
  go: (page: AuthPage) => void;
  github: boolean;
  mode: "fixture" | "live";
  error: string;
  busy: boolean;
  onToken: (token: string) => Promise<void>;
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
        </div>
      </section>
    </div>
  );
}

function Landing({ go, mode }: { go: (page: AuthPage) => void; mode: string }) {
  return (
    <div className="landing">
      <header className="landing-nav">
        <Brand />
        <nav aria-label="Sections">
          <a href="#features" onClick={(e) => scrollTo(e, "features")}>
            Features
          </a>
          <a href="#how" onClick={(e) => scrollTo(e, "how")}>
            How it works
          </a>
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
            : "Live model"}
        </span>
        <h1>Resolve with evidence.</h1>
        <p>
          SupportPilot investigates support tickets against your docs and your
          GitHub repository, drafts a cited answer, and keeps the final decision
          with your team.
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
        <div className="hero-frame">
          <img
            src="/product-overview.png"
            alt="SupportPilot dashboard showing ticket metrics, workspace activity, and health"
            width={1440}
            height={900}
          />
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

      <section className="landing-section" id="how" aria-labelledby="how-title">
        <span className="section-kicker">How it works</span>
        <h2 id="how-title">From GitHub to your dashboard in three steps.</h2>
        <div className="how-grid">
          {[
            [
              "Sign up with GitHub",
              "Authorize SupportPilot. We only list repositories you can push to.",
            ],
            [
              "Choose a repository",
              "A workspace is created and connected to that repository.",
            ],
            [
              "Save your token",
              "Your workspace token is shown once. Lost it? Regenerate after verifying with GitHub.",
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

      <section className="landing-cta">
        <h2>Ready to give your support team evidence?</h2>
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
        <span>© {new Date().getFullYear()} SupportPilot</span>
        <span>Evidence grounded · Human reviewed</span>
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

  if (page === "signup")
    return (
      <>
        <StepHeading
          title="Choose a repository"
          detail="Step 2 of 3 · A workspace is created for the repository you select."
        />
        {identity}
        {error && <InlineError message={error} />}
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
          detail={`@${session.login} has not created a workspace.`}
        />
        {identity}
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
        <small>Your token stays in memory and clears when you reload.</small>
      </form>
      <div className="switch-links">
        <button type="button" onClick={() => go("signin")}>
          Sign in with GitHub instead
        </button>
      </div>
    </>
  );
}
