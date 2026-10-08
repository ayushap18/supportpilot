# Evaluation runner

The dataset has 30 development cases and 20 held-out cases, totaling the category counts in [the evaluation plan](../docs/EVALUATION.md). Labels are never supplied to the investigation provider. Tool failures and incidents are injected through isolated synthetic fixtures.

Run from the repository root after installing the Python dependencies:

```bash
python -m evals.run --output evals/runs/development
```

The runner compares retrieval-only drafts with tool-assisted investigations. It writes a Markdown report and per-case JSON, including code, corpus, dataset, and prompt revisions. No provider calls are made in fixture mode.

Freeze the code before examining held-out results:

```bash
python -m evals.run --split held-out --allow-held-out --repeat 3 --output evals/runs/held-out
```

After using held-out failures to guide implementation, treat that set as a regression set and create a new held-out dataset for future quality claims.

## Replay evals from human reviews

`supportpilot evals --from-reviews --fail-below last` turns every human approve/reject in the local database into a case (`evals/from_reviews.py`, redacted), replays it with the stored evidence and recorded tool results frozen, and reports `approval_agreement`: an approved outcome must be reproduced, a rejected one must not. Results go to `evals/runs/reviews/`; `--fail-below last` exits 1 when agreement drops below the previous run, and lists approved tickets the change flips. Autopilot approvals are excluded. In live mode each case is one model call, so use `--limit`.

## Live evaluation

Set the OpenAI key and dated model/embedding pricing in your private environment. Run with `--mode live`, `--limit`, and `--max-spend-usd`. The runner reserves a conservative bound for all planned model rounds, potential retries, and embeddings before making requests. If the bound exceeds the cap, it refuses the run.

GitHub Actions provides a manually triggered **Live evaluation** workflow. It never runs on pull requests. Required configuration:

- Secret: `OPENAI_API_KEY`.
- Variables: `LLM_MODEL`, `INPUT_USD_PER_MILLION`, `OUTPUT_USD_PER_MILLION`, `EMBEDDING_USD_PER_MILLION`, and `PRICING_DATE` (`YYYY-MM-DD`).

Confirm pricing against your provider account and model before setting it. Do not paste keys into tickets, commit them, or share them in chat.

## What the automatic scores mean

Outcome accuracy checks the final route. Reference fact matching is a substring proxy. Citation ID validity checks whether a reference exists; it does not determine whether a claim is supported. Costs cover reported generation usage only and exclude embeddings and unreported failed requests.

Human review of all held-out outputs is still required to measure resolution correctness, semantic citation accuracy, and citation coverage. Live-model release gates remain pending until that review and live evaluations are complete. Fixture successes establish behavior of the offline demonstration, not model reliability.
