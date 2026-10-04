# Evaluation report

Mode: **fixture** · Split: **held-out** · Repetitions: 3

Code commit: `4ea9c56295021f239e2ce6005fdc5fe6f7f258c7` · Prompt: `support-investigation-v1`

These automatic checks do not satisfy the plan's human-reviewed live-model release gates.

| Experiment | Correct outcomes | Reference facts proxy | Median latency | p95 latency | Failures |
| --- | --- | --- | --- | --- | --- |
| baseline | 51/60 | 75% | 1.8 ms | 2.6 ms | 0 |
| workflow | 60/60 | 100% | 1.9 ms | 2.6 ms | 0 |

## Failures and limitations

No workflow reference-fact mismatches in this run. This is not evidence of live-model reliability.

- Fixture results validate routing behavior, not LLM quality.
- Reference fact matching is a substring proxy, not human resolution review.
- Citation ID validity does not establish semantic claim support.
- Generation cost excludes embeddings and failed unreported provider usage.
- Synthetic fixtures do not establish performance on real support traffic.

Inspect `results.json` for complete per-case outputs and provenance.
