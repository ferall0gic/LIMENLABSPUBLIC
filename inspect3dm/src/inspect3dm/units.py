"""Human-readable numbers and unit names (no raw radians, no scientific notation)."""

from __future__ import annotations

import math
import re
from decimal import Decimal


def unit_name(unit_system) -> str:
    """'Millimeters' -> 'millimeters', 'PrinterPoints' -> 'printer points', 'None' -> 'none'."""
    raw = getattr(unit_system, "name", str(unit_system).split(".")[-1])
    return re.sub(r"(?<!^)(?=[A-Z])", " ", raw).lower()


def unit_display(name: str) -> str:
    return "no units" if name == "none" else name


def decimal_str(value: float) -> str:
    """Plain decimal form: 1e-07 -> '0.0000001', 0.01 -> '0.01', 10.0 -> '10'."""
    if value is None or not math.isfinite(value):
        return str(value)
    d = Decimal(repr(float(value))).normalize()
    text = format(d, "f")
    return text


def degrees_str(value_degrees: float) -> str:
    """Angle in degrees, rounded to 6 significant decimals, with the unit."""
    rounded = round(float(value_degrees), 6)
    text = decimal_str(rounded)
    return f"{text} degree" + ("" if text == "1" else "s")


def length_str(value: float, unit: str) -> str:
    return f"{decimal_str(value)} {unit_display(unit)}"


# Millimeters per model unit, by report unit name (see unit_name). Values are
# exact SI / international-inch definitions; astronomical units, light years and
# parsecs use the IAU values. "none", "unset" and "custom units" are absent on
# purpose: a length in those units cannot be converted, so mm-based rules skip.
_MM_PER_UNIT = {
    "angstroms": 1e-7,
    "nanometers": 1e-6,
    "microns": 1e-3,
    "millimeters": 1.0,
    "centimeters": 10.0,
    "decimeters": 100.0,
    "meters": 1000.0,
    "dekameters": 1e4,
    "hectometers": 1e5,
    "kilometers": 1e6,
    "megameters": 1e9,
    "gigameters": 1e12,
    "microinches": 25.4e-6,
    "mils": 0.0254,
    "inches": 25.4,
    "feet": 304.8,
    "yards": 914.4,
    "miles": 1609344.0,
    "printer points": 25.4 / 72.0,
    "printer picas": 25.4 / 6.0,
    "nautical miles": 1852000.0,
    "astronomical units": 1.495978707e14,
    "light years": 9.4607304725808e18,
    "parsecs": 3.0856775814913673e19,
}


def mm_per_unit(unit: str | None) -> float | None:
    """Millimeters in one model unit, or None when the unit cannot be converted."""
    if unit is None:
        return None
    return _MM_PER_UNIT.get(unit.lower())


def sig_str(value: float, digits: int = 4) -> str:
    """Plain decimal rounded to `digits` significant figures (no scientific notation)."""
    if value is None or not math.isfinite(value):
        return str(value)
    if value == 0:
        return "0"
    from math import floor, log10
    places = digits - 1 - int(floor(log10(abs(value))))
    return decimal_str(round(float(value), places))
