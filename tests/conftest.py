import copy
import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

# Keep test runs from writing into the project's logs/ directory; must be set before main is imported.
os.environ.setdefault("LOG_DIR", tempfile.mkdtemp(prefix="bedrock-rag-test-logs-"))

import main  # noqa: E402
import mcp_client  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from mcp_server import server as mcp_server_module  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "mock_data"
KNOWLEDGE_DIR = ROOT / "knowledge"

TOOL_NAMES = {"get_parking_session", "get_payment_transaction", "get_garage_rate", "get_device_status"}


def load_mock(name: str) -> list:
    with open(DATA_DIR / name, encoding="utf-8") as file:
        return json.load(file)


def bedrock_response(content: list, stop_reason: str, input_tokens: int = 10, output_tokens: int = 5, latency_ms: int = 100) -> dict:
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop_reason,
        "usage": {"inputTokens": input_tokens, "outputTokens": output_tokens, "totalTokens": input_tokens + output_tokens},
        "metrics": {"latencyMs": latency_ms},
    }


def text_reply(text: str, **kwargs) -> dict:
    return bedrock_response([{"text": text}], "end_turn", **kwargs)


def tool_reply(*calls: tuple, text: str | None = None, **kwargs) -> dict:
    """Build a tool_use response from (tool_use_id, name, input) tuples."""
    content = [{"text": text}] if text else []
    content += [{"toolUse": {"toolUseId": tid, "name": name, "input": args}} for tid, name, args in calls]
    return bedrock_response(content, "tool_use", **kwargs)


def client_error(operation: str, code: str = "ValidationException", message: str = "boom") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message}}, operation)


class FakeBedrockRuntime:
    """Stands in for the bedrock-runtime client; replays scripted responses and records each converse call."""

    def __init__(self):
        self.calls: list[dict] = []
        self._script: list = []
        self._responder = None

    def script(self, *responses):
        self._script = list(responses)
        return self

    def always(self, responder):
        self._responder = responder
        return self

    def converse(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        if self._responder is not None:
            item = self._responder(len(self.calls) - 1, kwargs)
        elif self._script:
            item = self._script.pop(0)
        else:
            raise AssertionError("Unexpected extra converse call")
        if isinstance(item, Exception):
            raise item
        return copy.deepcopy(item)


class FakeAgentRuntime:
    """Stands in for the bedrock-agent-runtime client used for Knowledge Base retrieval."""

    def __init__(self):
        self.calls: list[dict] = []
        self.results: list[dict] = [
            {
                "content": {"text": "If an exit device is offline, the barrier will not open."},
                "score": 0.71,
                "location": {"s3Location": {"uri": "s3://kb/payment_failed.md"}},
            }
        ]
        self.error: Exception | None = None

    def retrieve(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        if self.error:
            raise self.error
        return {"retrievalResults": self.results}


def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_LIVE_TESTS") == "1":
        return
    skip_live = pytest.mark.skip(reason="live AWS test; set RUN_LIVE_TESTS=1 to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def in_process_mcp(request, monkeypatch):
    """Run MCP tools in-process (fast) unless a test is marked stdio, and reset cached state."""
    if "stdio" not in request.keywords:
        monkeypatch.setattr(mcp_client, "server_params", mcp_server_module.mcp)
    monkeypatch.setattr(mcp_client, "_bedrock_tool_config", None)
    main.conversations.clear()
    yield
    main.conversations.clear()


@pytest.fixture
def bedrock(monkeypatch):
    fake = FakeBedrockRuntime()
    monkeypatch.setattr(main, "bedrock_runtime", fake)
    return fake


@pytest.fixture
def kb(monkeypatch):
    fake = FakeAgentRuntime()
    monkeypatch.setattr(main, "bedrock_agent_runtime", fake)
    return fake


@pytest.fixture
def client(bedrock, kb):
    return TestClient(main.app)


@pytest.fixture
def chat(client, sample_conversation_id):
    """Post a message to /chat, defaulting to this test's conversation ID."""

    def send(message: str, conversation_id: str | None = None):
        return client.post("/chat", json={"message": message, "conversation_id": conversation_id or sample_conversation_id})

    return send


@pytest.fixture
def sample_conversation_id():
    return "test_conv_" + uuid4().hex[:8]


@pytest.fixture
def sessions():
    return load_mock("sessions.json")


@pytest.fixture
def transactions():
    return load_mock("transactions.json")


@pytest.fixture
def rates():
    return load_mock("rates.json")


@pytest.fixture
def devices():
    return load_mock("devices.json")


@pytest.fixture
def mock_parking_session(sessions):
    return sessions[0]


@pytest.fixture
def mock_payment_transaction(transactions):
    return transactions[0]


@pytest.fixture
def mock_rate(rates):
    return rates[0]


@pytest.fixture
def mock_device(devices):
    return devices[0]
