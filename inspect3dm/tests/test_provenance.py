"""Archive provenance (v0.2.1): the report says which Rhino version wrote the file,
and flags a file newer than the installed rhino3dm as an info finding (never a failure)."""

import json
from pathlib import Path
from types import SimpleNamespace as NS

import rhino3dm

from inspect3dm import _rh

DATA = Path(__file__).resolve().parent / "data"
V9 = DATA / "line_v9.3dm"  # written by rhino3dm 9.2.0b1 (scripts/make_v9_fixture.py)
READER = _rh.reader_major(rhino3dm)


def test_rhino_version_mapping():
    assert _rh.rhino_version(90) == 9 and _rh.rhino_version(80) == 8 and _rh.rhino_version(50) == 5
    assert _rh.rhino_version(4) == 4 and _rh.rhino_version(None) is None


def test_reader_major_parses_prerelease():
    assert _rh.reader_major(NS(__version__="9.2.0b1")) == 9
    assert _rh.reader_major(NS(__version__="8.35.0")) == 8
    assert _rh.reader_major(NS(__version__="dev")) is None
    assert _rh.reader_major(NS()) is None


def _fake(version, rav):
    def read_av(path):
        if isinstance(rav, BaseException):
            raise rav
        return rav
    return NS(__version__=version, File3dm=NS(ReadArchiveVersion=read_av))


def test_archive_version_missing_file_both_shapes():
    assert _rh.archive_version(_fake("8.35.0", 0), "x.3dm") is None                       # 8.x returns 0
    assert _rh.archive_version(_fake("9.2.0", FileNotFoundError()), "x.3dm") is None      # 9.x raises


def test_newer_than_reader_flag_from_fakes():
    model = NS(CreatedBy="Rhino 9 (build x)", LastEditedBy="")
    p = _rh.archive_provenance(_fake("8.35.0", 90), "x.3dm", model)
    assert p == {"archive_version": 90, "rhino_version": 9, "created_by": "Rhino 9 (build x)",
                 "last_edited_by": "", "newer_than_reader": True}
    assert _rh.archive_provenance(_fake("9.2.0b1", 90), "x.3dm")["newer_than_reader"] is False
    assert _rh.archive_provenance(_fake("8.35.0", 80), "x.3dm")["newer_than_reader"] is False
    assert _rh.archive_provenance(_fake("8.35.0", 4), "x.3dm")["newer_than_reader"] is False  # Rhino 4 archive


def test_v8_file_reports_rhino8_without_notice(fx, run_cli):
    code, out, _ = run_cli(fx["clean.3dm"], "--format", "json")
    assert code == 0
    doc = json.loads(out)
    assert doc["schema_version"] == "1.1"
    f = doc["files"][0]
    assert f["file"]["archive_version"] == 80 and f["file"]["rhino_version"] == 8
    assert f["file"]["created_by"] == "" and f["file"]["last_edited_by"] == ""  # rhino3dm leaves them empty
    assert not [x for x in f["findings"] if x["rule"] == "archive_newer_than_reader"]


def test_v9_file_provenance_and_notice(run_cli):
    code, out, _ = run_cli(V9, "--format", "json")
    doc = json.loads(out)
    f = doc["files"][0]
    assert f["file"]["archive_version"] == 90 and f["file"]["rhino_version"] == 9
    notices = [x for x in f["findings"] if x["rule"] == "archive_newer_than_reader"]
    if READER is not None and READER < 9:
        assert len(notices) == 1 and notices[0]["severity"] == "info"
        assert "Rhino 9 file" in notices[0]["message"] and rhino3dm.__version__ in notices[0]["message"]
    else:
        assert notices == []


def test_notice_never_changes_exit_code(run_cli):
    # Same exit code with every --fail-on level that the file's own findings would give;
    # the notice is info and must not count as error or warning.
    code, out, _ = run_cli(V9, "--format", "json", "--fail-on", "warning")
    s = json.loads(out)["files"][0]["summary"]
    assert code == (1 if s["errors"] or s["warnings"] else 0)


def test_markdown_shows_file_format_line(fx, run_cli):
    _, out, _ = run_cli(fx["clean.3dm"])
    assert "File format: Rhino 8 (archive version 80)." in out
    _, out9, _ = run_cli(V9)
    assert "File format: Rhino 9 (archive version 90)." in out9


def test_unreadable_file_still_gets_file_block_when_header_is_known(tmp_path, run_cli):
    # Truncate a real archive after its header: the full read fails, the version is still known.
    bad = tmp_path / "truncated.3dm"
    bad.write_bytes(V9.read_bytes()[:200])
    code, out, _ = run_cli(bad, "--format", "json")
    f = json.loads(out)["files"][0]
    assert code == 2 and f["status"] == "unreadable"
    assert f["file"]["archive_version"] == 90 and f["file"]["rhino_version"] == 9


def test_non_3dm_file_has_unknown_version(tmp_path, run_cli):
    bad = tmp_path / "notes.3dm"
    bad.write_text("not a model")
    _, out, _ = run_cli(bad, "--format", "json")
    f = json.loads(out)["files"][0]
    assert f["file"]["archive_version"] is None and f["file"]["rhino_version"] is None
