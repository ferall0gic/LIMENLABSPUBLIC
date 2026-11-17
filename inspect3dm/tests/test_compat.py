"""Tests for the rhino3dm 8.x / 9.x compatibility helpers, using fakes for both API shapes."""

from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from inspect3dm import _rh

ROOT = Path(__file__).resolve().parents[1]
SIBLING = ROOT.parent / "3dm-diff" / "src" / "diff3dm" / "_rh.py"


def test_rh_copies_are_identical():
    if not SIBLING.exists():
        pytest.skip("sibling tool not checked out next to this one")
    assert (ROOT / "src" / "inspect3dm" / "_rh.py").read_bytes() == SIBLING.read_bytes()


def test_object_id_both_shapes():
    assert _rh.object_id(NS(Id="a")) == "a"                 # 8.x
    assert _rh.object_id(NS(ObjectId="b")) == "b"           # 9.x


def test_layer_flags_both_shapes():
    assert _rh.layer_visible(NS(Visible=False)) is False and _rh.layer_locked(NS(Locked=True)) is True
    assert _rh.layer_visible(NS(IsVisible=True)) is True and _rh.layer_locked(NS(IsLocked=False)) is False


def test_validity_property_and_method():
    assert _rh.validity(NS(IsValidWithLog=(False, "bad trim"))) == (False, "bad trim")   # 8.x property
    assert _rh.validity(NS(IsValidWithLog=lambda: (False, "bad trim"))) == (False, "bad trim")  # 9.x method
    assert _rh.validity(NS(IsValidWithLog=(True, None))) == (True, "")


def test_validity_does_not_swallow_real_errors():
    def boom():
        raise RuntimeError("native failure")
    with pytest.raises(RuntimeError):
        _rh.validity(NS(IsValidWithLog=boom))


class _Geom8:
    def GetBoundingBox(self, *args):
        if args:
            raise TypeError("incompatible function arguments")  # rhino3dm#721
        return "bb8"


class _Geom9:
    def GetBoundingBox(self, accurate):
        return "bb9" if accurate else "loose"


def test_bbox_both_shapes():
    assert _rh.bbox(_Geom8()) == "bb8"
    assert _rh.bbox(_Geom9()) == "bb9"


def test_bbox_raises_when_neither_form_works():
    class G:
        def GetBoundingBox(self, accurate):
            raise ValueError("no box")
    with pytest.raises(ValueError):
        _rh.bbox(G())


def test_control_point_both_shapes():
    assert _rh.control_point_xyzw(NS(X=2, Y=2, Z=0, W=2)) == (2, 2, 0, 2)
    assert _rh.control_point_xyzw(NS(X=2, Y=2, Z=0, Weight=2)) == (2, 2, 0, 2)


def test_read_model_missing_file_is_none_on_both():
    def raises(path):
        raise FileNotFoundError(path)
    assert _rh.read_model(NS(File3dm=NS(Read=lambda p: None)), "x.3dm") is None
    assert _rh.read_model(NS(File3dm=NS(Read=raises)), "x.3dm") is None


def test_document_strings_both_shapes():
    class T9:
        Count = 2
        def GetKey(self, i): return ["a", "b"][i]
        def GetValue(self, i): return ["1", "2"][i]
    assert _rh.document_strings(NS(Strings=[("a", "1"), ("b", "2")])) == [("a", "1"), ("b", "2")]
    assert _rh.document_strings(NS(Strings=T9())) == [("a", "1"), ("b", "2")]



# ---- silent-skip regressions: a check that cannot run must say so (tool_error, info)

def _row(geom):
    return (None, geom, "id-1", type(geom).__name__, 0, "L")


def test_validity_failure_is_reported_not_skipped():
    from inspect3dm.inspector import _check_validity

    class Broken:
        @property
        def IsValidWithLog(self):
            raise RuntimeError("cannot evaluate")
    out = _check_validity([_row(Broken())], {"severity": "error"})
    assert [(f.severity, f.rule) for f in out] == [("info", "tool_error")]
    assert "validity" in out[0].message and "RuntimeError" in out[0].message


def test_validity_log_survives_method_shape():
    from inspect3dm.inspector import _check_validity
    out = _check_validity([_row(NS(IsValidWithLog=lambda: (False, "Brep trim is bad")))], {"severity": "error"})
    assert [(f.rule, f.message) for f in out] == [("validity", "Brep trim is bad")]


def test_bbox_failure_is_reported_not_skipped():
    from inspect3dm.inspector import _check_extents

    class NoBox:
        def GetBoundingBox(self, *a):
            raise RuntimeError("no box")
    out = _check_extents([_row(NoBox())], {"severity": "warning"}, 1.0, "millimeters")
    assert [(f.severity, f.rule) for f in out] == [("info", "tool_error")]


def test_info_findings_never_fail_or_count():
    from inspect3dm.inspector import FileResult, Finding
    f = FileResult(path="x", findings=[Finding("info", "tool_error", "m")])
    assert f.errors == 0 and f.warnings == 0
    assert not f.meets("error") and not f.meets("warning")
