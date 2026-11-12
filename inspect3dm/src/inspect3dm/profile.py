"""Rule profiles: loading, merging, and validation.

A profile is a small TOML file. Built-in profiles are ``default`` and
``strict``; an office profile lists only the keys it changes and inherits
the rest via ``[profile] extends = "default"`` (the default).
"""

from __future__ import annotations

import copy
import re
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on Python 3.10 only
    import tomli as tomllib

BUILTIN_PROFILES = ("default", "strict")
SEVERITIES = ("error", "warning")

# Schema: section -> key -> (accepted python types, description of type)
_SCHEMA: dict[str, dict[str, tuple[tuple[type, ...], str]]] = {
    "validity": {
        "enabled": ((bool,), "true or false"),
        "severity": ((str,), '"error" or "warning"'),
    },
    "document": {
        "enabled": ((bool,), "true or false"),
        "severity": ((str,), '"error" or "warning"'),
        "allowed_units": ((list,), "a list of unit names"),
        "absolute_tolerance_min": ((int, float), "a number"),
        "absolute_tolerance_max": ((int, float), "a number"),
        "angle_tolerance_min_degrees": ((int, float), "a number"),
        "angle_tolerance_max_degrees": ((int, float), "a number"),
    },
    "mesh": {
        "enabled": ((bool,), "true or false"),
        "severity": ((str,), '"error" or "warning"'),
        "require_closed": ((bool,), "true or false"),
        "require_manifold": ((bool,), "true or false"),
    },
    "layers": {
        "enabled": ((bool,), "true or false"),
        "severity": ((str,), '"error" or "warning"'),
        "name_pattern": ((str,), "a regular expression string"),
        "flag_empty_layers": ((bool,), "true or false"),
        "flag_objects_without_layer": ((bool,), "true or false"),
        "flag_objects_on_default_layer": ((bool,), "true or false"),
        "default_layer_names": ((list,), "a list of layer names"),
    },
}

# Unit names accepted in allowed_units (as shown in reports).
KNOWN_UNITS = (
    "none", "angstroms", "nanometers", "microns", "millimeters", "centimeters",
    "decimeters", "meters", "dekameters", "hectometers", "kilometers",
    "megameters", "gigameters", "microinches", "mils", "inches", "feet",
    "yards", "miles", "printer points", "printer picas", "nautical miles",
    "astronomical units", "light years", "parsecs", "custom units", "unset",
)


class ProfileError(Exception):
    """A profile file could not be used. The message is user-facing."""


@dataclass(frozen=True)
class Profile:
    name: str
    source: str  # "built-in" or the file path
    rules: dict[str, dict[str, Any]]

    def rule(self, section: str) -> dict[str, Any]:
        return self.rules[section]


def _read_builtin(name: str) -> dict[str, Any]:
    text = resources.files("inspect3dm").joinpath("profiles", f"{name}.toml").read_text("utf-8")
    return tomllib.loads(text)


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for section, values in override.items():
        out.setdefault(section, {}).update(copy.deepcopy(values))
    return out


def _resolve_builtin(name: str, seen: tuple[str, ...] = ()) -> tuple[str, dict[str, Any]]:
    data = _read_builtin(name)
    meta = data.get("profile", {})
    rules = data.get("rules", {})
    parent = meta.get("extends")
    if parent and parent not in seen:
        _, base = _resolve_builtin(parent, seen + (name,))
        rules = _merge(base, rules)
    return meta.get("name", name), rules


def _validate(rules: dict[str, Any], where: str) -> None:
    for section, values in rules.items():
        if section not in _SCHEMA:
            known = ", ".join(f"[rules.{s}]" for s in _SCHEMA)
            raise ProfileError(
                f"Profile {where}: unknown section [rules.{section}]. Known sections: {known}."
            )
        if not isinstance(values, dict):
            raise ProfileError(f"Profile {where}: [rules.{section}] must be a table.")
        for key, value in values.items():
            spec = _SCHEMA[section].get(key)
            if spec is None:
                known = ", ".join(_SCHEMA[section])
                raise ProfileError(
                    f"Profile {where}: unknown key '{key}' in [rules.{section}]. Known keys: {known}."
                )
            types, desc = spec
            # bool is a subclass of int; do not accept true/false as a number.
            if isinstance(value, bool) and bool not in types:
                raise ProfileError(
                    f"Profile {where}: [rules.{section}] {key} must be {desc}, not {value!r}."
                )
            if not isinstance(value, types):
                raise ProfileError(
                    f"Profile {where}: [rules.{section}] {key} must be {desc}, not {value!r}."
                )
            if key == "severity" and value not in SEVERITIES:
                raise ProfileError(
                    f"Profile {where}: [rules.{section}] severity must be \"error\" or \"warning\", not {value!r}."
                )
            if key in ("allowed_units", "default_layer_names"):
                if not all(isinstance(v, str) for v in value):
                    raise ProfileError(
                        f"Profile {where}: [rules.{section}] {key} must contain only strings."
                    )
            if key == "allowed_units":
                for unit in value:
                    if unit.lower() not in KNOWN_UNITS:
                        raise ProfileError(
                            f"Profile {where}: unknown unit '{unit}' in allowed_units. "
                            f"Use names such as \"millimeters\", \"meters\", \"inches\", \"feet\"."
                        )
            if key == "name_pattern":
                try:
                    re.compile(value)
                except re.error as exc:
                    raise ProfileError(
                        f"Profile {where}: [rules.layers] name_pattern is not a valid regular expression ({exc})."
                    ) from None
            if key.endswith(("_min", "_max", "_degrees")) and value < 0:
                raise ProfileError(f"Profile {where}: [rules.{section}] {key} must not be negative.")


def _check_ranges(rules: dict[str, Any], where: str) -> None:
    doc = rules.get("document", {})
    for lo_key, hi_key in (
        ("absolute_tolerance_min", "absolute_tolerance_max"),
        ("angle_tolerance_min_degrees", "angle_tolerance_max_degrees"),
    ):
        lo, hi = doc.get(lo_key), doc.get(hi_key)
        if lo is not None and hi is not None and lo > hi:
            raise ProfileError(
                f"Profile {where}: {lo_key} ({lo}) is greater than {hi_key} ({hi}) in [rules.document]."
            )


def load_profile(spec: str | None) -> Profile:
    """Load a built-in profile by name, or a TOML profile file by path."""
    if spec is None or spec in BUILTIN_PROFILES:
        name = spec or "default"
        pname, rules = _resolve_builtin(name)
        return Profile(name=pname, source="built-in", rules=rules)

    path = Path(spec)
    where = f"'{spec}'"
    if not path.exists():
        raise ProfileError(
            f"Profile file {where} was not found. Check the path, or use a built-in profile: "
            + ", ".join(BUILTIN_PROFILES) + "."
        )
    if path.is_dir():
        raise ProfileError(f"Profile {where} is a folder. Pass a .toml profile file.")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ProfileError(f"Profile file {where} could not be read ({exc.strerror}). Check the file permissions.") from None
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        raise ProfileError(f"Profile {where} is not UTF-8 text. Save it as a UTF-8 .toml file.") from None
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"Profile {where} is not valid TOML: {exc}. Fix the file and run again.") from None

    unknown_top = [k for k in data if k not in ("profile", "rules")]
    if unknown_top:
        raise ProfileError(
            f"Profile {where}: unknown top-level key '{unknown_top[0]}'. Use [profile] and [rules.<name>] tables."
        )
    meta = data.get("profile", {})
    if not isinstance(meta, dict):
        raise ProfileError(f"Profile {where}: [profile] must be a table.")
    for key in meta:
        if key not in ("name", "extends"):
            raise ProfileError(f"Profile {where}: unknown key '{key}' in [profile]. Known keys: name, extends.")
    extends = meta.get("extends", "default")
    if extends not in BUILTIN_PROFILES:
        raise ProfileError(
            f"Profile {where}: extends = {extends!r} is not a built-in profile. Use one of: "
            + ", ".join(BUILTIN_PROFILES) + "."
        )
    name = meta.get("name", path.stem)
    if not isinstance(name, str) or not name:
        raise ProfileError(f"Profile {where}: [profile] name must be a non-empty string.")
    rules = data.get("rules", {})
    if not isinstance(rules, dict):
        raise ProfileError(f"Profile {where}: 'rules' must be a set of [rules.<name>] tables.")
    _validate(rules, where)
    _, base = _resolve_builtin(extends)
    merged = _merge(base, rules)
    _check_ranges(merged, where)
    return Profile(name=name, source=str(spec), rules=merged)
