import os
from typing import Dict, List

import boto3
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

load_dotenv()

app = FastAPI()

region = os.getenv("AWS_REGION", "us-east-1")
model_id = os.getenv("BEDROCK_MODEL_ID")
knowledge_base_id = os.getenv("BEDROCK_KB_ID")

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

Use the retrieved company support documentation as your primary source of truth.

Rules:
- Clearly distinguish confirmed facts from possible causes.
- Do not invent customer, transaction, session, garage, or device information.
- If the retrieved context does not contain enough information, say so.
- Keep responses concise and structured.
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
        retrievalQuery={
            "text": query
        },
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": 3
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


@app.post("/chat")
def chat(request: ChatRequest):
    # 1. Retrieve relevant KB context
    contexts, sources = retrieve_context(request.message)

    context_text = "\n\n---\n\n".join(contexts)

    # 2. Build grounded user prompt
    grounded_message = f"""
    Retrieved support documentation:

    {context_text}

    User question:

    {request.message}

    Answer using the retrieved documentation.
    If the documentation is insufficient, say that clearly.
    """

    # 3. Get prior conversation history
    messages = conversations.get(request.conversation_id, [])

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

    # 5. Call Nova
    response = bedrock_runtime.converse(
        modelId=model_id,
        system=[
            {
                "text": system_prompt
            }
        ],
        messages=messages,
        inferenceConfig={
            "maxTokens": 500,
            "temperature": 0.2,
            "topP": 0.9,
        },
    )

    assistant_message = response["output"]["message"]

    # 6. Store assistant response
    messages.append(assistant_message)
    conversations[request.conversation_id] = messages

    # 7. Return answer + retrieval metadata
    return {
        "conversation_id": request.conversation_id,
        "response": assistant_message["content"][0]["text"],
        "sources": sources,
        "usage": response["usage"],
        "latency_ms": response["metrics"]["latencyMs"],
        "stop_reason": response["stopReason"],
    }