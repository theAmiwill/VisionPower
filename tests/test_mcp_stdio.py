import asyncio
import sys
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "mcp" / "server.py"


async def list_tool_names():
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_PATH)],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
    return {tool.name for tool in tools.tools}


class MCPStdioTests(unittest.TestCase):
    def test_initialize_and_list_tools(self):
        names = asyncio.run(list_tool_names())
        self.assertIn("understand_image", names)
        self.assertIn("get_vision_config", names)


if __name__ == "__main__":
    unittest.main()
