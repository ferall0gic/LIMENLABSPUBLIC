#! python3
"""Rhino 8 CPython host. Start ONLY in a new separate instance with its empty scratch.3dm."""
import hashlib
import json
import math
import os
from pathlib import Path
import time
import uuid
import Rhino
import System


def _atomic(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    os.replace(str(temporary), str(path))


def _vector(value, positive=False):
    if not isinstance(value, list) or len(value) != 3: raise ValueError("INVALID_VECTOR")
    if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 100000 for v in value): raise ValueError("INVALID_VECTOR")
    if positive and any(v <= 0 or v > 10000 for v in value): raise ValueError("INVALID_SIZE")
    return value


class ScratchHost:
    def __init__(self, root):
        self.root = Path(root).resolve()
        config = json.loads((self.root / "scratch.json").read_text(encoding="utf-8"))
        self.session_id = config["session_id"]
        if config != {"protocol": 1, "host": "rhino", "session_id": self.session_id, "scratch_only": True, "scratch_document": "scratch.3dm"}:
            raise ValueError("INVALID_SCRATCH_CONFIG")
        if self.root.name != "rhino-" + uuid.UUID(hex=self.session_id).hex: raise ValueError("INVALID_SCRATCH_ROOT")
        self.path = self.root / "scratch.3dm"
        self.doc = Rhino.RhinoDoc.ActiveDoc
        if self.doc is None or self.doc.Objects.Count != 0: raise ValueError("START_REQUIRES_EMPTY_SCRATCH_DOCUMENT")
        self.document_id = self.session_id + ":" + str(self.doc.RuntimeSerialNumber)
        self.created = set(); self.last_heartbeat = 0; self.guard()
        self.heartbeat()
        Rhino.RhinoApp.Idle += self.tick
        # A UI timer keeps file-queue polling alive while this separate instance is in the background.
        import clr
        clr.AddReference("System.Windows.Forms")
        from System.Windows.Forms import Timer
        self.timer = Timer(); self.timer.Interval = 200; self.timer.Tick += self.tick; self.timer.Start()

    def guard(self):
        active = Rhino.RhinoDoc.ActiveDoc
        if active is None or active.RuntimeSerialNumber != self.doc.RuntimeSerialNumber: raise ValueError("DOCUMENT_CHANGED")
        if Path(self.doc.Path).resolve() != self.path: raise ValueError("SCRATCH_PATH_CHANGED")

    def binding(self):
        return {"session_id": self.session_id, "document_id": self.document_id, "process_id": os.getpid()}

    def heartbeat(self):
        _atomic(self.root / "session.json", {"protocol": 1, "host": "rhino", **self.binding(), "scratch": True,
            "heartbeat": time.time(), "document_path": str(self.path)})

    def revision(self):
        options = Rhino.FileIO.SerializationOptions()
        rows = sorted((str(o.Id), o.Geometry.ToJSON(options), o.Attributes.ToJSON(options)) for o in self.doc.Objects if not o.IsDeleted)
        return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode("utf-8")).hexdigest()

    def context(self):
        return {"host": "rhino", **self.binding(), "scratch": True, "revision": self.revision(),
                "object_count": sum(1 for obj in self.doc.Objects if not obj.IsDeleted), "units": str(self.doc.ModelUnitSystem), "evidence": "live_rhino"}

    def execute(self, request):
        self.guard()
        if request.get("protocol") != 1 or request.get("binding") != self.binding(): raise ValueError("BINDING_MISMATCH")
        expiry = request.get("expires_at")
        if type(expiry) not in (int, float) or not math.isfinite(expiry) or time.time() > expiry: raise ValueError("REQUEST_EXPIRED")
        action = request.get("action"); payload = request.get("payload") or {}
        if action == "context": return self.context()
        if action == "list_objects":
            limit = payload.get("limit", 50)
            if type(limit) is not int or not 1 <= limit <= 200: raise ValueError("INVALID_LIMIT")
            rows = []
            for obj in self.doc.Objects:
                if obj.IsDeleted: continue
                if len(rows) >= limit: break
                box = obj.Geometry.GetBoundingBox(True)
                rows.append({"id": str(obj.Id), "name": obj.Attributes.Name or "", "geometry_type": obj.Geometry.GetType().Name,
                    "bbox": {"minimum": [box.Min.X, box.Min.Y, box.Min.Z], "maximum": [box.Max.X, box.Max.Y, box.Max.Z]},
                    "created_by_session": str(obj.Id) in self.created})
            return {**self.context(), "objects": rows}
        if action not in ("create_box", "delete_created"): raise ValueError("UNSUPPORTED_ACTION")
        if not request.get("expected_revision") or request["expected_revision"] != self.revision(): raise ValueError("STALE_REVISION")
        if action == "create_box":
            if set(payload) != {"origin_mm", "size_mm"}: raise ValueError("INVALID_BOX_PAYLOAD")
            origin = _vector(payload["origin_mm"]); size = _vector(payload["size_mm"], True)
            if sum(1 for obj in self.doc.Objects if not obj.IsDeleted) >= 500: raise ValueError("SCRATCH_OBJECT_LIMIT")
            factor = Rhino.RhinoMath.UnitScale(Rhino.UnitSystem.Millimeters, self.doc.ModelUnitSystem)
            minimum = Rhino.Geometry.Point3d(*(v * factor for v in origin))
            maximum = Rhino.Geometry.Point3d(*((a+b) * factor for a, b in zip(origin, size)))
            solid = Rhino.Geometry.BoundingBox(minimum, maximum).ToBrep()
            if solid is None or not solid.IsValid or not solid.IsSolid: raise ValueError("BOX_GEOMETRY_INVALID")
            undo = self.doc.BeginUndoRecord("LIMEN Labs scratch box")
            try:
                identifier = self.doc.Objects.AddBrep(solid)
                if identifier == System.Guid.Empty: raise ValueError("CREATE_FAILED")
                self.created.add(str(identifier))
            finally: self.doc.EndUndoRecord(undo)
            self.doc.Views.Redraw()
            return {**self.context(), "created_ids": [str(identifier)], "status": "scratch_box_created"}
        identifiers = payload.get("object_ids")
        if set(payload) != {"object_ids"} or not isinstance(identifiers, list) or len(identifiers) != 1: raise ValueError("DELETE_ONE_CREATED_OBJECT")
        identifier = identifiers[0]
        if identifier not in self.created: raise ValueError("NOT_CREATED_BY_SESSION")
        if self.doc.Objects.FindId(System.Guid.Parse(identifier)) is None: raise ValueError("OBJECT_MISSING")
        undo = self.doc.BeginUndoRecord("LIMEN Labs scratch delete")
        try:
            if not self.doc.Objects.Delete(System.Guid.Parse(identifier), True): raise ValueError("DELETE_FAILED")
            self.created.remove(identifier)
        finally: self.doc.EndUndoRecord(undo)
        self.doc.Views.Redraw()
        return {**self.context(), "deleted_ids": [identifier], "status": "scratch_object_deleted"}

    def tick(self, sender, args):
        try:
            if time.time() - self.last_heartbeat > .5:
                self.heartbeat(); self.last_heartbeat = time.time()
            for path in sorted((self.root / "requests").glob("*.json"))[:1]:
                if len(path.stem) != 32: continue
                uuid.UUID(hex=path.stem)
                claimed = path.with_suffix(".claimed")
                path.rename(claimed)  # Atomic claim before ANY native operation. Claimed files are never replayed.
                if claimed.stat().st_size > 65536: continue
                request = json.loads(claimed.read_text(encoding="utf-8"))
                if request.get("request_id") != path.stem: continue
                response = {"protocol": 1, "request_id": path.stem, "binding": request.get("binding")}
                try: response.update(ok=True, result=self.execute(request))
                except ValueError as exc: response.update(ok=False, error=str(exc))
                except Exception: response.update(ok=False, error="HOST_FAILURE: outcome requires inspection")
                _atomic(self.root / "responses" / path.name, response)
        except Exception:
            # A transport/journal error never replays a claimed request or reports native success.
            pass


_host = None


def start(root):
    global _host
    if _host is not None: raise ValueError("SCRATCH_HOST_ALREADY_STARTED")
    _host = ScratchHost(root)
    return _host.context()
