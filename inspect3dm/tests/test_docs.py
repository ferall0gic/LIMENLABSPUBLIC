"""The README is part of the interface: keep it true."""

from pathlib import Path

import pytest
import rhino3dm

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")

SPEC_README_DISCLAIMER = (
    "Validity results come from McNeel's openNURBS library (via rhino3dm). They may differ from "
    "Rhino's Check command. This tool reports problems; it does not repair models, and it is not a "
    "substitute for Check, SelBadObjects, or your own review."
)


def test_readme_first_screen_has_purpose_then_disclaimer():
    paras = [p for p in README.split("\n\n") if p.strip()]
    # title, purpose, disclaimer
    assert paras[0].startswith("# 3dm-inspect")
    assert paras[1].startswith("`3dm-inspect` checks Rhino `.3dm` files")
    assert paras[2] == SPEC_README_DISCLAIMER


def test_readme_documents_exit_codes_footer_and_install():
    assert "### Exit codes" in README
    for code in ("| 0 |", "| 1 |", "| 2 |"):
        assert code in README
    assert README.rstrip().endswith(
        "Validity is checked with openNURBS (via rhino3dm) and may differ from Rhino's Check command. "
        "This report does not repair models and is not a substitute for Check or for your own review.")
    assert "Python 3.10–3.14" in README and "Windows, macOS, or Linux" in README
    assert "pip install inspect3dm" not in README  # no public index install
    assert "git clone https://github.com/ferall0gic/LIMENLABSPUBLIC.git" in README
    assert "python -m pip install ./inspect3dm" in README
    assert 'python -m pip install -e "./inspect3dm[test]"' in README
    assert "There is no PyPI or Food4Rhino listing" in README
    # No LIMEN wordmark in the tool description, sample report, or help.
    # The public repository URL and checkout directory necessarily contain
    # "LIMEN"; a short Labs Public attribution is allowed in the license section.
    before_install, _, rest = README.partition("## Install")
    assert "LIMEN" not in before_install
    install_body, _, tail = rest.partition("## Report issues and license")
    stripped = install_body.replace(
        "https://github.com/ferall0gic/LIMENLABSPUBLIC.git", ""
    ).replace("LIMENLABSPUBLIC", "")
    assert "LIMEN" not in stripped
    assert "LIMEN Labs Public" in tail


def test_license_file_is_mit():
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text
    assert "Copyright (c) 2026 Sydney DeVille" in license_text
    assert not (ROOT / "PRIVATE-STAGING.md").exists()


def test_readme_documents_known_limitations():
    assert "v0.2 has been run and tested on Linux only" in README
    assert "it has not been checked against imports in Revit" in README
    assert "Windows and macOS should install via `rhino3dm` wheels but are untested" in README
    assert "Large (5–10 GB) files are untested" in README
    assert "Parity has not been tested on a Rhino host" in README
    assert "not a finished product" in README


def test_readme_documents_run_result_words():
    for word in ("pass", "fail", "report", "incomplete"):
        assert f"`{word}`" in README
    assert "Result: report only." in README
    assert "Result: incomplete." in README


@pytest.mark.skipif(not rhino3dm.__version__.startswith("8."),
                    reason="README sample output was recorded with rhino3dm 8")
def test_readme_sample_output_matches_real_run(run_cli, monkeypatch):
    monkeypatch.chdir(ROOT)
    code, out, _ = run_cli("samples/sample.3dm")
    assert code == 1
    assert out.rstrip("\n") in README


def test_readme_revit_section_is_honest_about_sources():
    section = README.split("## Checking files for Revit", 1)[1].split("\n## ", 1)[0]
    assert "the 1/32 in figure comes from Autodesk forum posts and a developer blog" in section
    assert "It has not been run against Revit" in section
    assert "About the Maximum Distance Limit" in section
    assert "guarantee" not in section.lower()


def test_changelog_has_current_version():
    from inspect3dm import __version__
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {__version__} " in changelog
