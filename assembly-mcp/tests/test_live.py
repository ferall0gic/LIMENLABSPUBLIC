"""Local transport contract with an emulated host; no native-host evidence."""
import json
from pathlib import Path
import threading
import time
import uuid
import pytest
from limen_assembly_mcp.live import LiveClient, LiveError, create_scratch_session


class Host:
    def __init__(self, root, host="rhino"):
        self.root = root; self.host = host; self.stop = threading.Event(); self.calls = []
        config = json.loads((root / "scratch.json").read_text())
        self.session = {"protocol": 1, "host": host, "session_id": config["session_id"], "document_id": "scratch-document",
                        "process_id": 12345, "scratch": True, "heartbeat": time.time(), "document_path": str(root / ("scratch.3dm" if host == "rhino" else "scratch.rvt"))}
        (root / "session.json").write_text(json.dumps(self.session))
        self.thread = threading.Thread(target=self.run, daemon=True); self.thread.start()

    def run(self):
        while not self.stop.wait(.01):
            for path in (self.root / "requests").glob("*.json"):
                request = json.loads(path.read_text()); path.rename(path.with_suffix(".claimed")); self.calls.append(request)
                response = {"protocol": 1, "request_id": request["request_id"], "binding": request["binding"],
                            "ok": True, "result": {"host": self.host, "evidence": "emulated_host", "revision": "r0", "objects": []}}
                (self.root / "responses" / path.name).write_text(json.dumps(response))

    def close(self): self.stop.set(); self.thread.join()


@pytest.mark.parametrize("host", ["rhino", "revit"])
def test_live_transport_routes_to_exact_scratch_binding(tmp_path, host):
    root = create_scratch_session(tmp_path, host); worker = Host(root, host)
    try:
        result = LiveClient(root, host, timeout=1).call("context")
        assert result["revision"] == "r0" and len(worker.calls) == 1
        request = worker.calls[0]
        assert request["binding"]["document_id"] == "scratch-document"
        assert request["binding"]["session_id"] == worker.session["session_id"]
        assert request["expires_at"] > request["created_at"]
    finally: worker.close()


@pytest.mark.parametrize("field,value", [("host", "revit"), ("scratch", False), ("heartbeat", 0), ("document_path", "C:/outside/user.3dm"), ("session_id", "foreign")])
def test_live_client_refuses_wrong_or_stale_session_before_enqueue(tmp_path, field, value):
    root = create_scratch_session(tmp_path, "rhino"); worker = Host(root); worker.close()
    descriptor = {**worker.session, field: value}; (root / "session.json").write_text(json.dumps(descriptor))
    with pytest.raises(LiveError): LiveClient(root, "rhino", timeout=.1).call("context")
    assert not list((root / "requests").glob("*.json"))


def test_mutations_require_revision_and_reject_unknown_actions(tmp_path):
    root = create_scratch_session(tmp_path, "rhino"); worker = Host(root)
    try:
        client = LiveClient(root, "rhino", timeout=1)
        for action in ("create_box", "delete_created"):
            with pytest.raises(LiveError, match="revision"): client.call(action)
        with pytest.raises(LiveError, match="Unsupported"): client.call("execute_script", {"script": "anything"})
        assert not worker.calls
    finally: worker.close()


def test_timeout_never_retries_a_mutation(tmp_path):
    root = create_scratch_session(tmp_path, "rhino"); worker = Host(root); worker.close()
    with pytest.raises(LiveError, match="unknown"):
        LiveClient(root, "rhino", timeout=.05).call("create_box", {"size_mm": [100, 200, 300]}, expected_revision="r0")
    assert len(list((root / "requests").glob("*.json"))) == 1


def test_session_creation_uses_new_child_directory_and_never_accepts_existing_model(tmp_path):
    a = create_scratch_session(tmp_path, "rhino"); b = create_scratch_session(tmp_path, "rhino")
    assert a != b and a.parent == tmp_path and b.parent == tmp_path
    assert json.loads((a / "scratch.json").read_text())["scratch_document"] == "scratch.3dm"
    with pytest.raises(ValueError): create_scratch_session(tmp_path, "other")
