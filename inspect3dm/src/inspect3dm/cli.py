"""Command-line interface for 3dm-inspect."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from . import TOOL_NAME, __version__
from .inspector import NoFilesError, PathNotFoundError, inspect_paths
from .profile import BUILTIN_PROFILES, ProfileError, load_profile
from .report import FOOTER, RHINO3DM_VERSION, render_json, render_markdown, render_quiet

DESCRIPTION = f"""\
Inspect Rhino .3dm files against a rule profile, without Rhino, and report
problems as Markdown (default) or JSON. Checks: object validity, model units
and tolerances, mesh closed/manifold (strict profile), layer hygiene, and
(revit profile) short edges and far-from-origin geometry against known Revit
import limits. <path> is a .3dm file or a folder; folders are searched
recursively for *.3dm.
"""

EPILOG = f"""\
options in detail:
  --profile NAME|FILE   Built-in profile ({', '.join(BUILTIN_PROFILES)}) or a .toml profile file.
                        Example: {TOOL_NAME} model.3dm --profile strict
                        Example: {TOOL_NAME} model.3dm --profile revit
  --list-profiles       List the built-in profiles and exit.
  --format md|json      Report format. Default: md. If omitted, inferred from an
                        --output file ending in .md or .json.
                        Example: {TOOL_NAME} exports/ --format json
  --fail-on LEVEL       error (default), warning, or never. Sets which findings
                        make the run exit 1. Example: --fail-on warning
  --output FILE         Write the report to FILE instead of standard output.
                        Example: --output report.json
  --quiet               One line per file and a total; no finding detail.
  --no-color            Plain text. Color is also off when NO_COLOR is set or
                        output is not a terminal. Severity is always a word.

examples:
  {TOOL_NAME} samples/sample.3dm
  {TOOL_NAME} exports/ --profile office.toml
  {TOOL_NAME} exports/ --format json --output report.json      (CI)
  {TOOL_NAME} exports/ --format json --fail-on warning         (strict CI gate)

exit codes:
  0  All files were read and no finding met --fail-on.
  1  All files were read and one or more findings met --fail-on.
  2  Usage error, invalid profile, no .3dm files found in a folder, or a file
     could not be read. A folder run continues past an unreadable file, records
     it as "unreadable", and exits 2.

run result (Markdown first line and JSON summary.result):
  pass         exit 0; all files readable, no finding met --fail-on
               (including --fail-on never with no findings). First line: Result: pass.
  fail         exit 1; all files readable, one or more findings met --fail-on.
               First line: Result: fail.
  report       exit 0; --fail-on never, all files readable, findings present.
               First line: Result: report only.
  incomplete   exit 2; a file could not be read (when a report is produced).
               First line: Result: incomplete. Usage errors and empty folders
               print an error message and exit 2 with no report.

file status is pass, fail, or unreadable. Finding severity is error or warning.

{FOOTER}
"""


PROFILE_SUMMARIES = {
    "default": "validity, units and tolerance, layer hygiene",
    "strict": "default plus closed/manifold meshes and objects on the default layer",
    "revit": "default plus known Revit import limits: short edges and curves (~0.79 mm), "
             "distance from origin (10 mi) and model extents (20 mi), units required, tolerance",
}


class UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # noqa: D401 - argparse hook
        raise UsageError(message)


def _build_parser() -> _Parser:
    p = _Parser(
        prog=TOOL_NAME,
        usage=f"{TOOL_NAME} <path> [<path> ...] [options]",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
        add_help=False,
    )
    p.add_argument("paths", nargs="*", metavar="path", help=".3dm file or folder (searched recursively)")
    p.add_argument("--profile", metavar="NAME|FILE", default=None,
                   help="rule profile: default, strict, revit, or a .toml file (default: default)")
    p.add_argument("--format", choices=("md", "json"), default=None, help="report format (default: md)")
    p.add_argument("--fail-on", choices=("error", "warning", "never"), default="error",
                   help="severity that makes the run exit 1 (default: error)")
    p.add_argument("--output", metavar="FILE", default=None, help="write the report to FILE")
    p.add_argument("--quiet", action="store_true", help="one-line summary per file and a total")
    p.add_argument("--no-color", action="store_true", help="disable color (NO_COLOR is also honored)")
    p.add_argument("--help", "-h", action="store_true", help="show this help and exit")
    p.add_argument("--version", action="store_true", help="show tool and rhino3dm versions and exit")
    p.add_argument("--list-profiles", action="store_true", help="list the built-in profiles and exit")
    return p


def _translate_usage(message: str) -> str:
    see = f"See {TOOL_NAME} --help."
    if message.startswith("argument --format: invalid choice"):
        return f"--format must be md or json. {see}"
    if message.startswith("argument --fail-on: invalid choice"):
        return f"--fail-on must be error, warning, or never. {see}"
    if "expected one argument" in message:
        opt = message.split(":")[0].replace("argument ", "")
        return f"Option '{opt}' needs a value. {see}"
    return f"{message[0].upper()}{message[1:]}. {see}" if message else see


def _want_color(args, stream) -> bool:
    if args.no_color or os.environ.get("NO_COLOR"):
        return False
    if args.output:
        return False
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _resolve_format(args) -> str:
    inferred = None
    if args.output:
        ext = Path(args.output).suffix.lower()
        inferred = {".json": "json", ".md": "md"}.get(ext)
    if args.format and inferred and args.format != inferred:
        raise UsageError(
            f"--format {args.format} does not match the --output file '{args.output}' "
            f"(which implies {inferred}). Use matching values, or omit --format. See {TOOL_NAME} --help."
        )
    return args.format or inferred or "md"


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out, err = sys.stdout, sys.stderr
    parser = _build_parser()
    try:
        args, extras = parser.parse_known_args(argv)
        if args.help:
            out.write(parser.format_help())
            return 0
        if args.version:
            out.write(f"{TOOL_NAME} {__version__} (rhino3dm {RHINO3DM_VERSION})\n")
            return 0
        if args.list_profiles:
            for name in BUILTIN_PROFILES:
                out.write(f"{name}: {PROFILE_SUMMARIES[name]}\n")
            return 0
        for extra in extras:
            if extra.startswith("-"):
                name = extra.split("=")[0]
                raise UsageError(f"Unknown option '{name}'. See {TOOL_NAME} --help.")
        if extras:
            raise UsageError(f"Unexpected argument '{extras[0]}'. See {TOOL_NAME} --help.")
        if not args.paths:
            raise UsageError(f"No path given. Pass a .3dm file or a folder. See {TOOL_NAME} --help.")
        fmt = _resolve_format(args)
    except UsageError as exc:
        msg = str(exc)
        if not msg.startswith(("Unknown option", "Unexpected argument", "No path", "--format ")):
            msg = _translate_usage(msg)
        err.write(msg + "\n")
        return 2

    try:
        profile = load_profile(args.profile)
    except ProfileError as exc:
        err.write(f"{exc}\n")
        return 2

    try:
        run = inspect_paths(args.paths, profile, args.fail_on)
    except (NoFilesError, PathNotFoundError) as exc:
        err.write(f"{exc}\n")
        return 2

    color = _want_color(args, out)
    if args.quiet and fmt == "md":
        text = render_quiet(run, color)
    elif fmt == "json":
        text = render_json(run, include_findings=not args.quiet)
    else:
        text = render_markdown(run, color)

    # Unreadable files go to stderr too when the report is not meant for a person at this terminal.
    if args.output or fmt == "json":
        for f in run.files:
            if f.status == "unreadable":
                err.write(f"{f.message}\n")

    if args.output:
        try:
            Path(args.output).write_text(text, encoding="utf-8")
        except OSError as exc:
            err.write(
                f"Could not write the report to '{args.output}': {exc.strerror}. "
                "Check that the folder exists and is writable.\n"
            )
            return 2
        if not args.quiet:
            err.write(f"Wrote {fmt} report to '{args.output}'. {run.result_phrase}: exit {run.exit_code}.\n")
    else:
        out.write(text)
    return run.exit_code


def entry() -> None:  # pragma: no cover
    sys.exit(main())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
