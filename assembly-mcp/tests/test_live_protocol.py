"""Actual MCP SDK calls with a recording fake host; no native evidence."""
import anyio
import pytest
from limen_assembly_mcp.server import create_server


class RecordingLive:
    host = "rhino"
    def __init__(self): self.calls = []
    def call(self, action, payload=None, expected_revision=None):
        self.calls.append((action, payload, expected_revision))
        return {"evidence": "emulated_host", "revision": "r1"}


def test_live_tools_are_optional_and_identity_must_match():
    async def check():
        assert len(await create_server("rhino").list_tools()) == 9
        tools = {t.name: t for t in await create_server("rhino", live=RecordingLive()).list_tools()}
        assert len(tools) == 13
        assert tools["live_context"].annotations.readOnlyHint
        assert not tools["live_create_scratch_box"].annotations.readOnlyHint
        assert tools["live_delete_scratch_objects"].annotations.destructiveHint
    anyio.run(check)
    with pytest.raises(ValueError): create_server("revit", live=RecordingLive())


def test_tool_calls_forward_revision_and_reject_unsafe_argument_shapes():
    async def check():
        live = RecordingLive(); server = create_server("rhino", live=live)
        await server.call_tool("live_create_scratch_box", {"origin_mm": [0, 0, 0], "size_mm": [100, 200, 300], "expected_revision": "r0"})
        assert live.calls == [("create_box", {"origin_mm": [0., 0., 0.], "size_mm": [100., 200., 300.]}, "r0")]
        with pytest.raises(Exception):
            await server.call_tool("live_create_scratch_box", {"origin_mm": [0, 0, 0], "size_mm": [True, 1, 1], "expected_revision": "r0"})
        with pytest.raises(Exception):
            await server.call_tool("live_delete_scratch_objects", {"object_ids": ["a", "b"], "expected_revision": "r0"})
        assert len(live.calls) == 1
    anyio.run(check)
