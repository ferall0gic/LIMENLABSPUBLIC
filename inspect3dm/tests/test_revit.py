"""v0.2 'revit' profile: short edges, extents, unit-aware tolerance.

All fixtures are synthetic models written by scripts/make_fixtures.py with
rhino3dm. These tests check what inspect3dm reports about a file; they do not
(and cannot) verify how Rhino or Revit would behave with that file.
"""

import json
import math

import pytest
import make_fixtures
import rhino3dm as r

from inspect3dm import inspect_file, load_profile
from inspect3dm.geometry_metrics import control_polygon_length, curve_length_bounds
from inspect3dm.profile import BUILTIN_PROFILES, ProfileError
from inspect3dm.units import mm_per_unit

REVIT = load_profile("revit")
V02_RULES = {"short_edges", "short_edges_unmeasured", "extents", "mm_rules_skipped", "tolerance_range", "units"}


def findings(fx, name, profile=REVIT):
    return inspect_file(str(fx[name]), profile).findings


def by_rule(fs, rule):
    return [f for f in fs if f.rule == rule]


# --- profile ------------------------------------------------------------------------

def test_revit_is_builtin_and_listed(run_cli):
    assert "revit" in BUILTIN_PROFILES
    code, out, _ = run_cli("--list-profiles")
    assert code == 0
    assert [line.split(":")[0] for line in out.splitlines()] == ["default", "strict", "revit"]


def test_revit_profile_values():
    rules = REVIT.rules
    assert rules["short_edges"]["enabled"] and rules["short_edges"]["min_length_mm"] == pytest.approx(0.79375)
    assert rules["extents"]["max_distance_from_origin_mm"] == pytest.approx(10 * 1609.344 * 1000)
    assert rules["extents"]["max_total_extent_mm"] == pytest.approx(20 * 1609.344 * 1000)
    assert rules["document"]["severity"] == "error"
    assert rules["document"]["tolerance_severity"] == "warning"
    assert rules["validity"]["severity"] == "error"


def test_default_and_strict_leave_new_rules_off():
    for name in ("default", "strict"):
        p = load_profile(name)
        assert not p.rules["short_edges"]["enabled"]
        assert not p.rules["extents"]["enabled"]


def test_office_profile_can_extend_revit(tmp_path, fx):
    p = tmp_path / "office-revit.toml"
    p.write_text('[profile]\nextends = "revit"\n[rules.short_edges]\nmin_length_mm = 0.4\n')
    prof = load_profile(str(p))
    assert prof.rules["short_edges"]["min_length_mm"] == 0.4
    assert prof.rules["extents"]["enabled"]  # inherited from revit
    # 0.5 mm edges now pass the lowered minimum and are outside the 10% band.
    assert by_rule(findings(fx, "revit_short_edge_mm.3dm", prof), "short_edges") == []


@pytest.mark.parametrize("text, needle", [
    ("[rules.short_edges]\nmin_length_mm = -1\n", "must not be negative"),
    ("[rules.short_edges]\nmin_length = 1\n", "unknown key 'min_length'"),
    ('[rules.document]\ntolerance_severity = "info"\n', 'tolerance_severity must be "error" or "warning"'),
    ("[rules.document]\nabsolute_tolerance_min_mm = 1\nabsolute_tolerance_max_mm = 0.1\n",
     "absolute_tolerance_min_mm (1) is greater than absolute_tolerance_max_mm (0.1)"),
    ("[rules.extents]\nmax_total_extent_mm = true\n", "must be a number"),
])
def test_invalid_v02_keys(tmp_path, text, needle):
    p = tmp_path / "bad.toml"
    p.write_text(text)
    with pytest.raises(ProfileError) as exc:
        load_profile(str(p))
    assert needle in str(exc.value)


# --- units ----------------------------------------------------------------------------

@pytest.mark.parametrize("unit, mm", [
    ("millimeters", 1.0), ("meters", 1000.0), ("centimeters", 10.0), ("inches", 25.4),
    ("feet", 304.8), ("miles", 1609344.0), ("kilometers", 1e6),
])
def test_mm_per_unit(unit, mm):
    assert mm_per_unit(unit) == pytest.approx(mm)


@pytest.mark.parametrize("unit", ["none", "unset", "custom units", None])
def test_mm_per_unit_unknown(unit):
    assert mm_per_unit(unit) is None


# --- length bounds -----------------------------------------------------------------------

def test_bounds_line_exact():
    lo, hi = curve_length_bounds(r.LineCurve(r.Point3d(0, 0, 0), r.Point3d(3, 4, 0)))
    assert lo == pytest.approx(5.0) and hi == pytest.approx(5.0)


@pytest.mark.parametrize("radius, angle", [(1.0, math.pi / 2), (2.5, math.pi), (0.4, 2 * math.pi)])
def test_bounds_arc_bracket_analytic(radius, angle):
    crv = r.Arc(r.Circle(radius), angle).ToNurbsCurve()
    lo, hi = curve_length_bounds(crv)
    true = radius * angle
    assert lo <= true + 1e-12 <= hi + 1e-12
    assert lo == pytest.approx(true, rel=2e-3)  # 16+ samples per span


def test_bounds_degree3_nurbs():
    pts = [r.Point3d(0, 0, 0), r.Point3d(1, 2, 0), r.Point3d(3, -1, 1), r.Point3d(4, 1, 0), r.Point3d(6, 0, 0)]
    crv = r.NurbsCurve.Create(False, 3, pts)
    lo, hi = curve_length_bounds(crv)
    fine, _ = curve_length_bounds(crv, refine=64)
    assert lo <= fine <= hi
    poly = sum(pts[i].DistanceTo(pts[i + 1]) for i in range(len(pts) - 1))
    assert hi == pytest.approx(poly)


def test_control_polygon_uses_euclidean_points_for_rational_curves():
    # Quarter circle: control points (1,0), (1,1), (0,1) -> polygon length 2.
    crv = r.Arc(r.Circle(1.0), math.pi / 2).ToNurbsCurve()
    assert crv.IsRational
    assert control_polygon_length(crv) == pytest.approx(2.0)


# --- fixtures: exact expected findings --------------------------------------------------

def test_clean_box_has_no_findings(fx):
    assert findings(fx, "revit_clean.3dm") == []


def test_unitless_is_error_and_mm_rules_say_skipped(fx):
    fs = findings(fx, "revit_unitless.3dm")
    assert [(f.severity, f.rule) for f in fs] == [("error", "units"), ("warning", "mm_rules_skipped")]
    assert "short_edges and extents could not be checked" in fs[1].message


def test_short_brep_edges_mm(fx):
    fs = findings(fx, "revit_short_edge_mm.3dm")
    short = by_rule(fs, "short_edges")
    assert len(fs) == len(short) == 4
    for f in short:
        assert f.severity == "error" and f.certainty == "certain"
        assert f.measured == pytest.approx(0.5, rel=0.01) and f.units == "millimeters"
        assert f.threshold == pytest.approx(0.79375)
        assert "0.5 millimeters long, shorter than the minimum of 0.79375 mm" in f.message


def test_near_threshold_edges_warn(fx):
    fs = findings(fx, "revit_near_edge_mm.3dm")
    assert len(fs) == 4
    for f in fs:
        assert (f.severity, f.rule, f.certainty) == ("warning", "short_edges", "near_threshold")
        assert f.measured == pytest.approx(0.8, rel=0.01)


def test_short_loose_curve_in_meters(fx):
    fs = findings(fx, "revit_short_curve_m.3dm")
    assert len(fs) == 1
    f = fs[0]
    assert (f.severity, f.rule, f.object_type, f.units) == ("error", "short_edges", "LineCurve", "meters")
    assert f.measured * 1000 == pytest.approx(0.5, rel=0.01)
    assert "0.0005 meters (0.5 mm)" in f.message


def test_include_curves_false_skips_loose_curves(fx, tmp_path):
    p = tmp_path / "no-curves.toml"
    p.write_text('[profile]\nextends = "revit"\n[rules.short_edges]\ninclude_curves = false\n')
    assert findings(fx, "revit_short_curve_m.3dm", load_profile(str(p))) == []


def test_short_polyline_segment(fx):
    fs = findings(fx, "revit_short_polyline_segment.3dm")
    assert len(fs) == 1 and fs[0].rule == "short_edges"
    assert fs[0].message.startswith("Segment 1 is 0.3 millimeters long")


def test_short_extrusion_edge_via_brep_form(fx):
    fs = findings(fx, "revit_short_extrusion.3dm")
    assert len(fs) == 1
    assert (fs[0].rule, fs[0].object_type) == ("short_edges", "Extrusion")
    assert fs[0].measured == pytest.approx(0.5, rel=0.01)


def test_far_object(fx):
    fs = findings(fx, "revit_far.3dm")
    assert len(fs) == 1
    f = fs[0]
    assert (f.severity, f.rule, f.object_type) == ("warning", "extents", "Brep")
    assert f.measured / 1e6 == pytest.approx(20.0, rel=0.01)  # km
    assert "beyond the limit of 16.09 km" in f.message


def test_model_span(fx):
    fs = findings(fx, "revit_span.3dm")
    assert len(fs) == 1
    f = fs[0]
    assert (f.rule, f.object_type, f.object_id) == ("extents", "Model", None)
    assert f.measured / 1e6 == pytest.approx(42.43, rel=0.01)


def test_tolerance_above_tenth_of_short_curve(fx):
    fs = findings(fx, "revit_tolerance.3dm")
    assert [(f.severity, f.rule) for f in fs] == [("warning", "tolerance_range")]
    assert "above the configured maximum of 0.079375 millimeters" in fs[0].message


@pytest.mark.skipif(not make_fixtures.CAN_SET_UNITS, reason=make_fixtures.NEEDS_UNIT_SETTER)
def test_mm_tolerance_converts_for_meter_files(tmp_path):
    m = r.File3dm()
    m.Settings.ModelUnitSystem = r.UnitSystem.Meters
    m.Settings.ModelAbsoluteTolerance = 0.001  # 1 mm
    path = tmp_path / "m.3dm"
    make_fixtures.write_model(m, path)
    fs = inspect_file(str(path), REVIT).findings
    tol = by_rule(fs, "tolerance_range")
    assert len(tol) == 1
    assert "0.000079375 meters (0.079375 mm)" in tol[0].message


def test_mm_keys_do_not_change_default_profile(fx):
    for name in ("clean.3dm", "tolerance_low.3dm", "tolerance_high.3dm", "invalid_object.3dm"):
        fs = findings(fx, name, load_profile("default"))
        assert not any(f.rule in ("short_edges", "extents", "mm_rules_skipped") for f in fs)
        assert all(f.measured is None for f in fs)


def test_v01_fixtures_never_crash_under_revit(fx):
    for name, path in fx.items():
        res = inspect_file(str(path), REVIT)
        assert res.status in ("pass", "fail"), name


def test_unmeasurable_edge_reported_not_swallowed(monkeypatch, fx):
    import inspect3dm.inspector as insp

    def boom(curve, refine=1):
        raise ValueError("synthetic")

    monkeypatch.setattr(insp, "curve_length_bounds", boom)
    fs = findings(fx, "revit_clean.3dm")
    assert len(fs) == 12 and {f.rule for f in fs} == {"short_edges_unmeasured"}
    assert "could not be measured (ValueError)" in fs[0].message


def test_uncertain_bounds_are_labelled(monkeypatch, fx):
    import inspect3dm.inspector as insp
    monkeypatch.setattr(insp, "curve_length_bounds", lambda c, refine=1: (0.7, 0.9))
    fs = findings(fx, "revit_short_curve_m.3dm")  # in a meters file, 0.7-0.9 m is far above the minimum
    assert fs == []
    fs = findings(fx, "revit_short_polyline_segment.3dm")
    assert {f.certainty for f in fs} == {"uncertain"}
    assert "may be shorter than the minimum" in fs[0].message


# --- CLI / JSON --------------------------------------------------------------------------

def test_cli_revit_json_fields(fx, run_cli):
    code, out, _ = run_cli(fx["revit_short_edge_mm.3dm"], "--profile", "revit", "--format", "json")
    assert code == 1
    doc = json.loads(out)
    assert doc["profile"] == "revit"
    f = doc["files"][0]
    assert f["next_steps"] == ["ShowEdges", "MergeAllEdges", "RebuildEdges"]
    finding = f["findings"][0]
    assert finding["rule"] == "short_edges"
    assert {"measured", "threshold", "units", "certainty"} <= set(finding)


def test_cli_v01_json_finding_shape_unchanged(fx, run_cli):
    _, out, _ = run_cli(fx["invalid_object.3dm"], "--format", "json")
    finding = json.loads(out)["files"][0]["findings"][0]
    assert set(finding) == {"severity", "rule", "object_id", "object_type", "layer", "message"}


def test_cli_revit_far_passes_on_error_fails_on_warning(fx, run_cli):
    assert run_cli(fx["revit_far.3dm"], "--profile", "revit")[0] == 0
    assert run_cli(fx["revit_far.3dm"], "--profile", "revit", "--fail-on", "warning")[0] == 1
