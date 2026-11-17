"""Core inspection: read .3dm files with rhino3dm and apply profile rules."""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import rhino3dm

from . import _rh
from .geometry_metrics import curve_length_bounds, midpoint
from .profile import Profile
from .units import degrees_str, length_str, mm_per_unit, sig_str, unit_name, unit_display

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
# "info" findings never count as errors or warnings and never fail a run.

# Rhino commands a user can run next, per finding rule (pointers only).
NEXT_STEPS = {
    "validity": ("Check", "SelBadObjects"),
    "mesh_not_closed": ("CheckMesh", "MeshRepair"),
    "mesh_non_manifold": ("CheckMesh", "MeshRepair"),
    "short_edges": ("ShowEdges", "MergeAllEdges", "RebuildEdges"),
    "short_edges_unmeasured": ("ShowEdges",),
    "extents": ("Zoom", "Move"),
}


@dataclass(frozen=True)
class Finding:
    severity: str  # "error" | "warning" | "info"
    rule: str
    message: str
    object_id: str | None = None
    object_type: str | None = None
    layer: str | None = None
    # v0.2 measured-value fields; present in JSON only when set.
    measured: float | None = None   # in model units
    threshold: float | None = None  # in model units
    units: str | None = None
    certainty: str | None = None    # "certain" | "uncertain" | "near_threshold"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "severity": self.severity,
            "rule": self.rule,
            "object_id": self.object_id,
            "object_type": self.object_type,
            "layer": self.layer,
            "message": self.message,
        }
        for key in ("measured", "threshold", "units", "certainty"):
            value = getattr(self, key)
            if value is not None:
                d[key] = value
        return d


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
            return self.errors > 0 or self.warnings > 0
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
        if self.fail_on == "never" and any(f.errors or f.warnings for f in self.files):
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
    model = _rh.read_model(rhino3dm, str(p))
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


def _tidy(value: float) -> float:
    """Round a unit-converted threshold to 9 significant figures for display."""
    return float(f"{value:.9g}")


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
    tsev = rules.get("tolerance_severity") or sev
    lo, hi = rules.get("absolute_tolerance_min"), rules.get("absolute_tolerance_max")
    lo_note = hi_note = ""
    scale = mm_per_unit(unit)
    # An *_mm key replaces the model-unit key on the same side when units are known.
    if scale is not None:
        lo_mm, hi_mm = rules.get("absolute_tolerance_min_mm"), rules.get("absolute_tolerance_max_mm")
        if lo_mm is not None:
            lo, lo_note = lo_mm / scale, ("" if unit == "millimeters" else f" ({sig_str(lo_mm, 6)} mm)")
        if hi_mm is not None:
            hi, hi_note = hi_mm / scale, ("" if unit == "millimeters" else f" ({sig_str(hi_mm, 6)} mm)")
    if tol is not None:
        if lo is not None and tol < lo:
            out.append(Finding(tsev, "tolerance_range",
                               f"Absolute tolerance {length_str(tol, unit)} is below the configured minimum of "
                               f"{length_str(_tidy(lo), unit)}{lo_note}."))
        elif hi is not None and tol > hi:
            out.append(Finding(tsev, "tolerance_range",
                               f"Absolute tolerance {length_str(tol, unit)} is above the configured maximum of "
                               f"{length_str(_tidy(hi), unit)}{hi_note}."))

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
        yield obj, geom, _rh.object_id(attrs), type(geom).__name__ if geom is not None else "Unknown", idx, layer


def _tool_error(check: str, exc: BaseException, oid, otype, layer) -> Finding:
    """Info finding for a check that could not be evaluated on one object.

    Replaces silent skips: the user sees that the object was not checked.
    """
    return Finding("info", "tool_error",
                   f"Could not evaluate {check} for this object ({type(exc).__name__}); it was not checked. "
                   "Please report this case with your rhino3dm version.", oid, otype, layer)


def _check_validity(rows, rules) -> list[Finding]:
    sev = rules["severity"]
    out: list[Finding] = []
    for _obj, geom, oid, otype, _idx, layer in rows:
        if geom is None:
            out.append(Finding(sev, "validity", "Object has no readable geometry.", oid, otype, layer))
            continue
        try:
            ok, log = _rh.validity(geom)
        except Exception as exc:
            out.append(_tool_error("validity", exc, oid, otype, layer))
            continue
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


# ---------------------------------------------------------------- v0.2 rules (mm-based)

def _fmt_pt(p) -> str:
    return "(" + ", ".join(sig_str(c, 6) for c in p) + ")"


def _measurable_curves(geom, include_curves: bool):
    """Yield (label, curve) pairs to measure, or (label, None) when a part cannot be read."""
    if isinstance(geom, rhino3dm.Extrusion):
        try:
            geom = geom.ToBrep(False)
        except Exception:
            geom = None
        if geom is None:
            yield "extrusion (could not convert to a Brep)", None
            return
    if isinstance(geom, rhino3dm.Brep):
        edges = geom.Edges
        for i in range(len(edges)):
            try:
                yield f"edge {i}", edges[i]
            except Exception:
                yield f"edge {i}", None
        return
    if not include_curves or not isinstance(geom, rhino3dm.Curve):
        return
    if isinstance(geom, rhino3dm.PolyCurve):
        for i in range(geom.SegmentCount):
            yield f"segment {i}", geom.SegmentCurve(i)
        return
    if isinstance(geom, rhino3dm.PolylineCurve):
        n = geom.PointCount
        if n > 2:
            for i in range(n - 1):
                a, b = geom.Point(i), geom.Point(i + 1)
                yield f"segment {i}", rhino3dm.LineCurve(a, b)
            return
    yield "curve", geom


def _check_short_edges(rows, rules, scale: float, unit: str) -> list[Finding]:
    sev = rules["severity"]
    min_mm = float(rules.get("min_length_mm", 0.79375))
    band = float(rules.get("near_band", 0.10))
    include_curves = rules.get("include_curves", True)
    lim = min_mm / scale          # model units
    lim_band = lim * (1.0 + band)
    out: list[Finding] = []
    for _obj, geom, oid, otype, _idx, layer in rows:
        if geom is None:
            continue
        for label, crv in _measurable_curves(geom, include_curves):
            if crv is None:
                out.append(Finding("warning", "short_edges_unmeasured",
                                   f"{label.capitalize()} could not be read, so its length was not checked.",
                                   oid, otype, layer))
                continue
            try:
                lo, hi = curve_length_bounds(crv)
                if lo < lim_band:
                    lo, hi = curve_length_bounds(crv, refine=4)
                mid = midpoint(crv)
            except Exception as exc:
                out.append(Finding("warning", "short_edges_unmeasured",
                                   f"{label.capitalize()} could not be measured ({type(exc).__name__}), "
                                   "so its length was not checked.", oid, otype, layer))
                continue
            if lo >= lim_band:
                continue
            where = f"Midpoint {_fmt_pt(mid)}."
            if hi is not None and hi < lim:
                msg = (f"{label.capitalize()} is {_len_with_mm(lo, scale, unit)} long, "
                       f"shorter than the minimum of {sig_str(min_mm, 6)} mm. {where}")
                out.append(Finding(sev, "short_edges", msg, oid, otype, layer,
                                   measured=_round(lo), threshold=_round(lim), units=unit, certainty="certain"))
            elif lo < lim:
                hi_txt = "an unbounded length" if hi is None else f"{sig_str(hi * scale)} mm"
                msg = (f"{label.capitalize()} length is between {sig_str(lo * scale)} mm and {hi_txt}, "
                       f"so it may be shorter than the minimum of {sig_str(min_mm, 6)} mm. {where}")
                out.append(Finding(sev, "short_edges", msg, oid, otype, layer,
                                   measured=_round(lo), threshold=_round(lim), units=unit, certainty="uncertain"))
            else:
                msg = (f"{label.capitalize()} is about {sig_str(lo * scale)} mm long, within "
                       f"{sig_str(band * 100)}% above the minimum of {sig_str(min_mm, 6)} mm. {where}")
                out.append(Finding("warning", "short_edges", msg, oid, otype, layer,
                                   measured=_round(lo), threshold=_round(lim), units=unit,
                                   certainty="near_threshold"))
    return out


def _len_with_mm(value: float, scale: float, unit: str) -> str:
    """'0.0005 meters (0.5 mm)', or just '0.5 millimeters' for mm files."""
    text = length_str(_round(value), unit)
    return text if unit == "millimeters" else f"{text} ({sig_str(value * scale)} mm)"


def _round(value: float) -> float:
    return float(f"{value:.9g}")


def _check_extents(rows, rules, scale: float, unit: str) -> list[Finding]:
    sev = rules["severity"]
    max_d_mm = float(rules.get("max_distance_from_origin_mm", 16093440.0))
    max_t_mm = float(rules.get("max_total_extent_mm", 32186880.0))
    max_d, max_t = max_d_mm / scale, max_t_mm / scale
    out: list[Finding] = []
    union = None
    for _obj, geom, oid, otype, _idx, layer in rows:
        if geom is None:
            continue
        try:
            bb = _rh.bbox(geom)
        except Exception as exc:
            out.append(_tool_error("extents", exc, oid, otype, layer))
            continue
        if bb is None or not bb.IsValid:
            continue
        lo, hi = bb.Min, bb.Max
        far = math.sqrt(sum(max(abs(a), abs(b)) ** 2 for a, b in ((lo.X, hi.X), (lo.Y, hi.Y), (lo.Z, hi.Z))))
        if far > max_d:
            out.append(Finding(
                sev, "extents",
                f"Object reaches {length_str(_round(far), unit)} ({sig_str(far * scale / 1e6)} km) from the "
                f"world origin, beyond the limit of {sig_str(max_d_mm / 1e6)} km. Bounding box "
                f"{_fmt_pt((lo.X, lo.Y, lo.Z))} to {_fmt_pt((hi.X, hi.Y, hi.Z))}.",
                oid, otype, layer, measured=_round(far), threshold=_round(max_d), units=unit, certainty="certain"))
        if union is None:
            union = [lo.X, lo.Y, lo.Z, hi.X, hi.Y, hi.Z]
        else:
            union = [min(union[0], lo.X), min(union[1], lo.Y), min(union[2], lo.Z),
                     max(union[3], hi.X), max(union[4], hi.Y), max(union[5], hi.Z)]
    if union is not None:
        diag = math.sqrt((union[3] - union[0]) ** 2 + (union[4] - union[1]) ** 2 + (union[5] - union[2]) ** 2)
        if diag > max_t:
            out.append(Finding(
                sev, "extents",
                f"Model extents span {length_str(_round(diag), unit)} ({sig_str(diag * scale / 1e6)} km, bounding-box "
                f"diagonal), beyond the limit of {sig_str(max_t_mm / 1e6)} km. Look for stray objects far from the rest.",
                None, "Model", None, measured=_round(diag), threshold=_round(max_t), units=unit, certainty="certain"))
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
    mm_rules = [k for k in ("short_edges", "extents") if r.get(k, {}).get("enabled", False)]
    if mm_rules:
        scale = mm_per_unit(res.units)
        if scale is None:
            what = "The model has no units" if res.units == "none" else f"Model units are {res.units or 'unset'}"
            findings.append(Finding(
                "warning", "mm_rules_skipped",
                f"{what}, so {' and '.join(mm_rules)} "
                "could not be checked (their limits are in millimeters). Set model units in Rhino and run again."))
        else:
            if "short_edges" in mm_rules:
                findings += _check_short_edges(rows, r["short_edges"], scale, res.units)
            if "extents" in mm_rules:
                findings += _check_extents(rows, r["extents"], scale, res.units)
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
