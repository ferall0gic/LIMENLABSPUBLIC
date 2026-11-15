"""ghx-deps PATH... [--format md|json] [--allow NAME] [--allowlist FILE]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import TOOL_NAME, __version__
from .manifest import GhxError, Manifest, discover, read_manifest

DASH = "\u2014"

EPILOG = f"""\
examples:
  {TOOL_NAME} facade.ghx
  {TOOL_NAME} definitions/ --format json --output deps.json
  {TOOL_NAME} definitions/ --allowlist office-plugins.txt     (CI gate)

exit codes:
  0  all files read; no library outside the allowlist (or no allowlist given)
  1  all files read; a definition needs a library that is not on the allowlist
  2  a file could not be read (including binary .gh files), or bad arguments
"""


def _load_allow(args) -> set[str] | None:
    names = list(args.allow or [])
    if args.allowlist:
        try:
            text = Path(args.allowlist).read_text(encoding="utf-8")
        except OSError as exc:
            raise GhxError(f"Allowlist '{args.allowlist}' could not be read ({exc.strerror}).") from None
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                names.append(line)
    if not names and not args.allowlist:
        return None
    return {n.lower() for n in names}


def _not_allowed(m: Manifest, allow: set[str] | None):
    if allow is None:
        return []
    return [lib for lib in m.libraries if lib.name.lower() not in allow and lib.id.lower() not in allow]


def _md(results, errors, allow) -> str:
    libs_all: dict[tuple[str, str], set[str]] = {}
    for m in results:
        for lib in m.libraries:
            libs_all.setdefault((lib.name, lib.display_version), set()).add(m.path)
    L = [f"{len(results)} definition(s) read, {len(errors)} not read. "
         f"{len(libs_all)} distinct plug-in library version(s).", "",
         f"{TOOL_NAME} {__version__}. Libraries are those the definition records in its GHALibraries "
         "list; components are counted by name.", ""]
    if libs_all:
        L += ["## Plug-in libraries (all files)", "", "| Library | Version | Used by |", "|---|---|---|"]
        for (name, ver), files in sorted(libs_all.items(), key=lambda kv: (kv[0][0].lower(), kv[0][1])):
            L.append(f"| {name or '(no name)'} | {ver or DASH} | {len(files)} file(s) |")
        L.append("")
    for m in results:
        L += [f"## {m.path}", "",
              f"Saved with Grasshopper {m.grasshopper_version or 'unknown'}. "
              f"{m.object_count} top-level object(s), {len(m.components)} distinct.", ""]
        if m.libraries:
            L += ["| Library | Version | Author | Id |", "|---|---|---|---|"]
            for lib in m.libraries:
                L.append(f"| {lib.name} | {lib.display_version or DASH} | {lib.author or DASH} | {lib.id} |")
        else:
            L.append("No plug-in libraries recorded.")
        L.append("")
        bad = _not_allowed(m, allow)
        if bad:
            L += ["Not on the allowlist: " + ", ".join(sorted(b.name for b in bad)) + ".", ""]
        if m.script_components:
            L += ["Script components: " + ", ".join(f"{n} x{c}" for n, c in sorted(m.script_components.items()))
                  + ". Their code may import further libraries that are not listed above.", ""]
        if m.clusters:
            L += [f"Clusters: {m.clusters}. Plug-ins used only inside clusters may not be listed.", ""]
        if m.file_references:
            L += ["Absolute file paths found in the definition:", ""] + [f"- `{r}`" for r in m.file_references] + [""]
    for path, msg in errors:
        L += [f"## {path}", "", f"Not read: {msg}", ""]
    return "\n".join(L)


def _json(results, errors, allow) -> str:
    doc = {
        "tool": TOOL_NAME, "tool_version": __version__,
        "files": [{
            "path": m.path, "grasshopper_version": m.grasshopper_version, "archive_version": m.archive_version,
            "libraries": [lib.to_dict() for lib in m.libraries],
            "not_allowed": sorted(b.name for b in _not_allowed(m, allow)),
            "object_count": m.object_count,
            "components": [{"name": n, "guid": g, "count": c}
                           for (n, g), c in sorted(m.components.items(), key=lambda kv: (-kv[1], kv[0]))],
            "script_components": dict(sorted(m.script_components.items())),
            "clusters": m.clusters,
            "file_references": m.file_references,
        } for m in results],
        "errors": [{"path": p, "message": msg} for p, msg in errors],
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=TOOL_NAME, epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description="List the plug-ins, components and file paths a Grasshopper .ghx needs, without Rhino.")
    ap.add_argument("paths", nargs="+", metavar="PATH", help=".ghx file or folder (searched recursively)")
    ap.add_argument("--format", choices=("md", "json"), default="md")
    ap.add_argument("--output", metavar="FILE")
    ap.add_argument("--allow", action="append", metavar="NAME_OR_ID", help="allowed library name or Id (repeatable)")
    ap.add_argument("--allowlist", metavar="FILE", help="text file, one allowed library name or Id per line")
    ap.add_argument("--version", action="version", version=f"{TOOL_NAME} {__version__}")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    try:
        allow = _load_allow(args)
    except GhxError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    ghx, gh = discover(args.paths)
    if not ghx and not gh:
        sys.stderr.write("No .ghx files found. Check the path.\n")
        return 2
    results, errors = [], []
    for f in ghx:
        try:
            results.append(read_manifest(f))
        except GhxError as exc:
            errors.append((str(f), str(exc)))
    for f in gh:
        errors.append((str(f), "binary .gh is not supported; save it as .ghx in Grasshopper."))
    text = _json(results, errors, allow) if args.format == "json" else _md(results, errors, allow)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if errors:
        return 2
    return 1 if any(_not_allowed(m, allow) for m in results) else 0


def entry() -> None:  # pragma: no cover
    sys.exit(main())
