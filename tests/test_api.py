"""Test FastAPI endpoints (unit-level, no real LLM calls)."""

import pytest
from fastapi.testclient import TestClient

from agiraph.server import app, agent_registry
from agiraph.agent import Agent


@pytest.fixture(autouse=True)
def clear_registry():
    agent_registry.clear()
    yield
    agent_registry.clear()


client = TestClient(app)


def test_list_agents_empty():
    resp = client.get("/agents")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_agent_not_found():
    resp = client.get("/agents/nonexistent")
    assert resp.status_code == 404


def test_create_agent():
    resp = client.post("/agents", json={
        "goal": "Test goal",
        "model": "anthropic/claude-sonnet-4-5",
        "mode": "finite",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["goal"] == "Test goal"
    assert data["mode"] == "finite"
    assert data["status"] in ("idle", "working")
    assert "id" in data


def test_list_agents_after_create():
    client.post("/agents", json={"goal": "Agent 1"})
    client.post("/agents", json={"goal": "Agent 2"})
    resp = client.get("/agents")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_agent():
    create_resp = client.post("/agents", json={"goal": "Test"})
    agent_id = create_resp.json()["id"]
    resp = client.get(f"/agents/{agent_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == agent_id


def test_get_board():
    create_resp = client.post("/agents", json={"goal": "Test"})
    agent_id = create_resp.json()["id"]
    resp = client.get(f"/agents/{agent_id}/board")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "stages" in data


def test_get_workers():
    create_resp = client.post("/agents", json={"goal": "Test"})
    agent_id = create_resp.json()["id"]
    resp = client.get(f"/agents/{agent_id}/workers")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_conversation():
    create_resp = client.post("/agents", json={"goal": "Test"})
    agent_id = create_resp.json()["id"]
    resp = client.get(f"/agents/{agent_id}/conversation")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_events():
    create_resp = client.post("/agents", json={"goal": "Test"})
    agent_id = create_resp.json()["id"]
    resp = client.get(f"/agents/{agent_id}/events")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_workspace_browser():
    create_resp = client.post("/agents", json={"goal": "Test"})
    agent_id = create_resp.json()["id"]
    resp = client.get(f"/agents/{agent_id}/workspace")
    assert resp.status_code == 200
    assert resp.json()["type"] == "dir"


def test_memory_browser():
    create_resp = client.post("/agents", json={"goal": "Test"})
    agent_id = create_resp.json()["id"]
    resp = client.get(f"/agents/{agent_id}/memory")
    assert resp.status_code == 200


def test_send_message():
    create_resp = client.post("/agents", json={"goal": "Test"})
    agent_id = create_resp.json()["id"]
    resp = client.post(f"/agents/{agent_id}/send", json={"message": "Hello agent"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"


def test_delete_agent():
    create_resp = client.post("/agents", json={"goal": "Test"})
    agent_id = create_resp.json()["id"]
    resp = client.delete(f"/agents/{agent_id}")
    assert resp.status_code == 200
    # Should be gone
    assert client.get(f"/agents/{agent_id}").status_code == 404
