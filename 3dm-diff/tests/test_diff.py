"""All inputs are synthetic models from scripts/make_fixtures.py."""

import json
import uuid

import pytest
import rhino3dm as r

import make_fixtures as mf
from diff3dm import diff_snapshots, load_snapshot
from diff3dm.snapshot import ReadError, geometry_hash


def ids(recs):
    return [x.id for x in recs]


@pytest.fixture(scope="module")
def d12(fx):
    return diff_snapshots(load_snapshot(fx["rev1.3dm"]), load_snapshot(fx["rev2.3dm"]))


def test_identical_files_have_no_differences(fx):
    d = diff_snapshots(load_snapshot(fx["rev1.3dm"]), load_snapshot(fx["rev1_copy.3dm"]))
    assert d.is_empty and d.unchanged_objects == 4


def test_added_removed(d12):
    assert ids(d12.objects_added) == [str(mf.O_NEW)]
    assert ids(d12.objects_removed) == [str(mf.O_GRID)]


def test_changed_geometry_reports_move_not_resize(d12):
    slab = next(c for c in d12.objects_changed if c.id == str(mf.O_SLAB))
    assert set(slab.changed) == {"geometry"}
    assert slab.moved_by == pytest.approx(500.0)
    assert slab.resized is False


def test_attribute_changes_without_geometry_change(d12):
    door = next(c for c in d12.objects_changed if c.id == str(mf.O_DOOR))
    assert set(door.changed) == {"layer", "user_text"}
    assert door.changed["layer"] == ("A-DOOR", "A-DOOR-INT")
    assert door.changed["user_text"] == ({"fire_rating": "30"}, {"fire_rating": "60"})


def test_unchanged_wall(d12):
    assert d12.unchanged_objects == 1
    assert str(mf.O_WALL) not in [c.id for c in d12.objects_changed]


def test_layers_settings_and_document_text(d12):
    assert [x["full_path"] for x in d12.layers_removed] == ["A-ANNO"]
    assert d12.layers_added == []
    (ch,) = d12.layers_changed
    assert ch["changed"] == {"full_path": {"old": "A-DOOR", "new": "A-DOOR-INT"}}
    assert d12.settings == {"absolute_tolerance": (0.01, 0.001)}
    assert d12.document_text == {"issue": ("P01", "P02")}


def test_ignore_fields(fx):
    d = diff_snapshots(load_snapshot(fx["rev1.3dm"]), load_snapshot(fx["rev2.3dm"]), ignore=("user_text", "layer"))
    assert str(mf.O_DOOR) not in [c.id for c in d.objects_changed]


def test_match_geometry_pairs_new_ids(fx):
    a, b = load_snapshot(fx["reid_a.3dm"]), load_snapshot(fx["reid_b.3dm"])
    plain = diff_snapshots(a, b)
    assert len(plain.objects_added) == len(plain.objects_removed) == 1
    m = diff_snapshots(a, b, match_geometry=True)
    assert m.objects_added == [] and m.objects_removed == []
    (old, new), = m.objects_reidentified
    assert (old.id, new.id) == (str(mf.O_GRID), str(mf.O_COPY))


def test_geometry_hash_is_stable_and_sensitive():
    line = r.LineCurve(r.Point3d(0, 0, 0), r.Point3d(1, 0, 0))
    same = r.LineCurve(r.Point3d(0, 0, 0), r.Point3d(1, 0, 0))
    other = r.LineCurve(r.Point3d(0, 0, 0), r.Point3d(1.0001, 0, 0))
    assert geometry_hash(line) == geometry_hash(same)
    assert geometry_hash(line) != geometry_hash(other)
    assert geometry_hash(None) is None


def test_read_errors(tmp_path):
    with pytest.raises(ReadError, match="does not exist"):
        load_snapshot(str(tmp_path / "nope.3dm"))
    empty = tmp_path / "e.3dm"
    empty.write_bytes(b"")
    with pytest.raises(ReadError, match="empty"):
        load_snapshot(str(empty))
    junk = tmp_path / "j.3dm"
    junk.write_bytes(b"not a model at all")
    with pytest.raises(ReadError, match="not a readable"):
        load_snapshot(str(junk))
    with pytest.raises(ReadError, match="is a folder"):
        load_snapshot(str(tmp_path))


def test_files_are_not_modified(fx):
    before = {k: p.read_bytes() for k, p in fx.items()}
    diff_snapshots(load_snapshot(fx["rev1.3dm"]), load_snapshot(fx["rev2.3dm"]))
    assert before == {k: p.read_bytes() for k, p in fx.items()}


# --- CLI ---------------------------------------------------------------------------

def test_cli_exit_codes(fx, run):
    assert run(fx["rev1.3dm"], fx["rev1_copy.3dm"])[0] == 0
    assert run(fx["rev1.3dm"], fx["rev2.3dm"])[0] == 1
    code, _, err = run(fx["rev1.3dm"])
    assert code == 2 and "Pass two files" in err
    code, _, err = run(fx["rev1.3dm"], "missing.3dm")
    assert code == 2 and "does not exist" in err


def test_cli_markdown(fx, run):
    _, out, _ = run(fx["rev1.3dm"], fx["rev2.3dm"])
    assert out.startswith("Objects: 1 added, 1 removed, 2 changed, 1 unchanged. 2 layer changes; "
                          "document settings changed; document text changed.")
    assert "geometry (bounding-box centre moved 500 millimeters, same size)" in out
    assert "user text fire_rating: 30 \u2192 60" in out
    assert "| removed | A-ANNO |" in out


def test_cli_json(fx, run, tmp_path):
    out_path = tmp_path / "d.json"
    code, out, _ = run(fx["rev1.3dm"], fx["rev2.3dm"], "--format", "json", "--output", out_path)
    assert code == 1 and out == ""
    doc = json.loads(out_path.read_text())
    assert doc["identical"] is False
    assert doc["summary"]["objects_changed"] == 2
    slab = next(c for c in doc["objects"]["changed"] if c["id"] == str(mf.O_SLAB))
    assert slab["bbox_centre_moved_by"] == pytest.approx(500.0)
    assert doc["settings"]["absolute_tolerance"] == {"old": 0.01, "new": 0.001}


def test_textconv_is_stable_and_sorted(fx, run):
    a = run("--textconv", fx["rev1.3dm"])[1]
    b = run("--textconv", fx["rev1_copy.3dm"])[1]
    assert a == b
    lines = a.splitlines()
    assert lines[0] == "units: millimeters"
    objs = [l for l in lines if l.startswith("object ")]
    assert objs == sorted(objs, key=lambda l: (l.split()[1], l.split()[2], l.split()[3]))
    assert "name=D1 fire_rating=30" in a


def test_textconv_shows_changes_as_line_diff(fx, run):
    import difflib
    a = run("--textconv", fx["rev1.3dm"])[1].splitlines()
    b = run("--textconv", fx["rev2.3dm"])[1].splitlines()
    changed = [l for l in difflib.unified_diff(a, b, lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    assert any(l.startswith("-object A-WALL LineCurve") for l in changed)
    assert any("name=C1" in l and l.startswith("+") for l in changed)


def test_large_model_is_fast(tmp_path):
    import time
    m = r.File3dm()
    lay = r.Layer(); lay.Name = "A"; li = mf.add_layer(m, lay)
    for i in range(2000):
        a = r.ObjectAttributes(); a.LayerIndex = li; mf.set_object_id(a, uuid.UUID(int=i + 1))
        m.Objects.AddBrep(mf._box(i * 20, 0, 0, 10, 10, 10), a)
    p = tmp_path / "big.3dm"
    mf.write_model(m, p)
    t = time.perf_counter()
    d = diff_snapshots(load_snapshot(str(p)), load_snapshot(str(p)))
    assert d.is_empty and d.unchanged_objects == 2000
    assert time.perf_counter() - t < 30
