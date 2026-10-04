import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowDownLeft,
  ArrowRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronRight,
  ClipboardCheck,
  Clock3,
  FileText,
  FlaskConical,
  Inbox,
  KeyRound,
  Layers3,
  LoaderCircle,
  LogOut,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Terminal,
  TriangleAlert,
  X,
} from "lucide-react";
import type {
  Evidence,
  Investigation,
  Review,
  Ticket,
  TicketInput,
} from "./types";

const EMPTY: TicketInput = {
  subject: "",
  description: "",
  product_version: null,
  account_id: null,
  log: "",
};
const LABELS = {
  resolved: "Resolution drafted",
  needs_information: "More details needed",
  escalate: "Human escalation",
};

export default function App() {
  const [token, setToken] = useState("");
  const [tokenEntry, setTokenEntry] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [mode, setMode] = useState<"fixture" | "live">("fixture");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [examples, setExamples] = useState<
    { id: string; ticket: Partial<TicketInput> }[]
  >([]);
  const [selected, setSelected] = useState<Ticket | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(
    null,
  );
  const [reviews, setReviews] = useState<Review[]>([]);
  const [composer, setComposer] = useState(false);
  const [form, setForm] = useState<TicketInput>(EMPTY);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<"evidence" | "trace">("evidence");
  const [reviewNote, setReviewNote] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [view, setView] = useState<"workspace" | "guide">("workspace");

  useEffect(() => {
    fetch("/api/config")
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then((data) => setMode(data.mode))
      .catch(() =>
        setError("The API is unavailable. Start the backend and try again."),
      );
  }, []);

  useEffect(() => {
    if (!composer) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) setComposer(false);
      if (event.key !== "Tab") return;
      const controls = Array.from(
        document.querySelectorAll<HTMLElement>(
          ".composer button:not(:disabled), .composer input, .composer textarea, .composer select",
        ),
      );
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKey);
    };
  }, [composer, busy]);

  async function api<T>(
    path: string,
    options: RequestInit = {},
    credential = token,
  ): Promise<T> {
    const response = await fetch("/api" + path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + credential,
        ...options.headers,
      },
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "Check the ticket fields and try again.",
      );
    return data;
  }

  async function connect(event: FormEvent) {
    event.preventDefault();
    setBusy("connect");
    setError("");
    try {
      const identity = await api<{ workspace_id: string }>(
        "/session",
        {},
        tokenEntry,
      );
      const [loaded, samples] = await Promise.all([
        api<Ticket[]>("/tickets", {}, tokenEntry),
        api<typeof examples>("/examples", {}, tokenEntry),
      ]);
      setToken(tokenEntry);
      setTokenEntry("");
      setWorkspace(identity.workspace_id);
      setTickets(loaded);
      setExamples(samples);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function selectTicket(ticket: Ticket) {
    setSelected(ticket);
    setInvestigation(null);
    setReviews([]);
    setView("workspace");
    setError("");
    setNotice("");
    setReviewNote("");
    setBusy("load");
    try {
      const runs = await api<Investigation[]>(
        "/tickets/" + ticket.id + "/investigations",
      );
      if (runs.length) {
        setInvestigation(runs[0]);
        setReviews(
          await api<Review[]>("/investigations/" + runs[0].id + "/reviews"),
        );
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function createTicket(event: FormEvent) {
    event.preventDefault();
    setBusy("create");
    setError("");
    try {
      const ticket = await api<Ticket>("/tickets", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setTickets((old) => [ticket, ...old]);
      setSelected(ticket);
      setInvestigation(null);
      setReviews([]);
      setComposer(false);
      setForm(EMPTY);
      setNotice("Ticket created. Ready to investigate.");
      setView("workspace");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function investigate() {
    if (!selected) return;
    setBusy("investigate");
    setError("");
    setNotice("");
    setReviews([]);
    setReviewNote("");
    try {
      const result = await api<Investigation>(
        "/tickets/" + selected.id + "/investigations",
        {
          method: "POST",
          headers: { "Idempotency-Key": crypto.randomUUID() },
        },
      );
      setInvestigation(result);
      setTab("evidence");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function review(decision: "approve" | "reject") {
    if (!investigation) return;
    setBusy("review");
    setError("");
    try {
      const saved = await api<Review>(
        "/investigations/" + investigation.id + "/reviews",
        {
          method: "POST",
          body: JSON.stringify({
            draft_revision: investigation.draft_revision,
            decision,
            note: reviewNote,
          }),
        },
      );
      setReviews([saved]);
      setNotice(
        decision === "approve"
          ? "Approval recorded. No customer message was sent."
          : "Draft rejected. Your feedback was recorded.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  function disconnect() {
    setToken("");
    setTickets([]);
    setExamples([]);
    setSelected(null);
    setInvestigation(null);
    setReviews([]);
    setError("");
    setNotice("");
    setWorkspace("");
  }

  const filtered = tickets.filter((ticket) =>
    (ticket.subject + ticket.description)
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const cited = new Set(investigation?.draft?.evidence_ids ?? []);
  const sources = investigation?.evidence.filter((e) => cited.has(e.id)) ?? [];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="SupportPilot home">
          <span className="brand-mark">S</span>SupportPilot
          <span className="brand-dot">.</span>
        </a>
        <div className="workspace-label">
          <span className="workspace-icon">R</span>
          <div>
            RelayDesk<span>Support workspace</span>
          </div>
          <ChevronRight size={15} />
        </div>
        <div className="nav-caption">WORKSPACE</div>
        <button
          className={"nav-link " + (view === "workspace" ? "active" : "")}
          onClick={() => setView("workspace")}
        >
          <Inbox size={18} />
          Ticket inbox<span>{tickets.length}</span>
        </button>
        <button
          className={"nav-link " + (view === "guide" ? "active" : "")}
          onClick={() => setView("guide")}
        >
          <BookOpen size={18} />
          How it works
        </button>
        <a
          className="nav-link"
          href="https://github.com/ayushap18/supportpilot/blob/main/docs/EVALUATION.md"
          target="_blank"
          rel="noreferrer"
        >
          <FlaskConical size={18} />
          Evaluation plan
          <ArrowDownLeft size={14} className="external" />
        </a>
        <div className="sidebar-card">
          <ShieldCheck size={23} />
          <h3>You have the final say.</h3>
          <p>
            Every response is a draft. Review the evidence before approving.
          </p>
          <span>HUMAN REVIEW BUILT IN</span>
        </div>
        <div className="sidebar-footer">
          <span className="avatar">AS</span>
          <div>
            {token ? workspace : "Not connected"}
            <span>
              {token ? "Workspace reviewer" : "Connect to get started"}
            </span>
          </div>
          {token && (
            <button
              title="Disconnect"
              aria-label="Disconnect"
              onClick={disconnect}
            >
              <LogOut size={17} />
            </button>
          )}
        </div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <span>
            Workspace <ChevronRight size={14} />{" "}
            <strong>
              {view === "workspace" ? "Ticket inbox" : "How it works"}
            </strong>
          </span>
          <div className="topbar-right">
            <span className="mode-badge">
              <span className="status-dot" />
              {mode === "fixture" ? "Fixture demo" : "Live model"}
            </span>
            <a
              href="https://github.com/ayushap18/supportpilot"
              target="_blank"
              rel="noreferrer"
            >
              View project <ArrowRight size={14} />
            </a>
          </div>
        </header>
        <div className="page-heading">
          <div>
            <div className="eyebrow">SUPPORT, WITH A CLEARER PICTURE</div>
            <h1>Resolve with evidence.</h1>
            <p>
              A focused workspace for investigation, grounded drafts, and human
              decisions.
            </p>
          </div>
          <button
            className="primary"
            disabled={!token || !!busy}
            onClick={() => {
              setComposer(true);
              setForm(EMPTY);
              setError("");
            }}
          >
            <Plus size={17} />
            New ticket
          </button>
        </div>
        {mode === "fixture" && (
          <div className="demo-note">
            <FlaskConical size={16} />
            <span>
              <strong>A working demo, with synthetic data.</strong> Fixture mode
              uses deterministic routing and lexical retrieval. No live model
              calls.
            </span>
          </div>
        )}
        {error && (
          <div className="alert error" role="alert">
            <TriangleAlert size={17} />
            {error}
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {notice && (
          <div className="alert success" role="status">
            <Check size={17} />
            {notice}
            <button aria-label="Dismiss notice" onClick={() => setNotice("")}>
              <X size={16} />
            </button>
          </div>
        )}

        {!token ? (
          <section className="connect-panel">
            <div className="connect-art">
              <div className="orbit-ring">
                <ShieldCheck size={43} />
              </div>
              <span className="mini-chip">
                <FileText size={14} />
                Evidence first
              </span>
              <h2>
                A little context.
                <br />A better resolution.
              </h2>
              <p>
                Connect your workspace to try a seeded ticket, follow the
                investigation, and review the draft.
              </p>
            </div>
            <form onSubmit={connect}>
              <div className="eyebrow">YOUR SUPPORT WORKSPACE</div>
              <h2>Connect to SupportPilot</h2>
              <p>
                Use the private workspace token from your local configuration or
                deployment administrator.
              </p>
              <label htmlFor="workspace-token">Workspace token</label>
              <div className="token-field">
                <KeyRound size={18} />
                <input
                  id="workspace-token"
                  type="password"
                  autoComplete="off"
                  required
                  minLength={24}
                  value={tokenEntry}
                  onChange={(e) => setTokenEntry(e.target.value)}
                  placeholder="Enter your workspace token"
                />
              </div>
              <button className="primary" disabled={!!busy}>
                {busy === "connect" ? (
                  <LoaderCircle size={17} className="spin" />
                ) : (
                  <ArrowRight size={17} />
                )}
                Connect workspace
              </button>
              <small>
                Your token stays in memory and clears when you reload.
              </small>
            </form>
          </section>
        ) : view === "guide" ? (
          <section className="guide-grid">
            <div>
              <span className="step-number">01</span>
              <h2>Bring the context.</h2>
              <p>
                Submit the exact error, API version, and account ID when
                relevant. Use the example tickets to explore different outcomes.
              </p>
            </div>
            <div>
              <span className="step-number">02</span>
              <h2>Follow the evidence.</h2>
              <p>
                SupportPilot retrieves version-aware documentation and checks
                read-only synthetic account or service tools. Open the trace to
                inspect each step.
              </p>
            </div>
            <div>
              <span className="step-number">03</span>
              <h2>Make the decision.</h2>
              <p>
                Review the sources and response. Approve or reject the exact
                draft revision. Approval records your decision inside the
                workspace.
              </p>
            </div>
            <div className="guide-foot">
              <ShieldCheck size={21} />
              No customer messages are sent. No account changes are executed.
            </div>
          </section>
        ) : (
          <section className="workbench">
            <div className="ticket-list">
              <div className="panel-heading">
                <h2>
                  Inbox <span>{tickets.length}</span>
                </h2>
                <span className="muted">Latest first</span>
              </div>
              <div className="search-field">
                <Search size={16} />
                <input
                  aria-label="Search tickets"
                  placeholder="Search tickets…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              <div className="ticket-scroll">
                {filtered.map((ticket) => (
                  <button
                    key={ticket.id}
                    disabled={!!busy}
                    className={
                      "ticket-item " +
                      (selected?.id === ticket.id ? "selected" : "")
                    }
                    onClick={() => selectTicket(ticket)}
                  >
                    <div>
                      <span className="ticket-code">
                        TKT-{ticket.id.slice(0, 6).toUpperCase()}
                      </span>
                      <ChevronRight size={14} />
                    </div>
                    <h3>{ticket.subject}</h3>
                    <p>{ticket.description}</p>
                    <footer>
                      <span>{ticket.product_version ?? "Version unknown"}</span>
                      <time>
                        {new Date(ticket.created_at).toLocaleDateString(
                          undefined,
                          { month: "short", day: "numeric" },
                        )}
                      </time>
                    </footer>
                  </button>
                ))}
                {!filtered.length && (
                  <div className="list-empty">
                    <Inbox size={28} />
                    <h3>{query ? "No matching tickets" : "A clean slate."}</h3>
                    <p>
                      {query
                        ? "Try a different search."
                        : "Create a ticket or start with an example."}
                    </p>
                  </div>
                )}
              </div>
              <button
                className="sample-button"
                disabled={!!busy}
                onClick={() => {
                  setComposer(true);
                  setForm(EMPTY);
                }}
              >
                <FlaskConical size={16} />
                Try an example
                <ArrowRight size={16} />
              </button>
            </div>
            <div className="ticket-detail">
              {!selected ? (
                <div className="empty-detail">
                  <div className="empty-icon">
                    <Layers3 size={32} />
                  </div>
                  <div className="eyebrow">CONTEXT → EVIDENCE → DECISION</div>
                  <h2>Good answers start here.</h2>
                  <p>
                    Select a ticket to investigate, or create one to see the
                    complete support workflow.
                  </p>
                  <button
                    className="primary"
                    onClick={() => {
                      setComposer(true);
                      setForm(EMPTY);
                    }}
                  >
                    <Plus size={16} />
                    Create your first ticket
                  </button>
                  <div className="empty-steps">
                    <span>
                      <Search size={16} />
                      Find sources
                    </span>
                    <span>
                      <Terminal size={16} />
                      Check tools
                    </span>
                    <span>
                      <ClipboardCheck size={16} />
                      Review draft
                    </span>
                  </div>
                </div>
              ) : (
                <>
                  <div className="detail-heading">
                    <div className="ticket-code">
                      TKT-{selected.id.slice(0, 6).toUpperCase()}
                      <span className="tag">
                        {selected.product_version ?? "Version unknown"}
                      </span>
                    </div>
                    <h2>{selected.subject}</h2>
                    <p className="ticket-description">{selected.description}</p>
                    {selected.account_id && (
                      <div className="account-label">
                        Account <code>{selected.account_id}</code>
                      </div>
                    )}
                    {selected.log && (
                      <details className="log-block">
                        <summary>Attached log</summary>
                        <pre>{selected.log}</pre>
                      </details>
                    )}
                    <div className="investigation-actions">
                      <button
                        className="primary"
                        disabled={!!busy}
                        onClick={investigate}
                      >
                        {busy === "investigate" ? (
                          <LoaderCircle size={17} className="spin" />
                        ) : (
                          <Sparkles size={17} />
                        )}
                        {busy === "investigate"
                          ? "Investigating…"
                          : investigation
                            ? "Investigate again"
                            : "Investigate ticket"}
                      </button>
                      <span>
                        <ShieldCheck size={14} />
                        Read-only tools
                      </span>
                    </div>
                  </div>
                  {busy === "investigate" && (
                    <div className="investigating" role="status">
                      <LoaderCircle className="spin" size={20} />
                      <div>
                        <strong>Gathering the evidence</strong>
                        <p>
                          Searching documentation and checking relevant tools.
                        </p>
                      </div>
                    </div>
                  )}
                  {investigation?.state === "failed" && (
                    <div className="failed-state" role="alert">
                      <TriangleAlert size={21} />
                      <h3>Investigation needs another try</h3>
                      <p>{investigation.error}</p>
                      <p>
                        Your ticket is saved. You can start a new investigation.
                      </p>
                    </div>
                  )}
                  {investigation?.draft && (
                    <div className="draft-section">
                      <div className="draft-heading">
                        <h3>
                          <FileText size={18} />
                          Response draft
                        </h3>
                        <span
                          className={"outcome " + investigation.draft.outcome}
                        >
                          {LABELS[investigation.draft.outcome]}
                        </span>
                      </div>
                      <div className="draft-copy">
                        {investigation.draft.response}
                      </div>
                      {investigation.draft.missing_information.length > 0 && (
                        <div className="missing-details">
                          <strong>Details to request</strong>
                          <ul>
                            {investigation.draft.missing_information.map(
                              (item) => (
                                <li key={item}>{item}</li>
                              ),
                            )}
                          </ul>
                        </div>
                      )}
                      <div className="source-pills">
                        {sources.map((source, i) => (
                          <button
                            key={source.id}
                            onClick={() => {
                              setTab("evidence");
                              setExpanded(source.id);
                            }}
                          >
                            <span>{i + 1}</span>
                            {source.title}
                            <ArrowRight size={12} />
                          </button>
                        ))}
                      </div>
                      <div className="review-section">
                        <div>
                          <ShieldCheck size={19} />
                          <h3>Ready for your review</h3>
                          <span>Revision {investigation.draft_revision}</span>
                        </div>
                        {reviews.length ? (
                          <div className="review-record">
                            <CheckCheck size={20} />
                            <strong>
                              {reviews[0].decision === "approve"
                                ? "Draft approved"
                                : "Draft rejected"}
                            </strong>
                            <p>
                              {reviews[0].note ||
                                "Decision recorded without a note."}
                            </p>
                            <small>
                              {reviews[0].reviewer_id} ·{" "}
                              {new Date(reviews[0].created_at).toLocaleString()}
                            </small>
                          </div>
                        ) : (
                          <>
                            <textarea
                              aria-label="Review note"
                              placeholder="Add a review note (optional)"
                              maxLength={1000}
                              value={reviewNote}
                              onChange={(e) => setReviewNote(e.target.value)}
                            />
                            <div className="review-actions">
                              <button
                                className="primary"
                                disabled={!!busy}
                                onClick={() => review("approve")}
                              >
                                <Check size={16} />
                                Approve draft
                              </button>
                              <button
                                className="secondary"
                                disabled={!!busy}
                                onClick={() => review("reject")}
                              >
                                <X size={16} />
                                Reject draft
                              </button>
                            </div>
                            <small>
                              Approval records a decision here. No message is
                              sent.
                            </small>
                          </>
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
            <aside className="evidence-panel">
              <div className="evidence-tabs">
                <button
                  className={tab === "evidence" ? "active" : ""}
                  onClick={() => setTab("evidence")}
                >
                  <BookOpen size={16} />
                  Evidence <span>{sources.length}</span>
                </button>
                <button
                  className={tab === "trace" ? "active" : ""}
                  onClick={() => setTab("trace")}
                >
                  <Layers3 size={16} />
                  Trace
                </button>
              </div>
              {!investigation ? (
                <div className="evidence-empty">
                  <BookOpen size={27} />
                  <h3>Every answer needs a source.</h3>
                  <p>
                    Documentation and tool evidence will appear here after
                    investigation.
                  </p>
                </div>
              ) : tab === "evidence" ? (
                <div className="evidence-scroll">
                  <p className="evidence-caption">
                    Sources cited in the current draft
                  </p>
                  {sources.length ? (
                    sources.map((source, i) => (
                      <EvidenceCard
                        key={source.id}
                        evidence={source}
                        number={i + 1}
                        expanded={expanded === source.id}
                        onClick={() =>
                          setExpanded(expanded === source.id ? null : source.id)
                        }
                      />
                    ))
                  ) : (
                    <p className="muted">
                      No sources cited. Review the trace for details.
                    </p>
                  )}
                </div>
              ) : (
                <div className="trace-list">
                  {investigation.trace.map((event, i) => (
                    <div className="trace-event" key={i}>
                      <span className="trace-dot">
                        <Check size={12} />
                      </span>
                      <div>
                        <h4>
                          {event.stage}
                          <time>{event.duration_ms.toFixed(0)} ms</time>
                        </h4>
                        <p>{event.summary}</p>
                        {event.tool_result != null && (
                          <details>
                            <summary>Tool result</summary>
                            <pre>
                              {JSON.stringify(event.tool_result, null, 2)}
                            </pre>
                          </details>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {investigation && (
                <div className="run-metrics">
                  <div>
                    <Clock3 size={14} />
                    Investigation time
                    <strong>
                      {(investigation.latency_ms / 1000).toFixed(2)}s
                    </strong>
                  </div>
                  <div>
                    <Terminal size={14} />
                    Tool calls
                    <strong>{investigation.usage.tool_calls} / 5</strong>
                  </div>
                  <div>
                    <Layers3 size={14} />
                    Model rounds
                    <strong>{investigation.usage.model_rounds} / 3</strong>
                  </div>
                  <div>
                    Generation cost
                    <strong>
                      {investigation.usage.estimated_cost_usd == null
                        ? "Unavailable"
                        : "$" +
                          investigation.usage.estimated_cost_usd.toFixed(5)}
                    </strong>
                  </div>
                  <small>
                    {mode === "fixture"
                      ? "Fixture routing · no model charges"
                      : "Generation estimate excludes embeddings"}
                  </small>
                </div>
              )}
            </aside>
          </section>
        )}
        <footer className="page-footer">
          <span>
            <ShieldCheck size={13} />
            Evidence grounded. Human reviewed.
          </span>
          <span>SupportPilot / RelayDesk demo</span>
        </footer>
      </main>

      {composer && (
        <div
          className="modal-backdrop"
          onClick={(e) => {
            if (e.target === e.currentTarget && !busy) setComposer(false);
          }}
        >
          <section
            className="composer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="composer-title"
          >
            <div className="modal-heading">
              <div>
                <div className="eyebrow">START AN INVESTIGATION</div>
                <h2 id="composer-title">New support ticket</h2>
              </div>
              <button
                className="icon-button"
                aria-label="Close ticket form"
                disabled={!!busy}
                onClick={() => setComposer(false)}
              >
                <X size={20} />
              </button>
            </div>
            <form onSubmit={createTicket}>
              {error && (
                <div className="alert error" role="alert">
                  {error}
                </div>
              )}
              {examples.length > 0 && (
                <label className="example-picker">
                  Start with an example
                  <select
                    value=""
                    onChange={(e) => {
                      const sample = examples.find(
                        (item) => item.id === e.target.value,
                      );
                      if (sample) setForm({ ...EMPTY, ...sample.ticket });
                    }}
                  >
                    <option value="">Choose a sample ticket…</option>
                    {examples.map((sample) => (
                      <option key={sample.id} value={sample.id}>
                        {sample.ticket.subject}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label>
                Subject
                <input
                  autoFocus
                  required
                  minLength={3}
                  maxLength={200}
                  placeholder="e.g. Webhook fails after upgrading"
                  value={form.subject}
                  onChange={(e) =>
                    setForm({ ...form, subject: e.target.value })
                  }
                />
              </label>
              <label>
                What happened?
                <textarea
                  required
                  minLength={10}
                  maxLength={6000}
                  rows={4}
                  placeholder="Describe the error, expected behavior, and steps to reproduce."
                  value={form.description}
                  onChange={(e) =>
                    setForm({ ...form, description: e.target.value })
                  }
                />
              </label>
              <div className="form-row">
                <label>
                  API version
                  <select
                    value={form.product_version ?? ""}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        product_version: (e.target.value ||
                          null) as TicketInput["product_version"],
                      })
                    }
                  >
                    <option value="">Unknown</option>
                    <option value="v1">API v1</option>
                    <option value="v2">API v2</option>
                  </select>
                </label>
                <label>
                  Account ID <span>optional</span>
                  <input
                    maxLength={80}
                    placeholder="acct_active"
                    value={form.account_id ?? ""}
                    onChange={(e) =>
                      setForm({ ...form, account_id: e.target.value || null })
                    }
                  />
                </label>
              </div>
              <label>
                Log excerpt <span>optional</span>
                <textarea
                  maxLength={12000}
                  rows={3}
                  placeholder="Paste relevant logs without credentials or personal data."
                  value={form.log}
                  onChange={(e) => setForm({ ...form, log: e.target.value })}
                />
              </label>
              <div className="modal-footer">
                <span>Synthetic tickets only. Keep secrets private.</span>
                <button className="primary" disabled={!!busy}>
                  {busy === "create" ? (
                    <LoaderCircle className="spin" size={16} />
                  ) : (
                    <Plus size={16} />
                  )}
                  Create ticket
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

function EvidenceCard({
  evidence,
  number,
  expanded,
  onClick,
}: {
  evidence: Evidence;
  number: number;
  expanded: boolean;
  onClick: () => void;
}) {
  return (
    <article className={"evidence-card " + (expanded ? "expanded" : "")}>
      <button
        className="evidence-card-heading"
        onClick={onClick}
        aria-expanded={expanded}
      >
        <span className="source-number">{number}</span>
        <div>
          <span className="source-type">
            {evidence.kind === "tool" ? "TOOL RESULT" : "DOCUMENTATION"}
          </span>
          <h4>{evidence.title}</h4>
        </div>
        <ChevronRight size={15} />
      </button>
      <p className={expanded ? "" : "clamped"}>{evidence.excerpt}</p>
      <div className="source-meta">
        {evidence.product_version && (
          <span>
            {evidence.product_version === "any"
              ? "All versions"
              : evidence.product_version}
          </span>
        )}
        <code>{evidence.source_path ?? "Read-only synthetic tool"}</code>
      </div>
    </article>
  );
}
