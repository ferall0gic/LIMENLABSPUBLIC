"""Generate .3dm test fixtures and the README sample with rhino3dm.

Every fixture is synthetic geometry created here; no client or third-party
models are used. Run:  python scripts/make_fixtures.py <output-folder>
"""

from __future__ import annotations

import sys
from pathlib import Path

import rhino3dm as r

ARCHIVE_VERSION = 8


def _model(units=r.UnitSystem.Millimeters, tol=0.001, angle_deg=1.0):
    m = r.File3dm()
    m.Settings.ModelUnitSystem = units
    m.Settings.ModelAbsoluteTolerance = tol
    m.Settings.ModelAngleToleranceDegrees = angle_deg
    return m


def _layer(m, name, parent=None):
    layer = r.Layer()
    layer.Name = name
    if parent is not None:
        layer.ParentLayerId = m.Layers[parent].Id
    return m.Layers.Add(layer)


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
    m.Settings.ModelAngleToleranceDegrees = 10.0
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


def write(model, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not model.Write(str(path), ARCHIVE_VERSION):
        raise RuntimeError(f"rhino3dm could not write {path}")
    return path


def build_all(outdir: Path) -> dict[str, Path]:
    outdir = Path(outdir)
    return {name: write(fn(), outdir / name) for name, fn in FIXTURES.items()}


def build_sample(path: Path) -> Path:
    return write(sample_model(), Path(path))


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "fixtures-out")
    for name, p in build_all(target).items():
        print(p)
