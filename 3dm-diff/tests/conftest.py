import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import make_fixtures  # noqa: E402


@pytest.fixture(scope="session")
def fx(tmp_path_factory):
    prebuilt = os.environ.get("DIFF3DM_FIXTURES")
    if prebuilt:
        # Fixtures built earlier by scripts/make_fixtures.py, e.g. under rhino3dm 8 for a
        # rhino3dm 9 test run (9.2 cannot set ModelUnitSystem from Python).
        return {p.name: p for p in sorted(Path(prebuilt).glob("*.3dm"))}
    return make_fixtures.build_all(tmp_path_factory.mktemp("fx"))


@pytest.fixture()
def run(capsys):
    from diff3dm.cli import main

    def _run(*args):
        code = main([str(a) for a in args])
        out = capsys.readouterr()
        return code, out.out, out.err
    return _run
