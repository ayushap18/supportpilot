# SupportPilot: operational workspace implementation

## Target and boundaries

Build an internal technical-support workspace for a small SaaS team. The first release supports manual ticket intake; a help-desk connector can be added after the provider and credentials are available. A useful release must let an operator triage a ticket, inspect evidence, review a draft, record notes, and manage the ticket lifecycle. Dashboard numbers must come from stored workspace data.

This iteration is an operational pilot, not a declaration of production readiness. External account/service tools remain synthetic in fixture mode and are disabled in live mode until real adapters exist. Customer deployment still requires identity-provider onboarding, live-model quality evaluation, backups and restore verification, hosting configuration, and an agreed data-retention policy.

## Workstreams and ownership

1. Backend agent: ticket lifecycle, optimistic editing, assignment, notes, paginated queue, aggregate dashboard, role-aware workspace configuration, authorization tests. Own `app.py`, `schemas.py`, `config.py`, `storage.py`, new `operations.py`, and `tests/test_operations_workspace.py`.
2. Frontend agent: a coherent dark dashboard with Overview, Tickets, Review queue, Knowledge, Activity, and Workspace navigation. Functional data, filters, triage controls, document management, role-aware actions, useful empty/error/loading states. Own frontend source and dependencies, excluding browser tests/configuration.
3. Quality agent: cross-feature browser coverage and a release checklist. Own frontend browser tests/configuration and `docs/RELEASE_CHECKLIST.md`. Audit integration risks and report them to the lead.
4. Lead: knowledge persistence and retrieval integration, provider grounding, integration review, local tests, visual QA, GitHub CI, and release documentation.

Agents implement against the contracts below before integration. Existing ticket creation, investigation, evidence, and review APIs remain compatible.

## API contracts

### Tickets and queue

Extend returned Ticket with `status` (`open|in_progress|waiting|resolved`, default open), `priority` (`low|normal|high|urgent`, default normal), `assignee` (nullable reviewer ID), `revision` (integer, default 1), and `updated_at` (nullable timestamp; legacy fallback created_at).

- `PATCH /api/tickets/{id}`: `{expected_revision, ...editable ticket fields, status?, priority?, assignee?}`. Require the exact current revision; reject stale edits with 409. Increment revision on changes. Investigation records capture `ticket_revision`; reviews reject a draft if the ticket has changed since investigation. Approval does not automatically resolve a ticket.
- `GET /api/queue`: query `search`, `status`, `priority`, `review` (`all|pending`), `page` (1+), `page_size` (1..100). `all` disables enum filters. Return `{items, total, page, page_size}`. Items extend Ticket with `latest_investigation_id`, `latest_outcome`, `review_status` (`none|pending|approved|rejected|stale`), and `investigation_state` (nullable). Use the latest investigation per ticket for review counts.
- `GET /api/tickets/{id}/notes`: array `{id, body, author_id, created_at}`.
- `POST /api/tickets/{id}/notes`: `{body}` (1..4000 chars); return note. Persist notes, author, and time.

### Operations

`GET /api/operations` returns:

```
{
  workspace_id, reviewer_id, role: "admin"|"agent", mode: "fixture"|"live",
  model, tool_mode: "synthetic"|"disabled", retention_days,
  limits: {max_rounds, max_tool_calls, timeout_seconds, max_investigations_per_hour},
  counts: {tickets, open, in_progress, waiting, resolved, awaiting_review, failed_investigations, knowledge_documents},
  trends: [{date, tickets, investigations, approved, rejected, failed}],
  outcomes: [{outcome, count}],
  activity: [{id, kind, title, detail, ticket_id, created_at}],
  recent_tickets: [QueueTicket],
  members: [{reviewer_id, role}],
  readiness: [{id, label, status: "ready"|"pending"|"demo", detail}]
}
```

Trends cover the last seven UTC dates, including zero-activity dates. No invented uptime, SLA, satisfaction, or accuracy metrics. Include all workspace tickets in counts rather than the legacy 100-item display cap. No credentials or other-workspace identity details in responses.

Token configuration accepts an optional `role` (`admin|agent`); legacy entries default to admin for compatibility. Both roles can work tickets and review. Only admins can mutate knowledge. All routes enforce authenticated workspace scope.

### Knowledge

The lead supplies `build_knowledge_router(database, retrieval, identity, settings)` for mounting in app.py before the static frontend.

- `GET /api/knowledge/documents`: `{items, total}`. Document: `{id,title,body,product_version,source_path,revision,origin:"seed"|"workspace",chunk_count,updated_at,archived}`. Version is `v1|v2|any`. Seed documents are read-only.
- `POST /api/knowledge/documents`: `{title,body,product_version,source_path}`; return document. Body 20..30000 chars; title 3..200; source_path 0..200. Content is plain text/Markdown. Index before reporting success.
- `PATCH /api/knowledge/documents/{id}`: same fields plus `expected_revision`; reject stale revision with 409.
- `POST /api/knowledge/documents/{id}/archive` and `/restore`: `{expected_revision}`; return document. Archive removes searchable chunks but retains the source; restore reindexes it.
- `POST /api/knowledge/search`: `{query,product_version:null|"v1"|"v2"}`; return `{evidence:[Evidence]}`. Available to both roles. Honest fixture lexical / live semantic labeling.

Workspace documents survive restarts. Corpus and embedding changes refresh indexes. Live mode uses workspace documents without silently adding the synthetic demo corpus. Tool integrations are explicitly disabled in live mode until implemented.

## End-to-end acceptance

- Connect, land on Overview, and see real counts with useful empty states.
- Create a ticket, set priority/owner/status, and locate it with queue filters.
- Add an internal note and edit missing context; stale edits and stale draft approvals fail clearly.
- Investigate, inspect sources/tools, review the exact current draft, and resolve/reopen explicitly.
- Review queue contains only current unreviewed drafts.
- Admin adds/edits/archives/restores a knowledge document; search respects workspace/version and index updates.
- Agent role can search knowledge but cannot mutate it; cross-workspace access fails.
- Activity and seven-day charts reflect persisted events.
- Desktop/mobile and keyboard flows pass against compiled assets with production headers.
- SQLite tests, PostgreSQL CI, fixture evaluation gate, frontend build, browser tests, and container smoke checks pass.

## Release sequence

Contract and plan → independent implementation → integration and authorization review → automated checks → screenshot review → README and known limitations → commit/push → verify GitHub CI. Public Render deployment and live quality claims remain gated on actual configuration and evidence.

## Implemented pilot

The standalone workflow is implemented across the backend, dark dashboard, and user guide. It includes role-scoped knowledge management, ticket triage and internal notes, revision checks, current-draft review queues, and persisted activity reporting. See [the user guide](USER_GUIDE.md) for connection and operating instructions and [release gates](RELEASE_CHECKLIST.md) for the remaining environment-specific work.

Local verification on 2026-10-04: backend lint/format checks pass; 39 tests pass with five PostgreSQL variants reserved for CI; fixture workflow evaluation passes 30/30 development cases; the production frontend compiles. PostgreSQL, container, and browser release evidence is recorded in the GitHub Actions run for the release commit. These results do not establish live-model answer quality or a public deployment.
