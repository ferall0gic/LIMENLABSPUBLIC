"""rhino3dm 8.x / 9.x compatibility helpers.

This file is kept byte-identical in inspect3dm (src/inspect3dm/_rh.py) and
3dm-diff (src/diff3dm/_rh.py); a test in each tool checks that. Each tool
ships its own copy so the tools stay independently installable.

Rule: feature-detect, never compare version strings. Only API-shape
differences are handled here. Any other error is raised to the caller, which
reports it instead of skipping the object silently.

Known differences (rhino3dm docs/migrating-to-9, branch 9.x, read 2026-11-17):
- ObjectAttributes.Id            -> ObjectId (8.35 has only Id)
- Layer.Visible / Layer.Locked   -> IsVisible / IsLocked
- GeometryBase.IsValidWithLog    property returning (ok, log) -> method
- GeometryBase.GetBoundingBox()  no-arg form removed; 8.x rejects (True) (rhino3dm#721)
- NurbsCurve control point .W    -> .Weight (X, Y, Z stay homogeneous in both)
- File3dm.Strings                no len()/indexing in 9.x -> Count, GetKey(i), GetValue(i)
- File3dm.Read(missing path)     returns None in 8.x, raises FileNotFoundError in 9.x
"""

from __future__ import annotations

from typing import Any


def object_id(attrs) -> str:
    """Object GUID as a string."""
    oid = getattr(attrs, "ObjectId", None)
    if oid is None:
        oid = attrs.Id
    return str(oid)


def layer_visible(layer) -> bool:
    return bool(layer.IsVisible if hasattr(layer, "IsVisible") else layer.Visible)


def layer_locked(layer) -> bool:
    return bool(layer.IsLocked if hasattr(layer, "IsLocked") else layer.Locked)


def validity(geom) -> tuple[bool, str]:
    """(is_valid, openNURBS log text). Raises if the object cannot be evaluated."""
    v = geom.IsValidWithLog
    ok, log = v() if callable(v) else v
    return bool(ok), str(log or "")


def bbox(geom) -> Any:
    """Bounding box: accurate overload where it exists (9.x), else the no-arg form (8.x)."""
    try:
        return geom.GetBoundingBox(True)
    except TypeError:
        return geom.GetBoundingBox()


def control_point_xyzw(p) -> tuple[float, float, float, float]:
    """Homogeneous (x*w, y*w, z*w, w) of a NURBS control point."""
    w = p.Weight if hasattr(p, "Weight") else p.W
    return p.X, p.Y, p.Z, w


def read_model(rhino3dm_module, path: str):
    """File3dm.Read that returns None for a missing or unreadable file on 8.x and 9.x."""
    try:
        return rhino3dm_module.File3dm.Read(str(path))
    except FileNotFoundError:
        return None


def document_strings(model) -> list[tuple[str, str]]:
    """Document user text as (key, value) pairs (9.x: Count/GetKey/GetValue, no len or indexing)."""
    table = model.Strings
    if hasattr(table, "GetKey"):
        return [(str(table.GetKey(i)), str(table.GetValue(i))) for i in range(table.Count)]
    return [(str(k), str(v)) for k, v in (table[i] for i in range(len(table)))]
