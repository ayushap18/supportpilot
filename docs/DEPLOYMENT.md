# Deployment and operations

## Current state

Render configuration and GitHub workflows are prepared. No Render service has been provisioned and no public demo URL exists yet. This repository currently has no deployment or model API secrets configured.

## Render setup

1. Create a [Render Blueprint](https://render.com/deploy?repo=https://github.com/ayushap18/supportpilot) from this repository.
2. Review `render.yaml`. It defines one Docker web service and a private PostgreSQL 16 database with pgvector support. Both start on the free plan.
3. Generate a private token with `python scripts/configure_local.py`. Supply the JSON array from `SUPPORTPILOT_API_TOKENS_JSON` to the Render environment variable of the same name. Keep token values private.
4. Let the initial Blueprint build finish. Check `/health/ready`, open the application, and connect using the token for the `demo` workspace.
5. In the service Settings, copy its deploy hook URL into the GitHub repository secret `RENDER_DEPLOY_HOOK_URL`. You may use the `production` environment's secrets instead.
6. Future pushes to `main` deploy only after the complete CI workflow passes. The deployment workflow pins the hook request to the tested commit SHA. It ignores pull-request runs and CI failures.

The initial Blueprint deploy is initiated by Render during provisioning. Later auto-deploys are disabled in the Blueprint because GitHub Actions controls the deployment gate.

The hook reports that deployment was requested, not that it finished. Verify completion in the Render dashboard and run the smoke checks below. [Render documents deploy hooks and specific-commit deployment](https://render.com/docs/deploy-hooks).

Render supports [pgvector extensions](https://render.com/docs/postgresql-extensions). The database user must be able to execute `CREATE EXTENSION IF NOT EXISTS vector`; startup then creates the MVP tables and ingests the synthetic corpus.

The free configuration is for a demonstration. Review [Render's current free-service limits](https://render.com/docs/free), including database expiry and web-service spin-down, before relying on it for a persistent portfolio URL. Change plans in the Blueprint when you choose to pay for persistent service.

## Live model configuration

Fixture mode is the default. It performs deterministic routing and lexical feature hashing without provider requests. The UI labels this mode explicitly.

To enable live mode, set these **server-side** Render variables:

- `SUPPORTPILOT_MODE=live`.
- `SUPPORTPILOT_OPENAI_API_KEY`: your private OpenAI API key.
- `SUPPORTPILOT_MODEL`: a Responses API model with structured output support available to your account.
- `SUPPORTPILOT_EMBEDDING_MODEL`: defaults to `text-embedding-3-small` with 1536 dimensions.

Restart the service after changing modes. Live embeddings are generated at startup when the corpus or embedding configuration changes. The live adapter has contract tests with mocked provider responses; real provider calls remain unverified until credentials are configured.

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
- An authenticated reviewer can create the migration example, inspect evidence, and approve its draft.
- Approval records a decision; no message is sent to a customer.
- Another workspace cannot read the ticket or submit a review.

## Operations and boundaries

- Run one API worker. Requests execute synchronously with a 45-second overall deadline; restart recovery marks interrupted investigations as failed and requires a new idempotency key.
- Up to three workflow rounds and five tool calls per investigation. Hosted provider requests may retry transient failures twice; invalid tool arguments are not retried.
- Default workspace allowance: 30 investigations per hour, persisted in the database. Idempotent replay does not consume another allowance.
- Model outputs are bounded to 1800 tokens per round; serialized model inputs are bounded to 40,000 characters. Tool outputs are capped.
- Reviews bind to an immutable draft revision. Duplicate or stale decisions are rejected.
- Obvious credentials are redacted before ticket persistence. This is a pattern-based safeguard, not comprehensive sensitive-data detection; use synthetic inputs only.
- Ticket, investigation, and review data older than 30 days are purged on startup. Configure `SUPPORTPILOT_RETENTION_DAYS` from 1 to 365. Product documents are retained. For uninterrupted deployments, restart periodically or add a separately reviewed scheduled cleanup job.
- Readiness currently checks database access; live provider availability is handled during investigations. Do not treat a green readiness check as an LLM quality guarantee.
- Schema initialization uses SQLAlchemy `create_all` for the initial MVP. Add explicit migrations before changing existing table structures in a deployed database.

## Remaining release work

Configure provider credentials, run budgeted live evaluations, manually review held-out outputs, provision Render, verify the public demo, record a short walkthrough, and collect tester feedback. Keep the evaluation and deployment issues open until those steps have evidence.
