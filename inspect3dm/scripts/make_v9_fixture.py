"""Write tests/data/line_v9.3dm: one line in a Rhino 9 (archive version 90) file.

Must run under rhino3dm 9.x (it writes the current archive version). The file is
committed so the rhino3dm 8.x test run can check how a newer archive is reported.
rhino3dm 9.2 cannot set ModelUnitSystem from Python, so the file keeps the
library's default units; the provenance tests do not depend on units.

    pip install --pre "rhino3dm>=9.2.0b1,<10"
    python scripts/make_v9_fixture.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import rhino3dm

OUT = Path(__file__).resolve().parents[1] / "tests" / "data" / "line_v9.3dm"


def main() -> int:
    major = int(rhino3dm.__version__.split(".")[0])
    if major < 9:
        print(f"needs rhino3dm 9.x (found {rhino3dm.__version__})", file=sys.stderr)
        return 2
    model = rhino3dm.File3dm()
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(1000, 0, 0))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not model.Write(str(OUT), 0):  # 0 = current archive version of this rhino3dm
        print("write failed", file=sys.stderr)
        return 1
    print(f"wrote {OUT} (archive version {rhino3dm.File3dm.ReadArchiveVersion(str(OUT))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
