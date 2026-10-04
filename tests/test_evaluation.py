import json
from collections import Counter

from supportpilot.config import ROOT
from supportpilot.schemas import TicketCreate

from evals.run import summarize


def test_dataset_contracts_and_split_balance():
    development = json.loads((ROOT / "evals/development.json").read_text())
    held = json.loads((ROOT / "evals/held-out.json").read_text())
    assert len(development) == 30 and len(held) == 20
    assert len({case["id"] for case in development + held}) == 50
    assert Counter(case["category"] for case in development + held) == {
        "document": 15,
        "tools": 10,
        "missing": 8,
        "unsupported": 5,
        "version": 5,
        "failure": 4,
        "injection": 3,
    }
    for case in development + held:
        TicketCreate.model_validate(case["ticket"])
        assert case["required_facts"] and case["expected_outcome"]


def test_summary_counts_failures_and_never_invents_cost():
    rows = [
        {
            "latency_ms": latency,
            "outcome_correct": correct,
            "reference_facts_match": correct,
            "retrieval_reference_match": True,
            "citation_ids_valid": correct,
            "state": "awaiting_review" if correct else "failed",
            "estimated_generation_cost_usd": None,
        }
        for latency, correct in [(10, True), (20, False)]
    ]
    result = summarize(rows)
    assert result["outcome_accuracy"] == 0.5
    assert result["failure_count"] == 1
    assert result["p95_latency_ms"] == 20
    assert result["total_generation_cost_usd"] is None
