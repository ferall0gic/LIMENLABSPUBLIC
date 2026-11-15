"""Command line: 3dm-diff OLD NEW [options]  |  3dm-diff --textconv FILE"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import TOOL_NAME, __version__
from .diff import diff_snapshots
from .report import RHINO3DM_VERSION, render_json, render_markdown, render_textconv
from .snapshot import ReadError, load_snapshot

EPILOG = f"""\
examples:
  {TOOL_NAME} tower_rev03.3dm tower_rev04.3dm
  {TOOL_NAME} old.3dm new.3dm --format json --output changes.json
  {TOOL_NAME} old.3dm new.3dm --match-geometry --ignore name
  {TOOL_NAME} --textconv model.3dm          (for git: see README)

exit codes (same as diff):
  0  no differences
  1  differences found
  2  a file could not be read, or the command line was wrong
"""


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=TOOL_NAME, description="Compare two Rhino .3dm files by object and layer ID, without Rhino.",
                                epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="*", metavar="FILE")
    p.add_argument("--format", choices=("md", "json"), default="md", help="report format (default: md)")
    p.add_argument("--output", metavar="PATH", help="write the report to PATH")
    p.add_argument("--match-geometry", action="store_true",
                   help="pair removed/added objects with identical geometry, type and layer as 're-identified'")
    p.add_argument("--ignore", action="append", choices=("name", "user_text", "layer"), default=[],
                   help="ignore changes to this object field (repeatable)")
    p.add_argument("--textconv", action="store_true", help="print one FILE as stable text (git textconv driver)")
    p.add_argument("--version", action="version", version=f"{TOOL_NAME} {__version__} (rhino3dm {RHINO3DM_VERSION})")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    p = _parser()
    try:
        args = p.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    try:
        if args.textconv:
            if len(args.files) != 1:
                sys.stderr.write("--textconv takes exactly one FILE.\n")
                return 2
            sys.stdout.write(render_textconv(load_snapshot(args.files[0])))
            return 0
        if len(args.files) != 2:
            sys.stderr.write(f"Pass two files: {TOOL_NAME} OLD.3dm NEW.3dm. See {TOOL_NAME} --help.\n")
            return 2
        old, new = (load_snapshot(f) for f in args.files)
    except ReadError as exc:
        sys.stderr.write(f"Could not read {exc}\n")
        return 2
    d = diff_snapshots(old, new, match_geometry=args.match_geometry, ignore=tuple(args.ignore))
    text = render_json(d) if args.format == "json" else render_markdown(d)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 0 if d.is_empty else 1


def entry() -> None:  # pragma: no cover
    sys.exit(main())
