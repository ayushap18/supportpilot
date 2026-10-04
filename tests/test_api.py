from conftest import OTHER_TOKEN


def test_health_and_auth(client, ticket_input):
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    assert client.post("/api/tickets", json=ticket_input).status_code == 401


def test_ticket_persistence_and_workspace_isolation(client, headers, ticket_input):
    result = client.post("/api/tickets", json=ticket_input, headers=headers)
    assert result.status_code == 201
    ticket = result.json()
    assert ticket["workspace_id"] == "demo"
    assert client.get("/api/tickets/" + ticket["id"], headers=headers).json() == ticket
    other = {"Authorization": "Bearer " + OTHER_TOKEN}
    assert client.get("/api/tickets/" + ticket["id"], headers=other).status_code == 404
    assert client.get("/api/tickets", headers=other).json() == []


def test_invalid_and_oversized_input(client, headers, ticket_input):
    assert (
        client.post(
            "/api/tickets", headers=headers, json={**ticket_input, "workspace_id": "other"}
        ).status_code
        == 422
    )


def test_create_investigation_is_idempotent(client, headers, ticket_input):
    ticket = client.post("/api/tickets", json=ticket_input, headers=headers).json()
    path = "/api/tickets/" + ticket["id"] + "/investigations"
    headers = {**headers, "Idempotency-Key": "test-investigation"}
    first = client.post(path, headers=headers)
    second = client.post(path, headers=headers)
    assert first.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert (
        client.post(
            "/api/tickets", headers=headers, json={**ticket_input, "log": "x" * 12001}
        ).status_code
        == 422
    )
