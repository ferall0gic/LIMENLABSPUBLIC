"""Native boundary replaced with stubs; these are emulated-host tests."""
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import uuid
import pytest


def module(monkeypatch):
    monkeypatch.setitem(sys.modules, "Rhino", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "System", SimpleNamespace())
    path = Path(__file__).parents[1] / "hosts/rhino_scratch.py"
    spec = importlib.util.spec_from_file_location("rhino_host_test", path)
    host = importlib.util.module_from_spec(spec); spec.loader.exec_module(host)
    return host


def worker(monkeypatch):
    mod = module(monkeypatch); host = mod.ScratchHost.__new__(mod.ScratchHost)
    host.guard = lambda: None; host.binding = lambda: {"session_id": "s", "document_id": "d", "process_id": 1}
    host.revision = lambda: "r0"
    return mod, host


@pytest.mark.parametrize("value", [[0, 1], [True, 1, 1], [float("nan"), 1, 1], [100001, 1, 1], [1, 0, 1], [10001, 1, 1]])
def test_rhino_host_rejects_invalid_box_size_before_native_calls(monkeypatch, value):
    mod = module(monkeypatch)
    with pytest.raises(ValueError): mod._vector(value, positive=True)


@pytest.mark.parametrize("patch,error", [({"binding": {}}, "BINDING_MISMATCH"), ({"expires_at": 0}, "REQUEST_EXPIRED"),
    ({"expected_revision": "old"}, "STALE_REVISION"), ({"action": "execute_script"}, "UNSUPPORTED_ACTION")])
def test_rhino_host_refuses_foreign_expired_stale_and_arbitrary_requests(monkeypatch, patch, error):
    _, host = worker(monkeypatch)
    request = {"protocol": 1, "binding": host.binding(), "expires_at": time.time()+5, "action": "create_box", "payload": {}, "expected_revision": "r0", **patch}
    with pytest.raises(ValueError, match=error): host.execute(request)


def test_rhino_host_deletes_only_its_own_created_ids(monkeypatch):
    _, host = worker(monkeypatch); host.created = {"mine"}
    request = {"protocol": 1, "binding": host.binding(), "expires_at": time.time()+5, "action": "delete_created",
               "payload": {"object_ids": ["foreign"]}, "expected_revision": "r0"}
    with pytest.raises(ValueError, match="NOT_CREATED_BY_SESSION"): host.execute(request)


@pytest.mark.parametrize("expiry", [float("nan"), True])
def test_invalid_request_expiry_is_refused_before_revision_checks(monkeypatch, expiry):
    _, host = worker(monkeypatch)
    request = {"protocol": 1, "binding": host.binding(), "expires_at": expiry, "action": "create_box",
               "payload": {}, "expected_revision": "old"}
    with pytest.raises(ValueError, match="REQUEST_EXPIRED"): host.execute(request)


def test_context_excludes_soft_deleted_rhino_objects(monkeypatch):
    _, host = worker(monkeypatch)
    class Table(list):
        Count = 2
    host.doc = SimpleNamespace(Objects=Table([SimpleNamespace(IsDeleted=False), SimpleNamespace(IsDeleted=True)]), ModelUnitSystem="Millimeters")
    assert host.context()["object_count"] == 1


def test_claimed_native_request_is_never_replayed_after_response_write_failure(monkeypatch, tmp_path):
    mod, host = worker(monkeypatch)
    host.root = tmp_path; host.last_heartbeat = time.time(); host.heartbeat = lambda: None
    (tmp_path/"requests").mkdir(); (tmp_path/"responses").mkdir()
    identifier = uuid.uuid4().hex
    (tmp_path/"requests"/(identifier+".json")).write_text(json.dumps({"request_id": identifier, "binding": host.binding()}))
    calls = []
    host.execute = lambda request: calls.append(request) or {"status": "native_write_happened"}
    monkeypatch.setattr(mod, "_atomic", lambda *args: (_ for _ in ()).throw(OSError("response journal failed")))
    host.tick(None, None); host.tick(None, None)
    assert len(calls) == 1
    assert (tmp_path/"requests"/(identifier+".claimed")).is_file()
    assert not list((tmp_path/"responses").glob("*.json"))
