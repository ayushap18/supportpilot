import json

from supportpilot.config import ROOT
from supportpilot.schemas import TicketCreate


def test_documents_and_development_labels_are_consistent():
    folder = ROOT / "data/relaydesk"
    documents = json.loads((folder / "documents.json").read_text())
    ids = {doc["id"] for doc in documents}
    assert len(ids) == len(documents)
    for doc in documents:
        assert doc["revision"] and doc["source_path"] and doc["body"]
        assert doc["product_version"] in {"v1", "v2", "any"}
    cases = json.loads((folder / "development.json").read_text())
    assert len(cases) == 10
    for case in cases:
        TicketCreate.model_validate(case["ticket"])
        assert set(case["required_evidence_ids"]) <= ids
        assert case["expected_outcome"] in {"resolved", "needs_information", "escalate"}
