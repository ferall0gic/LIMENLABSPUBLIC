"""Archive provenance (v0.1.1): which Rhino version wrote each file, and a note when a
file is newer than the installed rhino3dm. Notes never change the exit code."""

import json
from pathlib import Path

import pytest
import rhino3dm

from diff3dm import _rh

DATA = Path(__file__).resolve().parent / "data"
V9 = DATA / "line_v9.3dm"  # copy of inspect3dm/tests/data/line_v9.3dm (rhino3dm 9.2.0b1)
READER = _rh.reader_major(rhino3dm)


@pytest.fixture(scope="module")
def v8_copy(tmp_path_factory):
    """Same document re-saved as a Rhino 8 archive: same object IDs, same geometry."""
    out = tmp_path_factory.mktemp("prov") / "line_v8.3dm"
    model = rhino3dm.File3dm.Read(str(V9))
    if not model.Write(str(out), 8):
        pytest.skip("this rhino3dm cannot write a version-8 archive")
    assert rhino3dm.File3dm.ReadArchiveVersion(str(out)) == 80
    return out


def test_v8_vs_v9_same_content_is_identical(v8_copy, run):
    # Geometry hashes are comparable across archive versions for this line.
    code, out, _ = run(v8_copy, V9, "--format", "json")
    doc = json.loads(out)
    assert code == 0 and doc["identical"] is True
    assert doc["schema_version"] == "1.1"
    assert doc["old_file"]["archive_version"] == 80 and doc["old_file"]["rhino_version"] == 8
    assert doc["new_file"]["archive_version"] == 90 and doc["new_file"]["rhino_version"] == 9


def test_newer_archive_note(v8_copy, run):
    code, out, _ = run(v8_copy, V9)
    assert code == 0
    assert f"Old: {v8_copy} (Rhino 8 file, archive version 80)" in out
    assert f"New: {V9} (Rhino 9 file, archive version 90)" in out
    has_note = "Note: New file is a Rhino 9 file read with rhino3dm" in out
    assert has_note == (READER is not None and READER < 9)
    assert "Note: Old file" not in out


def test_json_notes_match_reader(v8_copy, run):
    _, out, _ = run(v8_copy, V9, "--format", "json")
    notes = json.loads(out)["notes"]
    assert len(notes) == (1 if READER is not None and READER < 9 else 0)


def test_v8_fixtures_have_no_note(fx, run):
    a = next(iter(fx.values()))
    _, out, _ = run(a, a, "--format", "json")
    doc = json.loads(out)
    assert doc["notes"] == [] and doc["old_file"]["rhino_version"] == 8
