"""Read only the model file explicitly bound at MCP server startup."""
from hashlib import sha256
import json
from pathlib import Path
from typing import Annotated, Literal
from pydantic import Field, model_validator
from .core import Record, Identifier, AssemblySpec


def _read(path: Path, maximum: int) -> bytes:
    path = Path(path)
    try:
        with path.open("rb") as source: data = source.read(maximum + 1)
    except OSError: raise ValueError("Source file is unavailable") from None
    if len(data) > maximum: raise ValueError("Source file exceeds size limit")
    return data


def inspect_rhino(path: Path) -> dict:
    import rhino3dm
    data = _read(path, 256 * 1024 * 1024)
    try: model = rhino3dm.File3dm.FromByteArray(data)
    except Exception: raise ValueError("Source file is not a readable .3dm") from None
    if model is None: raise ValueError("Source file is not a readable .3dm")
    rows = []
    layers = {l.Index: l.Name for l in model.Layers}
    for obj in model.Objects:
        if len(rows) >= 10000: raise ValueError("Model exceeds the alpha's 10000-object limit")
        rows.append({"id": str(obj.Attributes.Id), "name": obj.Attributes.Name or "", "layer": layers.get(obj.Attributes.LayerIndex, ""),
                     "geometry_type": type(obj.Geometry).__name__, "valid": bool(obj.Geometry.IsValid)})
    return {"host": "rhino", "units": str(model.Settings.ModelUnitSystem).split(".")[-1], "object_count": len(rows),
            "objects": rows, "source_sha256": sha256(data).hexdigest(), "evidence": "saved_file", "model_changed": False}


Finite = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Vector = Annotated[list[Finite], Field(min_length=3, max_length=3)]


class Bounds(Record):
    minimum: Vector
    maximum: Vector

    @model_validator(mode="after")
    def ordered(self):
        if any(a > b for a, b in zip(self.minimum, self.maximum)): raise ValueError("Inverted bounding box")
        return self


class Element(Record):
    id: Identifier
    name: Annotated[str, Field(strict=True, max_length=500)]
    category: Annotated[str, Field(strict=True, max_length=500)]
    type_name: Annotated[str, Field(strict=True, max_length=500)]
    bbox_mm: Bounds | None


class RevitSnapshot(Record):
    schema_version: Literal[1]
    host: Literal["revit"]
    units: Literal["mm"]
    document_label: Annotated[str, Field(strict=True, max_length=500)]
    elements: Annotated[list[Element], Field(max_length=10000)]

    @model_validator(mode="after")
    def unique_ids(self):
        if len({e.id for e in self.elements}) != len(self.elements): raise ValueError("Duplicate element IDs")
        return self


def inspect_revit(path: Path) -> dict:
    data = _read(path, 16 * 1024 * 1024)
    try: snapshot = RevitSnapshot.model_validate_json(data)
    except ValueError: raise ValueError("Invalid Revit snapshot schema") from None
    return {"host": "revit", "units": snapshot.units, "document_label": snapshot.document_label,
            "object_count": len(snapshot.elements), "objects": [e.model_dump() for e in snapshot.elements],
            "source_sha256": sha256(data).hexdigest(), "evidence": "exported_snapshot", "model_changed": False}


def check_sources(spec: dict, model: dict) -> dict:
    data = AssemblySpec.model_validate(spec)
    present = {o["id"] for o in model["objects"]}
    requested = {i for a in data.assemblies for i in a.source_ids}
    missing = sorted(requested - present)
    return {"all_sources_present": not missing, "checked_source_count": len(requested), "missing_ids": missing,
            "source_sha256": model["source_sha256"], "evidence": "identifier_check", "geometry_verified": False}
