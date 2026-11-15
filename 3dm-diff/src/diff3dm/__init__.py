"""diff3dm: headless, ID-based diff of two Rhino .3dm files.

Installs the ``3dm-diff`` command. Reads files with rhino3dm (openNURBS);
Rhino is not required and files are never modified.
"""

__version__ = "0.1.0"
TOOL_NAME = "3dm-diff"

from .snapshot import Snapshot, load_snapshot  # noqa: E402
from .diff import Diff, diff_snapshots  # noqa: E402

__all__ = ["__version__", "TOOL_NAME", "Snapshot", "load_snapshot", "Diff", "diff_snapshots"]
