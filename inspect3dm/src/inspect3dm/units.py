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
