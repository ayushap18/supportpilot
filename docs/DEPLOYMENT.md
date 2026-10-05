# Deployment and operations

## Current state

Render configuration and GitHub workflows are prepared. No Render service has been provisioned and no public demo URL exists yet. Real provider requests and public hosting remain unverified. Use the [release checklist](RELEASE_CHECKLIST.md), [real-use plan](REAL_USE_PLAN.md), and [operator guide](USER_GUIDE.md) alongside these steps.

## Render setup

1. Create a [Render Blueprint](https://render.com/deploy?repo=https://github.com/ayushap18/supportpilot) from this repository.
2. Review `render.yaml`. It defines one Docker web service and a private PostgreSQL 16 database with pgvector support. Both start on the free plan.
3. Generate a private token with `python scripts/configure_local.py`. Supply the JSON array from `SUPPORTPILOT_API_TOKENS_JSON` to the Render environment variable of the same name. Keep token values private.
4. Let the initial Blueprint build finish. Check `/health/ready`, open the application, and connect using the token for the `demo` workspace.
5. In the service Settings, copy its deploy hook URL into the GitHub repository secret `RENDER_DEPLOY_HOOK_URL`. You may use the `production` environment's secrets instead.
6. Future pushes to `main` deploy only after the complete CI workflow passes. The deployment workflow pins the hook request to the tested commit SHA. It ignores pull-request runs and CI failures.

The initial Blueprint deploy is initiated by Render during provisioning. Later auto-deploys are disabled in the Blueprint because GitHub Actions controls the deployment gate.

The hook reports that deployment was requested, not that it finished. Verify completion in the Render dashboard and run the smoke checks below. [Render documents deploy hooks and specific-commit deployment](https://render.com/docs/deploy-hooks).

Render supports [pgvector extensions](https://render.com/docs/postgresql-extensions). The database user must be able to execute `CREATE EXTENSION IF NOT EXISTS vector`; startup creates the pilot tables and indexes active workspace documents. Fixture mode additionally loads the synthetic corpus; live mode excludes it.

The free configuration is for a demonstration. Review [Render's current free-service limits](https://render.com/docs/free), including database expiry and web-service spin-down, before relying on it for a persistent portfolio URL. Change plans in the Blueprint when you choose to pay for persistent service.

## Workspace identities

`SUPPORTPILOT_API_TOKENS_JSON` is a private JSON array. Each entry contains a unique random `token` of at least 24 characters, `workspace_id`, `reviewer_id`, and optional `role` (`admin` or `agent`). Generate separate tokens per person; do not share the local demo token for a team deployment.

```json
[
  {"token": "REPLACE_WITH_PRIVATE_RANDOM_ADMIN_TOKEN", "workspace_id": "your-team", "reviewer_id": "alex", "role": "admin"},
  {"token": "REPLACE_WITH_PRIVATE_RANDOM_AGENT_TOKEN", "workspace_id": "your-team", "reviewer_id": "sam", "role": "agent"}
]
```

Replace both placeholder tokens with independently generated private random values before use. Set the array as the environment variable value, then restart the API. Members sharing a workspace ID can assign tickets to one another. Both roles can operate tickets and review drafts; only admins can mutate knowledge. Existing entries without a role default to admin for compatibility. Verify roles when migrating configuration.

Users connect by pasting their individual token into **Workspace token**. Tokens remain in browser memory and clear on reload. Rotation and revocation require changing server configuration and restarting. This pilot has no SSO, invitations, or self-service account administration.

## Live model configuration

Fixture mode is the default. It performs deterministic routing and lexical feature hashing without provider requests. The UI labels this mode explicitly.

To enable live mode, set these **server-side** Render variables:

- `SUPPORTPILOT_MODE=live`.
- `SUPPORTPILOT_OPENAI_API_KEY`: your private OpenAI API key.
- `SUPPORTPILOT_MODEL`: a Responses API model with structured output support available to your account.
- `SUPPORTPILOT_EMBEDDING_MODEL`: defaults to `text-embedding-3-small` with 1536 dimensions.

Restart the service after changing modes. Live mode does not load synthetic seed documents. Add your workspace knowledge through the admin interface; active saved sources survive restarts. Live embeddings are generated when documents are saved or when startup detects a source/embedding configuration change. Account, service-health, and incident tools are disabled in live application investigations until real adapters are implemented. The live adapter has contract tests with mocked provider responses; real provider calls remain unverified until credentials are configured.

Cost display needs dated input/output generation prices. Set `SUPPORTPILOT_INPUT_USD_PER_MILLION`, `SUPPORTPILOT_OUTPUT_USD_PER_MILLION`, and `SUPPORTPILOT_PRICING_DATE`. Live evaluations additionally require `SUPPORTPILOT_EMBEDDING_USD_PER_MILLION`. A missing price displays unavailable cost, not zero. Generation estimates exclude embeddings and usage from failed calls when the provider did not report it.

## Local Docker

Create `.env` first, then:

```bash
docker compose up --build
```

Open `http://127.0.0.1:8000`. The database is private to the Compose network and persists in the named `postgres-data` volume. Avoid deleting that volume unless you intend to reset the local demo data.

Docker is not running on the development machine used for the initial implementation. GitHub CI builds the image and runs readiness, frontend, and unauthorized-access smoke checks; the PostgreSQL integration test runs against a separate pgvector container.

## Smoke checks after deployment

- `/health/live` and `/health/ready` return 200.
- `/` renders the complete interface with local font assets.
- `/api/tickets` returns 401 without a workspace token.
- An authenticated operator can create a ticket, assign it, change priority/status, and add a note.
- In fixture mode, investigate the migration example and inspect evidence. In live mode, add relevant workspace knowledge and verify a grounded draft against its actual sources.
- Admins can add/edit/archive/restore knowledge; agents can search it but receive 403 for mutations.
- Stale ticket saves and reviews of a draft based on changed context return 409.
- Overview counts, current review queue, and activity reflect the saved actions.
- Approval records a decision; no message is sent to a customer.
- Another workspace cannot read the ticket or submit a review.

## Operations and boundaries

- Run one API worker. Requests execute synchronously with a 45-second overall deadline; restart recovery marks interrupted investigations as failed and requires a new idempotency key.
- Up to three workflow rounds and five tool calls per investigation. Hosted provider requests may retry transient failures twice; invalid tool arguments are not retried.
- Default workspace allowance: 30 investigations per hour, persisted in the database. Idempotent replay does not consume another allowance.
- Model outputs are bounded to 1800 tokens per round; serialized model inputs are bounded to 40,000 characters. Tool outputs are capped.
- Reviews bind to an immutable draft revision and the captured ticket revision. Duplicate or stale decisions are rejected. Even priority/status edits invalidate an older draft for review. Approval does not automatically resolve a ticket.
- Obvious credentials are redacted before ticket persistence. This is a pattern-based safeguard, not comprehensive sensitive-data detection; use synthetic inputs only.
- Tickets older than 30 days and their investigation, review, note, and activity data are purged on startup. Configure `SUPPORTPILOT_RETENTION_DAYS` from 1 to 365. Knowledge source documents are retained, including archives. Archive removes searchable chunks rather than deleting the source. For uninterrupted deployments, restart periodically or add a separately reviewed scheduled cleanup job.
- Readiness currently checks database access; live provider availability is handled during investigations. Do not treat a green readiness check as an LLM quality guarantee.
- Schema initialization uses SQLAlchemy `create_all` for the initial MVP. Add explicit migrations before changing existing table structures in a deployed database.

## Remaining release work

Configure provider credentials, run budgeted live evaluations, and manually review grounded answers before making quality claims. Provision Render, verify the deployed commit and public smoke flows, and test database backup/restore. Establish an agreed retention/data-handling policy and suitable team identity onboarding before processing customer data. External help-desk intake, customer-message delivery, and live operational tools require separate adapters.

Dashboard readiness labels are a checklist, not automated certification of these prerequisites. Keep evaluation and deployment issues open until the work has evidence; record a walkthrough and tester feedback after the pilot is usable.

## Optional engineering integrations

Follow [GitHub setup](GITHUB_SETUP.md) to configure the OAuth client, exact HTTPS callback, and stable encryption key as private server variables. These variables are optional; the UI reports unavailable configuration until provided. No GitHub credentials are taken from the developer machine automatically.

The hosted application stores task records and encrypted GitHub credentials; the [agent bridge](AGENT_BRIDGE.md) runs on an operator's machine with its own CLI authentication. Do not install unrestricted coding CLIs into the web service to execute queued tasks.

Agent runs expire under the configured startup retention policy. Runs linked to expired tickets are deleted with their captured ticket context, along with local GitHub issue mappings. Remote GitHub issues are unaffected. Repository snapshots and imported knowledge remain until integration disconnection or explicit knowledge management; disconnecting retains imported knowledge. Expired OAuth states are cleaned on startup. Retention does not stop an already-running external CLI process.
