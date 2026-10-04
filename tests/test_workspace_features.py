"""Operational acceptance against SQLite locally and PostgreSQL in CI."""

import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete
from supportpilot.app import create_app
from supportpilot.storage import Base, Database


@pytest.fixture(params=["sqlite", "postgres"])
def workspace(request, settings):
    if request.param == "postgres":
        database_url = os.getenv("SUPPORTPILOT_TEST_POSTGRES_URL")
        if not database_url:
            pytest.skip("PostgreSQL integration runs in CI")
        settings.database_url = database_url
    workspace_id = "acceptance-" + uuid4().hex
    tokens = {
        "admin": "acceptance-admin-" + uuid4().hex,
        "agent": "acceptance-agent-" + uuid4().hex,
        "other": "acceptance-other-" + uuid4().hex,
    }
    settings.api_tokens_json = SecretStr(
        json.dumps(
            [
                {
                    "token": token,
                    "workspace_id": workspace_id + ("-other" if name == "other" else ""),
                    "reviewer_id": name,
                    "role": "agent" if name == "agent" else "admin",
                }
                for name, token in tokens.items()
            ]
        )
    )
    headers = {name: {"Authorization": "Bearer " + token} for name, token in tokens.items()}
    yield settings, headers
    # The CI database is shared with other tests: remove only this test's workspaces.
    database = Database(settings.database_url)
    with database.engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            if "workspace_id" in table.c:
                connection.execute(
                    delete(table).where(
                        table.c.workspace_id.in_([workspace_id, workspace_id + "-other"])
                    )
                )
    database.engine.dispose()


def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def test_ticket_lifecycle_notes_review_revision_and_dashboard(workspace, ticket_input):
    settings, auth = workspace
    with TestClient(create_app(settings)) as client:
        ticket = checked(client.post("/api/tickets", headers=auth["agent"], json=ticket_input), 201)
        path = "/api/tickets/" + ticket["id"]
        changed = checked(
            client.patch(
                path,
                headers=auth["admin"],
                json={
                    "expected_revision": 1,
                    "status": "in_progress",
                    "priority": "urgent",
                    "assignee": "agent",
                },
            )
        )
        assert changed["revision"] == 2
        assert changed["assignee"] == "agent"
        assert (
            client.patch(
                path, headers=auth["admin"], json={"expected_revision": 1, "status": "resolved"}
            ).status_code
            == 409
        )
        assert (
            client.patch(
                path, headers=auth["admin"], json={"expected_revision": 2, "assignee": "other"}
            ).status_code
            == 422
        )
        assert (
            client.patch(
                path, headers=auth["other"], json={"expected_revision": 2, "status": "resolved"}
            ).status_code
            == 404
        )

        note = checked(
            client.post(
                path + "/notes",
                headers=auth["agent"],
                json={"body": "Verified migration; password=do-not-retain-this"},
            ),
            201,
        )
        assert note["author_id"] == "agent"
        assert "do-not-retain-this" not in note["body"]
        assert "[REDACTED]" in note["body"]
        assert checked(client.get(path + "/notes", headers=auth["admin"])) == [note]
        assert client.get(path + "/notes", headers=auth["other"]).status_code == 404
        assert (
            client.post(
                path + "/notes", headers=auth["other"], json={"body": "Forbidden"}
            ).status_code
            == 404
        )
        assert (
            client.post(path + "/notes", headers=auth["agent"], json={"body": "   "}).status_code
            == 422
        )

        inv = checked(
            client.post(
                path + "/investigations",
                headers={**auth["agent"], "Idempotency-Key": "before-context-change"},
            )
        )
        assert inv["state"] == "awaiting_review"
        assert inv["ticket_revision"] == 2
        pending = checked(client.get("/api/queue?review=pending", headers=auth["admin"]))
        assert [item["id"] for item in pending["items"]] == [ticket["id"]]
        changed = checked(
            client.patch(
                path,
                headers=auth["agent"],
                json={
                    "expected_revision": 2,
                    "description": "Updated context: only API v2 delivery is affected.",
                },
            )
        )
        review = {
            "draft_revision": inv["draft_revision"],
            "decision": "approve",
            "note": "Checked evidence",
        }
        assert (
            client.post(
                f"/api/investigations/{inv['id']}/reviews", headers=auth["admin"], json=review
            ).status_code
            == 409
        )
        assert checked(client.get("/api/queue?review=pending", headers=auth["admin"]))["total"] == 0
        assert (
            checked(client.get("/api/queue", headers=auth["admin"]))["items"][0]["review_status"]
            == "stale"
        )

        current = checked(
            client.post(
                path + "/investigations",
                headers={**auth["agent"], "Idempotency-Key": "after-context-change"},
            )
        )
        checked(
            client.post(
                f"/api/investigations/{current['id']}/reviews",
                headers=auth["admin"],
                json={**review, "draft_revision": current["draft_revision"]},
            ),
            201,
        )
        assert checked(client.get(path, headers=auth["admin"]))["status"] == "in_progress"
        resolved = checked(
            client.patch(
                path,
                headers=auth["agent"],
                json={"expected_revision": changed["revision"], "status": "resolved"},
            )
        )
        dashboard = checked(client.get("/api/operations", headers=auth["admin"]))
        assert dashboard["counts"]["tickets"] == dashboard["counts"]["resolved"] == 1
        assert dashboard["counts"]["awaiting_review"] == 0
        assert {member["reviewer_id"] for member in dashboard["members"]} == {"admin", "agent"}
        assert all(event["ticket_id"] == ticket["id"] for event in dashboard["activity"])
        assert {event["kind"] for event in dashboard["activity"]} >= {
            "ticket_created",
            "ticket_updated",
            "note_added",
            "investigation",
            "review",
        }
        today = datetime.now(UTC).date()
        assert [row["date"] for row in dashboard["trends"]] == [
            str(today - timedelta(days=offset)) for offset in range(6, -1, -1)
        ]
        assert dashboard["trends"][-1]["tickets"] == 1
        assert dashboard["trends"][-1]["investigations"] == 2
        assert dashboard["trends"][-1]["approved"] == 1
        assert (
            checked(client.get("/api/operations", headers=auth["other"]))["counts"]["tickets"] == 0
        )
        reopened = checked(
            client.patch(
                path,
                headers=auth["admin"],
                json={
                    "expected_revision": resolved["revision"],
                    "status": "open",
                    "assignee": None,
                },
            )
        )
        assert reopened["status"] == "open" and reopened["assignee"] is None


def test_queue_pagination_and_counts_include_more_than_one_hundred_tickets(workspace, ticket_input):
    settings, auth = workspace
    with TestClient(create_app(settings)) as client:
        for index in range(103):
            checked(
                client.post(
                    "/api/tickets",
                    headers=auth["admin"],
                    json={**ticket_input, "subject": f"Pagination probe {index:03}"},
                ),
                201,
            )
        first = checked(client.get("/api/queue?page_size=100", headers=auth["admin"]))
        second = checked(client.get("/api/queue?page_size=100&page=2", headers=auth["admin"]))
        assert first["total"] == second["total"] == 103
        assert len(first["items"]) == 100 and len(second["items"]) == 3
        assert not {item["id"] for item in first["items"]} & {
            item["id"] for item in second["items"]
        }
        assert (
            checked(client.get("/api/operations", headers=auth["admin"]))["counts"]["tickets"]
            == 103
        )
        found = checked(
            client.get(
                "/api/queue?search=Pagination%20probe%20077&status=open&priority=normal",
                headers=auth["admin"],
            )
        )
        assert found["total"] == 1
        assert found["items"][0]["subject"] == "Pagination probe 077"
        assert checked(client.get("/api/queue", headers=auth["other"]))["total"] == 0


def test_knowledge_permissions_revision_index_updates_archive_restore_and_restart(workspace):
    settings, auth = workspace
    original = {
        "title": "Webhook recovery runbook",
        "body": "To recover silverfin webhooks on API v2, retry delivery from the recovery queue.",
        "product_version": "v2",
        "source_path": "internal/recovery",
    }
    with TestClient(create_app(settings)) as client:
        assert (
            client.post(
                "/api/knowledge/documents", headers=auth["agent"], json=original
            ).status_code
            == 403
        )
        document = checked(
            client.post("/api/knowledge/documents", headers=auth["admin"], json=original), 201
        )
        path = "/api/knowledge/documents/" + document["id"]
        assert document["chunk_count"] > 0
        search = {"query": "silverfin webhook recovery", "product_version": "v2"}
        evidence = checked(
            client.post("/api/knowledge/search", headers=auth["agent"], json=search)
        )["evidence"]
        assert len(evidence) == 1 and evidence[0]["excerpt"] == original["body"]
        assert (
            checked(
                client.post(
                    "/api/knowledge/search",
                    headers=auth["agent"],
                    json={**search, "product_version": "v1"},
                )
            )["evidence"]
            == []
        )
        assert (
            checked(client.post("/api/knowledge/search", headers=auth["other"], json=search))[
                "evidence"
            ]
            == []
        )
        assert checked(client.get("/api/knowledge/documents", headers=auth["other"]))["total"] == 0
        updated_input = {
            **original,
            "body": "Silverfin recovery now requires checking the replay cursor before retrying.",
            "expected_revision": 1,
        }
        assert client.patch(path, headers=auth["agent"], json=updated_input).status_code == 403
        assert client.patch(path, headers=auth["other"], json=updated_input).status_code == 404
        updated = checked(client.patch(path, headers=auth["admin"], json=updated_input))
        assert updated["revision"] == 2
        assert client.patch(path, headers=auth["admin"], json=updated_input).status_code == 409
        assert (
            checked(client.post("/api/knowledge/search", headers=auth["admin"], json=search))[
                "evidence"
            ][0]["excerpt"]
            == updated_input["body"]
        )
        assert (
            client.post(
                path + "/archive", headers=auth["agent"], json={"expected_revision": 2}
            ).status_code
            == 403
        )
        assert (
            client.post(
                path + "/archive", headers=auth["admin"], json={"expected_revision": 1}
            ).status_code
            == 409
        )
        archived = checked(
            client.post(path + "/archive", headers=auth["admin"], json={"expected_revision": 2})
        )
        assert archived["archived"] and archived["chunk_count"] == 0
        assert (
            checked(client.post("/api/knowledge/search", headers=auth["admin"], json=search))[
                "evidence"
            ]
            == []
        )
        assert (
            client.patch(
                path, headers=auth["admin"], json={**updated_input, "expected_revision": 3}
            ).status_code
            == 409
        )
        assert (
            checked(client.get("/api/operations", headers=auth["admin"]))["counts"][
                "knowledge_documents"
            ]
            == 0
        )

    # Archived sources survive process restart without being silently reindexed.
    with TestClient(create_app(settings)) as restarted:
        persisted = checked(restarted.get("/api/knowledge/documents", headers=auth["admin"]))[
            "items"
        ]
        assert len(persisted) == 1 and persisted[0]["archived"]
        assert (
            checked(restarted.post("/api/knowledge/search", headers=auth["admin"], json=search))[
                "evidence"
            ]
            == []
        )
        assert (
            restarted.post(
                path + "/restore", headers=auth["agent"], json={"expected_revision": 3}
            ).status_code
            == 403
        )
        restored = checked(
            restarted.post(path + "/restore", headers=auth["admin"], json={"expected_revision": 3})
        )
        assert restored["revision"] == 4 and not restored["archived"]
        assert restored["chunk_count"] > 0
        assert (
            checked(restarted.post("/api/knowledge/search", headers=auth["agent"], json=search))[
                "evidence"
            ][0]["excerpt"]
            == updated_input["body"]
        )
        assert (
            checked(restarted.get("/api/operations", headers=auth["admin"]))["counts"][
                "knowledge_documents"
            ]
            == 1
        )


def test_failed_embedding_preserves_published_document_and_index(workspace, monkeypatch):
    settings, auth = workspace
    original = {
        "title": "Safe update runbook",
        "body": "The published recovery steps stay searchable when indexing a replacement fails.",
        "product_version": "any",
        "source_path": "internal/safe-update",
    }
    with TestClient(create_app(settings)) as client:
        document = checked(
            client.post("/api/knowledge/documents", headers=auth["admin"], json=original), 201
        )

        async def unavailable(_texts):
            raise RuntimeError("Simulated embedding provider failure")

        with monkeypatch.context() as patch:
            patch.setattr(client.app.state.provider, "embed", unavailable)
            result = client.patch(
                "/api/knowledge/documents/" + document["id"],
                headers=auth["admin"],
                json={
                    **original,
                    "body": "Replacement content must not publish after embedding fails.",
                    "expected_revision": 1,
                },
            )
            assert result.status_code == 503
            assert (
                client.post(
                    "/api/knowledge/documents", headers=auth["admin"], json=original
                ).status_code
                == 503
            )
        listing = checked(client.get("/api/knowledge/documents", headers=auth["admin"]))
        assert listing["total"] == 1
        assert listing["items"][0]["revision"] == 1
        assert listing["items"][0]["body"] == original["body"]
        evidence = checked(
            client.post(
                "/api/knowledge/search",
                headers=auth["admin"],
                json={"query": "published recovery steps", "product_version": "v2"},
            )
        )["evidence"]
        assert evidence[0]["excerpt"] == original["body"]
