"""Generate .3dm test fixtures and the README sample with rhino3dm.

Every fixture is synthetic geometry created here; no client or third-party
models are used. Run:  python scripts/make_fixtures.py <output-folder>
"""

from __future__ import annotations

import math
import sys
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

ARCHIVE_VERSION = 8


def _model(units=r.UnitSystem.Millimeters, tol=0.001, angle_deg=1.0):
    m = r.File3dm()
    m.Settings.ModelUnitSystem = units
    m.Settings.ModelAbsoluteTolerance = tol
    set_angle_tolerance_degrees(m.Settings, angle_deg)
    return m


def _layer(m, name, parent=None):
    layer = r.Layer()
    layer.Name = name
    if parent is not None:
        layer.ParentLayerId = m.Layers[parent].Id
    return add_layer(m, layer)


def _attrs(layer_index, name=None):
    a = r.ObjectAttributes()
    a.LayerIndex = layer_index
    if name:
        a.Name = name
    return a


def _line(m, layer_index, a=(0, 0, 0), b=(1000, 0, 0)):
    return m.Objects.AddLine(r.Point3d(*a), r.Point3d(*b), _attrs(layer_index))


def closed_tetra_mesh():
    mesh = r.Mesh()
    for p in [(0, 0, 0), (100, 0, 0), (0, 100, 0), (0, 0, 100)]:
        mesh.Vertices.Add(*p)
    for f in [(0, 2, 1), (0, 1, 3), (1, 2, 3), (0, 3, 2)]:
        mesh.Faces.AddFace(*f)
    mesh.Normals.ComputeNormals()
    return mesh


def open_triangle_mesh():
    mesh = r.Mesh()
    for p in [(0, 0, 0), (100, 0, 0), (0, 100, 0)]:
        mesh.Vertices.Add(*p)
    mesh.Faces.AddFace(0, 1, 2)
    return mesh


def nonmanifold_fan_mesh():
    """Three triangles sharing one edge: non-manifold (and open)."""
    mesh = r.Mesh()
    for p in [(0, 0, 0), (100, 0, 0), (0, 100, 0), (0, -100, 0), (0, 0, 100)]:
        mesh.Vertices.Add(*p)
    for f in [(0, 1, 2), (0, 1, 3), (0, 1, 4)]:
        mesh.Faces.AddFace(*f)
    return mesh


def clean_model():
    """Passes every rule in the default and strict profiles."""
    m = _model()
    wall = _layer(m, "A-WALL")
    _line(m, wall)
    sub = _layer(m, "A-WALL-EXTR")
    m.Objects.AddBrep(r.Sphere(r.Point3d(0, 0, 0), 500).ToBrep(), _attrs(sub))
    msh = _layer(m, "A-MESH")
    m.Objects.AddMesh(closed_tetra_mesh(), _attrs(msh))
    return m


def invalid_object_model():
    m = clean_model()
    _line(m, 0, (0, 0, 0), (0, 0, 0))  # zero-length line: "Line points are coincident."
    return m


def tolerance_low_model():
    m = clean_model()
    m.Settings.ModelUnitSystem = r.UnitSystem.Meters
    m.Settings.ModelAbsoluteTolerance = 1e-7
    return m


def tolerance_high_model():
    m = clean_model()
    m.Settings.ModelAbsoluteTolerance = 0.5
    return m


def no_units_model():
    m = clean_model()
    m.Settings.ModelUnitSystem = r.UnitSystem.None_ if hasattr(r.UnitSystem, "None_") else getattr(r.UnitSystem, "None")
    return m


def wide_angle_model():
    m = clean_model()
    set_angle_tolerance_degrees(m.Settings, 10.0)
    return m


def mesh_open_model():
    m = clean_model()
    m.Objects.AddMesh(open_triangle_mesh(), _attrs(2))
    return m


def mesh_nonmanifold_model():
    m = clean_model()
    m.Objects.AddMesh(nonmanifold_fan_mesh(), _attrs(2))
    return m


def bad_layer_name_model():
    m = clean_model()
    # Lower case with a space: fails an office naming pattern such as ^[A-Z]-[A-Z0-9-]+$.
    # (openNURBS strips leading/trailing whitespace from layer names on its own.)
    bad = _layer(m, "door misc")
    _line(m, bad)
    return m


def nested_layer_model():
    """Parent layer with no direct objects, child layer with one: not empty."""
    m = clean_model()
    parent = _layer(m, "A-FLOR")
    child = _layer(m, "A-FLOR-LEVL", parent=parent)
    _line(m, child)
    return m


def empty_layer_model():
    m = clean_model()
    _layer(m, "A-EMPTY")
    return m


def no_layer_model():
    m = clean_model()
    _line(m, -1)
    return m


def default_layer_model():
    m = clean_model()
    d = _layer(m, "Default")
    _line(m, d)
    return m


def sample_model():
    """README sample: one invalid object and one empty layer."""
    m = _model()
    wall = _layer(m, "A-WALL")
    _line(m, wall)
    _line(m, wall, (500, 0, 0), (500, 0, 0))
    _layer(m, "A-ANNO")
    return m


FIXTURES = {
    "clean.3dm": clean_model,
    "invalid_object.3dm": invalid_object_model,
    "tolerance_low.3dm": tolerance_low_model,
    "tolerance_high.3dm": tolerance_high_model,
    "no_units.3dm": no_units_model,
    "wide_angle.3dm": wide_angle_model,
    "mesh_open.3dm": mesh_open_model,
    "mesh_nonmanifold.3dm": mesh_nonmanifold_model,
    "bad_layer_name.3dm": bad_layer_name_model,
    "nested_layer.3dm": nested_layer_model,
    "empty_layer.3dm": empty_layer_model,
    "no_layer.3dm": no_layer_model,
    "default_layer.3dm": default_layer_model,
}


# ---- v0.2 "revit" profile fixtures ---------------------------------------------

def _box(m, layer_index, x0, y0, z0, dx, dy, dz):
    brep = box_brep(r.BoundingBox(x0, y0, z0, x0 + dx, y0 + dy, z0 + dz))
    return m.Objects.AddBrep(brep, _attrs(layer_index))


def revit_clean_model():
    """1 x 2 x 3 m box, meters, 0.01 mm tolerance: no findings in the revit profile."""
    m = _model(units=r.UnitSystem.Meters, tol=0.00001)
    _box(m, _layer(m, "A-MASS"), 0, 0, 0, 1, 2, 3)
    return m


def revit_unitless_model():
    m = _model(units=getattr(r.UnitSystem, "None"))
    _box(m, _layer(m, "A-MASS"), 0, 0, 0, 1000, 2000, 3000)
    return m


def revit_short_edge_mm_model():
    """10 x 10 x 0.5 mm slab: its four vertical edges are 0.5 mm long."""
    m = _model()
    _box(m, _layer(m, "A-MASS"), 0, 0, 0, 10, 10, 0.5)
    return m


def revit_near_edge_mm_model():
    """10 x 10 x 0.8 mm slab: four 0.8 mm edges, just above the 0.79375 mm minimum."""
    m = _model()
    _box(m, _layer(m, "A-MASS"), 0, 0, 0, 10, 10, 0.8)
    return m


def revit_short_curve_m_model():
    """Meters file with a loose 0.0005 m (0.5 mm) line."""
    m = _model(units=r.UnitSystem.Meters, tol=0.00001)
    _line(m, _layer(m, "A-DETL"), (0, 0, 0), (0.0005, 0, 0))
    return m


def revit_short_polyline_segment_model():
    """Polyline whose last segment is 0.3 mm long (two segments, one short)."""
    m = _model()
    pl = r.Polyline()
    for p in ((0, 0, 0), (100, 0, 0), (100, 0.3, 0)):
        pl.Add(*p)
    m.Objects.AddPolyline(pl, _attrs(_layer(m, "A-DETL")))
    return m


def revit_short_extrusion_model():
    """Cylinder extrusion r = 5 mm, height 0.5 mm: the seam edge is 0.5 mm."""
    m = _model()
    ext = r.Extrusion.Create(r.Circle(5.0).ToNurbsCurve(), 0.5, True)
    m.Objects.AddExtrusion(ext, _attrs(_layer(m, "A-MASS")))
    return m


def revit_far_model():
    """mm file: one box at the origin and one 1 m box 20 km away on X."""
    m = _model()
    lay = _layer(m, "A-MASS")
    _box(m, lay, 0, 0, 0, 1000, 1000, 1000)
    _box(m, lay, 20_000_000, 0, 0, 1000, 1000, 1000)
    return m


def revit_span_model():
    """mm file: four 1 m boxes 15 km from the origin on +/-X and +/-Y.

    Each is inside the 10-mile (16.09 km) limit, but the model's bounding-box
    diagonal is about 42 km, beyond the 20-mile (32.19 km) extent limit.
    """
    m = _model()
    lay = _layer(m, "A-MASS")
    for x, y in ((15_000_000, 0), (-15_001_000, 0), (0, 15_000_000), (0, -15_001_000)):
        _box(m, lay, x, y, 0, 1000, 1000, 1000)
    return m


def revit_tolerance_model():
    """mm file with 0.1 mm absolute tolerance (above 1/10 of ~0.79 mm)."""
    m = _model(tol=0.1)
    _box(m, _layer(m, "A-MASS"), 0, 0, 0, 1000, 1000, 1000)
    return m


REVIT_FIXTURES = {
    "revit_clean.3dm": revit_clean_model,
    "revit_unitless.3dm": revit_unitless_model,
    "revit_short_edge_mm.3dm": revit_short_edge_mm_model,
    "revit_near_edge_mm.3dm": revit_near_edge_mm_model,
    "revit_short_curve_m.3dm": revit_short_curve_m_model,
    "revit_short_polyline_segment.3dm": revit_short_polyline_segment_model,
    "revit_short_extrusion.3dm": revit_short_extrusion_model,
    "revit_far.3dm": revit_far_model,
    "revit_span.3dm": revit_span_model,
    "revit_tolerance.3dm": revit_tolerance_model,
}


def write(model, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not write_model(model, path, ARCHIVE_VERSION):
        raise RuntimeError(f"rhino3dm could not write {path}")
    return path


def build_all(outdir: Path) -> dict[str, Path]:
    outdir = Path(outdir)
    every = {**FIXTURES, **REVIT_FIXTURES}
    return {name: write(fn(), outdir / name) for name, fn in every.items()}


def build_sample(path: Path) -> Path:
    return write(sample_model(), Path(path))


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "fixtures-out")
    for name, p in build_all(target).items():
        print(p)
