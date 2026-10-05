# GitHub engineering workspace

## Product workflow

Connect a team's GitHub account → select authorized repositories → synchronize repository inventory, recent commits, issues, and contributor activity → import versioned README/docs or upload text/Markdown → create a support ticket → explicitly publish a linked GitHub issue → queue an agent task → run it with an authenticated local CLI bridge → inspect the result, usage, patch/branch/test evidence → review and publish a pull request through GitHub.

The existing support workflow remains available. This release adds a working engineering pilot; it does not claim that every repository has been exhaustively audited or every proposed fix is correct.

## Workstreams and ownership

1. **GitHub platform agent:** OAuth with state/PKCE, encrypted credentials, paginated repository discovery, selected-repository snapshots, bounded commit/source inspection, contributor activity, docs import, linked issue publication, integration tests.
2. **Agent runtime agent:** persisted task/run lifecycle, workspace isolation, claim leases, Codex/Claude Code CLI bridge, reported usage and artifacts, subprocess safeguards, tests.
3. **Engineering interface agent:** dark repository explorer, connection states, issue publishing workflow, contributor panels, agent queue/results/usage, responsive browser coverage.
4. **Primary integration:** shared configuration/dependencies, file upload, navigation, documentation, end-to-end verification, release and GitHub Actions checks.

## Scope and decisions

- GitHub connection is attached by an administrator to an existing SupportPilot workspace. Workspace tokens remain the app's sign-in method; GitHub authorization grants repository access, not automatic membership in a workspace.
- Discover accessible repositories with pagination. Analysis is requested for selected repositories. Show scan bounds, omitted files, and synchronization timestamps. Repository inventory is deterministic; agent-run analysis is separately labeled.
- OAuth app credentials and an encryption key are configured server-side. Repository content is untrusted data. Never execute repository code in the web service.
- GitHub issue creation is a deliberate action from a local ticket. Persist remote issue links and reconcile uncertain writes rather than blindly duplicating issues.
- README and `docs/` imports share the existing knowledge index. Text and Markdown uploads use the same validated, redacted indexing path. Archived sources remain archived until explicitly restored.
- Contributor panels summarize GitHub-recorded activity; commit counts are not a measurement of productivity or working hours.
- Coding CLIs authenticate on the operator's own machine. The web app queues work; the operator explicitly runs the bridge for a task and repository. Changes use a dedicated worktree/branch. Existing branch contents must remain intact. Publishing and merging remain review actions.
- Track per-run usage emitted by supported CLIs. Missing usage/cost stays unavailable. Provider subscription balance and organization billing are not inferred from run telemetry.
- Codex, Claude Code, and Antigravity have named adapters. Other tools use external reporting until their CLI and telemetry contracts are verified. The requested “agy” is Antigravity; its named adapter uses official headless JSON output and requires explicit editing authorization in a dedicated worktree.

## Acceptance gates

- GitHub OAuth rejects expired, replayed, mismatched, or unbound callbacks; tokens never appear in browser/API logs or plaintext database payloads.
- Repository and issue operations enforce workspace scope and administrator permissions, validate upstream responses, respect limits, and report network/rate errors without leaking secrets.
- Knowledge import/upload updates the search index atomically and preserves revisions, archived state, and workspace isolation.
- Agent tasks enforce queue/claim/completion transitions and ownership, and record missing telemetry honestly.
- CLI bridge uses fixed command arguments, bounded output/time, an explicit local repository, and no shell interpolation of task text.
- Existing support tests plus new integration/browser tests pass. External APIs and paid models use test doubles during CI; actual connection requires private credentials and account authorization.
- Production build, SQLite/PostgreSQL tests, lint, evaluation regression, and container checks pass before release.

## Later production milestones

GitHub App installation permissions for organization-scale access; GitHub-based app sign-in with explicit membership onboarding; signed webhooks and durable background sync; isolated remote workers with spend limits; automatic PR creation after reviewed changes; CI-result ingestion; expanded document formats; provider organization-usage adapters; live multi-provider evaluations. Each needs its own acceptance tests and real environment validation.

## Primary documentation

- [GitHub OAuth authorization and PKCE](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)
- [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive)
- [Claude Code programmatic execution](https://code.claude.com/docs/en/headless)

- [Antigravity headless CLI](https://antigravity.google/docs/cli/headless/)

## Implemented and locally verified (2026-10-05)

The four workstreams are integrated. Repository pages include commit patch inspection and recent GitHub event activity; agent results include reported usage coverage and reviewable artifacts. Markdown/text upload previews before saving.

Local verification: 69 backend tests passed, with 24 PostgreSQL variants deferred to GitHub CI; 11 Chromium browser tests passed against compiled assets; lint, formatting, production compilation, and the 30-case fixture workflow gate passed. Tests use mock GitHub/provider responses and temporary Git repositories, not live OAuth accounts or paid coding-agent sessions. The release commit's GitHub Actions run supplies PostgreSQL and container evidence.

First activation requires a configured GitHub OAuth app and stable encryption key, an authorized workspace admin, and locally installed/authenticated CLIs. This release does not replace workspace login with GitHub sign-in, automatically audit every repository, publish/merge agent changes, or expose subscription balances. Those are separate production milestones above.
