import json
import logging

import main
import mcp_client
from tests.conftest import text_reply, tool_reply


def tool_results_sent(call: dict) -> list[dict]:
    """The toolResult blocks in the last message Bedrock received."""
    return [block["toolResult"] for block in call["messages"][-1]["content"]]


def decoded(result: dict):
    return json.loads(result["content"][0]["text"])


def test_tool_call_runs_against_mock_data(chat, bedrock, mock_parking_session):
    sid = mock_parking_session["session_id"]
    bedrock.script(
        tool_reply(("t1", "get_parking_session", {"session_id": sid}), text="Let me look that up."),
        text_reply("Your session is active."),
    )
    response = chat(f"What's the status of {sid}?")

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Your session is active."
    assert data["tool_calls"] == [{"name": "get_parking_session", "input": {"session_id": sid}, "status": "success"}]

    (result,) = tool_results_sent(bedrock.calls[1])
    assert result["toolUseId"] == "t1"
    assert result["status"] == "success"
    assert decoded(result) == mock_parking_session


def test_tool_result_follows_assistant_tool_request(chat, bedrock):
    bedrock.script(tool_reply(("t1", "get_device_status", {"garage_id": "GAR-01"})), text_reply("Exit gate is offline."))
    chat("Is GAR-01 ok?")

    messages = bedrock.calls[1]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert "toolUse" in messages[1]["content"][0]
    assert messages[2]["content"][0]["toolResult"]["toolUseId"] == "t1"


def test_parallel_tool_calls_in_one_round(chat, bedrock):
    bedrock.script(
        tool_reply(
            ("a", "get_payment_transaction", {"transaction_id": "TXN-9001"}),
            ("b", "get_device_status", {"garage_id": "GAR-01"}),
        ),
        text_reply("Payment pending and exit gate offline."),
    )
    data = chat("TXN-9001 paid but can't exit GAR-01").json()

    assert [t["name"] for t in data["tool_calls"]] == ["get_payment_transaction", "get_device_status"]
    results = tool_results_sent(bedrock.calls[1])
    assert [r["toolUseId"] for r in results] == ["a", "b"]
    assert decoded(results[0])["gateway_status"] == "successful"
    assert decoded(results[1])["exit_device_status"] == "offline"


def test_multi_round_duplicate_charge_investigation(chat, bedrock):
    bedrock.script(
        tool_reply(("s", "get_parking_session", {"session_id": "SES-1006"})),
        tool_reply(
            ("t1", "get_payment_transaction", {"transaction_id": "TXN-9003"}),
            ("t2", "get_payment_transaction", {"transaction_id": "TXN-9004"}),
        ),
        text_reply("Two settled charges share one idempotency key: duplicate."),
    )
    data = chat("SES-1006 says they were charged twice").json()

    assert len(bedrock.calls) == 3
    assert decoded(tool_results_sent(bedrock.calls[1])[0])["transaction_ids"] == ["TXN-9003", "TXN-9004"]
    second_round = [decoded(r) for r in tool_results_sent(bedrock.calls[2])]
    assert {t["idempotency_key"] for t in second_round} == {"idem-SES-1006-1"}
    assert all(t["settled"] for t in second_round)
    assert len(data["tool_calls"]) == 3


def test_unknown_tool_does_not_crash(chat, bedrock):
    bedrock.script(tool_reply(("t1", "delete_everything", {})), text_reply("I can't do that."))
    response = chat("Delete all sessions")

    assert response.status_code == 200
    assert response.json()["tool_calls"][0]["status"] == "error"
    assert tool_results_sent(bedrock.calls[1])[0]["status"] == "error"


def test_record_not_found_is_passed_to_model(chat, bedrock):
    bedrock.script(tool_reply(("t1", "get_parking_session", {"session_id": "SES-9999"})), text_reply("No such session."))
    response = chat("Check SES-9999")

    assert response.status_code == 200
    assert decoded(tool_results_sent(bedrock.calls[1])[0]) == {"error": "session_not_found", "session_id": "SES-9999"}


def test_tool_exception_does_not_crash(chat, bedrock, monkeypatch):
    async def exploding_call(name, arguments):
        raise ConnectionError("MCP server unreachable")

    monkeypatch.setattr(mcp_client, "call_mcp_tool", exploding_call)
    bedrock.script(tool_reply(("t1", "get_parking_session", {"session_id": "SES-1002"})), text_reply("Lookup failed."))
    response = chat("Status of SES-1002?")

    assert response.status_code == 200
    (result,) = tool_results_sent(bedrock.calls[1])
    assert result["status"] == "error"
    assert "MCP server unreachable" in result["content"][0]["text"]


def test_final_response_excludes_tool_preamble(chat, bedrock):
    bedrock.script(
        tool_reply(("t1", "get_garage_rate", {"garage_id": "GAR-03"}), text="Checking rates..."),
        text_reply("Event pricing is $40 flat."),
    )
    assert chat("GAR-03 rate?").json()["response"] == "Event pricing is $40 flat."


def test_max_tool_rounds_returns_error(chat, bedrock, caplog):
    bedrock.always(lambda i, _: tool_reply((f"t{i}", "get_garage_rate", {"garage_id": "GAR-01"})))
    with caplog.at_level(logging.WARNING, logger="main"):
        response = chat("Loop forever")

    assert response.status_code == 500
    assert "too many tool calls" in response.json()["detail"]
    assert len(bedrock.calls) == main.MAX_TOOL_ROUNDS + 1
    assert f"exceeded {main.MAX_TOOL_ROUNDS} tool rounds" in caplog.text


def test_exactly_max_tool_rounds_then_answer_succeeds(chat, bedrock):
    rounds = [tool_reply((f"t{i}", "get_garage_rate", {"garage_id": "GAR-01"})) for i in range(main.MAX_TOOL_ROUNDS)]
    bedrock.script(*rounds, text_reply("Done."))
    response = chat("Check a lot")

    assert response.status_code == 200
    assert len(response.json()["tool_calls"]) == main.MAX_TOOL_ROUNDS
