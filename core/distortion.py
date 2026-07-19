# -*- coding: utf-8 -*-
"""Numeric projection-distortion analysis: Tissot parameters from any
lon/lat -> planar transform, plus a playful "honesty report card".

Pure Python: the projection is an injected callable ``project(lon, lat) ->
(x, y)`` (a QgsCoordinateTransform wrapper in production, an analytic
Mercator in the tests). The callable may raise on out-of-domain points;
callers sample defensively.
"""
from __future__ import annotations

import math
from contextlib import suppress

from .geomath import clamp

KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON_EQ = 111.320

AREA_BANDS = [(1.02, "A+"), (1.10, "A"), (1.5, "B"), (2.5, "C"), (5.0, "D"), (12.0, "E")]
SHAPE_BANDS = [(0.5, "A+"), (2.0, "A"), (10.0, "B"), (25.0, "C"), (45.0, "D"), (60.0, "E")]


def jacobian(project, lon: float, lat: float, step_km: float = 1.0) -> tuple[float, float, float, float]:
    """Row-major 2x2 Jacobian of the projection at (lon, lat), in
    projected-units per kilometre of true ground distance."""
    coslat = math.cos(math.radians(clamp(lat, -89.5, 89.5)))
    dlon = step_km / (KM_PER_DEG_LON_EQ * max(1e-6, coslat))
    dlat = step_km / KM_PER_DEG_LAT
    x0, y0 = project(lon, lat)
    xe, ye = project(lon + dlon, lat)
    xn, yn = project(lon, lat + dlat)
    return (
        (xe - x0) / step_km, (xn - x0) / step_km,
        (ye - y0) / step_km, (yn - y0) / step_km,
    )


def singular_values(jac: tuple[float, float, float, float]) -> tuple[float, float]:
    """Singular values (a >= b) of a 2x2 matrix — the Tissot semi-axes."""
    a, b, c, d = jac
    e = (a + d) / 2.0
    f = (a - d) / 2.0
    g = (c + b) / 2.0
    h = (c - b) / 2.0
    q = math.hypot(e, h)
    r = math.hypot(f, g)
    return q + r, abs(q - r)


def tissot(project, lon: float, lat: float, step_km: float = 1.0) -> dict:
    """Local Tissot parameters: semi-axes, areal factor and the maximum
    angular deformation 2*omega (degrees)."""
    axis_a, axis_b = singular_values(jacobian(project, lon, lat, step_km))
    areal = axis_a * axis_b
    if axis_a + axis_b > 0.0:
        omega = 2.0 * math.asin(clamp((axis_a - axis_b) / (axis_a + axis_b), 0.0, 1.0))
    else:
        omega = 0.0
    return {"a": axis_a, "b": axis_b, "areal": areal, "omega_deg": math.degrees(omega)}


def relative_areal(project, lon: float, lat: float, ref_lon: float, ref_lat: float) -> float:
    """How many times larger a patch of ground is drawn at (lon, lat) than at
    the reference point, in the given projection."""
    here = tissot(project, lon, lat)["areal"]
    ref = tissot(project, ref_lon, ref_lat)["areal"]
    if ref <= 0.0:
        raise ValueError("degenerate projection at reference point")
    return here / ref


def _grade(value: float, bands: list[tuple[float, str]]) -> str:
    for limit, letter in bands:
        if value <= limit:
            return letter
    return "F"


def report_card(project, lats=(0.0, 20.0, 40.0, 60.0, 75.0), lon: float = 15.0) -> dict:
    """Sample the projection along a meridian and grade its honesty.

    Returns rows per sampled latitude plus overall grades and a verdict.
    """
    rows = []
    for lat in lats:
        with suppress(Exception):
            t = tissot(project, lon, lat)
            if t["areal"] > 0.0 and math.isfinite(t["areal"]):
                rows.append({"lat": lat, "areal": t["areal"], "omega_deg": t["omega_deg"]})
    if len(rows) < 2:
        return {"ok": False, "rows": rows}
    areals = [r["areal"] for r in rows]
    area_spread = max(areals) / max(1e-12, min(areals))
    max_omega = max(r["omega_deg"] for r in rows)
    for r in rows:
        r["areal_rel"] = r["areal"] / min(areals)
    area_grade = _grade(area_spread, AREA_BANDS)
    shape_grade = _grade(max_omega, SHAPE_BANDS)
    verdict = _verdict(area_spread, max_omega)
    return {
        "ok": True,
        "rows": rows,
        "area_spread": area_spread,
        "max_omega_deg": max_omega,
        "area_grade": area_grade,
        "shape_grade": shape_grade,
        "verdict": verdict,
    }


def _verdict(area_spread: float, max_omega: float) -> str:
    honest_area = area_spread <= 1.10
    honest_shape = max_omega <= 2.0
    if honest_area and honest_shape:
        return "Remarkably honest around here — enjoy it while it lasts."
    if honest_shape and area_spread > 2.0:
        return ("Conformal at heart: local shapes and angles are kept, "
                "areas are quietly traded away. Greenland approves.")
    if honest_area and max_omega > 10.0:
        return ("Equal-area: sizes are honest, shapes pay the bill — "
                "expect things to look squashed near the edges.")
    if honest_area:
        return "Sizes are honest; shapes bend a little. A solid citizen."
    if honest_shape:
        return "Shapes are kept; areas drift. Read the scale bar with suspicion."
    return ("A compromise projection: everyone chips in a little distortion "
            "so nobody pays the full price.")
