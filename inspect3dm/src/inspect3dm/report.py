"""Report rendering: Markdown (default), JSON, and quiet one-line output."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import rhino3dm

from . import TOOL_NAME, VALIDATION_BASIS, __version__
from .inspector import FileResult, RunResult
from .units import degrees_str, length_str, unit_display

FOOTER = (
    "Validity is checked with openNURBS (via rhino3dm) and may differ from Rhino's Check command. "
    "This report does not repair models and is not a substitute for Check or for your own review."
)

RHINO3DM_VERSION = getattr(rhino3dm, "__version__", "unknown")

# JSON report schema. 1.0 = inspect3dm 0.1-0.2.0 (field not emitted).
# 1.1 = adds "schema_version" and the per-file "file" block (archive provenance). Additive only.
SCHEMA_VERSION = "1.1"

_ANSI = {"red": "\033[31m", "yellow": "\033[33m", "green": "\033[32m", "bold": "\033[1m", "reset": "\033[0m"}
_COLOR_FOR = {"error": "red", "fail": "red", "unreadable": "red", "incomplete": "red", "warning": "yellow", "report": "yellow", "pass": "green"}


def identity_line() -> str:
    return f"{TOOL_NAME} {__version__}, rhino3dm {RHINO3DM_VERSION}"


def _paint(word: str, key: str, color: bool) -> str:
    """Color is decoration only: the word itself always carries the meaning."""
    if not color or key not in _COLOR_FOR:
        return word
    return f"{_ANSI[_COLOR_FOR[key]]}{word}{_ANSI['reset']}"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _counts(errors: int, warnings: int) -> str:
    return f"{_plural(errors, 'error')}, {_plural(warnings, 'warning')}"


def _counts_clause(run: RunResult) -> str:
    n = len(run.files)
    parts = [f"{run.count('pass')} pass", f"{run.count('fail')} fail"]
    if run.count("unreadable"):
        parts.append(f"{run.count('unreadable')} unreadable")
    return (
        f"{_plural(n, 'file')} inspected ({', '.join(parts)}); "
        f"{_counts(run.errors, run.warnings)}."
    )


def _painted_phrase(run: RunResult, color: bool) -> str:
    return _paint(run.result_phrase, run.result, color)


def summary_line(run: RunResult, color: bool = False) -> str:
    return f"Result: {_painted_phrase(run, color)}. {_counts_clause(run)}"


EMPTY_CELL = "\u2014"  # em dash; not the word "none", which can be read as a name


def _cell(value: Any) -> str:
    if value is None or value == "":
        return EMPTY_CELL
    return str(value).replace("|", "\\|").replace("\n", " ")


def _file_settings_line(f: FileResult) -> str:
    unit = f.units or "unset"
    return (
        f"Units: {unit_display(unit)}. Absolute tolerance: {length_str(f.absolute_tolerance, unit)}. "
        f"Angle tolerance: {degrees_str(f.angle_tolerance_degrees)}."
    )


def archive_line(archive: dict[str, Any] | None) -> str | None:
    """One text line on where the file came from, or None when the version is unknown."""
    if not archive or archive.get("archive_version") is None:
        return None
    line = f"File format: Rhino {archive['rhino_version']} (archive version {archive['archive_version']})."
    if archive.get("created_by"):
        line += f" Created by: {archive['created_by']}."
    if archive.get("last_edited_by"):
        line += f" Last edited by: {archive['last_edited_by']}."
    return line


def _file_index_line(f: FileResult, color: bool) -> str:
    status = _paint(f.status, f.status, color)
    if f.status == "unreadable":
        return f"- {status}: {f.path} (could not be read)"
    return f"- {status}: {f.path} ({_counts(f.errors, f.warnings)})"


def render_markdown(run: RunResult, color: bool = False) -> str:
    lines: list[str] = [summary_line(run, color), "", f"{identity_line()}. Profile: {run.profile.name}. Fail on: {run.fail_on}.", ""]
    if run.folder_mode:
        lines += ["## Files", ""]
        lines += [_file_index_line(f, color) for f in run.files]
        lines.append("")
    for f in run.files:
        lines += [f"## {f.path}", ""]
        status = _paint(f.status, f.status, color)
        prov = archive_line(f.archive)
        if f.status == "unreadable":
            lines += [f"Status: {status}. {f.message}", ""]
            if prov:
                lines += [prov, ""]
            continue
        lines += [f"Status: {status}. {_counts(f.errors, f.warnings)}. "
                  f"{_plural(f.object_count, 'object')}, {_plural(f.layer_count, 'layer')}.", ""]
        lines += [_file_settings_line(f), ""]
        if prov:
            lines += [prov, ""]
        if f.findings:
            lines += ["| Severity | Rule | Object ID | Type | Layer | Message |",
                      "|---|---|---|---|---|---|"]
            for x in f.findings:
                sev = _paint(x.severity.capitalize(), x.severity, color)
                lines.append(
                    f"| {sev} | {_cell(x.rule)} | {_cell(x.object_id)} | {_cell(x.object_type)} | "
                    f"{_cell(x.layer)} | {_cell(x.message)} |"
                )
            lines.append("")
        else:
            lines += ["No findings for this profile.", ""]
        if f.next_steps:
            lines += [f"Next steps in Rhino: {', '.join(f.next_steps)}.", ""]
    lines += ["---", "", FOOTER, ""]
    return "\n".join(lines)


def _file_dict(f: FileResult, include_findings: bool = True) -> dict[str, Any]:
    d: dict[str, Any] = {"path": f.path, "status": f.status}
    if f.archive is not None:
        d["file"] = {k: f.archive[k] for k in ("archive_version", "rhino_version", "created_by", "last_edited_by")}
    if f.status == "unreadable":
        d["message"] = f.message
    else:
        unit = f.units or "unset"
        d.update({
            "units": f.units,
            "absolute_tolerance": f.absolute_tolerance,
            "absolute_tolerance_display": length_str(f.absolute_tolerance, unit),
            "angle_tolerance_degrees": f.angle_tolerance_degrees,
            "angle_tolerance_display": degrees_str(f.angle_tolerance_degrees),
            "object_count": f.object_count,
            "layer_count": f.layer_count,
        })
    d["summary"] = {"errors": f.errors, "warnings": f.warnings}
    if include_findings:
        d["findings"] = [x.to_dict() for x in f.findings]
    if f.next_steps:
        d["next_steps"] = f.next_steps
    return d


def run_dict(run: RunResult, include_findings: bool = True, generated_at: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "tool_version": __version__,
        "rhino3dm_version": RHINO3DM_VERSION,
        "profile": run.profile.name,
        "fail_on": run.fail_on,
        "generated_at": generated_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "validation_basis": VALIDATION_BASIS,
        "summary": {
            "result": run.result,
            "exit_code": run.exit_code,
            "files_inspected": len(run.files),
            "files_passed": run.count("pass"),
            "files_failed": run.count("fail"),
            "files_unreadable": run.count("unreadable"),
            "errors": run.errors,
            "warnings": run.warnings,
        },
        "files": [_file_dict(f, include_findings) for f in run.files],
    }


def render_json(run: RunResult, include_findings: bool = True) -> str:
    return json.dumps(run_dict(run, include_findings), indent=2, ensure_ascii=False) + "\n"


def render_quiet(run: RunResult, color: bool = False) -> str:
    def one(f: FileResult) -> str:
        status = _paint(f.status, f.status, color)
        if f.status == "unreadable":
            return f"{status}: {f.path} (could not be read)"
        return f"{status}: {f.path} ({_counts(f.errors, f.warnings)})"

    if not run.folder_mode and len(run.files) == 1:
        return one(run.files[0]) + "\n"
    lines = [one(f) for f in run.files]
    lines.append("Total: " + _painted_phrase(run, color) + ". " + _counts_clause(run))
    return "\n".join(lines) + "\n"
