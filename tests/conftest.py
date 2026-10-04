import json

import pytest
from fastapi.testclient import TestClient
from supportpilot.app import create_app
from supportpilot.config import Settings

TOKEN = "test-demo-token-at-least-24-characters"
OTHER_TOKEN = "test-other-token-at-least-24-characters"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        database_url="sqlite:///" + str(tmp_path / "test.db"),
        api_tokens_json=json.dumps(
            [
                {"token": TOKEN, "workspace_id": "demo", "reviewer_id": "alice"},
                {"token": OTHER_TOKEN, "workspace_id": "other", "reviewer_id": "bob"},
            ]
        ),
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def headers():
    return {"Authorization": "Bearer " + TOKEN}


@pytest.fixture
def ticket_input():
    return {
        "subject": "Webhook migration failure",
        "description": "Our webhook fails after upgrading to API v2.",
        "product_version": "v2",
        "account_id": "acct_active",
    }
