import argparse
import asyncio
import hashlib
import json
import math
import statistics
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from supportpilot.config import ROOT, Settings
from supportpilot.provider import PROMPT_VERSION, Provider
from supportpilot.retrieval import Retrieval
from supportpilot.schemas import Investigation, Ticket
from supportpilot.storage import Database
from supportpilot.tools import Tools
from supportpilot.workflow import investigate


def measure(case, investigation):
    draft = investigation.draft
    outcome = draft.outcome if draft else None
    cited = set(draft.evidence_ids) if draft else set()
    available = {item.id for item in investigation.evidence}
    retrieved_docs = {
        item.id.split(":")[1] for item in investigation.evidence if item.kind == "document"
    }
    cited_docs = {
        item.id.split(":")[1]
        for item in investigation.evidence
        if item.kind == "document" and item.id in cited
    }
    tools = [event.tool_result.name for event in investigation.trace if event.tool_result]
    fact_matches = bool(draft) and all(
        fact.lower() in draft.response.lower() for fact in case["required_facts"]
    )
    outcome_match = outcome == case["expected_outcome"]
    return {
        "case_id": case["id"],
        "category": case["category"],
        "expected_outcome": case["expected_outcome"],
        "actual_outcome": outcome,
        "outcome_correct": outcome_match,
        "reference_facts_match": bool(outcome_match and fact_matches),
        "retrieval_reference_match": set(case["required_evidence_ids"]) <= retrieved_docs,
        "cited_reference_match": set(case["required_evidence_ids"]) <= cited_docs,
        "citation_ids_valid": bool(draft) and cited <= available,
        "required_tools_used": set(case["required_tools"]) <= set(tools),
        "tools_used": tools,
        "state": investigation.state,
        "latency_ms": investigation.latency_ms,
        "estimated_generation_cost_usd": investigation.usage.estimated_cost_usd,
        "investigation": investigation.model_dump(mode="json"),
    }


def summarize(rows):
    latency = sorted(row["latency_ms"] for row in rows)
    costs = [row["estimated_generation_cost_usd"] for row in rows]
    return {
        "cases": len(rows),
        "outcome_correct": sum(row["outcome_correct"] for row in rows),
        "outcome_accuracy": sum(row["outcome_correct"] for row in rows) / len(rows),
        "reference_facts_match": sum(row["reference_facts_match"] for row in rows) / len(rows),
        "retrieval_reference_match": sum(row["retrieval_reference_match"] for row in rows)
        / len(rows),
        "citation_id_validity": sum(row["citation_ids_valid"] for row in rows) / len(rows),
        "median_latency_ms": statistics.median(latency),
        "p95_latency_ms": latency[math.ceil(len(latency) * 0.95) - 1],
        "failure_count": sum(row["state"] == "failed" for row in rows),
        "total_generation_cost_usd": sum(costs)
        if all(cost is not None for cost in costs)
        else None,
    }


async def evaluate(args):
    dataset_path = ROOT / "evals" / (args.split + ".json")
    if args.split == "held-out" and not args.allow_held_out:
        raise SystemExit("Held-out cases require --allow-held-out after freezing the release.")
    settings = Settings(mode=args.mode)
    cases = json.loads(dataset_path.read_text())
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("No cases selected")
    if args.mode == "live":
        # Reserve a conservative upper bound before any chargeable request.
        if (
            not all(
                value is not None
                for value in (
                    settings.input_usd_per_million,
                    settings.output_usd_per_million,
                    settings.embedding_usd_per_million,
                    settings.pricing_date,
                )
            )
            or args.max_spend_usd <= 0
        ):
            raise SystemExit(
                "Live evaluation requires dated generation/embedding pricing and a spend cap."
            )
        requests = len(cases) * args.repeat * 2
        generation_bound = (
            requests
            * settings.max_rounds
            * 3
            * (
                (settings.max_input_chars * 4 + 12000) * settings.input_usd_per_million
                + settings.max_output_tokens * settings.output_usd_per_million
            )
            / 1_000_000
        )
        corpus_bytes = len((settings.data_dir / "documents.json").read_bytes())
        embedding_bound = (
            3
            * (corpus_bytes * 4 + requests * 32000)
            * settings.embedding_usd_per_million
            / 1_000_000
        )
        if generation_bound + embedding_bound > args.max_spend_usd:
            raise SystemExit(
                f"Conservative bound ${generation_bound + embedding_bound:.2f} exceeds spend cap; "
                "reduce cases/rounds or review the cap."
            )
    with tempfile.TemporaryDirectory(prefix="supportpilot-evaluation-") as temporary:
        settings.database_url = "sqlite:///" + str(Path(temporary) / "evaluation.db")
        database = Database(settings.database_url)
        database.initialize()
        provider = Provider(settings)
        retrieval = Retrieval(database, settings, provider)
        try:
            await retrieval.ingest()
            experiments = {}
            for name, allow_tools in (("baseline", False), ("workflow", True)):
                rows = []
                for repetition in range(args.repeat):
                    for case in cases:
                        tools = Tools(settings.data_dir)
                        tools.errors = {name: True for name in case.get("tool_errors", [])}
                        for key, value in case.get("tool_overrides", {}).items():
                            tools.fixtures[key] = value
                        ticket = Ticket(
                            **case["ticket"],
                            id=str(uuid4()),
                            workspace_id="demo",
                            created_at=datetime.now(UTC),
                        )
                        investigation = Investigation(
                            id=str(uuid4()),
                            ticket_id=ticket.id,
                            workspace_id="demo",
                            state="queued",
                            created_at=datetime.now(UTC),
                            mode=settings.mode,
                        )
                        result = await investigate(
                            ticket,
                            investigation,
                            retrieval,
                            provider,
                            settings,
                            tools=tools,
                            allow_tools=allow_tools,
                        )
                        row = measure(case, result)
                        row["repetition"] = repetition + 1
                        rows.append(row)
                experiments[name] = {"summary": summarize(rows), "cases": rows}
        finally:
            await provider.close()
            database.engine.dispose()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    report = {
        "mode": args.mode,
        "split": args.split,
        "repeat": args.repeat,
        "code_commit": commit,
        "prompt_version": PROMPT_VERSION,
        "model": settings.model if args.mode == "live" else "deterministic-fixture-router",
        "embedding": provider.embedding_signature,
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "corpus_sha256": hashlib.sha256(
            (settings.data_dir / "documents.json").read_bytes()
        ).hexdigest(),
        "pricing_date": settings.pricing_date,
        "created_at": datetime.now(UTC).isoformat(),
        "limitations": [
            "Fixture results validate routing behavior, not LLM quality.",
            "Reference fact matching is a substring proxy, not human resolution review.",
            "Citation ID validity does not establish semantic claim support.",
            "Generation cost excludes embeddings and failed unreported provider usage.",
            "Synthetic fixtures do not establish performance on real support traffic.",
        ],
        "experiments": experiments,
    }
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [
        "# Evaluation report",
        "",
        f"Mode: **{args.mode}** · Split: **{args.split}** · Repetitions: {args.repeat}",
        "",
        f"Code commit: `{commit}` · Prompt: `{PROMPT_VERSION}`",
        "",
        "These automatic checks do not satisfy the plan's human-reviewed live-model release gates.",
        "",
        "| Experiment | Correct outcomes | Reference facts proxy | "
        "Median latency | p95 latency | Failures |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, experiment in experiments.items():
        summary = experiment["summary"]
        lines.append(
            f"| {name} | {summary['outcome_correct']}/{summary['cases']} | "
            f"{summary['reference_facts_match']:.0%} | {summary['median_latency_ms']:.1f} ms | "
            f"{summary['p95_latency_ms']:.1f} ms | {summary['failure_count']} |"
        )
    lines.extend(["", "## Failures and limitations", ""])
    failures = [row for row in experiments["workflow"]["cases"] if not row["reference_facts_match"]]
    lines.extend(
        f"- `{row['case_id']}`: expected `{row['expected_outcome']}`, "
        f"observed `{row['actual_outcome']}`; facts matched: {row['reference_facts_match']}."
        for row in failures
    )
    if not failures:
        lines.append(
            "No workflow reference-fact mismatches in this run. "
            "This is not evidence of live-model reliability."
        )
    lines.extend(
        [
            "",
            *["- " + item for item in report["limitations"]],
            "",
            "Inspect `results.json` for complete per-case outputs and provenance.",
        ]
    )
    (output / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({name: value["summary"] for name, value in experiments.items()}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fixture", "live"], default="fixture")
    parser.add_argument("--split", choices=["development", "held-out"], default="development")
    parser.add_argument("--allow-held-out", action="store_true")
    parser.add_argument("--repeat", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-spend-usd", type=float, default=0)
    parser.add_argument("--output", default="evals/runs/latest")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    asyncio.run(evaluate(args))


if __name__ == "__main__":
    main()
