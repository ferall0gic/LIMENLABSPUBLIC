import json
import os
from pathlib import Path
import pytest
from limen_assembly_mcp.models import inspect_rhino, inspect_revit, check_sources


def test_rhino_inspection_reads_a_synthetic_file_without_changing_it(tmp_path):
    import rhino3dm as r
    model = r.File3dm(); model.Settings.ModelUnitSystem = r.UnitSystem.Millimeters
    layer = r.Layer(); layer.Name = "Test layer"; index = model.Layers.Add(layer)
    attributes = r.ObjectAttributes(); attributes.Name = "Test cube"; attributes.LayerIndex = index
    identifier = model.Objects.AddBrep(r.BoundingBox(0, 0, 0, 10, 20, 30).ToBrep(), attributes)
    source = tmp_path / "synthetic.3dm"; assert model.Write(str(source), 8)
    before = source.read_bytes(); result = inspect_rhino(source)
    assert source.read_bytes() == before
    assert result["host"] == "rhino" and result["object_count"] == 1
    assert result["objects"][0]["id"] == str(identifier)
    assert result["objects"][0]["name"] == "Test cube" and result["objects"][0]["layer"] == "Test layer"
    assert result["units"] == "Millimeters" and result["evidence"] == "saved_file"
    assert "path" not in result and "live" not in result["evidence"]


def test_revit_requires_explicit_snapshot_schema_and_identifies_export_evidence(tmp_path):
    source = tmp_path / "revit.json"
    snapshot = {"schema_version": 1, "host": "revit", "units": "mm", "document_label": "Synthetic",
                "elements": [{"id": "1001", "name": "Wall A", "category": "Walls", "type_name": "Generic", "bbox_mm": None}]}
    source.write_text(json.dumps(snapshot), encoding="utf-8")
    before = source.read_bytes(); result = inspect_revit(source)
    assert result["host"] == "revit" and result["object_count"] == 1
    assert result["evidence"] == "exported_snapshot" and result["objects"][0]["id"] == "1001"
    assert source.read_bytes() == before
    for field, value in [("host", "rhino"), ("units", "ft"), ("schema_version", 2), ("unapproved_field", "private")]:
        changed = {**snapshot, field: value}; source.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(ValueError): inspect_revit(source)


def test_sources_report_missing_ids_without_asserting_geometric_continuity():
    from test_core import spec
    data = spec(); data["assemblies"][0]["source_ids"] = ["a", "b"]
    result = check_sources(data, {"objects": [{"id": "a"}], "source_sha256": "f" * 64})
    assert result["missing_ids"] == ["b"] and not result["all_sources_present"]
    assert not result["geometry_verified"]


def test_missing_and_oversize_sources_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="Source file"): inspect_revit(tmp_path / "missing.json")
    path = tmp_path / "large.json"
    with path.open("wb") as out: out.truncate(16 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="size limit"): inspect_revit(path)


def test_duplicate_revit_ids_and_nonfinite_bboxes_are_refused(tmp_path):
    source = tmp_path / "bad.json"
    element = {"id": "1", "name": "A", "category": "Walls", "type_name": "T", "bbox_mm": None}
    snapshot = {"schema_version": 1, "host": "revit", "units": "mm", "document_label": "Synthetic", "elements": [element, element]}
    source.write_text(json.dumps(snapshot), encoding="utf-8")
    with pytest.raises(ValueError): inspect_revit(source)
