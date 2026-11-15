"""Compare two snapshots by object and layer ID."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .snapshot import ObjectRec, Snapshot


@dataclass
class ObjectChange:
    id: str
    type: str
    layer: str | None
    changed: dict[str, tuple[Any, Any]]  # field -> (old, new)
    moved_by: float | None = None        # bbox-centre distance, model units of NEW file
    resized: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"id": self.id, "type": self.type, "layer": self.layer,
                             "changed": {k: {"old": a, "new": b} for k, (a, b) in self.changed.items()}}
        if "geometry" in self.changed:
            d["bbox_centre_moved_by"] = self.moved_by
            d["bbox_size_changed"] = self.resized
        return d


@dataclass
class Diff:
    old: Snapshot
    new: Snapshot
    settings: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    document_text: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    layers_added: list[dict[str, Any]] = field(default_factory=list)
    layers_removed: list[dict[str, Any]] = field(default_factory=list)
    layers_changed: list[dict[str, Any]] = field(default_factory=list)
    objects_added: list[ObjectRec] = field(default_factory=list)
    objects_removed: list[ObjectRec] = field(default_factory=list)
    objects_changed: list[ObjectChange] = field(default_factory=list)
    objects_reidentified: list[tuple[ObjectRec, ObjectRec]] = field(default_factory=list)
    unchanged_objects: int = 0

    @property
    def is_empty(self) -> bool:
        return not (self.settings or self.document_text or self.layers_added or self.layers_removed
                    or self.layers_changed or self.objects_added or self.objects_removed
                    or self.objects_changed or self.objects_reidentified)

    def counts(self) -> dict[str, int]:
        return {
            "objects_added": len(self.objects_added),
            "objects_removed": len(self.objects_removed),
            "objects_changed": len(self.objects_changed),
            "objects_reidentified": len(self.objects_reidentified),
            "objects_unchanged": self.unchanged_objects,
            "layers_added": len(self.layers_added),
            "layers_removed": len(self.layers_removed),
            "layers_changed": len(self.layers_changed),
            "settings_changed": len(self.settings),
            "document_text_changed": len(self.document_text),
        }


def _centre(b):
    return ((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2)


def _size(b):
    return (b[3] - b[0], b[4] - b[1], b[5] - b[2])


def _close(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _dict_delta(old: dict, new: dict) -> dict[str, tuple[Any, Any]]:
    out = {}
    for k in sorted(set(old) | set(new)):
        if old.get(k) != new.get(k):
            out[k] = (old.get(k), new.get(k))
    return out


def diff_snapshots(old: Snapshot, new: Snapshot, match_geometry: bool = False,
                   ignore: tuple[str, ...] = ()) -> Diff:
    """Diff two snapshots.

    Objects and layers are matched by their IDs (GUIDs), which Rhino keeps
    across saves. With ``match_geometry``, a removed and an added object with
    identical geometry, type and layer are reported as one re-identified object
    (for example after Copy/Paste or re-import) instead of a removal plus an addition.
    ``ignore`` may contain "name", "user_text", "layer" to skip those fields.
    """
    d = Diff(old=old, new=new)
    d.settings = _dict_delta(old.settings, new.settings)
    d.document_text = _dict_delta(old.document_text, new.document_text)

    for lid in sorted(set(new.layers) - set(old.layers), key=lambda i: new.layers[i].full_path):
        d.layers_added.append({"id": lid, **new.layers[lid].fields()})
    for lid in sorted(set(old.layers) - set(new.layers), key=lambda i: old.layers[i].full_path):
        d.layers_removed.append({"id": lid, **old.layers[lid].fields()})
    for lid in sorted(set(old.layers) & set(new.layers), key=lambda i: new.layers[i].full_path):
        delta = _dict_delta(old.layers[lid].fields(), new.layers[lid].fields())
        if delta:
            d.layers_changed.append({"id": lid, "full_path": new.layers[lid].full_path,
                                     "changed": {k: {"old": a, "new": b} for k, (a, b) in delta.items()}})

    tol = max(old.settings.get("absolute_tolerance") or 0.0, new.settings.get("absolute_tolerance") or 0.0)
    added = [new.objects[i] for i in sorted(set(new.objects) - set(old.objects))]
    removed = [old.objects[i] for i in sorted(set(old.objects) - set(new.objects))]
    for oid in sorted(set(old.objects) & set(new.objects)):
        a, b = old.objects[oid], new.objects[oid]
        fa, fb = a.fields(), b.fields()
        for k in ignore:
            fa.pop(k, None)
            fb.pop(k, None)
        delta = _dict_delta(fa, fb)
        if not delta:
            d.unchanged_objects += 1
            continue
        ch = ObjectChange(id=oid, type=b.type, layer=b.layer, changed=delta)
        if "geometry" in delta and a.bbox and b.bbox:
            ca, cb = _centre(a.bbox), _centre(b.bbox)
            ch.moved_by = math.dist(ca, cb)
            ch.resized = not _close(_size(a.bbox), _size(b.bbox), tol)
        d.objects_changed.append(ch)

    if match_geometry:
        pool: dict[tuple, list[ObjectRec]] = {}
        for rec in added:
            if rec.geometry_hash:
                pool.setdefault((rec.geometry_hash, rec.type, rec.layer), []).append(rec)
        still_removed = []
        for rec in removed:
            key = (rec.geometry_hash, rec.type, rec.layer)
            if rec.geometry_hash and pool.get(key):
                d.objects_reidentified.append((rec, pool[key].pop(0)))
            else:
                still_removed.append(rec)
        paired = {n.id for _, n in d.objects_reidentified}
        added = [x for x in added if x.id not in paired]
        removed = still_removed
    d.objects_added, d.objects_removed = added, removed
    return d
