import { useEffect, useState } from "react";
import {
  BookOpen,
  ExternalLink,
  GitBranch,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Card, CardContent } from "@/components/ui/card";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import type { Api, QueueTicket } from "../types";
import { Empty, SectionHeading, StateBadge } from "./shared";
import {
  githubUrl,
  type GitHubStatus,
  type Repository,
  type Snapshot,
  type CommitDetail,
} from "./engineering-types";
import "./engineering.css";
function normalize(data: Snapshot): Snapshot | null {
  return data.analysis
    ? {
        ...data,
        commits: data.commits || [],
        issues: data.issues || [],
        docs: data.docs || [],
        contributors: data.contributors || [],
        files: data.files || [],
      }
    : null;
}
function Link({ url, children }: { url?: string; children: React.ReactNode }) {
  const safe = githubUrl(url);
  return safe ? (
    <a href={safe} target="_blank" rel="noreferrer">
      {children}
      <ExternalLink size={12} />
    </a>
  ) : (
    <span>{children}</span>
  );
}
export function GitHubView({
  api,
  admin,
  onError,
}: {
  api: Api;
  admin: boolean;
  onError: (message: string) => void;
}) {
  const [status, setStatus] = useState<GitHubStatus | null>(null),
    [repositories, setRepositories] = useState<Repository[]>([]),
    [available, setAvailable] = useState<Repository[]>([]),
    [selected, setSelected] = useState(""),
    [snapshot, setSnapshot] = useState<Snapshot | null>(null),
    [commitDetail, setCommitDetail] = useState<CommitDetail | null>(null),
    [busy, setBusy] = useState(""),
    [tab, setTab] = useState("analysis"),
    [notice, setNotice] = useState(""),
    [page, setPage] = useState(1),
    [hasMore, setHasMore] = useState(false),
    [tickets, setTickets] = useState<QueueTicket[]>([]),
    [ticketId, setTicketId] = useState(""),
    [reviewIssue, setReviewIssue] = useState(false),
    [disconnecting, setDisconnecting] = useState(false),
    [loading, setLoading] = useState(true);
  async function load() {
    const [connection, repos] = await Promise.all([
      api<GitHubStatus>("/github/status"),
      api<{ items: Repository[] }>("/github/repositories"),
    ]);
    setStatus(connection);
    setRepositories(repos.items);
  }
  useEffect(() => {
    load()
      .catch((e) => onError(e.message))
      .finally(() => setLoading(false));
  }, []);
  async function action(name: string, task: () => Promise<void>) {
    setBusy(name);
    setNotice("");
    try {
      await task();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function browse(next = 1) {
    await action("browse", async () => {
      const data = await api<{ items: Repository[]; has_more: boolean }>(
        `/github/repos?page=${next}`,
      );
      setAvailable(data.items);
      setPage(next);
      setHasMore(data.has_more);
    });
  }
  async function inspect(id: string) {
    setSelected(id);
    setSnapshot(null);
    setReviewIssue(false);
    await action("inspect", async () =>
      setSnapshot(normalize(await api<Snapshot>(`/github/repositories/${id}`))),
    );
  }
  const current = repositories.find((repo) => String(repo.id) === selected),
    ticket = tickets.find((item) => item.id === ticketId);
  return (
    <div className="engineering-view">
      <Card>
        <CardContent>
          <SectionHeading
            title="Repository intelligence"
            detail="Connect code, documentation, and support work in one workspace."
            action={<GitBranch size={23} />}
          />
          {loading ? (
            <p className="muted">Loading GitHub connection…</p>
          ) : (
            <div className="engineering-connection">
              <span className="engineering-icon">
                <ShieldCheck size={22} />
              </span>
              <div>
                <strong>
                  {status?.connected
                    ? `Connected as ${status.login}`
                    : "Connect your GitHub account"}
                </strong>
                <p>
                  {status?.configured
                    ? "Choose repositories explicitly. Sync captures a bounded snapshot of the default branch."
                    : "An administrator must configure GitHub OAuth before accounts can connect."}
                </p>
              </div>
              <StateBadge
                value={
                  status?.connected
                    ? "connected"
                    : status?.configured
                      ? "ready"
                      : "setup_required"
                }
              />
            </div>
          )}
          {!status?.configured && !loading && (
            <div className="engineering-callout">
              <strong>GitHub setup</strong>
              <p>
                Create a GitHub OAuth application for your deployed SupportPilot
                URL. Configure the client ID, client secret, callback URL, and
                token encryption key on the server. See the deployment guide for
                exact variables. Credentials never belong in repository content.
              </p>
              {!!status?.missing?.length && (
                <p>Missing configuration: {status.missing.join(", ")}</p>
              )}
            </div>
          )}
          <div className="engineering-actions">
            {admin && status?.configured && !status.connected && (
              <Button
                disabled={!!busy}
                onClick={() =>
                  action("connect", async () => {
                    const data = await api<{ authorize_url: string }>(
                      "/github/connect",
                      { method: "POST" },
                    );
                    const safe = githubUrl(data.authorize_url);
                    if (
                      !safe ||
                      new URL(safe).pathname !== "/login/oauth/authorize"
                    )
                      throw new Error(
                        "GitHub returned an invalid authorization address.",
                      );
                    window.location.assign(safe);
                  })
                }
              >
                <GitBranch size={16} />
                Connect GitHub
              </Button>
            )}
            {admin && status?.connected && (
              <Button
                variant="outline"
                disabled={!!busy}
                onClick={() => browse()}
              >
                Browse accessible repositories
              </Button>
            )}
            {admin && status?.connected && (
              <Button
                variant="ghost"
                disabled={!!busy}
                onClick={() => setDisconnecting(!disconnecting)}
              >
                Disconnect GitHub
              </Button>
            )}
            {!admin && (
              <p className="muted small">
                An administrator manages the GitHub connection and repository
                synchronization.
              </p>
            )}
          </div>
          {disconnecting && (
            <div className="engineering-callout">
              <strong>Disconnect this workspace from GitHub?</strong>
              <p>
                New syncs, imports, and issue creation stop. Stored repository
                snapshots remain available in this workspace.
              </p>
              <div className="engineering-actions">
                <Button
                  variant="outline"
                  disabled={!!busy}
                  onClick={() =>
                    action("disconnect", async () => {
                      await api("/github/connection", { method: "DELETE" });
                      await load();
                      setAvailable([]);
                      setDisconnecting(false);
                      setNotice("GitHub connection removed.");
                    })
                  }
                >
                  Confirm disconnect
                </Button>
                <Button variant="ghost" onClick={() => setDisconnecting(false)}>
                  Keep connected
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
      {!!available.length && (
        <Card>
          <CardContent>
            <SectionHeading
              title="Accessible repositories"
              detail="Only selected repositories are stored and analyzed."
            />
            <div className="engineering-repo-list">
              {available.map((repo) => (
                <div className="engineering-list-row" key={repo.id}>
                  <GitBranch size={17} />
                  <div>
                    <strong>{repo.full_name}</strong>
                    <p>
                      {repo.description ||
                        (repo.private
                          ? "Private repository"
                          : "Public repository")}
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!!busy || !admin}
                    onClick={() =>
                      action("select", async () => {
                        await api("/github/repos/select", {
                          method: "POST",
                          body: JSON.stringify({ full_name: repo.full_name }),
                        });
                        await load();
                        setNotice(`${repo.full_name} added to this workspace.`);
                      })
                    }
                  >
                    Add repository
                  </Button>
                </div>
              ))}
            </div>
            <div className="engineering-actions">
              <Button
                variant="ghost"
                disabled={page === 1 || !!busy}
                onClick={() => browse(page - 1)}
              >
                Previous repositories
              </Button>
              <span className="muted small">Page {page}</span>
              <Button
                variant="ghost"
                disabled={!hasMore || !!busy}
                onClick={() => browse(page + 1)}
              >
                More repositories
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
      {notice && (
        <p className="engineering-notice" role="status">
          {notice}
        </p>
      )}
      <Card>
        <CardContent>
          <SectionHeading
            title="Workspace repositories"
            detail={`${repositories.length} repositories selected · contributor activity reflects this snapshot`}
          />
          {repositories.length ? (
            <>
              <div className="engineering-toolbar">
                <NativeSelect
                  aria-label="Selected repository"
                  value={selected}
                  onChange={(e) => inspect(e.target.value)}
                >
                  <NativeSelectOption value="">
                    Choose a repository
                  </NativeSelectOption>
                  {repositories.map((repo) => (
                    <NativeSelectOption key={repo.id} value={String(repo.id)}>
                      {repo.full_name}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
                {selected && admin && (
                  <Button
                    disabled={!!busy || !status?.connected}
                    onClick={() =>
                      action("sync", async () => {
                        setSnapshot(
                          await api<Snapshot>(
                            `/github/repositories/${selected}/sync`,
                            { method: "POST" },
                          ),
                        );
                        setNotice("Repository snapshot updated.");
                      })
                    }
                  >
                    <RefreshCw
                      size={15}
                      className={busy === "sync" ? "animate-spin" : ""}
                    />
                    {busy === "sync" ? "Syncing…" : "Sync repository"}
                  </Button>
                )}
              </div>
              {current && (
                <p className="muted small">
                  {current.full_name} ·{" "}
                  {current.default_branch || "Default branch"} ·{" "}
                  <Link url={current.html_url}>Open repository</Link>
                </p>
              )}
            </>
          ) : (
            <Empty title="Your code belongs here">
              Connect GitHub, browse your repositories, and select the ones your
              team supports.
            </Empty>
          )}
          {busy === "inspect" && (
            <p className="muted">Loading repository snapshot…</p>
          )}
          {selected && !snapshot && !busy && (
            <p className="muted small">
              Sync this repository to collect commits, issues, contributor
              totals, and documentation.
            </p>
          )}
          {snapshot && (
            <>
              <div
                className="engineering-tabs"
                role="tablist"
                aria-label="Repository details"
              >
                {[
                  "analysis",
                  "commits",
                  "issues",
                  "docs",
                  "contributors",
                  "activity",
                ].map((item) => (
                  <button
                    key={item}
                    role="tab"
                    aria-selected={tab === item}
                    onClick={() => setTab(item)}
                  >
                    {item === "docs"
                      ? "Documentation"
                      : item[0].toUpperCase() + item.slice(1)}
                  </button>
                ))}
              </div>
              <div
                className="engineering-tab-content"
                role="tabpanel"
                aria-label={tab}
              >
                {tab === "analysis" && (
                  <>
                    <div className="engineering-stats">
                      {[
                        ["Commits", snapshot.commits.length],
                        ["Issues", snapshot.issues.length],
                        ["Documents", snapshot.docs.length],
                        ["Contributors", snapshot.contributors.length],
                      ].map(([label, count]) => (
                        <div key={label}>
                          <span>{label}</span>
                          <strong>{count}</strong>
                        </div>
                      ))}
                    </div>
                    {typeof snapshot.analysis === "string" ? (
                      <p className="muted small">{snapshot.analysis}</p>
                    ) : (
                      <div className="engineering-checks">
                        {[
                          ["README", "has_readme"],
                          ["Tests", "has_tests"],
                          ["CI workflows", "has_ci"],
                          ["Documentation", "has_docs"],
                        ].map(([label, key]) => (
                          <div key={key}>
                            <span>{label}</span>
                            <StateBadge
                              value={
                                snapshot.analysis &&
                                typeof snapshot.analysis === "object" &&
                                snapshot.analysis[key]
                                  ? "detected"
                                  : "not_detected"
                              }
                            />
                          </div>
                        ))}
                      </div>
                    )}
                    <p className="muted small">
                      This inventory samples the default branch. It does not
                      audit security or measure contributor performance. Up to
                      30 commits, 30 issues, 30 contributors, 500 files, and 20
                      documents are retained per sync.
                    </p>
                    {snapshot.limits &&
                      Object.entries(snapshot.limits).some(
                        ([key, value]) =>
                          (key.endsWith("truncated") ||
                            key.endsWith("may_have_more")) &&
                          value === true,
                      ) && (
                        <p className="engineering-callout">
                          More data is available on GitHub than this snapshot
                          includes.
                        </p>
                      )}
                  </>
                )}
                {tab === "commits" &&
                  (snapshot.commits.length ? (
                    snapshot.commits.map((commit) => (
                      <div className="engineering-list-row" key={commit.sha}>
                        <GitBranch size={16} />
                        <div>
                          <strong>{commit.message}</strong>
                          <p>
                            {commit.author || "Unknown author"}
                            {commit.date
                              ? ` · ${new Date(commit.date).toLocaleDateString()}`
                              : ""}
                          </p>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={!!busy}
                          onClick={() =>
                            action("diff", async () =>
                              setCommitDetail(
                                await api<CommitDetail>(
                                  `/github/repositories/${selected}/commits/${commit.sha}`,
                                ),
                              ),
                            )
                          }
                        >
                          Inspect {commit.sha.slice(0, 7)}
                        </Button>
                      </div>
                    ))
                  ) : (
                    <Empty title="No commits in this snapshot" />
                  ))}
                {tab === "issues" && (
                  <>
                    {snapshot.issues.map((issue) => (
                      <div className="engineering-list-row" key={issue.number}>
                        <div>
                          <strong>
                            <Link url={issue.html_url}>
                              #{issue.number} {issue.title}
                            </Link>
                          </strong>
                        </div>
                        <StateBadge value={issue.state} />
                      </div>
                    ))}
                    {admin && (
                      <div className="engineering-callout">
                        <strong>Create a GitHub issue from a ticket</strong>
                        <p>
                          You will review the selected ticket before its content
                          is published to this repository.
                        </p>
                        <Button
                          variant="outline"
                          disabled={!!busy}
                          onClick={() =>
                            action("tickets", async () => {
                              setTickets(
                                (
                                  await api<{ items: QueueTicket[] }>(
                                    "/queue?page_size=100",
                                  )
                                ).items,
                              );
                              setReviewIssue(true);
                            })
                          }
                        >
                          Choose ticket for issue
                        </Button>
                        {reviewIssue && (
                          <div className="engineering-issue-review">
                            <NativeSelect
                              aria-label="Ticket to publish"
                              value={ticketId}
                              onChange={(e) => setTicketId(e.target.value)}
                            >
                              <NativeSelectOption value="">
                                Select ticket
                              </NativeSelectOption>
                              {tickets.map((item) => (
                                <NativeSelectOption
                                  key={item.id}
                                  value={item.id}
                                >
                                  {item.subject}
                                </NativeSelectOption>
                              ))}
                            </NativeSelect>
                            {ticket && (
                              <>
                                <p>
                                  <strong>{ticket.subject}</strong>
                                </p>
                                <p className="engineering-wrap">
                                  {ticket.description}
                                </p>
                                <p className="muted small">
                                  Publish to {current?.full_name}. This sends
                                  ticket content to GitHub.
                                </p>
                                <Button
                                  disabled={!!busy}
                                  onClick={() =>
                                    action("issue", async () => {
                                      const result = await api<{
                                        html_url?: string;
                                        number?: number;
                                      }>(
                                        `/github/repositories/${selected}/issues`,
                                        {
                                          method: "POST",
                                          body: JSON.stringify({
                                            ticket_id: ticketId,
                                          }),
                                        },
                                      );
                                      setNotice(
                                        `GitHub issue ${result.number ? `#${result.number} ` : ""}created. Sync to refresh the issue list.`,
                                      );
                                      setReviewIssue(false);
                                    })
                                  }
                                >
                                  Create GitHub issue
                                </Button>
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
                {tab === "docs" && (
                  <>
                    <div className="engineering-actions">
                      {admin && (
                        <Button
                          disabled={!!busy || !snapshot.docs.length}
                          onClick={() =>
                            action("import", async () => {
                              const result = await api<{
                                imported: unknown[];
                                skipped: unknown[];
                                errors: unknown[];
                              }>(
                                `/github/repositories/${selected}/import-docs`,
                                { method: "POST" },
                              );
                              setNotice(
                                `Knowledge import: ${result.imported.length} imported, ${result.skipped.length} skipped, ${result.errors.length} errors.`,
                              );
                            })
                          }
                        >
                          <BookOpen size={15} />
                          {busy === "import"
                            ? "Indexing documentation…"
                            : "Import docs into knowledge"}
                        </Button>
                      )}
                    </div>
                    {snapshot.docs.map((doc) => (
                      <div className="engineering-list-row" key={doc.path}>
                        <BookOpen size={16} />
                        <div>
                          <strong>{doc.path}</strong>
                          <p>
                            {doc.content?.slice(0, 180) ||
                              "Documentation discovered in repository snapshot"}
                          </p>
                        </div>
                      </div>
                    ))}
                    {!snapshot.docs.length && (
                      <Empty title="No documentation discovered">
                        Add Markdown or text documents to your repository's docs
                        folder, then sync again.
                      </Empty>
                    )}
                  </>
                )}
                {tab === "activity" && (
                  <>
                    <p className="muted small">
                      Recent events available from GitHub. The snapshot does not
                      include every action or private activity outside this
                      repository.
                    </p>
                    {snapshot.activity?.length ? (
                      snapshot.activity.map((event) => (
                        <div className="engineering-list-row" key={event.id}>
                          <span className="engineering-avatar">
                            {event.actor.slice(0, 2).toUpperCase()}
                          </span>
                          <div>
                            <strong>
                              {event.actor} · {event.summary}
                            </strong>
                            <p>{new Date(event.created_at).toLocaleString()}</p>
                          </div>
                        </div>
                      ))
                    ) : (
                      <Empty title="No recent repository events" />
                    )}
                  </>
                )}
                {tab === "contributors" && (
                  <>
                    <p className="muted small">
                      GitHub contribution totals for contributors returned by
                      this snapshot. These totals do not describe current tasks,
                      working hours, or performance.
                    </p>
                    {snapshot.contributors.map((person) => (
                      <div className="engineering-list-row" key={person.login}>
                        <span className="engineering-avatar">
                          {person.login.slice(0, 2).toUpperCase()}
                        </span>
                        <div>
                          <strong>
                            <Link url={person.html_url}>{person.login}</Link>
                          </strong>
                        </div>
                        <span className="muted small">
                          {person.contributions} contributions
                        </span>
                      </div>
                    ))}
                  </>
                )}
              </div>
            </>
          )}
        </CardContent>
      </Card>
      <Dialog
        open={!!commitDetail}
        onOpenChange={(open) => {
          if (!open) setCommitDetail(null);
        }}
      >
        <DialogContent className="document-dialog engineering-diff-dialog">
          <DialogHeader>
            <DialogTitle>Commit changes</DialogTitle>
            <DialogDescription>
              {commitDetail?.sha.slice(0, 7)} · {commitDetail?.message}
            </DialogDescription>
          </DialogHeader>
          {commitDetail && (
            <>
              <p className="muted small">
                +{commitDetail.stats.additions} additions · −
                {commitDetail.stats.deletions} deletions ·{" "}
                <Link url={commitDetail.html_url}>View on GitHub</Link>
              </p>
              {commitDetail.files.map((file) => (
                <section key={file.filename}>
                  <h3 className="engineering-subtitle">
                    {file.filename} · {file.status} · +{file.additions} −
                    {file.deletions}
                  </h3>
                  {file.patch_available && file.patch ? (
                    <pre className="engineering-pre">{file.patch}</pre>
                  ) : (
                    <p className="muted small">
                      Patch unavailable. This may be binary content or omitted
                      by GitHub.
                    </p>
                  )}
                  {file.patch_truncated && (
                    <p className="muted small">
                      Patch truncated. Open GitHub to inspect the complete diff.
                    </p>
                  )}
                </section>
              ))}
              {(commitDetail.limits.files_truncated ||
                commitDetail.limits.upstream_may_have_more) && (
                <p className="engineering-callout">
                  This commit contains more changes than this bounded preview
                  includes.
                </p>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
