"""Real MCP SDK/client over stdio, synthetic inputs, no host applications."""
import json
import os
import sys
import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from test_core import spec


@pytest.mark.parametrize("host", ["rhino", "revit"])
def test_stdio_discovery_calls_and_refusals(host):
    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=["-c",
            "from limen_assembly_mcp.server import create_server; create_server(" + repr(host) + ").run(transport='stdio')"])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                assert len(listed.tools) == 9
                for tool in listed.tools:
                    assert tool.annotations.readOnlyHint and not tool.annotations.destructiveHint
                assert not ({"execute", "commit", "rollback", "run_script"} & {t.name for t in listed.tools})
                result = await session.call_tool("assembly_preview", {"spec": spec()})
                assert not result.isError
                payload = json.loads(result.content[0].text)
                assert payload["host"] == host and payload["status"] == "plan_only" and not payload["model_changed"]
                bad = await session.call_tool("assembly_preview", {"spec": {"units": "ft"}})
                assert bad.isError
                unbound = await session.call_tool("model_inspect", {})
                assert unbound.isError and "No source bound" in unbound.content[0].text
                invalid_grid = await session.call_tool("spatial_connectivity", {"grid": [[True]]})
                assert invalid_grid.isError
                unknown = await session.call_tool("run_script", {"code": "anything"})
                assert unknown.isError
    anyio.run(exercise)
