import main
from tests.conftest import TOOL_NAMES, text_reply, tool_reply


def user_text(message: dict) -> str:
    return message["content"][0]["text"]


def test_simple_answer_without_tools(chat, bedrock):
    bedrock.script(text_reply("Hello! I help with parking support."))
    response = chat("Hi")

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Hello! I help with parking support."
    assert data["tool_calls"] == []
    assert data["stop_reason"] == "end_turn"
    assert len(bedrock.calls) == 1


def test_converse_request_configuration(chat, bedrock):
    bedrock.script(text_reply("ok"))
    chat("Hi")

    call = bedrock.calls[0]
    assert call["modelId"] == main.model_id
    assert call["system"] == [{"text": main.system_prompt}]
    assert call["inferenceConfig"] == {"maxTokens": 500, "temperature": 0.2, "topP": 0.9}
    assert {t["toolSpec"]["name"] for t in call["toolConfig"]["tools"]} == TOOL_NAMES


def test_prompt_contains_retrieved_docs_and_question(chat, bedrock, kb):
    kb.results = [
        {"content": {"text": "Doc one text"}, "score": 0.9, "location": {"s3Location": {"uri": "s3://kb/one.md"}}},
        {"content": {"text": "Doc two text"}, "score": 0.5, "location": {"s3Location": {"uri": "s3://kb/two.md"}}},
    ]
    bedrock.script(text_reply("ok"))
    chat("Why did my payment fail?")

    prompt = user_text(bedrock.calls[0]["messages"][-1])
    assert "Doc one text" in prompt
    assert "Doc two text" in prompt
    assert "Why did my payment fail?" in prompt


def test_knowledge_base_query(chat, bedrock, kb):
    bedrock.script(text_reply("ok"))
    chat("Card declined")

    assert kb.calls == [
        {
            "knowledgeBaseId": main.knowledge_base_id,
            "retrievalQuery": {"text": "Card declined"},
            "retrievalConfiguration": {"managedSearchConfiguration": {"numberOfResults": 5}},
        }
    ]


def test_sources_returned_from_retrieval(chat, bedrock, kb):
    bedrock.script(text_reply("ok"))
    data = chat("Hi").json()
    assert data["sources"] == [{"uri": "s3://kb/payment_failed.md", "score": 0.71}]


def test_retrieval_with_missing_fields(chat, bedrock, kb):
    kb.results = [{}]
    bedrock.script(text_reply("ok"))
    data = chat("Hi").json()
    assert data["sources"] == [{"uri": None, "score": None}]


def test_retrieval_with_no_results_still_answers(chat, bedrock, kb):
    kb.results = []
    bedrock.script(text_reply("I don't have documentation on that."))
    response = chat("Something obscure")
    assert response.status_code == 200
    assert response.json()["sources"] == []


def test_multiple_text_blocks_are_joined(chat, bedrock):
    bedrock.script(
        {
            "output": {"message": {"role": "assistant", "content": [{"text": "Part one."}, {"text": "Part two."}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
            "metrics": {"latencyMs": 1},
        }
    )
    assert chat("Hi").json()["response"] == "Part one.\nPart two."


def test_usage_and_latency_reported(chat, bedrock):
    bedrock.script(text_reply("ok", input_tokens=850, output_tokens=180, latency_ms=1200))
    data = chat("Hi").json()
    assert data["usage"] == {"inputTokens": 850, "outputTokens": 180, "totalTokens": 1030}
    assert data["latency_ms"] == 1200


def test_usage_and_latency_summed_across_tool_rounds(chat, bedrock):
    bedrock.script(
        tool_reply(("t1", "get_garage_rate", {"garage_id": "GAR-01"}), input_tokens=100, output_tokens=20, latency_ms=300),
        text_reply("Standard rate is $6/hour.", input_tokens=200, output_tokens=30, latency_ms=400),
    )
    data = chat("Rate at GAR-01?").json()
    assert data["usage"] == {"inputTokens": 300, "outputTokens": 50, "totalTokens": 350}
    assert data["latency_ms"] == 700


def test_max_tokens_stop_reason_is_returned(chat, bedrock):
    reply = text_reply("Truncated answ")
    reply["stopReason"] = "max_tokens"
    bedrock.script(reply)
    data = chat("Explain everything").json()
    assert data["stop_reason"] == "max_tokens"
    assert data["response"] == "Truncated answ"
