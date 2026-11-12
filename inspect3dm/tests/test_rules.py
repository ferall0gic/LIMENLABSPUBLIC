"""Every rule has at least one passing and one failing fixture."""

import shutil

import pytest

from inspect3dm import inspect_file, load_profile
from inspect3dm.inspector import max_faces_per_edge

import make_fixtures as mf


def rules_of(result):
    return [f.rule for f in result.findings]


@pytest.fixture(scope="module")
def default():
    return load_profile("default")


@pytest.fixture(scope="module")
def strict():
    return load_profile("strict")


@pytest.fixture(scope="module")
def office(request):
    from pathlib import Path
    return load_profile(str(Path(__file__).resolve().parents[1] / "examples" / "office-profile.toml"))


def test_clean_passes_every_builtin_and_office_profile(fx, default, strict, office):
    for profile in (default, strict, office):
        res = inspect_file(str(fx["clean.3dm"]), profile)
        assert res.status == "pass", (profile.name, res.findings)
        assert res.findings == []


# --- validity -------------------------------------------------------------

def test_validity_fails_on_zero_length_line(fx, default):
    res = inspect_file(str(fx["invalid_object.3dm"]), default)
    assert res.status == "fail"
    (f,) = [f for f in res.findings if f.rule == "validity"]
    assert f.severity == "error"
    assert f.message == "Line points are coincident."
    assert f.object_type == "LineCurve"
    assert f.layer == "A-WALL"
    assert len(f.object_id) == 36
    assert res.next_steps == ["Check", "SelBadObjects"]


def test_validity_passes_valid_objects(fx, default):
    res = inspect_file(str(fx["clean.3dm"]), default)
    assert "validity" not in rules_of(res)
    assert res.object_count == 3


# --- document settings ------------------------------------------------------

def test_tolerance_below_minimum_message_in_model_units(fx, default):
    res = inspect_file(str(fx["tolerance_low.3dm"]), default)
    (f,) = res.findings
    assert (f.rule, f.severity) == ("tolerance_range", "warning")
    assert f.message == ("Absolute tolerance 0.0000001 meters is below the configured minimum "
                         "of 0.0001 meters.")
    assert res.status == "pass"  # warnings do not fail by default


def test_tolerance_above_maximum(fx, default):
    res = inspect_file(str(fx["tolerance_high.3dm"]), default)
    (f,) = res.findings
    assert f.rule == "tolerance_range"
    assert "0.5 millimeters is above the configured maximum of 0.01 millimeters" in f.message


def test_tolerance_in_range_passes(fx, default):
    assert "tolerance_range" not in rules_of(inspect_file(str(fx["clean.3dm"]), default))


def test_units_none_warns(fx, default):
    res = inspect_file(str(fx["no_units.3dm"]), default)
    assert rules_of(res) == ["units"]
    assert res.units == "none"


def test_units_not_allowed_by_office_profile(fx, office):
    res = inspect_file(str(fx["tolerance_low.3dm"]), office)  # meters is allowed
    assert "units" not in rules_of(res)
    m = mf.clean_model()
    import rhino3dm
    m.Settings.ModelUnitSystem = rhino3dm.UnitSystem.Inches
    p = fx["clean.3dm"].parent / "inches.3dm"
    mf.write(m, p)
    res = inspect_file(str(p), office)
    (f,) = [f for f in res.findings if f.rule == "units"]
    assert f.message == "Model units are inches; this profile allows millimeters, meters."


def test_angle_tolerance_range_in_degrees(fx, office):
    res = inspect_file(str(fx["wide_angle.3dm"]), office)
    (f,) = [f for f in res.findings if f.rule == "angle_tolerance_range"]
    assert f.message == "Angle tolerance 10 degrees is above the configured maximum of 2 degrees."
    assert "rad" not in f.message
    assert res.angle_tolerance_degrees == pytest.approx(10.0)


def test_angle_tolerance_in_range_passes(fx, office):
    assert "angle_tolerance_range" not in rules_of(inspect_file(str(fx["clean.3dm"]), office))


# --- mesh -------------------------------------------------------------------

def test_mesh_rules_off_in_default_profile(fx, default):
    res = inspect_file(str(fx["mesh_nonmanifold.3dm"]), default)
    assert not any(r.startswith("mesh_") for r in rules_of(res))


def test_mesh_not_closed_in_strict(fx, strict):
    res = inspect_file(str(fx["mesh_open.3dm"]), strict)
    assert rules_of(res) == ["mesh_not_closed"]  # an open triangle is still manifold
    assert res.findings[0].severity == "error"
    assert res.next_steps == ["CheckMesh", "MeshRepair"]


def test_mesh_non_manifold_in_strict(fx, strict):
    res = inspect_file(str(fx["mesh_nonmanifold.3dm"]), strict)
    assert sorted(rules_of(res)) == ["mesh_non_manifold", "mesh_not_closed"]


def test_closed_manifold_mesh_passes_strict(fx, strict):
    res = inspect_file(str(fx["clean.3dm"]), strict)
    assert res.findings == []


def test_max_faces_per_edge_topology():
    assert max_faces_per_edge(mf.closed_tetra_mesh()) == 2
    assert max_faces_per_edge(mf.open_triangle_mesh()) == 1
    assert max_faces_per_edge(mf.nonmanifold_fan_mesh()) == 3


def test_mesh_rule_can_disable_one_check(fx, tmp_path):
    p = tmp_path / "p.toml"
    p.write_text('[profile]\nextends = "strict"\n[rules.mesh]\nrequire_closed = false\n')
    res = inspect_file(str(fx["mesh_open.3dm"]), load_profile(str(p)))
    assert res.findings == []


# --- layers -----------------------------------------------------------------

def test_layer_name_pattern_fails(fx, office):
    res = inspect_file(str(fx["bad_layer_name.3dm"]), office)
    (f,) = [f for f in res.findings if f.rule == "layer_name"]
    assert f.layer == "door misc" and f.object_type == "Layer" and f.severity == "warning"


def test_layer_name_pattern_passes(fx, office):
    assert "layer_name" not in rules_of(inspect_file(str(fx["clean.3dm"]), office))


def test_empty_layer_flagged(fx, default):
    res = inspect_file(str(fx["empty_layer.3dm"]), default)
    (f,) = res.findings
    assert (f.rule, f.layer) == ("empty_layer", "A-EMPTY")


def test_parent_of_used_sublayer_is_not_empty(fx, default):
    res = inspect_file(str(fx["nested_layer.3dm"]), default)
    assert res.findings == []


def test_object_without_layer(fx, default):
    res = inspect_file(str(fx["no_layer.3dm"]), default)
    (f,) = res.findings
    assert f.rule == "object_without_layer"
    assert f.layer is None
    assert "layer index -1" in f.message


def test_object_on_default_layer_only_when_enabled(fx, default, strict):
    assert inspect_file(str(fx["default_layer.3dm"]), default).findings == []
    res = inspect_file(str(fx["default_layer.3dm"]), strict)
    (f,) = res.findings
    assert (f.rule, f.layer) == ("object_on_default_layer", "Default")


def test_object_on_named_layer_passes_strict(fx, strict):
    assert "object_on_default_layer" not in rules_of(inspect_file(str(fx["clean.3dm"]), strict))


def test_errors_sorted_before_warnings(fx, tmp_path, default):
    m = mf.invalid_object_model()
    mf._layer(m, "A-EMPTY")
    p = mf.write(m, tmp_path / "mix.3dm")
    sev = [f.severity for f in inspect_file(str(p), default).findings]
    assert sev == sorted(sev, key=lambda s: s != "error")
    assert sev[0] == "error" and "warning" in sev


def test_rule_severity_override(fx, tmp_path):
    p = tmp_path / "p.toml"
    p.write_text('[rules.layers]\nseverity = "error"\n')
    res = inspect_file(str(fx["empty_layer.3dm"]), load_profile(str(p)))
    assert res.findings[0].severity == "error" and res.status == "fail"


def test_rule_can_be_disabled(fx, tmp_path):
    p = tmp_path / "p.toml"
    p.write_text('[rules.validity]\nenabled = false\n')
    assert inspect_file(str(fx["invalid_object.3dm"]), load_profile(str(p))).findings == []
