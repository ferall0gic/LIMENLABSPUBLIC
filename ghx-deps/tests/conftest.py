import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import make_fixtures  # noqa: E402


@pytest.fixture(scope="session")
def fx(tmp_path_factory):
    return make_fixtures.build_all(tmp_path_factory.mktemp("fx"))


@pytest.fixture()
def run(capsys):
    from ghxdeps.cli import main

    def _run(*args):
        code = main([str(a) for a in args])
        out = capsys.readouterr()
        return code, out.out, out.err
    return _run
