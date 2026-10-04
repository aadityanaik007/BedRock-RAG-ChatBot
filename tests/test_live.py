"""End-to-end checks against real AWS Bedrock. Opt in with RUN_LIVE_TESTS=1; these cost money and need credentials."""

import pytest
from fastapi.testclient import TestClient

import main
from tests.conftest import KNOWLEDGE_DIR

pytestmark = pytest.mark.live


@pytest.fixture
def live_client(monkeypatch):
    docs = [p.read_text(encoding="utf-8") for p in sorted(KNOWLEDGE_DIR.glob("*.md"))]
    monkeypatch.setattr(main, "retrieve_context", lambda query: (docs, []))
    return TestClient(main.app)


def ask(client, message, conversation_id):
    response = client.post("/chat", json={"message": message, "conversation_id": conversation_id})
    assert response.status_code == 200, response.text
    return response.json()


def test_knowledge_base_retrieval():
    contexts, sources = main.retrieve_context("payment failed")
    assert contexts and sources


def test_model_looks_up_session(live_client):
    data = ask(live_client, "What's the status of parking session SES-1002?", "live-1")
    assert {"name": "get_parking_session", "input": {"session_id": "SES-1002"}, "status": "success"} in data["tool_calls"]
    assert "active" in data["response"].lower()


def test_model_chains_session_to_transactions(live_client):
    data = ask(live_client, "Customer on session SES-1006 says they were charged twice. Is that right?", "live-2")
    looked_up = {t["input"].get("transaction_id") for t in data["tool_calls"] if t["name"] == "get_payment_transaction"}
    assert looked_up == {"TXN-9003", "TXN-9004"}


def test_model_advises_against_retry_when_gateway_succeeded(live_client):
    data = ask(live_client, "Payment TXN-9009 failed. Should the customer just retry?", "live-3")
    assert any(t["name"] == "get_payment_transaction" for t in data["tool_calls"])
    assert "not" in data["response"].lower()
