import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowUpRight,
  ChevronsUpDown,
  Radar,
  LayoutDashboard,
  Settings2,
  RefreshCw,
  Activity,
  GitBranch,
  Code2,
  Menu,
  PanelLeft,
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
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Kbd } from "@/components/ui/kbd";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Overview,
  ActivityList,
  WorkspaceView,
} from "./features/OperationsViews";
import { GitHubView } from "./features/GitHubView";
import { AgentRunsView } from "./features/AgentRunsView";
import { KnowledgeView } from "./features/KnowledgeView";
import { AuthPages, usePage } from "./features/AuthPages";
import { TeamInvites } from "./features/TeamInvites";
import { AttentionPanel, MissionControl } from "./features/MissionControl";
import { TicketManagement, TicketNotes } from "./features/TicketManagement";
import { StateBadge, SectionHeading } from "./features/shared";
import type { Operations, QueueTicket } from "./types";
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

function formatLatency(milliseconds: number) {
  return milliseconds < 1000
    ? Math.round(milliseconds) + "ms"
    : (milliseconds / 1000).toFixed(2) + "s";
}

type View =
  | "mission"
  | "overview"
  | "repositories"
  | "agents"
  | "workspace"
  | "reviews"
  | "knowledge"
  | "activity"
  | "settings"
  | "guide";
const NAV = [
  {
    id: "overview",
    group: "Support",
    label: "Overview",
    icon: LayoutDashboard,
    description: "Your team's support work, in one clear view.",
  },
  {
    id: "workspace",
    group: "Support",
    label: "Tickets",
    icon: Inbox,
    description: "Triage, investigate, and resolve with evidence.",
  },
  {
    id: "reviews",
    group: "Support",
    label: "Review queue",
    icon: ClipboardCheck,
    description: "Current drafts waiting for a human decision.",
  },
  {
    id: "knowledge",
    group: "Support",
    label: "Knowledge",
    icon: BookOpen,
    description: "Manage the source material behind your team's answers.",
  },
  {
    id: "mission",
    group: "Engineering",
    label: "Mission control",
    icon: Radar,
    description:
      "Agent pipeline, work queue, review desk, live GitHub activity, and knowledge freshness.",
  },
  {
    id: "repositories",
    group: "Engineering",
    label: "Repositories",
    icon: GitBranch,
    description:
      "Connect GitHub, inspect changes, and turn tickets into issues.",
  },
  {
    id: "agents",
    group: "Engineering",
    label: "Agent runs",
    icon: Terminal,
    description:
      "Queue coding tasks and inspect results, artifacts, and reported usage.",
  },
  {
    id: "activity",
    group: "Workspace",
    label: "Activity",
    icon: Activity,
    description: "A shared record of investigations, decisions, and handoffs.",
  },
  {
    id: "settings",
    group: "Workspace",
    label: "Workspace",
    icon: Settings2,
    description: "Your team, execution limits, and readiness checks.",
  },
  {
    id: "guide",
    group: "Workspace",
    label: "How it works",
    icon: Layers3,
    description: "From context to evidence to a reviewed decision.",
  },
] as const;
const NAV_GROUPS = ["Support", "Engineering", "Workspace"] as const;

export default function App() {
  const [token, setToken] = useState("");
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
  const composerTrigger = useRef<HTMLElement | null>(null);
  const [composer, setComposer] = useState(false);
  const [form, setForm] = useState<TicketInput>(EMPTY);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<"evidence" | "trace">("evidence");
  const [reviewNote, setReviewNote] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [view, setView] = useState<View>("overview");
  const [focusRun, setFocusRun] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [githubLogin, setGithubLogin] = useState(false);
  const [authPage, goAuth] = usePage();
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const [operations, setOperations] = useState<Operations | null>(null);
  const [queuePage, setQueuePage] = useState(1),
    [queueTotal, setQueueTotal] = useState(0);
  const [queueStatus, setQueueStatus] = useState("all"),
    [queuePriority, setQueuePriority] = useState("all");
  const [queueLoading, setQueueLoading] = useState(false);
  const [queueError, setQueueError] = useState("");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [history, setHistory] = useState<Investigation[]>([]);
  const activeView = NAV.find((item) => item.id === view)!;
  const staleDraft = Boolean(
    selected &&
    investigation &&
    investigation.ticket_revision !== selected.revision,
  );
  function navigate(next: View) {
    setView(next);
    setNotice("");
    setError("");
    setNavigationOpen(false);
    setQueuePage(1);
    setQuery("");
    setQueueStatus("all");
    setQueuePriority("all");
  }
  async function refreshWorkspace() {
    if (!token) return;
    setOperations(await api<Operations>("/operations"));
    setRefreshVersion((value) => value + 1);
  }
  async function openTicketId(id: string) {
    try {
      await selectTicket(await api<Ticket>("/tickets/" + id));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    if (!token || !["workspace", "reviews"].includes(view)) return;
    let active = true;
    const controller = new AbortController();
    setQueueLoading(true);
    setQueueError("");
    const timer = setTimeout(() => {
      const params = new URLSearchParams({
        search: query,
        status: queueStatus,
        priority: queuePriority,
        review: view === "reviews" ? "pending" : "all",
        page: String(queuePage),
        page_size: "15",
      });
      api<{ items: QueueTicket[]; total: number }>("/queue?" + params, {
        signal: controller.signal,
      })
        .then((data) => {
          if (active) {
            setTickets(data.items);
            setQueueTotal(data.total);
          }
        })
        .catch((e) => {
          if (active) {
            setQueueError(e.message);
          }
        })
        .finally(() => {
          if (active) setQueueLoading(false);
        });
    }, 150);
    return () => {
      active = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, [
    token,
    view,
    query,
    queueStatus,
    queuePriority,
    queuePage,
    refreshVersion,
  ]);
  async function updateTicket(changes: Partial<Ticket>) {
    if (!selected) return;
    setBusy("update");
    setError("");
    try {
      const {
        subject,
        description,
        product_version,
        account_id,
        log,
        status,
        priority,
        assignee,
      } = changes;
      const updated = await api<Ticket>("/tickets/" + selected.id, {
        method: "PATCH",
        body: JSON.stringify({
          expected_revision: selected.revision,
          subject,
          description,
          product_version,
          account_id,
          log,
          status,
          priority,
          assignee,
        }),
      });
      setSelected(updated);
      setTickets((old) =>
        old.map((item) => (item.id === updated.id ? updated : item)),
      );
      setNotice(
        "Ticket updated. Existing drafts retain their original context.",
      );
      await refreshWorkspace();
    } catch (e) {
      setError((e as Error).message);
      throw e;
    } finally {
      setBusy("");
    }
  }

  useEffect(() => {
    const githubResult = new URLSearchParams(window.location.search).get(
      "github",
    );
    if (githubResult === "connected")
      setNotice(
        "GitHub authorization returned. Reconnect your workspace and open Repositories to verify the connection.",
      );
    else if (githubResult === "authorization_failed")
      setError(
        "GitHub authorization did not complete. Reconnect your workspace to try again.",
      );
    const loginResult = new URLSearchParams(window.location.search).get(
      "login",
    );
    if (loginResult === "failed")
      setError("GitHub sign-in did not complete. Try again.");
    else if (loginResult === "unavailable")
      setError("GitHub sign-in is not configured on this server.");
    if (githubResult || loginResult)
      window.history.replaceState(null, "", window.location.pathname);
    fetch("/api/auth/config")
      .then((r) => r.json())
      .then((data) => setGithubLogin(Boolean(data.github)))
      .catch(() => undefined);
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

  async function connectWith(credential: string) {
    setBusy("connect");
    setError("");
    try {
      const identity = await api<{ workspace_id: string; label?: string }>(
        "/session",
        {},
        credential,
      );
      const [loaded, samples, summary] = await Promise.all([
        api<Ticket[]>("/tickets", {}, credential),
        api<typeof examples>("/examples", {}, credential),
        api<Operations>("/operations", {}, credential),
      ]);
      setToken(credential);
      window.history.replaceState(null, "", window.location.pathname);
      setWorkspace(identity.label ?? identity.workspace_id);
      setTickets(loaded);
      setExamples(samples);
      setOperations(summary);
      setView("overview");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function selectTicket(ticket: Ticket) {
    setSelected(ticket);
    setInvestigation(null);
    setHistory([]);
    setReviews([]);
    setView(view === "reviews" ? "reviews" : "workspace");
    setError("");
    setNotice("");
    setReviewNote("");
    setBusy("load");
    try {
      const runs = await api<Investigation[]>(
        "/tickets/" + ticket.id + "/investigations",
      );
      setHistory(runs);
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
      setHistory([]);
      setInvestigation(null);
      setReviews([]);
      setComposer(false);
      setForm(EMPTY);
      setNotice("Ticket created. Ready to investigate.");
      navigate("workspace");
      setHistory([]);
      await refreshWorkspace();
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
      setHistory((old) => [result, ...old]);
      setTab("evidence");
      await refreshWorkspace();
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
      await refreshWorkspace();
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
    goAuth("home");
    setToken("");
    setOperations(null);
    setHistory([]);
    setView("overview");
    setTickets([]);
    setExamples([]);
    setSelected(null);
    setInvestigation(null);
    setReviews([]);
    setError("");
    setNotice("");
    setWorkspace("");
  }

  const filtered = tickets;
  const cited = new Set(investigation?.draft?.evidence_ids ?? []);
  const sources = investigation?.evidence.filter((e) => cited.has(e.id)) ?? [];

  const reviewCount = operations?.counts.awaiting_review ?? 0;
  const initials = (workspace || "SP").slice(0, 2).toUpperCase();
  const navList = (onPick: (id: View) => void) =>
    NAV_GROUPS.map((group) => (
      <div className="nav-group" key={group}>
        <div className="nav-caption">{group}</div>
        {NAV.filter((item) => item.group === group).map((item) => (
          <Button
            key={item.id}
            variant="ghost"
            className={"nav-link " + (view === item.id ? "active" : "")}
            aria-current={view === item.id ? "page" : undefined}
            disabled={!!busy}
            onClick={() => onPick(item.id)}
          >
            <item.icon size={16} />
            {item.label}
            {item.id === "reviews" && reviewCount > 0 && (
              <span className="nav-count">{reviewCount}</span>
            )}
          </Button>
        ))}
      </div>
    ));
  const openComposer = () => {
    composerTrigger.current = document.activeElement as HTMLElement;
    setComposer(true);
    setForm(EMPTY);
    setError("");
  };

  if (!token)
    return (
      <AuthPages
        page={authPage}
        go={(next) => {
          setError("");
          goAuth(next);
        }}
        github={githubLogin}
        mode={mode}
        error={error}
        busy={busy === "connect"}
        onToken={connectWith}
      />
    );

  return (
    <TooltipProvider delayDuration={250}>
      <div className="app-shell">
        <aside className="sidebar" aria-label="Main navigation">
          <a className="brand" href="/" aria-label="SupportPilot home">
            <span className="brand-mark">
              <Layers3 size={18} />
            </span>
            SupportPilot
          </a>
          <button
            type="button"
            className="palette-trigger"
            onClick={() => setPaletteOpen(true)}
          >
            <Search size={14} />
            Search or jump to…
            <Kbd>⌘K</Kbd>
          </button>
          <nav className="nav-groups">{navList(navigate)}</nav>
          <div className="sidebar-links">
            <a
              className="nav-link"
              href="https://github.com/ayushap18/supportpilot/blob/main/docs/EVALUATION.md"
              target="_blank"
              rel="noreferrer"
            >
              <FlaskConical size={16} />
              Evaluation plan
              <ArrowUpRight size={13} className="external" />
            </a>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button type="button" className="sidebar-footer">
                <Avatar className="avatar">
                  <AvatarFallback>{initials}</AvatarFallback>
                </Avatar>
                <div>
                  {workspace}
                  <span>{operations?.role ?? "member"} access</span>
                </div>
                <ChevronsUpDown size={14} />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="start" className="w-52">
              <DropdownMenuLabel>{workspace}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => navigate("settings")}>
                <Settings2 /> Workspace settings
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <a
                  href="https://github.com/ayushap18/supportpilot"
                  target="_blank"
                  rel="noreferrer"
                >
                  <Code2 /> Source on GitHub
                </a>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={disconnect} disabled={!!busy}>
                <LogOut /> Disconnect
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </aside>

        <CommandDialog
          open={paletteOpen}
          onOpenChange={setPaletteOpen}
          title="Command palette"
          description="Jump to a view or run an action"
        >
          <CommandInput placeholder="Type a command or search…" />
          <CommandList>
            <CommandEmpty>No results.</CommandEmpty>
            <CommandGroup heading="Actions">
              <CommandItem
                onSelect={() => {
                  setPaletteOpen(false);
                  openComposer();
                }}
              >
                <Plus /> New ticket
              </CommandItem>
            </CommandGroup>
            {NAV_GROUPS.map((group) => (
              <CommandGroup heading={group} key={group}>
                {NAV.filter((item) => item.group === group).map((item) => (
                  <CommandItem
                    key={item.id}
                    value={item.label}
                    keywords={[item.group]}
                    onSelect={() => {
                      setPaletteOpen(false);
                      navigate(item.id);
                    }}
                  >
                    <item.icon /> {item.label}
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
            <CommandGroup heading="Session">
              <CommandItem
                onSelect={() => {
                  setPaletteOpen(false);
                  disconnect();
                }}
              >
                <LogOut /> Disconnect
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </CommandDialog>

        <main className="main-shell">
          <header className="topbar">
            <div className="breadcrumb">
              <Dialog open={navigationOpen} onOpenChange={setNavigationOpen}>
                <Button
                  variant="ghost"
                  size="icon"
                  className="mobile-menu"
                  aria-label="Open navigation"
                  onClick={() => setNavigationOpen(true)}
                >
                  <Menu size={18} />
                </Button>
                <DialogContent className="mobile-navigation">
                  <DialogHeader>
                    <DialogTitle>SupportPilot</DialogTitle>
                    <DialogDescription>{workspace} workspace</DialogDescription>
                  </DialogHeader>
                  {navList(navigate)}
                  <Button
                    variant="outline"
                    onClick={() => {
                      disconnect();
                      setNavigationOpen(false);
                    }}
                  >
                    <LogOut />
                    Disconnect
                  </Button>
                </DialogContent>
              </Dialog>
              <span className="crumb-muted">{activeView.group}</span>
              <ChevronRight size={13} className="crumb-sep" />
              <strong>{activeView.label}</strong>
            </div>
            <div className="topbar-right">
              <span className={"mode-badge " + mode}>
                <span className="status-dot" />
                {mode === "fixture" ? "Fixture mode" : "Live model"}
              </span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Refresh workspace"
                    disabled={!!busy}
                    onClick={async () => {
                      setBusy("refresh");
                      try {
                        await refreshWorkspace();
                        if (
                          selected &&
                          (view === "workspace" || view === "reviews")
                        ) {
                          await selectTicket(
                            await api<Ticket>("/tickets/" + selected.id),
                          );
                        }
                      } catch (e) {
                        setError((e as Error).message);
                      } finally {
                        setBusy("");
                      }
                    }}
                  >
                    <RefreshCw
                      size={15}
                      className={busy === "refresh" ? "spin" : ""}
                    />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Refresh</TooltipContent>
              </Tooltip>
              <Button
                variant="default"
                size="sm"
                className="primary"
                disabled={!!busy}
                onClick={openComposer}
              >
                <Plus size={15} />
                New ticket
              </Button>
            </div>
          </header>
          <div className="page-heading">
            <h1>
              {activeView.id === "overview"
                ? "Your support, in focus."
                : activeView.label}
            </h1>
            <p>{activeView.description}</p>
          </div>
          {error && (
            <div className="alert error" role="alert">
              <TriangleAlert size={16} />
              {error}
              <Button
                variant="ghost"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <X size={15} />
              </Button>
            </div>
          )}
          {notice && (
            <div className="alert success" role="status">
              <Check size={16} />
              {notice}
              <Button
                variant="ghost"
                aria-label="Dismiss notice"
                onClick={() => setNotice("")}
              >
                <X size={15} />
              </Button>
            </div>
          )}

          {view === "workspace" && selected && (
            <section className="overview-grid" aria-label="Workspace overview">
              {[
                {
                  label: "Workspace tickets",
                  value: String(
                    operations?.counts.tickets ?? tickets.length,
                  ),
                  note: "Available in your inbox",
                  icon: Inbox,
                  tone: "emerald",
                },
                {
                  label: "Cited sources",
                  value: investigation
                    ? String(sources.length)
                    : "—",
                  note: "Selected investigation",
                  icon: BookOpen,
                  tone: "violet",
                },
                {
                  label: "Investigation time",
                  value: investigation
                    ? formatLatency(investigation.latency_ms)
                    : "—",
                  note: "Selected investigation",
                  icon: Activity,
                  tone: "blue",
                },
                {
                  label: "Review status",
                  value: reviews.length
                    ? reviews[0].decision === "approve"
                      ? "Approved"
                      : "Rejected"
                    : investigation?.draft
                      ? "Awaiting review"
                      : "No draft yet",
                  note: reviews.length
                    ? "Decision saved for this draft"
                    : "Human decision required",
                  icon: ShieldCheck,
                  tone: "amber",
                },
              ].map((metric) => (
                <Card
                  className={"overview-card " + metric.tone}
                  key={metric.label}
                >
                  <CardContent>
                    <div className="metric-label">
                      {metric.label}
                      <metric.icon size={16} />
                    </div>
                    <strong>{metric.value}</strong>
                    <span>{metric.note}</span>
                  </CardContent>
                </Card>
              ))}
            </section>
          )}
          {view === "overview" && operations ? (
            <div className="operational-content">
              <Overview
                data={operations}
                onTicket={selectTicket}
                onQueue={(review) => navigate(review ? "reviews" : "workspace")}
                onKnowledge={() => navigate("knowledge")}
                attention={
                  <AttentionPanel
                    api={api}
                    onOpenRun={(id) => {
                      setFocusRun(id);
                      navigate("agents");
                    }}
                    onOpenTicket={openTicketId}
                    onOpenMission={() => navigate("mission")}
                  />
                }
              />
            </div>
          ) : view === "repositories" && operations ? (
            <div className="operational-content">
              <GitHubView
                api={api}
                admin={operations.role === "admin"}
                onError={setError}
              />
            </div>
          ) : view === "mission" && operations ? (
            <div className="operational-content">
              <MissionControl
                api={api}
                admin={operations.role === "admin"}
                onError={setError}
                onOpenRun={(id) => {
                  setFocusRun(id);
                  navigate("agents");
                }}
                onOpenTicket={openTicketId}
              />
            </div>
          ) : view === "agents" && operations ? (
            <div className="operational-content">
              <AgentRunsView
                api={api}
                admin={operations.role === "admin"}
                onError={setError}
                focusRun={focusRun}
              />
            </div>
          ) : view === "knowledge" && operations ? (
            <div className="operational-content">
              <KnowledgeView
                api={api}
                admin={operations.role === "admin"}
                mode={mode}
                onChange={refreshWorkspace}
                onError={setError}
              />
            </div>
          ) : view === "activity" && operations ? (
            <div className="operational-content">
              <Card>
                <CardContent>
                  <SectionHeading
                    title="Team activity"
                    detail="The latest 50 recorded actions in your workspace"
                  />
                  <ActivityList data={operations} onTicket={openTicketId} />
                </CardContent>
              </Card>
            </div>
          ) : view === "settings" && operations ? (
            <div className="operational-content">
              <WorkspaceView data={operations} />
              <TeamInvites
                api={api}
                admin={operations.role === "admin"}
                onError={setError}
              />
            </div>
          ) : view === "guide" ? (
            <section className="guide-grid">
              <div>
                <span className="step-number">01</span>
                <h2>Bring the context.</h2>
                <p>
                  Submit the exact error, API version, and account ID when
                  relevant. Use the example tickets to explore different
                  outcomes.
                </p>
              </div>
              <div>
                <span className="step-number">02</span>
                <h2>Follow the evidence.</h2>
                <p>
                  SupportPilot retrieves version-aware documentation and checks
                  read-only synthetic account or service tools. Open the trace
                  to inspect each step.
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
                    {view === "reviews" ? "Pending review" : "Ticket inbox"}{" "}
                    <span>{queueTotal}</span>
                  </h2>
                  <span className="muted">Latest updates</span>
                </div>
                <div className="search-field">
                  <Search size={16} />
                  <Input
                    aria-label="Search tickets"
                    placeholder="Search tickets…"
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value);
                      setQueuePage(1);
                    }}
                  />
                </div>
                <div className="queue-filters">
                  <NativeSelect
                    aria-label="Filter status"
                    value={queueStatus}
                    onChange={(e) => {
                      setQueueStatus(e.target.value);
                      setQueuePage(1);
                    }}
                  >
                    {["all", "open", "in_progress", "waiting", "resolved"].map(
                      (value) => (
                        <NativeSelectOption value={value} key={value}>
                          {value === "all"
                            ? "All statuses"
                            : value.replaceAll("_", " ")}
                        </NativeSelectOption>
                      ),
                    )}
                  </NativeSelect>
                  <NativeSelect
                    aria-label="Filter priority"
                    value={queuePriority}
                    onChange={(e) => {
                      setQueuePriority(e.target.value);
                      setQueuePage(1);
                    }}
                  >
                    {["all", "urgent", "high", "normal", "low"].map((value) => (
                      <NativeSelectOption value={value} key={value}>
                        {value === "all" ? "All priorities" : value}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </div>
                {queueLoading && (
                  <p className="queue-message">Loading tickets…</p>
                )}
                {queueError && (
                  <p className="queue-message error-banner" role="alert">
                    {queueError}
                  </p>
                )}
                <div className="ticket-scroll">
                  {filtered.map((ticket) => (
                    <Button
                      variant="ghost"
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
                      <div className="ticket-badges">
                        <StateBadge value={ticket.status} />
                        {ticket.priority !== "normal" && (
                          <StateBadge value={ticket.priority} />
                        )}
                      </div>
                      <p>{ticket.description}</p>
                      <footer>
                        <span>
                          {ticket.product_version ?? "Version unknown"}
                        </span>
                        <time>
                          {new Date(ticket.created_at).toLocaleDateString(
                            undefined,
                            { month: "short", day: "numeric" },
                          )}
                        </time>
                      </footer>
                    </Button>
                  ))}
                  {!filtered.length && (
                    <div className="list-empty">
                      <Inbox size={28} />
                      <h3>
                        {query ? "No matching tickets" : "A clean slate."}
                      </h3>
                      <p>
                        {query
                          ? "Try a different search."
                          : "Create a ticket or start with an example."}
                      </p>
                    </div>
                  )}
                </div>
                <div className="queue-pagination">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={queuePage <= 1 || queueLoading}
                    onClick={() => setQueuePage((value) => value - 1)}
                  >
                    Previous
                  </Button>
                  <span>
                    {queuePage} / {Math.max(1, Math.ceil(queueTotal / 15))}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={queuePage * 15 >= queueTotal || queueLoading}
                    onClick={() => setQueuePage((value) => value + 1)}
                  >
                    Next
                  </Button>
                </div>
                <Button
                  variant="ghost"
                  className="sample-button"
                  disabled={!!busy}
                  onClick={() => {
                    composerTrigger.current =
                      document.activeElement as HTMLElement;
                    setComposer(true);
                    setForm(EMPTY);
                  }}
                >
                  <FlaskConical size={16} />
                  Try an example
                  <ArrowRight size={16} />
                </Button>
              </div>
              <div className="ticket-detail">
                {!selected ? (
                  <div className="empty-detail">
                    <div className="empty-icon">
                      <Layers3 size={32} />
                    </div>
                    <div className="eyebrow">CONTEXT → EVIDENCE → DECISION</div>
                    <h2>
                      {tickets.length
                        ? "Pick a ticket to investigate."
                        : "Good answers start here."}
                    </h2>
                    <p>
                      {tickets.length
                        ? "Choose a ticket from the inbox to see its evidence, draft, and review."
                        : "Create a ticket to see the complete support workflow."}
                    </p>
                    <Button
                      variant="default"
                      className="primary"
                      onClick={() => {
                        composerTrigger.current =
                          document.activeElement as HTMLElement;
                        setComposer(true);
                        setForm(EMPTY);
                      }}
                    >
                      <Plus size={16} />
                      {tickets.length ? "Create a ticket" : "Create your first ticket"}
                    </Button>
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
                    <div
                      className="workflow-strip"
                      aria-label="Investigation progress"
                    >
                      <span className="complete">
                        <Check size={13} />
                        Ticket received
                      </span>
                      <ChevronRight size={12} />
                      <span className={investigation?.draft ? "complete" : ""}>
                        <Search size={13} />
                        Investigation
                      </span>
                      <ChevronRight size={12} />
                      <span className={reviews.length ? "complete" : ""}>
                        <ShieldCheck size={13} />
                        Human review
                      </span>
                    </div>
                    <TicketManagement
                      ticket={selected}
                      members={operations?.members || []}
                      busy={!!busy}
                      onUpdate={updateTicket}
                    />
                    <div className="detail-heading">
                      <div className="ticket-code">
                        TKT-{selected.id.slice(0, 6).toUpperCase()}
                        <span className="tag">
                          {selected.product_version ?? "Version unknown"}
                        </span>
                      </div>
                      <h2>{selected.subject}</h2>
                      <p className="ticket-description">
                        {selected.description}
                      </p>
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
                        <Button
                          variant="default"
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
                        </Button>
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
                          Your ticket is saved. You can start a new
                          investigation.
                        </p>
                      </div>
                    )}
                    {history.length > 1 && (
                      <div className="investigation-history">
                        <details>
                          <summary>
                            Investigation history · {history.length} runs
                          </summary>
                          {history.map((run) => (
                            <div key={run.id}>
                              <span>
                                {new Date(run.created_at).toLocaleString()}
                              </span>
                              <span>
                                Ticket rev. {run.ticket_revision} ·{" "}
                                {run.draft?.outcome.replaceAll("_", " ") ||
                                  run.state}
                              </span>
                            </div>
                          ))}
                        </details>
                      </div>
                    )}
                    {staleDraft && (
                      <div className="stale-notice" role="status">
                        <TriangleAlert size={16} />
                        <span>
                          This draft uses an older ticket revision. Investigate
                          again before reviewing.
                        </span>
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
                            <Button
                              variant="ghost"
                              key={source.id}
                              onClick={() => {
                                setTab("evidence");
                                setExpanded(source.id);
                              }}
                            >
                              <span>{i + 1}</span>
                              {source.title}
                              <ArrowRight size={12} />
                            </Button>
                          ))}
                        </div>
                        <div className="review-section">
                          <div>
                            <ShieldCheck size={19} />
                            <h3>
                              {reviews.length
                                ? "Review recorded"
                                : "Ready for your review"}
                            </h3>
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
                                {new Date(
                                  reviews[0].created_at,
                                ).toLocaleString()}
                              </small>
                            </div>
                          ) : (
                            <>
                              <Textarea
                                aria-label="Review note"
                                placeholder="Add a review note (optional)"
                                maxLength={1000}
                                value={reviewNote}
                                onChange={(e) => setReviewNote(e.target.value)}
                              />
                              <div className="review-actions">
                                <Button
                                  variant="default"
                                  className="primary"
                                  disabled={!!busy || staleDraft}
                                  onClick={() => review("approve")}
                                >
                                  <Check size={16} />
                                  Approve draft
                                </Button>
                                <Button
                                  variant="ghost"
                                  className="secondary"
                                  disabled={!!busy || staleDraft}
                                  onClick={() => review("reject")}
                                >
                                  <X size={16} />
                                  Reject draft
                                </Button>
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
                    <TicketNotes
                      key={selected.id}
                      ticketId={selected.id}
                      api={api}
                      onError={setError}
                      onChange={refreshWorkspace}
                    />
                  </>
                )}
              </div>
              <aside className="evidence-panel">
                <Tabs
                  value={tab}
                  onValueChange={(value) =>
                    setTab(value as "evidence" | "trace")
                  }
                >
                  <TabsList className="evidence-tabs">
                    <TabsTrigger value="evidence">
                      <BookOpen size={16} />
                      Evidence{" "}
                      <Badge variant="secondary">{sources.length}</Badge>
                    </TabsTrigger>
                    <TabsTrigger value="trace">
                      <GitBranch size={16} />
                      Trace
                    </TabsTrigger>
                  </TabsList>
                  <TabsContent value={tab} className="evidence-tab-content">
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
                                setExpanded(
                                  expanded === source.id ? null : source.id,
                                )
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
                                  <summary>Tool input & result</summary>
                                  <pre>
                                    {JSON.stringify(
                                      {
                                        arguments: event.tool_arguments,
                                        result: event.tool_result,
                                      },
                                      null,
                                      2,
                                    )}
                                  </pre>
                                </details>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </TabsContent>
                </Tabs>
                {investigation && (
                  <div className="run-metrics">
                    <div>
                      <Clock3 size={14} />
                      Investigation time
                      <strong>{formatLatency(investigation.latency_ms)}</strong>
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
            <span>
              SupportPilot /{" "}
              {mode === "fixture" ? "Fixture workspace" : "Team workspace"}
            </span>
          </footer>
        </main>

        <Dialog
          open={composer}
          onOpenChange={(open) => {
            if (!busy) setComposer(open);
          }}
        >
          <DialogContent
            className="composer"
            showCloseButton={!busy}
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              composerTrigger.current?.focus();
            }}
          >
            <DialogHeader>
              <div className="eyebrow">START AN INVESTIGATION</div>
              <DialogTitle>New support ticket</DialogTitle>
              <DialogDescription>
                Add the context your investigation needs, or choose a sample
                ticket.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={createTicket}>
              <div className="composer-fields">
                {error && (
                  <div className="alert error" role="alert">
                    {error}
                  </div>
                )}
                {examples.length > 0 && (
                  <label className="example-picker">
                    Start with an example
                    <NativeSelect
                      value=""
                      onChange={(e) => {
                        const sample = examples.find(
                          (item) => item.id === e.target.value,
                        );
                        if (sample) setForm({ ...EMPTY, ...sample.ticket });
                      }}
                    >
                      <NativeSelectOption value="">
                        Choose a sample ticket…
                      </NativeSelectOption>
                      {examples.map((sample) => (
                        <NativeSelectOption key={sample.id} value={sample.id}>
                          {sample.ticket.subject}
                        </NativeSelectOption>
                      ))}
                    </NativeSelect>
                  </label>
                )}
                <label>
                  Subject
                  <Input
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
                  <Textarea
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
                    <NativeSelect
                      value={form.product_version ?? ""}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          product_version: (e.target.value ||
                            null) as TicketInput["product_version"],
                        })
                      }
                    >
                      <NativeSelectOption value="">Unknown</NativeSelectOption>
                      <NativeSelectOption value="v1">API v1</NativeSelectOption>
                      <NativeSelectOption value="v2">API v2</NativeSelectOption>
                    </NativeSelect>
                  </label>
                  <label>
                    Account ID <span>optional</span>
                    <Input
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
                  <Textarea
                    maxLength={12000}
                    rows={3}
                    placeholder="Paste relevant logs without credentials or personal data."
                    value={form.log}
                    onChange={(e) => setForm({ ...form, log: e.target.value })}
                  />
                </label>
              </div>
              <div className="modal-footer">
                <span>Synthetic tickets only. Keep secrets private.</span>
                <Button variant="default" className="primary" disabled={!!busy}>
                  {busy === "create" ? (
                    <LoaderCircle className="spin" size={16} />
                  ) : (
                    <Plus size={16} />
                  )}
                  Create ticket
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </TooltipProvider>
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
      <Button
        variant="ghost"
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
      </Button>
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
