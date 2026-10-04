import asyncio
import logging
import os
from typing import Dict, List

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from logging_config import setup_logging
from mcp_client import get_bedrock_tool_config, run_tool_use

load_dotenv()

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI()

region = os.getenv("AWS_REGION", "us-east-1")
model_id = os.getenv("BEDROCK_MODEL_ID")
knowledge_base_id = os.getenv("BEDROCK_KB_ID")

MAX_TOOL_ROUNDS = 5

SERVICE_UNAVAILABLE_MESSAGE = "Sorry, the support assistant is temporarily unavailable. Please try again in a few minutes."

bedrock_runtime = boto3.client(
    "bedrock-runtime",
    region_name=region,
)

bedrock_agent_runtime = boto3.client(
    "bedrock-agent-runtime",
    region_name=region,
)

# Temporary conversation store
conversations: Dict[str, List[dict]] = {}

system_prompt = """
You are a technical support assistant for a parking management platform.

You have tools to look up parking sessions, payment transactions, garage rates and device status.
When the user mentions a session, transaction or garage, look it up before answering.
IDs look like SES-1002, TXN-9001 and GAR-01. Convert variants such as "garage-01", "garage 1" or "ses 1002" to that format before calling a tool.

How to answer:
- Answer only the question asked, and lead with the direct answer.
- Keep it short: usually 1-3 sentences, or a few bullets when there are several findings. No headings.
- Mention only the record details that matter to the question. Do not repeat the whole record.
- Do not add next steps, offers of further help or follow-up suggestions unless the user asks what to do or an action is required to fix the problem.
- Do not speculate. State only what tool results and the documentation confirm. If a cause is likely but not confirmed, say so.
- Never invent customer, transaction, session, garage or device details.
- If a record is not found or the information is insufficient, say so in one sentence.
- Use the support documentation as the source of truth for causes and procedures, but do not summarize it unless it answers the question.
"""


class ChatRequest(BaseModel):
    conversation_id: str
    message: str


@app.get("/health")
def health():
    return {"status": "ok"}


def retrieve_context(query: str):
    response = bedrock_agent_runtime.retrieve(
    knowledgeBaseId=knowledge_base_id,
    retrievalQuery={"text": query},
    retrievalConfiguration={
            "managedSearchConfiguration": {   # was "vectorSearchConfiguration"
                "numberOfResults": 5
            }
        },
    )

    results = response.get("retrievalResults", [])

    contexts = []
    sources = []

    for result in results:
        text = result.get("content", {}).get("text", "")
        score = result.get("score")

        location = result.get("location", {})
        s3_location = location.get("s3Location", {})
        uri = s3_location.get("uri")

        contexts.append(text)

        sources.append(
            {
                "uri": uri,
                "score": score,
            }
        )

    return contexts, sources


def converse(messages: List[dict], tool_config: dict):
    return bedrock_runtime.converse(
        modelId=model_id,
        system=[
            {
                "text": system_prompt
            }
        ],
        messages=messages,
        toolConfig=tool_config,
        inferenceConfig={
            "maxTokens": 500,
            "temperature": 0.2,
            "topP": 0.9,
        },
    )


@app.post("/chat")
async def chat(request: ChatRequest):
    logger.info(
        "Chat request for conversation %s: %r",
        request.conversation_id,
        request.message[:200],
    )

    # 1. Retrieve relevant KB context
    try:
        contexts, sources = await asyncio.to_thread(retrieve_context, request.message)
    except (BotoCoreError, ClientError):
        logger.exception("Knowledge Base retrieval failed for conversation %s", request.conversation_id)
        raise HTTPException(status_code=502, detail=SERVICE_UNAVAILABLE_MESSAGE)

    logger.info("Retrieved %d documents for conversation %s", len(contexts), request.conversation_id)

    context_text = "\n\n---\n\n".join(contexts)

    # 2. Build grounded user prompt
    grounded_message = f"""
    Retrieved support documentation:

    {context_text}

    User question:

    {request.message}

    Answer using the retrieved documentation and any tool results.
    If the available information is insufficient, say that clearly.
    """

    # 3. Copy prior history so a failed request doesn't leave a broken turn behind
    messages = list(conversations.get(request.conversation_id, []))

    # 4. Add current user message
    messages.append(
        {
            "role": "user",
            "content": [
                {
                    "text": grounded_message
                }
            ],
        }
    )

    tool_config = await get_bedrock_tool_config()

    usage: Dict[str, int] = {}
    latency_ms = 0
    tool_calls = []
    tool_rounds = 0

    # 5. Call the model, running any requested tools, until it gives a final answer
    for _ in range(MAX_TOOL_ROUNDS + 1):
        try:
            response = await asyncio.to_thread(converse, messages, tool_config)
        except (BotoCoreError, ClientError):
            logger.exception("Bedrock Converse call failed for conversation %s", request.conversation_id)
            raise HTTPException(status_code=502, detail=SERVICE_UNAVAILABLE_MESSAGE)

        logger.info(
            "Model round %d for conversation %s: stop_reason=%s latency_ms=%s",
            tool_rounds + 1,
            request.conversation_id,
            response["stopReason"],
            response["metrics"]["latencyMs"],
        )

        for key, value in response["usage"].items():
            usage[key] = usage.get(key, 0) + value
        latency_ms += response["metrics"]["latencyMs"]

        assistant_message = response["output"]["message"]
        messages.append(assistant_message)

        if response["stopReason"] != "tool_use":
            break

        if tool_rounds >= MAX_TOOL_ROUNDS:
            logger.warning(
                "Conversation %s exceeded %d tool rounds; giving up",
                request.conversation_id,
                MAX_TOOL_ROUNDS,
            )
            raise HTTPException(
                status_code=500,
                detail="The assistant made too many tool calls without reaching an answer. Please try rephrasing your question.",
            )

        tool_uses = [block["toolUse"] for block in assistant_message["content"] if "toolUse" in block]
        tool_results = [await run_tool_use(tool_use) for tool_use in tool_uses]

        messages.append({"role": "user", "content": tool_results})
        tool_rounds += 1

        tool_calls.extend(
            {
                "name": tool_use["name"],
                "input": tool_use.get("input"),
                "status": result["toolResult"]["status"],
            }
            for tool_use, result in zip(tool_uses, tool_results)
        )

    logger.info(
        "Conversation %s: sources=%s tool_calls=%s usage=%s latency_ms=%s",
        request.conversation_id,
        sources,
        tool_calls,
        usage,
        latency_ms,
    )

    # 6. Store the full turn, including tool calls and results
    conversations[request.conversation_id] = messages

    response_text = "\n".join(
        block["text"] for block in assistant_message["content"] if "text" in block
    )

    # 7. Return answer + retrieval and tool metadata
    return {
        "conversation_id": request.conversation_id,
        "response": response_text,
        "sources": sources,
        "tool_calls": tool_calls,
        "usage": usage,
        "latency_ms": latency_ms,
        "stop_reason": response["stopReason"],
    }
