"""Write synthetic .3dm revision pairs with rhino3dm (no client or third-party models).

Run:  python scripts/make_fixtures.py <output-folder>
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path

import rhino3dm as r


# ---- rhino3dm 8.x / 9.x neutral helpers (fixtures only; see src/*/_rh.py for the tool side)

def add_layer(m, layer) -> int:
    """Add a layer and return its index (9.x Layers.Add returns None)."""
    idx = m.Layers.Add(layer)
    return len(m.Layers) - 1 if idx is None else idx


def set_object_id(attrs, oid) -> None:
    if hasattr(attrs, "ObjectId"):
        attrs.ObjectId = oid
    else:
        attrs.Id = oid


def set_angle_tolerance_degrees(settings, degrees: float) -> None:
    """9.x has no Degrees setter; Radians works on both majors."""
    settings.ModelAngleToleranceRadians = math.radians(degrees)


def box_brep(bb):
    """Box Brep from a BoundingBox (9.x has no Brep.CreateFromBoundingBox)."""
    if hasattr(r.Brep, "CreateFromBoundingBox"):
        return r.Brep.CreateFromBoundingBox(bb)
    return r.Brep.CreateFromBox(r.Box(bb))


def _can_set_units() -> bool:
    try:
        r.File3dm().Settings.ModelUnitSystem = r.UnitSystem.Millimeters
        return True
    except AttributeError:  # rhino3dm 9.2.0b0/b1: ModelUnitSystem has no setter
        return False


CAN_SET_UNITS = _can_set_units()
NEEDS_UNIT_SETTER = "this rhino3dm cannot set ModelUnitSystem; build fixtures under rhino3dm 8"


def write_model(model, path, version: int = 8) -> bool:
    """Write a v8 archive where the reader supports it; 9.x writes only its own version (0)."""
    try:
        if model.Write(str(path), version):
            return True
    except (TypeError, ValueError):
        pass
    return bool(model.Write(str(path), 0))

L_WALL = uuid.UUID("10000000-0000-4000-8000-000000000001")
L_DOOR = uuid.UUID("10000000-0000-4000-8000-000000000002")
L_ANNO = uuid.UUID("10000000-0000-4000-8000-000000000003")
O_WALL = uuid.UUID("20000000-0000-4000-8000-000000000001")
O_SLAB = uuid.UUID("20000000-0000-4000-8000-000000000002")
O_DOOR = uuid.UUID("20000000-0000-4000-8000-000000000003")
O_GRID = uuid.UUID("20000000-0000-4000-8000-000000000004")
O_NEW = uuid.UUID("20000000-0000-4000-8000-000000000005")
O_COPY = uuid.UUID("20000000-0000-4000-8000-000000000006")


def _layer(m, lid, name, color=(0, 0, 0, 255)):
    layer = r.Layer()
    layer.Name = name
    layer.Id = lid
    layer.Color = color
    return add_layer(m, layer)


def _attrs(layer_index, oid, name="", text=None):
    a = r.ObjectAttributes()
    a.LayerIndex = layer_index
    set_object_id(a, oid)
    if name:
        a.Name = name
    for k, v in (text or {}).items():
        a.SetUserString(k, v)
    return a


def _box(x0, y0, z0, dx, dy, dz):
    return box_brep(r.BoundingBox(x0, y0, z0, x0 + dx, y0 + dy, z0 + dz))


def revision(rev: int):
    """rev 1 = base. rev 2 = a typical next issue (see README for the expected diff)."""
    m = r.File3dm()
    m.Settings.ModelUnitSystem = r.UnitSystem.Millimeters
    m.Settings.ModelAbsoluteTolerance = 0.01 if rev == 1 else 0.001       # tolerance tightened
    set_angle_tolerance_degrees(m.Settings, 1.0)
    m.Strings["project"] = "Synthetic test tower"
    m.Strings["issue"] = "P01" if rev == 1 else "P02"                     # document text changed
    wall = _layer(m, L_WALL, "A-WALL", (200, 0, 0, 255))
    door = _layer(m, L_DOOR, "A-DOOR" if rev == 1 else "A-DOOR-INT")     # layer renamed
    if rev == 1:
        _layer(m, L_ANNO, "A-ANNO")                                       # layer removed in rev 2
    m.Objects.AddBrep(_box(0, 0, 0, 6000, 200, 3000), _attrs(wall, O_WALL, "W1", {"fire_rating": "60"}))
    # slab: moved 500 mm in X in rev 2
    dx = 0 if rev == 1 else 500
    m.Objects.AddBrep(_box(dx, 0, -300, 6000, 6000, 300), _attrs(wall, O_SLAB, "S1"))
    # door: same geometry, user text changed in rev 2
    rating = "30" if rev == 1 else "60"
    m.Objects.AddBrep(_box(1000, 0, 0, 900, 200, 2100), _attrs(door, O_DOOR, "D1", {"fire_rating": rating}))
    if rev == 1:
        # grid line: deleted in rev 2
        m.Objects.AddLine(r.Point3d(0, -1000, 0), r.Point3d(0, 7000, 0), _attrs(wall, O_GRID, "Grid A"))
    else:
        # new column
        m.Objects.AddBrep(_box(5600, 5600, 0, 400, 400, 3000), _attrs(wall, O_NEW, "C1"))
    return m


def reid_pair():
    """Same line in both files, but with a new object ID in the second (e.g. after Copy/Paste)."""
    out = []
    for oid in (O_GRID, O_COPY):
        m = r.File3dm()
        m.Settings.ModelUnitSystem = r.UnitSystem.Millimeters
        lay = _layer(m, L_WALL, "A-WALL")
        m.Objects.AddLine(r.Point3d(0, 0, 0), r.Point3d(1000, 0, 0), _attrs(lay, oid))
        out.append(m)
    return out


def write(model, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not write_model(model, path, 8):
        raise RuntimeError(f"rhino3dm could not write {path}")
    return path


def build_all(outdir) -> dict[str, Path]:
    outdir = Path(outdir)
    a, b = reid_pair()
    return {
        "rev1.3dm": write(revision(1), outdir / "rev1.3dm"),
        "rev1_copy.3dm": write(revision(1), outdir / "rev1_copy.3dm"),
        "rev2.3dm": write(revision(2), outdir / "rev2.3dm"),
        "reid_a.3dm": write(a, outdir / "reid_a.3dm"),
        "reid_b.3dm": write(b, outdir / "reid_b.3dm"),
    }


if __name__ == "__main__":
    for p in build_all(Path(sys.argv[1] if len(sys.argv) > 1 else "fixtures-out")).values():
        print(p)
