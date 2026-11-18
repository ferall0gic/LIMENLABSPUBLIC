"""Preparation only; does not start or install a host application."""
import importlib.util
from pathlib import Path
import pytest
from limen_assembly_mcp.live import create_scratch_session


def launcher():
    path = Path(__file__).parents[1] / "scripts/start_scratch.py"
    spec = importlib.util.spec_from_file_location("scratch_launcher_test", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_rhino_preparation_creates_only_its_new_empty_file_and_bootstrap(tmp_path):
    import rhino3dm
    root = create_scratch_session(tmp_path, "rhino"); module = launcher()
    module.prepare_rhino(root, Path("host.py"))
    assert len(rhino3dm.File3dm.Read(str(root/"scratch.3dm")).Objects) == 0
    assert "start(" in (root/"bootstrap.py").read_text()
    before = (root/"scratch.3dm").read_bytes()
    with pytest.raises(ValueError): module.prepare_rhino(root, Path("host.py"))
    assert (root/"scratch.3dm").read_bytes() == before


def test_revit_manifest_escapes_path_and_uses_only_scratch_application():
    from xml.etree import ElementTree as ET
    text = launcher().revit_manifest(Path("C:/scratch/A&B/host.dll"))
    node = ET.fromstring(text).find("AddIn")
    assert node.findtext("Assembly") == str(Path("C:/scratch/A&B/host.dll"))
    assert node.findtext("FullClassName") == "LimenLabs.Scratch.Revit.ScratchApplication"
