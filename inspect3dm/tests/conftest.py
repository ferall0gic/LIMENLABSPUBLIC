import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import make_fixtures  # noqa: E402


@pytest.fixture(scope="session")
def fx(tmp_path_factory):
    """All rule fixtures, generated with rhino3dm into a fresh folder."""
    prebuilt = os.environ.get("INSPECT3DM_FIXTURES")
    if prebuilt:
        # Fixtures built earlier by scripts/make_fixtures.py, e.g. under rhino3dm 8 for a
        # rhino3dm 9 test run (9.2 cannot set ModelUnitSystem from Python).
        return {p.name: p for p in sorted(Path(prebuilt).glob("*.3dm"))}
    out = tmp_path_factory.mktemp("fixtures")
    return make_fixtures.build_all(out)


@pytest.fixture()
def run_cli(monkeypatch, capsys):
    """Run the CLI in-process; returns (exit_code, stdout, stderr)."""
    from inspect3dm.cli import main

    def _run(*args, env=None):
        monkeypatch.delenv("NO_COLOR", raising=False)
        for k, v in (env or {}).items():
            monkeypatch.setenv(k, v)
        code = main([str(a) for a in args])
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


@pytest.fixture()
def office_profile():
    return ROOT / "examples" / "office-profile.toml"
