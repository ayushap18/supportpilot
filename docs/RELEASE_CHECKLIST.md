# Operational pilot release checklist

SupportPilot targets a standalone internal support workspace. Completing this checklist does not establish live-model accuracy or production readiness. Record the commit, environment, date, and evidence for each release gate; a fixture result must remain labeled as fixture evidence.

## Automated acceptance gates

Run these against the release commit after integration:

- Backend lint, formatting, SQLite tests, and PostgreSQL integration tests pass.
- Existing ticket creation, investigation, citation, review, redaction, and workspace isolation tests remain passing.
- Ticket assignment, lifecycle, internal notes, optimistic revisions, and stale-draft review rejection pass.
- Dashboard counts and review queues agree with persisted records, including queues larger than the legacy 100-ticket limit.
- Knowledge creation, edits, archive, restore, version filtering, and restart persistence pass; agents cannot mutate knowledge and other workspaces cannot read it.
- Live mode does not silently ingest the synthetic corpus or execute synthetic account/service tools.
- Fixture evaluation threshold passes. This checks deterministic regression behavior, not LLM answer quality.
- Frontend production build passes. Chromium tests run against compiled assets with deployment security headers and an isolated test database.
- Browser coverage exercises approval, missing-context and escalation outcomes, ticket operations, knowledge operations, rejected tokens, keyboard controls, and mobile overflow.
- Packaged Docker application passes readiness, frontend serving, and authentication smoke checks.

Use the current GitHub Actions run and its artifacts as release evidence. A deploy workflow that skips a missing hook is not a deployed application.

## Human interface review

- Inspect desktop and mobile screenshots for readable contrast, usable spacing, consistent navigation, and clipped content.
- Confirm real empty, loading, error, forbidden, stale, and success states are understandable.
- Verify reviewers can inspect source excerpts and tool input/results before deciding.
- Verify approval records a decision and does not imply a customer message was sent or automatically resolve the ticket.
- Confirm fixture/live labels, tool availability, metrics, and readiness indicators describe actual behavior.

## Required before handling real customer data

- Provision the hosting service and durable PostgreSQL database; apply and verify the schema, pgvector extension, TLS, secrets, and health checks.
- Configure the Render deploy hook securely; verify the intended commit is live, authenticated, and recoverable after restart. Test rollback.
- Establish team identity onboarding, token rotation/revocation, access review, and an agreed SSO/session-management plan. Static workspace tokens are pilot authentication.
- Agree on data retention, deletion, logging, redaction limitations, and vendor data-processing requirements. Check that retained data matches the stated policy.
- Configure automated database backups and demonstrate restore into an isolated environment. Record recovery time and data-loss expectations.
- Configure error monitoring, investigation failure alerts, spend limits, and an operational owner.
- Assess concurrent usage, database locks, investigation limits, and the current one-worker execution model under representative load.

## Required before claiming AI support quality

- Configure the model provider and embedding credentials through secrets; run a real provider integration smoke test.
- Load and review the team's own knowledge documents. Verify source/version/workspace scoping and ingestion updates.
- Keep account, service health, and incident tools disabled in live mode until real authenticated adapters and authorization tests exist.
- Run budgeted live evaluations on representative tickets. Report dataset size, outcome correctness, citation support, escalation behavior, latency, and cost separately from fixture scores.
- Have human reviewers assess unsupported claims, incomplete evidence, prompt injection attempts, and unsafe operational advice.
- Obtain pilot feedback and document failures, rollback criteria, and escalation ownership before expanding usage.

## Evidence status

This document defines gates; unchecked prose is not a claim that a gate passed. Record actual test results in the release summary and CI artifacts. Hosting, SSO, backups, live-provider quality, real external tool adapters, and customer feedback require environment-specific evidence and cannot be inferred from a successful local build.

## Engineering integration gates

- OAuth state/cookie binding, expiration, replay prevention, encrypted storage, and workspace/admin scope are verified with mocked GitHub responses.
- Snapshot and import limits are visible; uncertain issue writes reconcile without blind recreation.
- Agent claim/completion is atomic and scoped. Missing usage remains unknown, provider errors stay failed, and no automatic merge/issue-resolution claim is made.
- Local bridge checks repository identity, passes task data through stdin, bounds output/time, and isolates authorized edits in a preserved worktree.
- Real OAuth authorization, repository import, deliberate issue publication, and each installed CLI's live behavior require an operator test after credentials are configured.
