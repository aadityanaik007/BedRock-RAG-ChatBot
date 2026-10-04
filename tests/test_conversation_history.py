import main
from tests.conftest import client_error, text_reply, tool_reply


def roles(messages: list[dict]) -> list[str]:
    return [m["role"] for m in messages]


def test_history_saved_after_success(chat, bedrock, sample_conversation_id):
    bedrock.script(text_reply("Hi there."))
    chat("Hello")
    assert roles(main.conversations[sample_conversation_id]) == ["user", "assistant"]


def test_follow_up_includes_prior_turns(chat, bedrock):
    bedrock.script(text_reply("SES-1002 is active."), text_reply("It's at GAR-01."))
    chat("Status of SES-1002?")
    chat("Which garage?")

    messages = bedrock.calls[1]["messages"]
    assert roles(messages) == ["user", "assistant", "user"]
    assert "Status of SES-1002?" in messages[0]["content"][0]["text"]
    assert messages[1]["content"][0]["text"] == "SES-1002 is active."


def test_tool_turns_are_stored(chat, bedrock, sample_conversation_id):
    bedrock.script(tool_reply(("t1", "get_device_status", {"garage_id": "GAR-05"})), text_reply("Camera degraded."))
    chat("GAR-05 devices?")
    history = main.conversations[sample_conversation_id]
    assert roles(history) == ["user", "assistant", "user", "assistant"]
    assert "toolResult" in history[2]["content"][0]


def test_conversations_are_isolated(chat, bedrock):
    bedrock.script(text_reply("A"), text_reply("B"))
    chat("First", conversation_id="conv-a")
    chat("Second", conversation_id="conv-b")
    assert len(bedrock.calls[1]["messages"]) == 1
    assert set(main.conversations) == {"conv-a", "conv-b"}


def test_failed_model_call_leaves_history_unchanged(chat, bedrock, sample_conversation_id):
    bedrock.script(text_reply("First answer."), client_error("Converse"), text_reply("Recovered."))
    chat("First")
    before = list(main.conversations[sample_conversation_id])

    assert chat("Second").status_code == 502
    assert main.conversations[sample_conversation_id] == before

    assert chat("Third").status_code == 200
    assert roles(bedrock.calls[-1]["messages"]) == ["user", "assistant", "user"]


def test_failed_retrieval_leaves_history_unchanged(chat, bedrock, kb, sample_conversation_id):
    kb.error = client_error("Retrieve")
    assert chat("Hello").status_code == 502
    assert sample_conversation_id not in main.conversations
    assert bedrock.calls == []


def test_max_rounds_failure_leaves_history_unchanged(chat, bedrock, sample_conversation_id):
    bedrock.always(lambda i, _: tool_reply((f"t{i}", "get_garage_rate", {"garage_id": "GAR-01"})))
    assert chat("Loop").status_code == 500
    assert sample_conversation_id not in main.conversations


def test_failed_tool_turn_does_not_leave_orphan_tool_use(chat, bedrock, sample_conversation_id):
    bedrock.script(tool_reply(("t1", "get_garage_rate", {"garage_id": "GAR-01"})), client_error("Converse"), text_reply("ok"))
    assert chat("Rate?").status_code == 502
    assert sample_conversation_id not in main.conversations

    chat("Try again")
    assert roles(bedrock.calls[-1]["messages"]) == ["user"]
