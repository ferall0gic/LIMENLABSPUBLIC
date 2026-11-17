"""Input validation and error recovery (LABPUB-005, 2026-11-17).

Every bad input must exit 2 with one plain-language line on stderr and no traceback.
Two known defects are recorded as strict xfails (D-005-1, D-005-2); fixing them turns
these tests into unexpected passes, which fails the run until the marker is removed."""

import os
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent / "data"
GOOD = DATA / "line_v9.3dm"


@pytest.fixture()
def bad(tmp_path):
    v9 = GOOD.read_bytes()
    files = {
        "empty": tmp_path / "empty.3dm",
        "random": tmp_path / "random.3dm",
        "text": tmp_path / "text.3dm",
        "truncated": tmp_path / "truncated.3dm",
        "header_only": tmp_path / "header_only.3dm",
    }
    files["empty"].write_bytes(b"")
    files["random"].write_bytes(bytes(range(256)) * 16)
    files["text"].write_text("not a rhino file\n")
    files["truncated"].write_bytes(v9[: len(v9) // 2])
    files["header_only"].write_bytes(v9[:64])
    return files


@pytest.mark.parametrize("kind", ["empty", "random", "text", "truncated", "header_only"])
@pytest.mark.parametrize("side", ["old", "new"])
def test_unreadable_file_exits_2_without_traceback(run, bad, kind, side):
    args = (bad[kind], GOOD) if side == "old" else (GOOD, bad[kind])
    code, out, err = run(*args)
    assert code == 2
    assert "Traceback" not in err and err.count("\n") == 1
    assert str(bad[kind]) in err


@pytest.mark.parametrize("kind", ["random", "truncated"])
def test_textconv_unreadable_exits_2(run, bad, kind):
    code, out, err = run("--textconv", bad[kind])
    assert code == 2 and "Traceback" not in err


def test_missing_file_and_folder(run, tmp_path):
    code, _, err = run(tmp_path / "nope.3dm", GOOD)
    assert code == 2 and "does not exist" in err
    code, _, err = run(tmp_path, GOOD)
    assert code == 2 and "is a folder" in err


@pytest.mark.parametrize("argv", [(), (GOOD,), (GOOD, GOOD, GOOD), ("--textconv", GOOD, GOOD)])
def test_wrong_argument_count_exits_2(run, argv):
    try:
        code, _, _ = run(*argv)
    except SystemExit as exc:  # argparse usage errors
        code = exc.code
    assert code == 2


def test_same_file_is_no_difference(run):
    code, _, _ = run(GOOD, GOOD)
    assert code == 0


@pytest.mark.xfail(strict=True, reason="D-005-1: message reads \"Could not read 'x' is empty\" (missing ': the file')")
def test_error_message_is_a_sentence(run, bad):
    _, _, err = run(bad["empty"], GOOD)
    assert f"Could not read '{bad['empty']}': " in err


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root can read mode-000 files")
@pytest.mark.xfail(strict=True, reason="D-005-2: permission denied is reported as 'not a readable .3dm file (or is truncated)'")
def test_permission_denied_is_named(run, tmp_path):
    p = tmp_path / "locked.3dm"
    p.write_bytes(GOOD.read_bytes())
    p.chmod(0)
    try:
        code, _, err = run(p, GOOD)
    finally:
        p.chmod(0o644)
    assert code == 2 and "permission" in err.replace(str(p), "").lower()  # tmp_path contains the test name
