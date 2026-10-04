import os

import pytest
from fastapi.testclient import TestClient
from supportpilot.app import create_app
from supportpilot.storage import Database


@pytest.mark.skipif(not os.getenv("SUPPORTPILOT_TEST_POSTGRES_URL"), reason="Postgres CI only")
def test_postgres_vector_fts_and_persistence(settings, headers, ticket_input):
    settings.database_url = os.environ["SUPPORTPILOT_TEST_POSTGRES_URL"]
    with TestClient(create_app(settings)) as client:
        ticket = client.post("/api/tickets", json=ticket_input, headers=headers).json()
        response = client.post(
            "/api/tickets/" + ticket["id"] + "/investigations",
            headers={**headers, "Idempotency-Key": "postgres-integration-test"},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["state"] == "awaiting_review"
        assert "Bearer" in result["draft"]["response"]
        assert all(item["product_version"] in {"v2", "any"} for item in result["evidence"])
    db = Database(settings.database_url)
    db.ready()
    db.engine.dispose()
