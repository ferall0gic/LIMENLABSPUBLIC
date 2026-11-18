"""Local file-queue transport. No network listener, arbitrary script or automatic retry."""
import argparse
import json
from pathlib import Path
import time
import uuid


class LiveError(ValueError): pass


def create_scratch_session(parent: Path, host: str) -> Path:
    if host not in ("rhino", "revit"): raise ValueError("Unsupported host")
    parent = Path(parent).resolve(); parent.mkdir(parents=True, exist_ok=True)
    session_id = uuid.uuid4().hex; root = parent / (host + "-" + session_id); root.mkdir()
    (root / "requests").mkdir(); (root / "responses").mkdir()
    config = {"protocol": 1, "host": host, "session_id": session_id, "scratch_only": True,
              "scratch_document": "scratch.3dm" if host == "rhino" else "scratch.rvt"}
    (root / "scratch.json").write_text(json.dumps(config), encoding="utf-8")
    return root


def _read(path: Path) -> dict:
    try:
        with path.open("rb") as source: data = source.read(1024*1024+1)
        if len(data) > 1024*1024: raise LiveError("Host message exceeds size limit")
        result = json.loads(data)
        if not isinstance(result, dict): raise ValueError()
        return result
    except (OSError, ValueError): raise LiveError("Host session/message unavailable or invalid") from None


class LiveClient:
    def __init__(self, root: Path, host: str, timeout: float = 15):
        if host not in ("rhino", "revit"): raise LiveError("Unsupported host")
        self.root = Path(root).resolve(); self.host = host; self.timeout = timeout

    def descriptor(self) -> dict:
        config = _read(self.root / "scratch.json"); session = _read(self.root / "session.json")
        expected_file = "scratch.3dm" if self.host == "rhino" else "scratch.rvt"
        if config.get("protocol") != 1 or config.get("host") != self.host or config.get("scratch_only") is not True or config.get("scratch_document") != expected_file:
            raise LiveError("Invalid scratch configuration")
        if session.get("protocol") != 1 or session.get("host") != self.host or session.get("scratch") is not True or session.get("session_id") != config.get("session_id"):
            raise LiveError("Wrong scratch session binding")
        if Path(session.get("document_path", "")).resolve() != self.root / expected_file:
            raise LiveError("Host is not bound to this scratch file")
        heartbeat = session.get("heartbeat")
        if type(heartbeat) not in (int, float) or not -5 <= time.time()-heartbeat <= 30:
            raise LiveError("Host heartbeat is stale")
        if not session.get("document_id") or type(session.get("process_id")) is not int:
            raise LiveError("Missing instance/document identity")
        return session

    def call(self, action: str, payload: dict | None = None, expected_revision: str | None = None) -> dict:
        if action not in ("context", "list_objects", "create_box", "delete_created"): raise LiveError("Unsupported live action")
        if action in ("create_box", "delete_created") and not expected_revision: raise LiveError("A current revision is required")
        session = self.descriptor(); binding = {k: session[k] for k in ("session_id", "document_id", "process_id")}
        identifier = uuid.uuid4().hex; created = time.time()
        request = {"protocol": 1, "request_id": identifier, "binding": binding, "action": action,
                   "payload": payload or {}, "expected_revision": expected_revision, "created_at": created,
                   "expires_at": created + self.timeout}
        temporary = self.root / "requests" / (identifier + ".tmp")
        with temporary.open("x", encoding="utf-8") as target: json.dump(request, target, allow_nan=False)
        temporary.rename(temporary.with_suffix(".json"))
        response_path = self.root / "responses" / (identifier + ".json")
        while time.time() < request["expires_at"]:
            if response_path.is_file():
                response = _read(response_path)
                if response.get("protocol") != 1 or response.get("request_id") != identifier or response.get("binding") != binding:
                    raise LiveError("Response binding mismatch; outcome unknown")
                if response.get("ok") is not True: raise LiveError(str(response.get("error", "Host operation failed")))
                result = response.get("result")
                if not isinstance(result, dict): raise LiveError("Invalid host result; outcome unknown")
                return result
            time.sleep(.02)
        raise LiveError("Host timed out; native outcome unknown. Inspect the session before issuing another mutation. No retry was sent.")


def main():
    parser = argparse.ArgumentParser(description="Create a NEW isolated scratch-session directory; does not attach to an existing document.")
    parser.add_argument("host", choices=("rhino", "revit")); parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(); print(create_scratch_session(args.root, args.host))


if __name__ == "__main__": main()
