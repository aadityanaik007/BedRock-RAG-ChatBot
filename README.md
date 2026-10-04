# Bedrock RAG ChatBot

A technical support chatbot for a parking management platform. It uses **Amazon Bedrock Knowledge Bases** to retrieve relevant support documentation (RAG), then answers with a Bedrock foundation model through the **Converse API**. The repo also includes an **MCP server** that exposes tools for looking up parking sessions, payment transactions, garage rates and device status from mock data.

## How it works

```
User ──POST /chat──▶ FastAPI (main.py)
                        │
                        ├─ 1. Retrieve top 3 chunks ──▶ Bedrock Knowledge Base
                        │                                (built from knowledge/*.md)
                        │
                        ├─ 2. Build a grounded prompt (retrieved docs + question)
                        │
                        ├─ 3. Converse ──▶ Bedrock model (e.g. Amazon Nova)
                        │      with system prompt + conversation history
                        │
                        └─ 4. Return answer, sources, token usage and latency
```

- The conversation history is kept **in memory**, keyed by `conversation_id`. It's lost when the server restarts.
- The system prompt tells the model to treat the retrieved docs as the source of truth, keep confirmed facts separate from possible causes, and say so when the docs don't have enough information.

### MCP tools

`mcp_server/server.py` runs an MCP server named `parking-support-tools` over stdio. It has these tools, which read from `mock_data/`:

| Tool | Argument | Data source |
| --- | --- | --- |
| `get_parking_session` | `session_id` (e.g. `SES-1002`) | `sessions.json` |
| `get_payment_transaction` | `transaction_id` | `transactions.json` |
| `get_garage_rate` | `garage_id` (e.g. `GAR-01`) | `rates.json` |
| `get_device_status` | `garage_id` | `devices.json` |

`mcp_client.py` has helpers (`list_mcp_tools`, `call_mcp_tool`) that start the server and call its tools.

`/chat` passes these tools to the model through Bedrock tool use. When the model asks for a tool, the endpoint runs it through MCP, sends the result back, and repeats until the model gives a final answer (up to 5 tool rounds per request). Tool failures go back to the model as error results instead of failing the request. The response lists the tools that were called in `tool_calls`.

## Project structure

```
.
├── main.py               # FastAPI app: /health and /chat (RAG + Converse)
├── app.py                # Streamlit chat UI
├── logging_config.py     # Console + rotating file logging
├── tests/                # pytest suite
├── mcp_client.py         # Helpers to list and call MCP tools over stdio
├── mcp_server/
│   └── server.py         # MCP server with parking support tools
├── knowledge/            # Support docs to load into the Bedrock Knowledge Base
│   ├── active_session.md
│   ├── duplicate_charge.md
│   ├── incorrect_rate.md
│   └── payment_failed.md
├── mock_data/            # Mock records used by the MCP tools
├── requirements.txt
└── pyproject.toml
```

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended; the MCP client starts the server with `uv run`)
- An AWS account with:
  - access to a Bedrock text model (for example Amazon Nova) in your region
  - a Bedrock Knowledge Base

## Setup

### 1. Install dependencies

```bash
uv venv
uv pip install -r requirements.txt
```

Or with pip:

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create the Knowledge Base

1. Upload the files in `knowledge/` to an S3 bucket.
2. In the Bedrock console, create a Knowledge Base that uses that bucket as its data source.
3. Sync the data source, then copy the Knowledge Base ID.

### 3. Configure environment variables

Create a `.env` file in the project root. It's listed in `.gitignore`, so it won't be committed.

```env
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=amazon.nova-lite-v1:0
BEDROCK_KB_ID=your-knowledge-base-id
AWS_BEARER_TOKEN_BEDROCK=your-bedrock-api-key
```

`AWS_BEARER_TOKEN_BEDROCK` is optional if you use standard AWS credentials instead, such as `aws configure`, an AWS profile or environment variables. Knowledge Base retrieval (`bedrock-agent-runtime`) uses your standard AWS credentials.

## Running

### Start the API

```bash
uv run uvicorn main:app --reload
```

Check that it's running:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

Ask a question:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "demo-1", "message": "A customer says their payment failed. What should I check?"}'
```

Example response:

```json
{
  "conversation_id": "demo-1",
  "response": "...",
  "sources": [{ "uri": "s3://your-bucket/payment_failed.md", "score": 0.71 }],
  "tool_calls": [{ "name": "get_payment_transaction", "input": { "transaction_id": "TXN-9001" }, "status": "success" }],
  "usage": { "inputTokens": 850, "outputTokens": 180, "totalTokens": 1030 },
  "latency_ms": 1200,
  "stop_reason": "end_turn"
}
```

To ask follow-up questions in the same conversation, send the same `conversation_id` again.

Interactive API docs are at http://localhost:8000/docs.

### Run the chat UI

With the API running, start the Streamlit app in a second terminal:

```bash
uv run streamlit run app.py
```

It opens at http://localhost:8501. Each answer shows the tools that were called (with their inputs and outputs), the source documents, token usage and latency. **New conversation** in the sidebar starts a fresh `conversation_id`. To point the UI at a different backend, set `CHAT_API_URL` (default `http://localhost:8000`).

### Run the MCP server

```bash
uv run python mcp_server/server.py
```

To browse and test the tools with the MCP Inspector:

```bash
uv run mcp dev mcp_server/server.py
```

## Logging

Logs go to the console and to `logs/app.log`, which rotates at 5 MB and keeps 3 backups. Each chat request logs the question, the number of documents retrieved, every model round, every MCP tool call and its result, and a summary line with sources, tool calls, token usage and latency. AWS errors are logged with a traceback and returned to the client as a 502.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Minimum level to log (`DEBUG`, `INFO`, `WARNING`, ...) |
| `LOG_DIR` | `logs` | Folder for `app.log` |

## Tests

```bash
uv run pytest                                   # full suite (Bedrock is faked, MCP tools are real)
uv run pytest --cov --cov-report=term-missing   # with coverage
RUN_LIVE_TESTS=1 uv run pytest tests/test_live.py   # opt-in: real Bedrock calls, needs AWS credentials
```

The default suite needs no AWS access. It replaces the Bedrock clients with scripted fakes and runs the MCP tools in-process against `mock_data/`. One test also starts the MCP server over stdio.

## Roadmap

- Store conversations in a persistent store instead of memory.
