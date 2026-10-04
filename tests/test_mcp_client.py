import json
import logging
from types import SimpleNamespace

import pytest

import mcp_client
from tests.conftest import TOOL_NAMES


def tool_use(name: str, args: dict | None, tool_use_id: str = "tu-1") -> dict:
    return {"toolUseId": tool_use_id, "name": name, "input": args}


def result_payload(block: dict):
    """Decode the single content item of a Bedrock toolResult block."""
    (item,) = block["toolResult"]["content"]
    return item["json"] if "json" in item else json.loads(item["text"])


async def test_list_mcp_tools_returns_all_tools():
    tools = await mcp_client.list_mcp_tools()
    assert {t.name for t in tools} == TOOL_NAMES


async def test_listed_tools_have_descriptions_and_required_args():
    expected_args = {
        "get_parking_session": "session_id",
        "get_payment_transaction": "transaction_id",
        "get_garage_rate": "garage_id",
        "get_device_status": "garage_id",
    }
    for tool in await mcp_client.list_mcp_tools():
        assert tool.description
        assert tool.input_schema["required"] == [expected_args[tool.name]]


async def test_call_mcp_tool_returns_record(mock_parking_session):
    result = await mcp_client.call_mcp_tool("get_parking_session", {"session_id": mock_parking_session["session_id"]})
    assert not result.is_error
    assert json.loads(result.content[0].text) == mock_parking_session


async def test_bedrock_tool_config_shape():
    config = await mcp_client.get_bedrock_tool_config()
    specs = [tool["toolSpec"] for tool in config["tools"]]
    assert {spec["name"] for spec in specs} == TOOL_NAMES
    for spec in specs:
        assert spec["description"]
        assert spec["inputSchema"]["json"]["type"] == "object"


async def test_bedrock_tool_config_is_cached(monkeypatch):
    calls = 0
    real_list = mcp_client.list_mcp_tools

    async def counting_list():
        nonlocal calls
        calls += 1
        return await real_list()

    monkeypatch.setattr(mcp_client, "list_mcp_tools", counting_list)
    first = await mcp_client.get_bedrock_tool_config()
    second = await mcp_client.get_bedrock_tool_config()
    assert first is second
    assert calls == 1


async def test_bedrock_tool_config_falls_back_to_name_for_empty_description(monkeypatch):
    async def fake_list():
        return [SimpleNamespace(name="mystery_tool", description="", input_schema={"type": "object", "properties": {}})]

    monkeypatch.setattr(mcp_client, "list_mcp_tools", fake_list)
    config = await mcp_client.get_bedrock_tool_config()
    assert config["tools"][0]["toolSpec"]["description"] == "mystery_tool"


@pytest.mark.parametrize(
    "name, args, fixture",
    [
        ("get_parking_session", "session_id", "mock_parking_session"),
        ("get_payment_transaction", "transaction_id", "mock_payment_transaction"),
        ("get_garage_rate", "garage_id", "mock_rate"),
        ("get_device_status", "garage_id", "mock_device"),
    ],
)
async def test_run_tool_use_success_for_every_tool(request, name, args, fixture):
    record = request.getfixturevalue(fixture)
    block = await mcp_client.run_tool_use(tool_use(name, {args: record[args]}, "abc"))
    assert block["toolResult"]["toolUseId"] == "abc"
    assert block["toolResult"]["status"] == "success"
    assert result_payload(block) == record


async def test_run_tool_use_record_not_found_is_a_successful_call():
    block = await mcp_client.run_tool_use(tool_use("get_parking_session", {"session_id": "SES-9999"}))
    assert block["toolResult"]["status"] == "success"
    assert result_payload(block) == {"error": "session_not_found", "session_id": "SES-9999"}


async def test_run_tool_use_unknown_tool_returns_error(caplog):
    with caplog.at_level(logging.WARNING, logger="mcp_client"):
        block = await mcp_client.run_tool_use(tool_use("no_such_tool", {}))
    assert block["toolResult"]["status"] == "error"
    assert "no_such_tool" in block["toolResult"]["content"][0]["text"]
    assert "returned an error" in caplog.text


async def test_run_tool_use_missing_argument_returns_error():
    block = await mcp_client.run_tool_use(tool_use("get_parking_session", {}))
    assert block["toolResult"]["status"] == "error"


async def test_run_tool_use_none_input_is_treated_as_empty(monkeypatch):
    seen = {}

    async def fake_call(name, arguments):
        seen["arguments"] = arguments
        return SimpleNamespace(is_error=False, structured_content=None, content=[SimpleNamespace(type="text", text="ok")])

    monkeypatch.setattr(mcp_client, "call_mcp_tool", fake_call)
    await mcp_client.run_tool_use(tool_use("get_parking_session", None))
    assert seen["arguments"] == {}


async def test_run_tool_use_exception_becomes_error_result(monkeypatch, caplog):
    async def exploding_call(name, arguments):
        raise RuntimeError("server crashed")

    monkeypatch.setattr(mcp_client, "call_mcp_tool", exploding_call)
    with caplog.at_level(logging.ERROR, logger="mcp_client"):
        block = await mcp_client.run_tool_use(tool_use("get_parking_session", {"session_id": "SES-1002"}, "xyz"))

    assert block == {
        "toolResult": {
            "toolUseId": "xyz",
            "content": [{"text": "Tool call failed: server crashed"}],
            "status": "error",
        }
    }
    assert "MCP tool get_parking_session failed" in caplog.text
    assert "server crashed" in caplog.text


async def test_run_tool_use_prefers_structured_content(monkeypatch):
    async def fake_call(name, arguments):
        return SimpleNamespace(is_error=False, structured_content={"status": "active"}, content=[])

    monkeypatch.setattr(mcp_client, "call_mcp_tool", fake_call)
    block = await mcp_client.run_tool_use(tool_use("get_parking_session", {"session_id": "SES-1002"}))
    assert block["toolResult"]["content"] == [{"json": {"status": "active"}}]


async def test_run_tool_use_empty_output_gets_placeholder(monkeypatch):
    async def fake_call(name, arguments):
        return SimpleNamespace(is_error=False, structured_content=None, content=[SimpleNamespace(type="image", data="...")])

    monkeypatch.setattr(mcp_client, "call_mcp_tool", fake_call)
    block = await mcp_client.run_tool_use(tool_use("get_parking_session", {"session_id": "SES-1002"}))
    assert block["toolResult"]["content"] == [{"text": "(no output)"}]


async def test_run_tool_use_logs_call_and_result(caplog):
    with caplog.at_level(logging.INFO, logger="mcp_client"):
        await mcp_client.run_tool_use(tool_use("get_garage_rate", {"garage_id": "GAR-01"}))
    assert "Calling MCP tool get_garage_rate" in caplog.text
    assert "MCP tool get_garage_rate returned" in caplog.text


@pytest.mark.stdio
async def test_stdio_server_lists_and_calls_tools(mock_parking_session):
    assert {t.name for t in await mcp_client.list_mcp_tools()} == TOOL_NAMES
    block = await mcp_client.run_tool_use(tool_use("get_parking_session", {"session_id": mock_parking_session["session_id"]}))
    assert result_payload(block) == mock_parking_session
