"""Fake Revit API only: verifies export contract and exclusive local file creation."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest


def exporter(monkeypatch, tmp_path, selected=(1,)):
    point = lambda x, y, z: SimpleNamespace(X=x, Y=y, Z=z)
    element = SimpleNamespace(UniqueId="fake-wall-1", Name="Wall", Category=SimpleNamespace(Name="Walls"),
        GetTypeId=lambda: 99, get_BoundingBox=lambda view: SimpleNamespace(Min=point(0, 0, 0), Max=point(1, 2, 3)))
    doc = SimpleNamespace(Title="Synthetic", GetElement=lambda identifier: SimpleNamespace(Name="Wall type") if identifier == 99 else element)
    revit = SimpleNamespace(doc=doc, uidoc=SimpleNamespace(Selection=SimpleNamespace(GetElementIds=lambda: selected)))
    destination = tmp_path / "export.json"; alerts = []
    forms = SimpleNamespace(alert=alerts.append, save_file=lambda **kwargs: str(destination))
    monkeypatch.setitem(sys.modules, "pyrevit", SimpleNamespace(revit=revit, forms=forms))
    units = SimpleNamespace(ConvertFromInternalUnits=lambda value, unit: value * 304.8)
    monkeypatch.setitem(sys.modules, "Autodesk.Revit.DB", SimpleNamespace(UnitUtils=units, UnitTypeId=SimpleNamespace(Millimeters="mm")))
    path = Path(__file__).parents[1] / "exporters/revit_selected_snapshot.py"
    spec = importlib.util.spec_from_file_location("test_revit_exporter", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module, destination, alerts


def test_exporter_fake_api_produces_schema_accepted_by_snapshot_reader(monkeypatch, tmp_path):
    from limen_assembly_mcp.models import inspect_revit
    module, destination, alerts = exporter(monkeypatch, tmp_path)
    module.main()
    result = inspect_revit(destination)
    assert result["evidence"] == "exported_snapshot"
    assert result["objects"][0]["bbox_mm"]["maximum"] == pytest.approx([304.8, 609.6, 914.4])
    assert alerts and "document was not changed" in alerts[0]


def test_exporter_does_not_overwrite_existing_file(monkeypatch, tmp_path):
    module, destination, _ = exporter(monkeypatch, tmp_path)
    destination.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError): module.main()
    assert destination.read_text() == "keep"


def test_exporter_requires_a_bounded_explicit_selection(monkeypatch, tmp_path):
    for ids in ([], list(range(1001))):
        module, destination, alerts = exporter(monkeypatch, tmp_path, ids)
        module.main()
        assert not destination.exists() and "Select 1 to 1,000" in alerts[-1]
