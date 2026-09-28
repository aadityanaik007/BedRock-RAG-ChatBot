from mcp import Client
from mcp.client.stdio import StdioServerParameters


server_params = StdioServerParameters(
    command="uv",
    args=["run", "python", "mcp_server/server.py"],
)


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