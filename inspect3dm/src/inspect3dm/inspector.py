"""Core inspection: read .3dm files with rhino3dm and apply profile rules."""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import rhino3dm

from .profile import Profile
from .units import degrees_str, length_str, unit_name, unit_display

SEVERITY_ORDER = {"error": 0, "warning": 1}

# Rhino commands a user can run next, per finding rule (pointers only).
NEXT_STEPS = {
    "validity": ("Check", "SelBadObjects"),
    "mesh_not_closed": ("CheckMesh", "MeshRepair"),
    "mesh_non_manifold": ("CheckMesh", "MeshRepair"),
}


@dataclass(frozen=True)
class Finding:
    severity: str  # "error" | "warning"
    rule: str
    message: str
    object_id: str | None = None
    object_type: str | None = None
    layer: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "rule": self.rule,
            "object_id": self.object_id,
            "object_type": self.object_type,
            "layer": self.layer,
            "message": self.message,
        }


@dataclass
class FileResult:
    path: str
    status: str = "pass"  # "pass" | "fail" | "unreadable"
    message: str | None = None  # set when unreadable
    units: str | None = None
    absolute_tolerance: float | None = None
    angle_tolerance_degrees: float | None = None
    object_count: int = 0
    layer_count: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    @property
    def next_steps(self) -> list[str]:
        steps: list[str] = []
        for f in self.findings:
            for cmd in NEXT_STEPS.get(f.rule, ()):
                if cmd not in steps:
                    steps.append(cmd)
        return steps

    def meets(self, fail_on: str) -> bool:
        if fail_on == "never":
            return False
        if fail_on == "warning":
            return bool(self.findings)
        return self.errors > 0


@dataclass
class RunResult:
    files: list[FileResult]
    profile: Profile
    fail_on: str
    folder_mode: bool

    @property
    def errors(self) -> int:
        return sum(f.errors for f in self.files)

    @property
    def warnings(self) -> int:
        return sum(f.warnings for f in self.files)

    def count(self, status: str) -> int:
        return sum(1 for f in self.files if f.status == status)

    @property
    def exit_code(self) -> int:
        if any(f.status == "unreadable" for f in self.files):
            return 2
        if any(f.meets(self.fail_on) for f in self.files):
            return 1
        return 0

    @property
    def result(self) -> str:
        """Run-level result: pass, fail, report, or incomplete."""
        if any(f.status == "unreadable" for f in self.files):
            return "incomplete"
        if self.fail_on == "never" and any(f.findings for f in self.files):
            return "report"
        if any(f.meets(self.fail_on) for f in self.files):
            return "fail"
        return "pass"

    @property
    def result_phrase(self) -> str:
        """Words used after 'Result:' / 'Total:' and in the --output stderr line."""
        return "report only" if self.result == "report" else self.result


# ---------------------------------------------------------------- discovery

class NoFilesError(Exception):
    """A folder contained no .3dm files. Message is user-facing."""


class PathNotFoundError(Exception):
    """A given path does not exist. Message is user-facing."""


def _is_3dm(name: str) -> bool:
    return name.lower().endswith(".3dm")


def discover(paths: Iterable[str]) -> tuple[list[str], bool]:
    """Expand the given paths into a sorted list of files.

    Folders are searched recursively for ``*.3dm`` (case-insensitive).
    Returns (files, folder_mode).
    """
    files: list[str] = []
    folder_mode = False
    given = list(paths)
    for raw in given:
        p = Path(raw)
        if p.is_dir():
            folder_mode = True
            found: list[str] = []
            for root, dirs, names in os.walk(p):
                dirs.sort()
                for name in sorted(names):
                    if _is_3dm(name):
                        found.append((Path(root) / name).as_posix())
            if not found:
                shown = raw if raw.endswith(("/", os.sep)) else raw + "/"
                raise NoFilesError(
                    f"No .3dm files found in '{shown}'. Check the path, or pass a .3dm file directly."
                )
            files.extend(sorted(found))
        elif p.exists() or p.is_symlink():
            files.append(raw)
        else:
            raise PathNotFoundError(
                f"Path '{raw}' does not exist. Check the path, or pass a .3dm file or folder."
            )
    if len(given) > 1:
        folder_mode = True
    # De-duplicate while keeping order.
    seen: set[str] = set()
    unique = [f for f in files if not (f in seen or seen.add(f))]
    return unique, folder_mode


# ---------------------------------------------------------------- reading

def _unreadable(path: str, reason: str) -> FileResult:
    return FileResult(path=path, status="unreadable", message=f"Could not read '{path}': {reason}")


def _read(path: str) -> tuple[Any | None, FileResult | None]:
    p = Path(path)
    if p.is_dir():
        return None, _unreadable(path, "it is a folder, not a file. Pass a .3dm file or run on the folder.")
    try:
        with open(p, "rb") as fh:
            head = fh.read(32)
    except PermissionError:
        return None, _unreadable(path, "permission denied. Check the file permissions.")
    except OSError as exc:
        return None, _unreadable(path, f"{exc.strerror or 'the file could not be opened'}. Check the path.")
    if not head:
        return None, _unreadable(path, "the file is empty (0 bytes). Check that the export completed.")
    model = rhino3dm.File3dm.Read(str(p))
    if model is None:
        return None, _unreadable(
            path,
            "the file is not a valid 3DM (or is truncated). Check the path and that the file opens in Rhino.",
        )
    return model, None


# ---------------------------------------------------------------- rules

def _layer_paths(model) -> list[tuple[int, str, str, str]]:
    """List of (index, name, full_path, id) for every layer."""
    out = []
    for i in range(len(model.Layers)):
        layer = model.Layers[i]
        out.append((i, layer.Name or "", layer.FullPath or layer.Name or "", str(layer.Id)))
    return out


def _check_document(model, rules: dict[str, Any], res: FileResult) -> list[Finding]:
    sev = rules["severity"]
    out: list[Finding] = []
    unit = res.units or "unset"
    allowed = [u.lower() for u in rules.get("allowed_units", [])]
    if unit in ("none", "unset") and not (allowed and unit in allowed):
        what = "Model has no units." if unit == "none" else "Model units are unset."
        out.append(Finding(sev, "units", f"{what} Set model units in Rhino (Units) before sharing the file."))
    elif allowed and unit not in allowed:
        out.append(Finding(sev, "units", f"Model units are {unit}; this profile allows {', '.join(allowed)}."))

    tol = res.absolute_tolerance
    lo, hi = rules.get("absolute_tolerance_min"), rules.get("absolute_tolerance_max")
    if tol is not None:
        if lo is not None and tol < lo:
            out.append(Finding(sev, "tolerance_range",
                               f"Absolute tolerance {length_str(tol, unit)} is below the configured minimum of "
                               f"{length_str(lo, unit)}."))
        elif hi is not None and tol > hi:
            out.append(Finding(sev, "tolerance_range",
                               f"Absolute tolerance {length_str(tol, unit)} is above the configured maximum of "
                               f"{length_str(hi, unit)}."))

    ang = res.angle_tolerance_degrees
    alo, ahi = rules.get("angle_tolerance_min_degrees"), rules.get("angle_tolerance_max_degrees")
    if ang is not None:
        if alo is not None and ang < alo - 1e-9:
            out.append(Finding(sev, "angle_tolerance_range",
                               f"Angle tolerance {degrees_str(ang)} is below the configured minimum of {degrees_str(alo)}."))
        elif ahi is not None and ang > ahi + 1e-9:
            out.append(Finding(sev, "angle_tolerance_range",
                               f"Angle tolerance {degrees_str(ang)} is above the configured maximum of {degrees_str(ahi)}."))
    return out


def _object_rows(model, layers):
    by_index = {i: full for i, _n, full, _id in layers}
    for obj in model.Objects:
        geom = obj.Geometry
        attrs = obj.Attributes
        idx = attrs.LayerIndex
        layer = by_index.get(idx)
        yield obj, geom, str(attrs.Id), type(geom).__name__ if geom is not None else "Unknown", idx, layer


def _check_validity(rows, rules) -> list[Finding]:
    sev = rules["severity"]
    out: list[Finding] = []
    for _obj, geom, oid, otype, _idx, layer in rows:
        if geom is None:
            out.append(Finding(sev, "validity", "Object has no readable geometry.", oid, otype, layer))
            continue
        try:
            ok, log = geom.IsValidWithLog
        except Exception:  # pragma: no cover - defensive; rhino3dm exposes a property
            ok, log = geom.IsValid, ""
        if not ok:
            msg = (log or "").strip() or "Object is not valid (openNURBS gave no message)."
            out.append(Finding(sev, "validity", msg, oid, otype, layer))
    return out


def max_faces_per_edge(mesh) -> int:
    """Largest number of faces sharing one edge, with vertices merged by identical position.

    This is the topological non-manifold test (an edge used by more than two
    faces). It is computed here because rhino3dm 8.35's Mesh.IsManifold(True)
    returned False for a single open triangle, which is manifold.
    """
    verts = mesh.Vertices
    key: dict[int, int] = {}
    pos_to_id: dict[tuple[float, float, float], int] = {}
    for i in range(len(verts)):
        v = verts[i]
        key[i] = pos_to_id.setdefault((v.X, v.Y, v.Z), len(pos_to_id))
    counts: dict[tuple[int, int], int] = {}
    faces = mesh.Faces
    for fi in range(len(faces)):
        a, b, c, d = faces[fi]
        ring = [a, b, c] if c == d else [a, b, c, d]
        ring = [key[i] for i in ring]
        for j in range(len(ring)):
            u, w = ring[j], ring[(j + 1) % len(ring)]
            if u == w:
                continue
            e = (u, w) if u < w else (w, u)
            counts[e] = counts.get(e, 0) + 1
    return max(counts.values(), default=0)


def _check_mesh(rows, rules) -> list[Finding]:
    sev = rules["severity"]
    out: list[Finding] = []
    for _obj, geom, oid, otype, _idx, layer in rows:
        if not isinstance(geom, rhino3dm.Mesh):
            continue
        if rules.get("require_closed", True) and not geom.IsClosed:
            out.append(Finding(sev, "mesh_not_closed", "Mesh is not closed (it has naked edges).", oid, otype, layer))
        if rules.get("require_manifold", True):
            if max_faces_per_edge(geom) > 2:
                out.append(Finding(sev, "mesh_non_manifold",
                                   "Mesh is non-manifold (an edge is shared by more than two faces).",
                                   oid, otype, layer))
    return out


def _check_layers(rows, layers, rules) -> list[Finding]:
    sev = rules["severity"]
    out: list[Finding] = []
    pattern = rules.get("name_pattern") or ""
    if pattern:
        rx = re.compile(pattern)
        for _i, name, full, lid in layers:
            if not rx.search(name):
                out.append(Finding(sev, "layer_name",
                                   f"Layer name {name!r} does not match the profile pattern {pattern}.",
                                   None, "Layer", full))

    used = {row[4] for row in rows}
    if rules.get("flag_empty_layers", True) and layers:
        used_paths = {full for i, _n, full, _id in layers if i in used}
        for _i, _name, full, _lid in layers:
            prefix = full + "::"
            if full in used_paths or any(u.startswith(prefix) for u in used_paths):
                continue
            out.append(Finding(sev, "empty_layer", "Layer has no objects (on it or its sublayers).",
                               None, "Layer", full))

    valid_indexes = {i for i, *_ in layers}
    if rules.get("flag_objects_without_layer", True):
        for _obj, _geom, oid, otype, idx, _layer in rows:
            if idx not in valid_indexes:
                out.append(Finding(sev, "object_without_layer",
                                   f"Object has no layer (layer index {idx}).", oid, otype, None))

    if rules.get("flag_objects_on_default_layer", False):
        names = set(rules.get("default_layer_names", ["Default"]))
        for _obj, _geom, oid, otype, idx, layer in rows:
            if layer is not None and layer in names:
                out.append(Finding(sev, "object_on_default_layer",
                                   f"Object is on the default layer {layer!r}. Move it to a named office layer.",
                                   oid, otype, layer))
    return out


def inspect_model(model, path: str, profile: Profile) -> FileResult:
    res = FileResult(path=path)
    settings = model.Settings
    res.units = unit_name(settings.ModelUnitSystem)
    res.absolute_tolerance = float(settings.ModelAbsoluteTolerance)
    rad = float(settings.ModelAngleToleranceRadians)
    res.angle_tolerance_degrees = round(math.degrees(rad), 9)
    layers = _layer_paths(model)
    rows = list(_object_rows(model, layers))
    res.object_count = len(rows)
    res.layer_count = len(layers)

    findings: list[Finding] = []
    r = profile.rules
    if r["document"].get("enabled", True):
        findings += _check_document(model, r["document"], res)
    if r["validity"].get("enabled", True):
        findings += _check_validity(rows, r["validity"])
    if r["mesh"].get("enabled", False):
        findings += _check_mesh(rows, r["mesh"])
    if r["layers"].get("enabled", True):
        findings += _check_layers(rows, layers, r["layers"])
    # Errors first; otherwise keep the deterministic rule/file order.
    findings.sort(key=lambda f: SEVERITY_ORDER[f.severity])
    res.findings = findings
    return res


def inspect_file(path: str, profile: Profile, fail_on: str = "error") -> FileResult:
    model, bad = _read(path)
    if bad is not None:
        return bad
    res = inspect_model(model, path, profile)
    status_threshold = "error" if fail_on == "never" else fail_on
    res.status = "fail" if res.meets(status_threshold) else "pass"
    return res


def inspect_paths(paths: Iterable[str], profile: Profile, fail_on: str = "error") -> RunResult:
    """Inspect files and folders. Raises NoFilesError / PathNotFoundError."""
    files, folder_mode = discover(paths)
    results = []
    for f in files:
        try:
            results.append(inspect_file(f, profile, fail_on))
        except Exception as exc:  # never let one bad file stop a folder run
            results.append(_unreadable(
                f, f"inspection stopped on this file ({type(exc).__name__}: {exc}). "
                   "Check that the file opens in Rhino, and report this case if it does."))
    return RunResult(files=results, profile=profile, fail_on=fail_on, folder_mode=folder_mode)
