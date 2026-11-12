import pytest

from inspect3dm import ProfileError, load_profile


def test_builtin_profiles():
    d, s = load_profile("default"), load_profile("strict")
    assert d.name == "default" and s.name == "strict"
    assert d.rules["mesh"]["enabled"] is False
    assert s.rules["mesh"]["enabled"] is True
    assert d.rules["document"]["absolute_tolerance_min"] == 0.0001
    assert d.rules["document"]["absolute_tolerance_max"] == 0.01
    assert s.rules["layers"]["flag_objects_on_default_layer"] is True


def test_example_office_profile_loads(office_profile):
    p = load_profile(str(office_profile))
    assert p.name == "example-office"
    assert p.rules["validity"]["severity"] == "error"  # inherited
    assert p.rules["document"]["allowed_units"] == ["millimeters", "meters"]


@pytest.mark.parametrize(
    "text, needle",
    [
        ("[rules.validity\n", "is not valid TOML"),
        ("[rules.colour]\nenabled = true\n", "unknown section [rules.colour]"),
        ("[rules.layers]\nflag_empty = true\n", "unknown key 'flag_empty' in [rules.layers]"),
        ('[rules.validity]\nseverity = "fatal"\n', 'severity must be "error" or "warning"'),
        ('[rules.layers]\nname_pattern = "[A-"\n', "name_pattern is not a valid regular expression"),
        ("[rules.document]\nabsolute_tolerance_min = 0.1\nabsolute_tolerance_max = 0.01\n",
         "absolute_tolerance_min (0.1) is greater than absolute_tolerance_max (0.01)"),
        ('[rules.document]\nallowed_units = ["furlongs"]\n', "unknown unit 'furlongs'"),
        ("[rules.mesh]\nenabled = \"yes\"\n", "enabled must be true or false"),
        ("[rules.document]\nabsolute_tolerance_min = true\n", "must be a number"),
        ('[profile]\nextends = "lenient"\n', "is not a built-in profile"),
        ("rules = 3\n", "'rules' must be a set of"),
        ("colour = 1\n", "unknown top-level key 'colour'"),
    ],
)
def test_invalid_profiles_give_specific_errors(tmp_path, text, needle):
    p = tmp_path / "bad.toml"
    p.write_text(text)
    with pytest.raises(ProfileError) as exc:
        load_profile(str(p))
    assert needle in str(exc.value)
    assert "Traceback" not in str(exc.value)


def test_missing_profile_file(tmp_path):
    with pytest.raises(ProfileError, match="was not found"):
        load_profile(str(tmp_path / "nope.toml"))


def test_invalid_profile_exits_2_via_cli(fx, tmp_path, run_cli):
    p = tmp_path / "bad.toml"
    p.write_text('[rules.validity]\nseverity = "fatal"\n')
    code, out, err = run_cli(fx["clean.3dm"], "--profile", p)
    assert code == 2 and out == ""
    assert "severity must be" in err and "Traceback" not in err
