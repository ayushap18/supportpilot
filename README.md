# SupportPilot

**An AI support agent that investigates technical tickets, gathers evidence, and drafts a response for human review.**

SupportPilot is a portfolio project for applied AI engineering. It will combine retrieval, tool calling, evaluation, and a deployed Python service around one concrete workflow: resolving support tickets for a fictional SaaS product.

> **Status: planning.** This repository currently contains the implementation plan and design documents. The application, demo, and benchmark results have not been built yet.

## The problem

Technical support teams must connect an error report to documentation, account information, and service status before recommending a fix. SupportPilot will gather that evidence and prepare a reviewable response, including when the correct next step is to ask a question or escalate.

## Example workflow

A customer reports: “My webhook stopped working after upgrading to API v2.”

1. Extract the product version, error, and missing details from the ticket.
2. Search the relevant product documentation and migration guide.
3. Check the customer's account and service status through read-only mock tools.
4. Draft a resolution with citations to the evidence.
5. Ask for missing information or escalate if the evidence is insufficient.
6. Present the draft and investigation trace to a human reviewer.

This is an intended demonstration scenario, not a measured capability.

## MVP scope

- Ticket submission with an optional bounded text log.
- Version-aware documentation retrieval using PostgreSQL and pgvector.
- Three read-only tools: account status, service health, and known incidents.
- Structured outcomes: `resolved`, `needs_information`, or `escalate`.
- Source-linked response drafts and an evidence trace.
- Human approval or rejection of a draft; approval is recorded locally.
- Per-investigation latency, token usage, and estimated model cost.
- A reproducible evaluation suite with a baseline comparison.

The MVP will use **RelayDesk**, a fictional webhook delivery SaaS, and synthetic accounts and tickets. It will not connect to a real help desk or send customer messages.

## Planned stack

| Layer | Choice |
| --- | --- |
| Backend | Python, FastAPI, Pydantic |
| Retrieval | PostgreSQL, pgvector, text search |
| Models | One hosted LLM provider, chosen in milestone 1 |
| Workflow | Explicit state machine with typed tools |
| Frontend | React, TypeScript, Vite |
| Packaging | Docker Compose |
| Quality checks | pytest, Ruff, GitHub Actions |

Start with a small explicit workflow. Introduce an orchestration framework only if the implementation demonstrates a need for it.

## Build roadmap

| Milestone | Deliverable |
| --- | --- |
| 1. Fixtures and contracts | RelayDesk docs, 10 development tickets, API schemas |
| 2. Retrieval baseline | Ingestion, retrieval, grounded draft generation |
| 3. Investigation workflow | Read-only tools, bounded execution, escalation |
| 4. Review interface | Ticket UI, citations, trace, approval history |
| 5. Evaluation | 50 labeled cases, baseline comparison, CI checks |
| 6. Deployment and portfolio | Hosted demo, operations checks, measured report, video |

A four-week schedule is an estimate for someone already comfortable with Python and web development. Acceptance criteria, rather than dates, determine completion.

## Project documents

- [Implementation plan](docs/PLAN.md): milestones, acceptance criteria, and build order.
- [Architecture](docs/ARCHITECTURE.md): data flow, contracts, and operational boundaries.
- [Evaluation plan](docs/EVALUATION.md): dataset, metrics, comparisons, and release gates.
- [GitHub issues](https://github.com/ayushap18/supportpilot/issues): implementation tracking.

## Local development

There is no runnable application yet. Setup commands and environment configuration will be added with the first working implementation. Do not provide real customer data or credentials in tickets or issues.

## Definition of done

- A fresh checkout can run the app using documented commands.
- The deployed demo can investigate a seeded ticket and show its evidence.
- Every external action remains under human control.
- Automated tests exercise tool failures, access boundaries, and review behavior.
- A versioned evaluation report publishes actual results and failure examples.
- The README links to the live demo, architecture, evaluation report, and a short walkthrough.

## Contributing

Use the linked implementation issues in milestone order. Keep changes focused and include the relevant acceptance evidence in each pull request. Update this README when a capability becomes available; do not present planned features as implemented.
