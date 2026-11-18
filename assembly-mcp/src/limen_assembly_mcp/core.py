"""Small declarative assembly plans; no host execution or model mutations."""
from hashlib import sha256
import json
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False, le=1e9)]
Identifier = Annotated[str, Field(strict=True, min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Layer(Record):
    material: Annotated[str, Field(strict=True, min_length=1, max_length=200, pattern=r"\S")]
    role: Annotated[str, Field(strict=True, min_length=1, max_length=100)] = "unspecified"
    thickness_mm: Positive | None  # Unknown is explicit; it never becomes a nominal modeled thickness.


class Assembly(Record):
    id: Identifier
    kind: Literal["wall", "slab", "roof", "component"]
    layers: Annotated[list[Layer], Field(min_length=1, max_length=32)]
    area_m2: Positive | None = None
    quantity: Annotated[int, Field(strict=True, ge=1, le=1000)] = 1
    source_ids: Annotated[list[Identifier], Field(max_length=1000)] = Field(default_factory=list)


class Relationship(Record):
    source: Identifier
    target: Identifier
    kind: Literal["supported_by", "hosted_by", "adjacent", "continuous_with"]


class AssemblySpec(Record):
    units: Literal["mm"]
    assemblies: Annotated[list[Assembly], Field(min_length=1, max_length=128)]
    relationships: Annotated[list[Relationship], Field(max_length=1024)] = Field(default_factory=list)

    @model_validator(mode="after")
    def references(self):
        ids = {a.id for a in self.assemblies}
        if len(ids) != len(self.assemblies): raise ValueError("Assembly IDs must be unique")
        for edge in self.relationships:
            if edge.source not in ids or edge.target not in ids: raise ValueError("Relationship target or source is missing")
            if edge.source == edge.target: raise ValueError("Self relationships are not supported")
        return self


def validate_assembly(spec: dict) -> dict:
    data = AssemblySpec.model_validate(spec)
    return {"valid": True, "assembly_count": len(data.assemblies), "evidence": "schema_checked",
            "geometry_verified": False, "unknown_thickness_count": sum(l.thickness_mm is None for a in data.assemblies for l in a.layers)}


def preview_assembly(spec: dict, host: str) -> dict:
    if host not in ("rhino", "revit"): raise ValueError("Unsupported host")
    data = AssemblySpec.model_validate(spec)
    canonical = json.dumps({"host": host, "schema_version": 1, "spec": data.model_dump()}, sort_keys=True, separators=(",", ":"), allow_nan=False)
    plans = []
    for assembly in data.assemblies:
        offset = 0.0; layers = []
        for layer in assembly.layers:
            end = offset + layer.thickness_mm if offset is not None and layer.thickness_mm is not None else None
            layers.append({**layer.model_dump(), "start_mm": offset, "end_mm": end})
            offset = end
        plans.append({"id": assembly.id, "kind": assembly.kind, "layers": layers,
                      "total_thickness_mm": offset, "known_thickness_mm": sum(l.thickness_mm or 0 for l in assembly.layers)})
    return {"schema_version": 1, "host": host, "status": "plan_only", "plan_hash": sha256(canonical.encode()).hexdigest(),
            "geometry_verified": False, "model_changed": False, "assemblies": plans,
            "limitations": ["No geometry is generated or committed.", "Layer order is the supplied order; orientation is not inferred.",
                            "Declared support and continuity do not establish structural or envelope performance."]}


def assembly_schedule(spec: dict) -> dict:
    data = AssemblySpec.model_validate(spec); rows = []
    for assembly in data.assemblies:
        for index, layer in enumerate(assembly.layers):
            area = assembly.area_m2 * assembly.quantity if assembly.area_m2 is not None else None
            volume = area * layer.thickness_mm / 1000 if area is not None and layer.thickness_mm is not None else None
            rows.append({"assembly_id": assembly.id, "layer_index": index, "material": layer.material, "role": layer.role,
                         "thickness_mm": layer.thickness_mm, "quantity": assembly.quantity, "area_m2": area, "volume_m3": volume})
    return {"rows": rows, "evidence": "supplied_dimensions", "geometry_verified": False}


def assembly_relationships(spec: dict, assembly_id: str) -> dict:
    data = AssemblySpec.model_validate(spec)
    if assembly_id not in {a.id for a in data.assemblies}: raise ValueError("Unknown assembly")
    return {"assembly_id": assembly_id, "relationships": [{**r.model_dump(), "evidence": "declared"} for r in data.relationships
            if assembly_id in (r.source, r.target)], "geometry_verified": False}
