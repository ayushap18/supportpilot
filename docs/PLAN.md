# Implementation plan

## Current progress

Milestones 1–4 are implemented and tested. Milestone 5 has datasets, a runner, fixture reports, and a live workflow; live evaluation and human review remain pending. Milestone 6 has packaging and deployment configuration; public hosting and portfolio release work remain pending. See README for current evidence.

## Objective

Build and deploy a small support investigation system that demonstrates backend engineering, grounded generation, typed tool use, evaluation, and clear technical communication.

The product is deliberately narrow: support for RelayDesk, a fictional webhook delivery SaaS. The MVP handles authentication errors, rate limits, delivery failures, version migrations, and service incidents. All documentation, customer records, and logs are synthetic.

## Working principles

- Implement a complete vertical slice before expanding scope.
- Build evaluation examples before prompt tuning.
- Keep tool behavior deterministic and model outputs schema-validated.
- Treat retrieved documents and logs as untrusted input.
- Record failure cases and tradeoffs, not just successful examples.
- Use one provider and one deployment environment initially.

## Milestone 1: Fixtures and contracts

Create the RelayDesk knowledge base: overview, API v1 and v2, authentication, rate limits, webhook delivery, troubleshooting, migration guide, and incident policies. Include purposeful differences between versions.

Create synthetic account records, incident records, and 10 development tickets. Each ticket includes a reference outcome and evidence. Define Pydantic models for tickets, evidence, tool arguments/results, investigations, and reviews.

Acceptance criteria:

- [x] Every document has a stable ID, product version, and revision.
- [x] Every development ticket has an expected outcome and cited evidence IDs.
- [x] Mock tool fixtures cover healthy, failing, unknown, and unauthorized states.
- [x] Repository setup, dependency lockfile, environment example, and basic CI exist.
- [x] A local API accepts a ticket, persists it, and returns an investigation ID.

## Milestone 2: Retrieval baseline

Implement document ingestion and chunking with stable source metadata. Add PostgreSQL full-text and vector retrieval with product/version filtering. Initially use a simple retrieval baseline; add hybrid ranking after measuring the baseline.

Generate a structured draft from retrieved evidence. Show exact source excerpts in the API response, not fabricated source URLs.

Acceptance criteria:

- [x] Re-ingesting an unchanged document does not duplicate chunks.
- [x] Updated documents replace or retire stale searchable revisions.
- [x] Retrieved evidence respects workspace and known version filters.
- [x] Unknown versions trigger clarification when the answer depends on version.
- [x] Unsupported questions return clarification or escalation.
- [x] A development-set report records retrieval and answer quality.

## Milestone 3: Investigation workflow

Add `get_account_status`, `get_service_health`, and `search_known_incidents` as typed, read-only tools backed by fixtures. Use an explicit state machine: classify, retrieve, investigate, compose, validate, and await review.

Limit each investigation to three model rounds and five tool calls. Enforce tool schemas, timeouts, and a total budget. Retry transient failures at most twice with backoff; never retry invalid arguments or access denials automatically.

Acceptance criteria:

- [x] Tool requests are validated before execution.
- [x] Caller workspace identity comes from authentication, never model arguments.
- [x] Invalid calls and tool failures are represented in the trace.
- [x] Execution terminates when a call, time, or cost budget is reached.
- [x] Prompt injection in logs or documents cannot authorize tools or change access scope.
- [x] The final outcome is resolved, needs information, or escalate, with an explanation.

## Milestone 4: Human review interface

Build a minimal React interface for ticket submission, investigation status, evidence, and draft review. Reviewers can approve or reject a draft and provide a note. Record reviewer identity, draft revision, and timestamp.

Approval records a decision inside SupportPilot; it does not send a message or execute a fix.

Acceptance criteria:

- [x] The UI shows cited excerpts alongside the draft.
- [x] The trace shows tool outcomes and summarized decisions without exposing private model reasoning.
- [x] Failed and timed-out investigations have useful visible states.
- [x] Review endpoints require authentication and workspace access.
- [x] Reviews refer to a specific draft revision and reject stale approvals.

## Milestone 5: Evaluation and regression checks

Expand to 50 labeled synthetic cases: 30 development cases and 20 held-out cases. Follow [the evaluation plan](EVALUATION.md). Compare retrieval-only generation against the complete investigation workflow using the same model, corpus, and test inputs.

Acceptance criteria:

- [ ] The dataset and evaluation configuration are versioned.
- [ ] CI runs deterministic contract, authorization, and workflow regression checks.
- [ ] A separately triggered live-model evaluation generates per-case results.
- [ ] A report includes outcome correctness, evidence accuracy, tool correctness, latency, and cost.
- [ ] Failed cases are discussed; held-out cases are not used to tune the release being evaluated.
- [ ] Release gates are met or the limitations are explicitly documented before further work.

## Milestone 6: Deployment and portfolio

Package the services with Docker Compose and deploy to one hosting environment. Choose hosting based on database support, operating cost, and deployment simplicity during this milestone.

Acceptance criteria:

- [ ] A fresh checkout works using the documented setup commands.
- [ ] CI runs tests, lint, frontend checks, and build validation.
- [ ] The demo uses synthetic data, authenticated reviews, and bounded usage.
- [ ] Readiness checks cover required service dependencies.
- [ ] Secrets remain server-side; logs redact obvious credentials.
- [ ] Cost limits, rate limits, timeouts, and data-retention behavior are documented.
- [ ] README contains demo, report, and walkthrough links.
- [ ] A three-minute walkthrough includes a successful resolution and an escalation.
- [ ] Record feedback from external testers when available, with consent and without overstating adoption.

## Suggested four-week schedule

| Week | Focus |
| --- | --- |
| 1 | Fixtures, contracts, local API, and retrieval baseline |
| 2 | Investigation tools, bounded execution, and review UI |
| 3 | Evaluation, failure handling, and regression checks |
| 4 | Deployment, evaluation report, documentation, and demo |

Extend this schedule when learning the stack. Do not skip evaluation to meet an arbitrary deadline.

## Out of scope for the MVP

Real customer integrations, automatic replies, billing, fine-tuning, multi-agent orchestration, Kubernetes, and unrestricted browser or shell execution. Add a capability only after identifying a specific user need and a measurable improvement.

## Key decisions to record

Use short architecture decision records when selecting the model/provider, chunking strategy, retrieval ranking, synchronous versus background execution, and deployment platform. Explain the alternatives, measured evidence where available, and the tradeoff.
