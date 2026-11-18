"""Explicit native scratch-only acceptance. Never attaches to an existing user model.

Run against a NEW scratch session with --host, --session and an output --report path.
Creates one 100x200x300 mm box, checks refusals, then deletes that session-owned box.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from limen_assembly_mcp.live import LiveClient, LiveError


async def exercise(host, root):
    env = dict(os.environ)
    env["LIMEN_" + host.upper() + "_LIVE_SESSION"] = str(root)
    entry = "rhino_main" if host == "rhino" else "revit_main"
    params = StdioServerParameters(command=sys.executable,
        args=["-c", "from limen_assembly_mcp.server import " + entry + "; " + entry + "()"], env=env)
    report = {"host": host, "checks": [], "evidence": "live_" + host}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools(); assert len(tools.tools) == 13
            async def call(name, args=None, error=None):
                result = await session.call_tool(name, args or {})
                if error:
                    assert result.isError and error in result.content[0].text, result
                    report["checks"].append({"tool": name, "refusal": error, "passed": True})
                    return None
                assert not result.isError, result
                return json.loads(result.content[0].text)
            before = await call("live_context")
            assert before["scratch"] and before["object_count"] == 0
            report["checks"].append({"tool": "live_context", "initial_count": 0, "passed": True})
            created = await call("live_create_scratch_box", {"origin_mm": [0, 0, 0], "size_mm": [100, 200, 300], "expected_revision": before["revision"]})
            assert len(created["created_ids"]) == 1 and created["revision"] != before["revision"]
            rows = await call("live_list_objects")
            assert len(rows["objects"]) == 1
            obj = rows["objects"][0]; box = obj.get("bbox_mm") or obj["bbox"]
            assert all(abs(b-a-size) < 1e-6 for a, b, size in zip(box["minimum"], box["maximum"], [100, 200, 300]))
            report["checks"].append({"tool": "live_create_scratch_box", "native_dimensions_mm": [100, 200, 300], "passed": True})
            await call("live_create_scratch_box", {"origin_mm": [0, 0, 0], "size_mm": [100, 200, 300], "expected_revision": before["revision"]}, error="STALE_REVISION")
            current = await call("live_context")
            await call("live_delete_scratch_objects", {"object_ids": ["00000000-0000-0000-0000-000000000000"], "expected_revision": current["revision"]}, error="NOT_CREATED_BY_SESSION")
            unchanged = await call("live_context"); assert unchanged["revision"] == current["revision"]
            deleted = await call("live_delete_scratch_objects", {"object_ids": created["created_ids"], "expected_revision": current["revision"]})
            assert deleted["deleted_ids"] == created["created_ids"]
            after = await call("live_context"); assert after["object_count"] == 0
            report["checks"].append({"tool": "live_delete_scratch_objects", "final_count": 0, "passed": True})
    client = LiveClient(root, host)
    descriptor = client.descriptor
    client.descriptor = lambda: {**descriptor(), "document_id": "foreign-document"}
    try: client.call("context")
    except LiveError as error: assert "BINDING_MISMATCH" in str(error)
    else: raise AssertionError("Foreign document binding was accepted")
    report["checks"].append({"tool": "live_context", "refusal": "BINDING_MISMATCH", "passed": True})
    report["passed"] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, choices=("rhino", "revit"))
    parser.add_argument("--session", required=True, type=Path); parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    report = anyio.run(exercise, args.host, args.session.resolve())
    with args.report.open("x", encoding="utf-8") as target: json.dump(report, target, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__": main()
