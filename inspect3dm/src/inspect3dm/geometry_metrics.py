"""Deterministic length bounds for curves read with rhino3dm.

rhino3dm (8.x) does not expose ``Curve.GetLength``. Instead of an estimate
with an unknown error, this module returns two bounds that bracket the true
arc length of a curve:

- lower bound: the length of a polyline through points sampled on the curve
  (a chord can never be longer than the arc it spans);
- upper bound: the length of the NURBS control polygon. Knot insertion moves
  control points onto the segments of the previous polygon (for positive
  weights), so the polygon length never increases and converges to the curve
  length; the original polygon is therefore an upper bound.

If any weight is not positive the upper bound is not guaranteed and ``hi`` is
returned as ``None``.
"""

from __future__ import annotations

import math

from ._rh import control_point_xyzw


def _dist(a, b) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _xyz(p) -> tuple[float, float, float]:
    return (p.X, p.Y, p.Z)


def sample_count(curve) -> int:
    try:
        spans = int(curve.SpanCount)
    except Exception:
        spans = 1
    return max(16, 8 * max(spans, 1))


def chord_length(curve, n: int) -> float:
    """Polyline length through n+1 evenly spaced parameters over the curve domain."""
    dom = curve.Domain
    t0, t1 = dom.T0, dom.T1
    prev = _xyz(curve.PointAt(t0))
    total = 0.0
    for i in range(1, n + 1):
        cur = _xyz(curve.PointAt(t0 + (t1 - t0) * i / n))
        total += _dist(prev, cur)
        prev = cur
    return total


def control_polygon_length(nurbs) -> float | None:
    """Euclidean control-polygon length of a NurbsCurve, or None if a weight <= 0."""
    pts = nurbs.Points
    prev = None
    total = 0.0
    for i in range(len(pts)):
        x, y, z, w = control_point_xyzw(pts[i])
        if not (w > 0):
            return None
        cur = (x / w, y / w, z / w)  # rhino3dm returns homogeneous (x*w, y*w, z*w, w)
        if prev is not None:
            total += _dist(prev, cur)
        prev = cur
    return total


def curve_length_bounds(curve, refine: int = 1) -> tuple[float, float | None]:
    """(lo, hi) with lo <= true length <= hi. hi is None when it cannot be bounded.

    ``refine`` multiplies the number of samples used for the lower bound.
    Raises if the curve cannot be evaluated; callers report that as
    "could not measure".
    """
    lo = chord_length(curve, sample_count(curve) * max(1, refine))
    nurbs = curve.ToNurbsCurve()
    hi = control_polygon_length(nurbs) if nurbs is not None else None
    if hi is not None and hi < lo:  # floating-point noise on straight curves
        hi = lo
    return lo, hi


def midpoint(curve) -> tuple[float, float, float]:
    dom = curve.Domain
    return _xyz(curve.PointAt((dom.T0 + dom.T1) / 2.0))
