# ADR 0001: Keep the first runtime explicit and reproducible

Status: accepted for the MVP.

## Decisions

- Python/FastAPI owns ticket persistence, authorization, investigation, and reviews.
- PostgreSQL/pgvector is the deployment database. SQLite is a convenient local/test fallback, with Python ranking rather than pretending to provide PostgreSQL full-text search.
- Hybrid retrieval combines separately ranked vector and lexical lists through reciprocal rank fusion. Workspace and version filters apply before ranking.
- Fixture mode uses lexical feature hashing and deterministic routing. Live mode uses OpenAI embeddings and schema-validated Responses API output. They are labeled separately in the UI and reports.
- Typed model output proposes read-only tool calls; the server validates arguments and supplies workspace identity. The explicit workflow enforces rounds, calls, and time limits.
- One API worker executes requests directly. A persisted investigation ID and idempotency key prevent duplicate work. A durable worker queue remains a future extension if restart frequency or request duration justifies it.
- One Docker service serves both the React build and API, avoiding separate-origin configuration for the MVP.
- CI tests backend behavior against SQLite and PostgreSQL, runs Chromium workflows, gates fixture regressions, then builds and smoke-tests the Docker image. Successful main-branch CI can request a Render deployment of that commit.

## Evidence and tradeoffs

The first ten development cases produced seven expected outcomes in retrieval-only fixture mode; the three misses required tools. The expanded dataset and reports record later measurements. These fixture observations motivated the demonstration workflow but do not establish live-model quality.

The live adapter follows [structured output documentation](https://developers.openai.com/api/docs/guides/structured-outputs) and [embedding documentation](https://developers.openai.com/api/docs/guides/embeddings). Provider credentials and semantic human review are still required before making quality claims.

The repository avoids additional orchestration, message brokers, and infrastructure while the workflow is small. This keeps local setup and investigation traces reviewable, at the cost of limited concurrency and explicit restart recovery.
