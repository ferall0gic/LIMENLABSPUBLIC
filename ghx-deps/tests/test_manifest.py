"""Synthetic .ghx fixtures only (scripts/make_fixtures.py)."""

import json

import pytest

from ghxdeps import read_manifest
from ghxdeps.manifest import GhxError, discover


def test_core_only(fx):
    m = read_manifest(fx["core_only.ghx"])
    assert m.libraries == []
    assert m.object_count == 3
    assert m.components[("Number Slider", "aaaaaaaa-0000-4000-8000-000000000001")] == 2
    assert m.grasshopper_version == "1.0.7" and m.archive_version == "0.2.2"


def test_libraries_are_read_and_sorted(fx):
    m = read_manifest(fx["two_plugins.ghx"])
    assert [lib.name for lib in m.libraries] == ["MeshKit", "SolarLab"]
    mk, sl = m.libraries
    assert (mk.version, mk.author, mk.id) == ("2.1.0", "Example Author", "bbbbbbbb-0000-4000-8000-000000000001")
    assert mk.assembly_full_name.startswith("MeshKit, Version=2.1.0.0")
    assert sl.version == "" and sl.display_version == "0.9.3.0"  # falls back to assembly version


def test_scripts_clusters_and_absolute_paths(fx):
    m = read_manifest(fx["scripts_clusters_paths.ghx"])
    assert dict(m.script_components) == {"C# Script": 2}
    assert m.clusters == 1
    assert m.file_references == [r"C:\Projects\Tower\site_survey.csv"]  # relative "notes.txt" is not listed


@pytest.mark.parametrize("name, needle", [
    ("not_xml.ghx", "is not valid XML"),
    ("other_xml.ghx", "not a Grasshopper archive"),
    ("binary.gh", "binary .gh file"),
])
def test_unreadable_inputs(fx, name, needle):
    with pytest.raises(GhxError, match=needle):
        read_manifest(fx[name])


def test_missing_file(tmp_path):
    with pytest.raises(GhxError, match="does not exist"):
        read_manifest(tmp_path / "nope.ghx")


def test_discover_splits_gh_and_ghx(fx):
    folder = fx["core_only.ghx"].parent
    ghx, gh = discover([folder])
    assert {p.name for p in gh} == {"binary.gh"}
    assert "core_only.ghx" in {p.name for p in ghx}


# --- CLI ------------------------------------------------------------------------------------

def test_cli_no_allowlist_exit_0(fx, run):
    code, out, _ = run(fx["two_plugins.ghx"])
    assert code == 0
    assert "| MeshKit | 2.1.0 | 1 file(s) |" in out


def test_cli_allowlist_gate(fx, run, tmp_path):
    allow = tmp_path / "office-plugins.txt"
    allow.write_text("# approved plug-ins\nMeshKit\n", encoding="utf-8")
    code, out, _ = run(fx["two_plugins.ghx"], "--allowlist", allow)
    assert code == 1 and "Not on the allowlist: SolarLab." in out
    code, _, _ = run(fx["two_plugins.ghx"], "--allowlist", allow, "--allow", "bbbbbbbb-0000-4000-8000-000000000002")
    assert code == 0  # allowed by Id


def test_cli_empty_allowlist_rejects_any_plugin(fx, run, tmp_path):
    allow = tmp_path / "none.txt"
    allow.write_text("", encoding="utf-8")
    assert run(fx["two_plugins.ghx"], "--allowlist", allow)[0] == 1
    assert run(fx["core_only.ghx"], "--allowlist", allow)[0] == 0


def test_cli_json(fx, run):
    code, out, _ = run(fx["scripts_clusters_paths.ghx"], "--format", "json", "--allow", "MeshKit")
    doc = json.loads(out)
    f = doc["files"][0]
    assert code == 0 and f["not_allowed"] == []
    assert f["script_components"] == {"C# Script": 2}
    assert f["components"][0] == {"name": "C# Script", "guid": "aaaaaaaa-0000-4000-8000-000000000003", "count": 2}
    assert doc["errors"] == []


def test_cli_folder_with_unreadable_exits_2(fx, run):
    code, out, _ = run(fx["core_only.ghx"].parent)
    assert code == 2
    assert "binary .gh is not supported" in out and "is not valid XML" in out


def test_cli_no_files(tmp_path, run):
    code, _, err = run(tmp_path)
    assert code == 2 and "No .ghx files found" in err


def test_files_not_modified(fx):
    before = {k: p.read_bytes() for k, p in fx.items()}
    for k, p in fx.items():
        try:
            read_manifest(p)
        except GhxError:
            pass
    assert before == {k: p.read_bytes() for k, p in fx.items()}
