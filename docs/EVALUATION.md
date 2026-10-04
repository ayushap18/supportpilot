# Evaluation plan

## Goal

Determine whether SupportPilot produces supported resolutions, asks for missing information, and escalates when necessary. Measure the benefit of tools against a simpler retrieval-only baseline.

No benchmark results exist yet. All targets below are proposed release criteria, not reported performance.

## Dataset

Create 50 synthetic RelayDesk cases. Use 30 for development and 20 held out from tuning. Include these primary categories, while allowing additional tags per case:

| Primary category | Cases |
| --- | --- |
| Document-grounded resolutions | 15 |
| Resolutions requiring tool evidence | 10 |
| Missing information | 8 |
| Unsupported questions requiring escalation | 5 |
| Conflicting or outdated version evidence | 5 |
| Tool failures | 4 |
| Prompt-injection attempts | 3 |
| Total | 50 |

Balance both splits across categories where feasible. Keep independent deterministic security and authorization tests in addition to these model-driven cases.

Each case records: input ticket, workspace/version context, mock tool fixtures, expected outcome, acceptable resolution facts, required evidence IDs, required or forbidden tool behavior, and forbidden unsupported claims. Review labels before running the system.

Use 10 cases for the initial vertical slice, then expand without silently changing labels to match model output. Store dataset revision and random seed with results.

## Experiments

1. **Baseline:** version-aware retrieval followed by one grounded draft; no tools.
2. **Investigation workflow:** same corpus and model plus bounded typed tool calls.
3. **Optional retrieval experiment:** compare simple retrieval with hybrid retrieval only after baseline measurements exist.

Use identical fixtures and the same outcome/citation schema. Record prompts, provider/model identifiers, settings, code commit, corpus revision, dataset revision, and dated pricing configuration. Repeat the final held-out run three times and report variability. Freeze the release before opening held-out results; improvements after that require a new held-out set or a clearly labeled reused benchmark.

## Metrics

| Metric | Definition |
| --- | --- |
| Outcome accuracy | Cases with the correct resolved/needs-information/escalate outcome divided by cases evaluated |
| Resolution correctness | Resolvable cases whose response satisfies the reference rubric without a critical incorrect claim |
| Citation accuracy | Supported cited factual claims divided by reviewed cited factual claims |
| Citation coverage | Claims requiring evidence that have supporting citations divided by all claims requiring evidence |
| Escalation recall | Cases requiring escalation that are escalated divided by all escalation-required cases |
| Clarification accuracy | Missing-information cases that ask for the reference missing detail |
| Tool behavior correctness | Tool-relevant cases meeting allowed/required tool and argument rules |
| Operational performance | Median and p95 end-to-end latency, estimated cost per ticket, and failure rate |

Report counts and denominators, including category results. Mark metrics with no eligible examples as N/A. Include failed investigations in operational reporting and score their missing answers as failures where an answer was required.

Deterministic checks validate schemas, evidence references, tool arguments, and access rules. A human reviews all 20 held-out cases using the rubric; an LLM judge may supplement review but does not replace it. Human reviewers should not be told which implementation generated a response when practical.

## Proposed release gates

- Outcome accuracy of at least 85% on the held-out set.
- Resolution correctness of at least 80% on resolvable held-out cases.
- Citation accuracy and coverage of at least 90% each.
- No unsafe tool executions or workspace access violations in dedicated regression tests.
- No approval applied to a stale draft revision in regression tests.
- Every investigation respects execution budgets and handles provider/tool failure explicitly.

These are small-sample gates for a synthetic demonstration, not production guarantees. Publish all observed scores even when a gate fails. Tune latency and cost targets after collecting the initial baseline; do not invent measurements or performance claims.

## CI and live evaluations

Run deterministic tests with mocked model outputs on every pull request. Run live-model evaluations through an explicitly triggered GitHub Actions workflow with server-side secrets and a maximum spend budget. Fork PRs must not receive provider credentials.

Save machine-readable per-case outputs and a Markdown report. Review generated artifacts for credentials before publication.

## Final portfolio report

Publish baseline versus workflow results, category-level errors, latency and cost, exact evaluation configuration, at least three representative failure cases, and changes justified by the evidence. Explain that synthetic RelayDesk fixtures do not establish generalization to real support traffic.
