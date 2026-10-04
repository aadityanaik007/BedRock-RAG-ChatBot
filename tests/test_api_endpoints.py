import pytest
import main
from botocore.exceptions import EndpointConnectionError

from tests.conftest import client_error, text_reply


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_response_schema(chat, bedrock, sample_conversation_id):
    bedrock.script(text_reply("ok"))
    data = chat("Hi").json()
    assert set(data) == {"conversation_id", "response", "sources", "tool_calls", "usage", "latency_ms", "stop_reason"}
    assert data["conversation_id"] == sample_conversation_id


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"message": "hi"},
        {"conversation_id": "c1"},
        {"message": None, "conversation_id": "c1"},
        {"message": ["hi"], "conversation_id": "c1"},
        {"message": "hi", "conversation_id": {"id": 1}},
    ],
    ids=["empty", "no-conversation-id", "no-message", "null-message", "list-message", "object-conversation-id"],
)
def test_chat_rejects_invalid_body(client, bedrock, body):
    assert client.post("/chat", json=body).status_code == 422
    assert bedrock.calls == []


def test_chat_rejects_non_json(client):
    response = client.post("/chat", content="hello", headers={"Content-Type": "text/plain"})
    assert response.status_code == 422


def test_chat_requires_post(client):
    assert client.get("/chat").status_code == 405


def test_unknown_route(client):
    assert client.get("/history/abc").status_code == 404


def test_retrieval_error_returns_502(chat, kb):
    kb.error = client_error("Retrieve", message="Knowledge base not found")
    response = chat("Hi")
    assert response.status_code == 502
    assert response.json()["detail"] == main.SERVICE_UNAVAILABLE_MESSAGE


def test_model_error_returns_502(chat, bedrock):
    bedrock.script(client_error("Converse", code="AccessDeniedException", message="Authentication failed: Please make sure your API Key is valid."))
    response = chat("Hi")
    assert response.status_code == 502
    assert response.json()["detail"] == main.SERVICE_UNAVAILABLE_MESSAGE
    assert "AccessDenied" not in response.text and "API Key" not in response.text


def test_network_error_returns_502(chat, bedrock):
    bedrock.script(EndpointConnectionError(endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com"))
    assert chat("Hi").status_code == 502


def test_openapi_lists_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/chat" in paths and "/health" in paths
