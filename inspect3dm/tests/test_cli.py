import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from inspect3dm.report import FOOTER

ANSI = re.compile(r"\x1b\[")
EXACT_FOOTER = (
    "Validity is checked with openNURBS (via rhino3dm) and may differ from Rhino's Check command. "
    "This report does not repair models and is not a substitute for Check or for your own review."
)


def _exe():
    """The 3dm-inspect script installed next to this interpreter (falls back to PATH)."""
    return shutil.which("3dm-inspect", path=os.path.dirname(sys.executable)) or shutil.which("3dm-inspect")


def strip_time(doc):
    doc = dict(doc)
    doc.pop("generated_at")
    return doc


@pytest.fixture()
def folder(fx, tmp_path):
    """A folder with a nested subfolder: clean, invalid, warning-only files."""
    d = tmp_path / "exports"
    (d / "sub").mkdir(parents=True)
    shutil.copy(fx["clean.3dm"], d / "a_clean.3dm")
    shutil.copy(fx["invalid_object.3dm"], d / "sub" / "b_invalid.3dm")
    shutil.copy(fx["empty_layer.3dm"], d / "c_warn.3DM")
    (d / "notes.txt").write_text("not a model")
    return d


def test_footer_constant_is_exact():
    assert FOOTER == EXACT_FOOTER


# --- exit codes and fail-on ------------------------------------------------

def test_clean_file_exit_0(fx, run_cli):
    code, out, err = run_cli(fx["clean.3dm"])
    assert code == 0 and err == ""
    assert out.splitlines()[0].startswith("Result: pass. 1 file inspected")


def test_error_finding_exit_1(fx, run_cli):
    code, *_ = run_cli(fx["invalid_object.3dm"])
    assert code == 1


@pytest.mark.parametrize("fail_on, invalid, warn_only", [("error", 1, 0), ("warning", 1, 1), ("never", 0, 0)])
def test_fail_on_levels(fx, run_cli, fail_on, invalid, warn_only):
    assert run_cli(fx["invalid_object.3dm"], "--fail-on", fail_on)[0] == invalid
    assert run_cli(fx["empty_layer.3dm"], "--fail-on", fail_on)[0] == warn_only
    assert run_cli(fx["clean.3dm"], "--fail-on", fail_on)[0] == 0


def test_fail_on_warning_marks_warning_file_as_fail(fx, run_cli):
    code, out, _ = run_cli(fx["empty_layer.3dm"], "--fail-on", "warning", "--format", "json")
    assert code == 1 and json.loads(out)["files"][0]["status"] == "fail"


def test_fail_on_never_still_exits_2_for_unreadable(tmp_path, run_cli):
    bad = tmp_path / "bad.3dm"
    bad.write_bytes(b"definitely not a 3dm file")
    assert run_cli(bad, "--fail-on", "never")[0] == 2


# --- unreadable / corrupt / empty ------------------------------------------

def test_non_3dm_file_is_unreadable_exit_2(tmp_path, run_cli):
    bad = tmp_path / "facade.3dm"
    bad.write_bytes(b"hello, I am a text file")
    code, out, err = run_cli(bad)
    assert code == 2
    assert ("the file is not a valid 3DM (or is truncated). Check the path and that the file opens in Rhino.") in out
    assert "Status: unreadable." in out
    assert "Traceback" not in out + err


def test_truncated_file_is_unreadable(fx, tmp_path, run_cli):
    t = tmp_path / "trunc.3dm"
    t.write_bytes(fx["clean.3dm"].read_bytes()[:400])
    code, out, err = run_cli(t, "--format", "json")
    assert code == 2
    f = json.loads(out)["files"][0]
    assert f["status"] == "unreadable"
    assert f["message"] == (f"Could not read '{t}': the file is not a valid 3DM (or is truncated). "
                            "Check the path and that the file opens in Rhino.")
    assert f"Could not read '{t}'" in err  # also on stderr for JSON/CI


def test_zero_byte_file_is_unreadable(tmp_path, run_cli):
    e = tmp_path / "empty.3dm"
    e.write_bytes(b"")
    code, out, _ = run_cli(e)
    assert code == 2 and "the file is empty (0 bytes)" in out


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="permission bits are not enforced for root/Windows")
def test_permission_denied_is_unreadable(fx, tmp_path, run_cli):
    p = tmp_path / "locked.3dm"
    shutil.copy(fx["clean.3dm"], p)
    p.chmod(0)
    try:
        code, out, _ = run_cli(p)
    finally:
        p.chmod(0o644)
    assert code == 2 and "permission denied" in out


def test_empty_folder_exit_2_exact_message(tmp_path, run_cli, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "exports").mkdir()
    (tmp_path / "exports" / "readme.txt").write_text("x")
    for arg in ("exports", "exports/"):
        code, out, err = run_cli(arg)
        assert code == 2 and out == ""
        assert err == "No .3dm files found in 'exports/'. Check the path, or pass a .3dm file directly.\n"


def test_missing_path_exit_2(tmp_path, run_cli):
    code, _, err = run_cli(tmp_path / "nowhere.3dm")
    assert code == 2 and "does not exist" in err


def test_folder_continues_after_unreadable(folder, run_cli):
    (folder / "broken.3dm").write_bytes(b"junk")
    code, out, _ = run_cli(folder, "--format", "json")
    doc = json.loads(out)
    assert code == 2
    statuses = {Path(f["path"]).name: f["status"] for f in doc["files"]}
    assert statuses == {"a_clean.3dm": "pass", "broken.3dm": "unreadable",
                        "c_warn.3DM": "pass", "b_invalid.3dm": "fail"}
    assert doc["summary"]["files_unreadable"] == 1
    assert doc["summary"]["exit_code"] == 2
    assert doc["summary"]["result"] == "incomplete"


def test_folder_is_recursive_and_case_insensitive(folder, run_cli):
    code, out, _ = run_cli(folder, "--format", "json")
    names = [Path(f["path"]).name for f in json.loads(out)["files"]]
    assert names == ["a_clean.3dm", "c_warn.3DM", "b_invalid.3dm"]  # sorted per folder level
    assert code == 1


# --- file status vocabulary --------------------------------------------------

def test_file_status_values_only_pass_fail_unreadable(folder, run_cli):
    (folder / "broken.3dm").write_bytes(b"junk")
    for fail_on in ("error", "warning", "never"):
        _, out, _ = run_cli(folder, "--format", "json", "--fail-on", fail_on)
        doc = json.loads(out)
        assert {f["status"] for f in doc["files"]} <= {"pass", "fail", "unreadable"}
        for f in doc["files"]:
            for finding in f.get("findings", []):
                assert finding["severity"] in ("error", "warning")


# --- format / output -----------------------------------------------------------

def test_default_format_is_markdown_even_when_not_tty(fx, run_cli):
    _, out, _ = run_cli(fx["clean.3dm"])
    assert out.startswith("Result: ")
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)


def test_format_inferred_from_output_extension(fx, tmp_path, run_cli):
    j, m = tmp_path / "r.json", tmp_path / "r.md"
    assert run_cli(fx["clean.3dm"], "--output", j)[0] == 0
    assert json.loads(j.read_text())["tool"] == "3dm-inspect"
    assert run_cli(fx["clean.3dm"], "--output", m)[0] == 0
    assert m.read_text().startswith("Result: pass.")


@pytest.mark.parametrize("fmt, name", [("json", "r.md"), ("md", "r.json")])
def test_format_output_disagreement_exit_2(fx, tmp_path, run_cli, fmt, name):
    code, out, err = run_cli(fx["clean.3dm"], "--format", fmt, "--output", tmp_path / name)
    assert code == 2 and out == ""
    assert "does not match" in err and "See 3dm-inspect --help." in err
    assert not (tmp_path / name).exists()


def test_unknown_option_message(fx, run_cli):
    code, out, err = run_cli(fx["clean.3dm"], "--profle", "x.toml")
    assert code == 2
    assert err == "Unknown option '--profle'. See 3dm-inspect --help.\n"


def test_bad_choice_and_missing_path(fx, run_cli):
    code, _, err = run_cli(fx["clean.3dm"], "--format", "html")
    assert code == 2 and err == "--format must be md or json. See 3dm-inspect --help.\n"
    code, _, err = run_cli()
    assert code == 2 and "No path given" in err


# --- JSON shape and reproducibility -----------------------------------------------

def test_json_fields(fx, run_cli):
    code, out, _ = run_cli(fx["invalid_object.3dm"], "--format", "json")
    doc = json.loads(out)
    assert doc["tool"] == "3dm-inspect"
    assert doc["tool_version"] == "0.2.0"
    assert doc["rhino3dm_version"].startswith("8.")
    assert doc["validation_basis"] == "openNURBS via rhino3dm; may differ from Rhino Check"
    assert doc["profile"] == "default"
    f = doc["files"][0]
    assert f["next_steps"] == ["Check", "SelBadObjects"]
    assert f["angle_tolerance_display"] == "1 degree"
    assert f["absolute_tolerance_display"] == "0.001 millimeters"
    assert set(f["findings"][0]) == {"severity", "rule", "object_id", "object_type", "layer", "message"}


def test_next_steps_omitted_when_empty(fx, run_cli):
    _, out, _ = run_cli(fx["empty_layer.3dm"], "--format", "json")
    assert "next_steps" not in json.loads(out)["files"][0]
    _, md, _ = run_cli(fx["empty_layer.3dm"])
    assert "Next steps in Rhino" not in md


def test_json_reproducible(folder, run_cli):
    a = strip_time(json.loads(run_cli(folder, "--format", "json", "--profile", "strict")[1]))
    b = strip_time(json.loads(run_cli(folder, "--format", "json", "--profile", "strict")[1]))
    assert a == b


def test_json_reproducible_across_processes(folder):
    exe = _exe()
    assert exe, "3dm-inspect is not on PATH; run pip install -e ."
    docs = [strip_time(json.loads(subprocess.run([exe, str(folder), "--format", "json"],
                                                 capture_output=True, text=True).stdout)) for _ in range(2)]
    assert docs[0] == docs[1]


# --- Markdown shape -------------------------------------------------------------

def test_single_file_markdown(fx, run_cli):
    _, out, _ = run_cli(fx["tolerance_low.3dm"])
    lines = out.splitlines()
    assert lines[0] == "Result: pass. 1 file inspected (1 pass, 0 fail); 0 errors, 1 warning."
    assert lines[2].startswith("3dm-inspect 0.2.0, rhino3dm 8.")
    assert "## Files" not in out  # no index in single-file mode
    assert "Angle tolerance: 1 degree." in out
    assert "Absolute tolerance: 0.0000001 meters." in out
    assert "| Severity | Rule | Object ID | Type | Layer | Message |" in out
    assert "| Warning | tolerance_range |" in out
    assert out.rstrip().endswith(EXACT_FOOTER)
    assert out.count(EXACT_FOOTER) == 1


def test_folder_markdown_index_before_sections(folder, run_cli):
    _, out, _ = run_cli(folder)
    lines = out.splitlines()
    assert lines[0].startswith("Result: fail. 3 files inspected (2 pass, 1 fail)")
    assert lines[2].startswith("3dm-inspect 0.2.0")
    assert lines[4] == "## Files"
    assert lines[6].startswith("- pass: ") and lines[6].endswith("a_clean.3dm (0 errors, 0 warnings)")
    assert lines[8].startswith("- fail: ") and "b_invalid.3dm" in lines[8]
    first_section = next(i for i, l in enumerate(lines) if l.startswith("## ") and l != "## Files")
    assert first_section > 8
    assert "Next steps in Rhino: Check, SelBadObjects." in out
    assert out.count("Next steps in Rhino") == 1


def test_markdown_has_no_decoration(folder, run_cli):
    _, out, _ = run_cli(folder)
    assert not ANSI.search(out)
    assert "LIMEN" not in out and "<" not in out
    # Em dash (U+2014) is used for empty Markdown table cells; no emoji or box-drawing.
    assert all(ord(c) < 0x2000 or c == "\u2014" for c in out)


def test_pipe_in_message_is_escaped(fx, tmp_path, run_cli):
    p = tmp_path / "p.toml"
    p.write_text("[rules.layers]\nname_pattern = '^(A|S)-'\n")
    _, out, _ = run_cli(fx["bad_layer_name.3dm"], "--profile", p)
    row = next(l for l in out.splitlines() if l.startswith("| Warning | layer_name"))
    assert row.count(" | ") == 5 and "^(A\\|S)-" in row


# --- quiet and color ---------------------------------------------------------------

def test_quiet_single_file(fx, run_cli):
    code, out, _ = run_cli(fx["invalid_object.3dm"], "--quiet")
    assert code == 1
    assert out.count("\n") == 1
    assert out.startswith("fail: ") and out.endswith("(1 error, 0 warnings)\n")
    assert EXACT_FOOTER not in out


def test_quiet_folder(folder, run_cli):
    code, out, _ = run_cli(folder, "--quiet")
    lines = out.splitlines()
    assert code == 1 and len(lines) == 4
    assert lines[-1].startswith("Total: fail. 3 files inspected")
    assert "Total: Result:" not in out
    assert "|" not in out and EXACT_FOOTER not in out


def test_quiet_json_omits_findings(fx, run_cli):
    _, out, _ = run_cli(fx["invalid_object.3dm"], "--quiet", "--format", "json")
    f = json.loads(out)["files"][0]
    assert "findings" not in f and f["summary"]["errors"] == 1


class _Tty:
    def __init__(self):
        self.buf = []

    def write(self, s):
        self.buf.append(s)

    def isatty(self):
        return True

    def flush(self):
        pass


@pytest.fixture()
def tty_run(monkeypatch):
    from inspect3dm.cli import main

    def _run(*args, no_color_env=None):
        monkeypatch.delenv("NO_COLOR", raising=False)
        if no_color_env is not None:
            monkeypatch.setenv("NO_COLOR", no_color_env)
        t = _Tty()
        monkeypatch.setattr(sys, "stdout", t)
        code = main([str(a) for a in args])
        monkeypatch.undo()
        return code, "".join(t.buf)

    return _run


def test_color_on_tty_keeps_words(fx, tty_run):
    code, out = tty_run(fx["invalid_object.3dm"])
    assert ANSI.search(out)
    assert "Error" in ANSI.sub("", out)
    assert re.search(r"\| \x1b\[31mError\x1b\[0m \|", out)


def test_no_color_flag(fx, tty_run):
    _, out = tty_run(fx["invalid_object.3dm"], "--no-color")
    assert not ANSI.search(out) and "| Error |" in out


def test_no_color_env(fx, tty_run):
    _, out = tty_run(fx["invalid_object.3dm"], no_color_env="1")
    assert not ANSI.search(out) and "| Error |" in out


def test_no_color_when_not_tty(fx, run_cli):
    _, out, _ = run_cli(fx["invalid_object.3dm"])
    assert not ANSI.search(out)


# --- run result wording -----------------------------------------------------------

def test_fail_on_never_with_errors_is_report_only(fx, run_cli):
    code, out, _ = run_cli(fx["invalid_object.3dm"], "--fail-on", "never", "--no-color")
    assert code == 0
    assert out.splitlines()[0].startswith("Result: report only.")
    assert "Status: fail." in out
    code, out, _ = run_cli(fx["invalid_object.3dm"], "--fail-on", "never", "--format", "json")
    doc = json.loads(out)
    assert code == 0
    assert doc["summary"]["result"] == "report"
    assert doc["summary"]["exit_code"] == 0
    assert doc["files"][0]["status"] == "fail"


def test_fail_on_never_clean_file_is_pass(fx, run_cli):
    code, out, _ = run_cli(fx["clean.3dm"], "--fail-on", "never")
    assert code == 0
    assert out.splitlines()[0].startswith("Result: pass.")
    _, out, _ = run_cli(fx["clean.3dm"], "--fail-on", "never", "--format", "json")
    assert json.loads(out)["summary"]["result"] == "pass"


def test_fail_on_never_warning_only_is_report_with_file_pass(fx, run_cli):
    code, out, _ = run_cli(fx["empty_layer.3dm"], "--fail-on", "never")
    assert code == 0
    assert out.splitlines()[0].startswith("Result: report only.")
    assert "Status: pass." in out


def test_unreadable_report_is_incomplete(tmp_path, run_cli):
    bad = tmp_path / "facade.3dm"
    bad.write_bytes(b"hello, I am a text file")
    code, out, err = run_cli(bad)
    assert code == 2
    assert out.startswith("Result: incomplete.")
    assert "Status: unreadable." in out
    code, out, err = run_cli(bad, "--format", "json")
    assert code == 2
    assert json.loads(out)["summary"]["result"] == "incomplete"


def test_folder_unreadable_markdown_is_incomplete(folder, run_cli):
    (folder / "broken.3dm").write_bytes(b"junk")
    code, out, _ = run_cli(folder)
    assert code == 2
    assert out.startswith("Result: incomplete.")
    assert "unreadable" in out.splitlines()[0]


def test_quiet_folder_fail_on_never_total_is_report_only(folder, run_cli):
    code, out, _ = run_cli(folder, "--quiet", "--fail-on", "never")
    assert code == 0
    assert out.splitlines()[-1].startswith("Total: report only. 3 files inspected")
    assert "Total: Result:" not in out


def test_output_stderr_uses_result_phrase(fx, tmp_path, run_cli):
    outp = tmp_path / "r.md"
    code, out, err = run_cli(fx["invalid_object.3dm"], "--fail-on", "never", "--output", outp)
    assert code == 0 and out == ""
    assert f"Wrote md report to '{outp}'. report only: exit 0." in err
    assert outp.read_text().startswith("Result: report only.")
    outp = tmp_path / "clean.md"
    code, _, err = run_cli(fx["clean.3dm"], "--output", outp)
    assert code == 0 and "pass: exit 0." in err
    bad = tmp_path / "bad.3dm"
    bad.write_bytes(b"junk")
    outp = tmp_path / "bad.md"
    code, _, err = run_cli(bad, "--output", outp)
    assert code == 2 and "incomplete: exit 2." in err
    assert outp.read_text().startswith("Result: incomplete.")


def test_markdown_empty_object_id_is_em_dash(fx, run_cli):
    _, out, _ = run_cli(fx["empty_layer.3dm"], "--no-color")
    row = next(l for l in out.splitlines() if "| empty_layer |" in l)
    assert "| Warning | empty_layer | — |" in row
    assert " none " not in row


# --- help and version -----------------------------------------------------------------

def test_help_contains_footer_and_exit_codes(run_cli):
    code, out, _ = run_cli("--help")
    assert code == 0
    flat = " ".join(out.split())
    assert EXACT_FOOTER in flat
    for needle in ("exit codes:", "0  All files were read", "1  All files were read",
                   "2  Usage error", "no .3dm files found", "unreadable",
                   "run result", "Result: report only.", "Result: incomplete.", "summary.result",
                   "--profile", "--format", "--fail-on", "--output", "--quiet", "--no-color",
                   "--version", "NO_COLOR", "3dm-inspect exports/ --format json"):
        assert needle in out, needle
    assert "LIMEN" not in out


def test_version(run_cli):
    code, out, _ = run_cli("--version")
    assert code == 0 and re.fullmatch(r"3dm-inspect 0\.2\.0 \(rhino3dm 8\.[\d.]+\)\n", out)


# --- installed entry point ---------------------------------------------------------------

def test_console_script_installed(fx):
    exe = _exe()
    assert exe, "3dm-inspect is not on PATH; run pip install -e ."
    r = subprocess.run([exe, str(fx["invalid_object.3dm"]), "--format", "json"], capture_output=True, text=True)
    assert r.returncode == 1
    assert json.loads(r.stdout)["files"][0]["findings"][0]["message"] == "Line points are coincident."
    r = subprocess.run([exe, "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "usage: 3dm-inspect" in r.stdout


def test_python_dash_m(fx):
    r = subprocess.run([sys.executable, "-m", "inspect3dm", str(fx["clean.3dm"]), "--quiet"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("pass: ")
