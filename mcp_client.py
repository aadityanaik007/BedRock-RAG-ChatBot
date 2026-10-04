import logging

from mcp import Client
from mcp.client.stdio import StdioServerParameters

logger = logging.getLogger(__name__)

server_params = StdioServerParameters(
    command="uv",
    args=["run", "python", "mcp_server/server.py"],
)

_bedrock_tool_config: dict | None = None


async def list_mcp_tools():
    async with Client(server_params) as client:
        result = await client.list_tools()
        return result.tools


async def call_mcp_tool(name: str, arguments: dict):
    async with Client(server_params) as client:
        result = await client.call_tool(
            name,
            arguments=arguments,
        )

        return result


async def get_bedrock_tool_config() -> dict:
    global _bedrock_tool_config

    if _bedrock_tool_config is None:
        tools = await list_mcp_tools()
        _bedrock_tool_config = {
            "tools": [
                {
                    "toolSpec": {
                        "name": tool.name,
                        "description": tool.description or tool.name,
                        "inputSchema": {"json": tool.input_schema},
                    }
                }
                for tool in tools
            ]
        }

    return _bedrock_tool_config


async def run_tool_use(tool_use: dict) -> dict:
    """Run a Bedrock toolUse block through MCP and return the matching toolResult block."""
    tool_use_id = tool_use["toolUseId"]
    name = tool_use["name"]
    arguments = tool_use.get("input") or {}

    logger.info("Calling MCP tool %s with %s", name, arguments)

    try:
        result = await call_mcp_tool(name, arguments)
    except Exception as exc:
        logger.exception("MCP tool %s failed", name)
        return {
            "toolResult": {
                "toolUseId": tool_use_id,
                "content": [{"text": f"Tool call failed: {exc}"}],
                "status": "error",
            }
        }

    if result.structured_content is not None:
        content = [{"json": result.structured_content}]
    else:
        text = "\n".join(block.text for block in result.content if block.type == "text")
        content = [{"text": text or "(no output)"}]

    if result.is_error:
        logger.warning("MCP tool %s returned an error: %s", name, content)
    else:
        logger.info("MCP tool %s returned %s", name, content)

    return {
        "toolResult": {
            "toolUseId": tool_use_id,
            "content": content,
            "status": "error" if result.is_error else "success",
        }
    }
