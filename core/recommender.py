# -*- coding: utf-8 -*-
"""CRS distortion evaluator and purpose-based projection recommender for zero2truesize."""
from __future__ import annotations

import math
from contextlib import suppress

from .distortion import SHAPE_BANDS, AREA_BANDS, _grade
from .geomath import clamp

# Standard cartographic projection catalog with analytic / standard properties
PROJECTION_CATALOG: list[dict] = [
    {
        "auth_id": "EPSG:8857",
        "name": "Equal Earth (Modern Global Equal-Area)",
        "family": "Equal-Area",
        "scope": "Global Thematic & Choropleth Maps",
        "lat_min": -90.0, "lat_max": 90.0,
        "areal_formula": lambda lat: 1.0,  # Strict Equal-Area
        "angular_deg": lambda lat: math.degrees(math.radians(abs(lat)) * 0.36),
    },
    {
        "auth_id": "ESRI:54009",
        "name": "World Mollweide",
        "family": "Equal-Area",
        "scope": "Global Thematic & Density Maps",
        "lat_min": -90.0, "lat_max": 90.0,
        "areal_formula": lambda lat: 1.0,  # Strict Equal-Area
        "angular_deg": lambda lat: math.degrees(math.radians(abs(lat)) * 0.45),
    },
    {
        "auth_id": "ESRI:54012",
        "name": "World Eckert IV",
        "family": "Equal-Area",
        "scope": "Equal-Area World Thematic Mapping",
        "lat_min": -90.0, "lat_max": 90.0,
        "areal_formula": lambda lat: 1.0,  # Strict Equal-Area
        "angular_deg": lambda lat: math.degrees(math.radians(abs(lat)) * 0.4),
    },
    {
        "auth_id": "ESRI:54034",
        "name": "World Cylindrical Equal Area (Gall-Peters)",
        "family": "Equal-Area",
        "scope": "Area-Honest Thematic Comparison",
        "lat_min": -85.0, "lat_max": 85.0,
        "areal_formula": lambda lat: 1.0,  # Strict Equal-Area
        "angular_deg": lambda lat: math.degrees(2.0 * math.asin(clamp(abs(math.cos(math.radians(clamp(lat, -85, 85))) ** 2 - 1.0) / (math.cos(math.radians(clamp(lat, -85, 85))) ** 2 + 1.0), 0, 1))),
    },
    {
        "auth_id": "ESRI:54042",
        "name": "World Winkel Tripel (NGS Standard)",
        "family": "Compromise",
        "scope": "General Reference World Maps",
        "lat_min": -90.0, "lat_max": 90.0,
        "areal_formula": lambda lat: 1.0 + (abs(lat) / 90.0) ** 2 * 0.42,
        "angular_deg": lambda lat: min(32.0, abs(lat) * 0.34),
    },
    {
        "auth_id": "ESRI:54030",
        "name": "World Robinson",
        "family": "Compromise",
        "scope": "World Atlas & Education",
        "lat_min": -90.0, "lat_max": 90.0,
        "areal_formula": lambda lat: 1.0 + (abs(lat) / 90.0) ** 2 * 0.6,
        "angular_deg": lambda lat: min(40.0, abs(lat) * 0.4),
    },
    {
        "auth_id": "EPSG:3857",
        "name": "WGS 84 / Pseudo-Mercator (Web Mercator)",
        "family": "Conformal",
        "scope": "Web Navigation / Basemaps",
        "lat_min": -85.0, "lat_max": 85.0,
        "areal_formula": lambda lat: 1.0 / (math.cos(math.radians(clamp(lat, -85, 85))) ** 2),
        "angular_deg": 0.0,
    },
    {
        "auth_id": "EPSG:4326",
        "name": "WGS 84 (Plate Carrée / Equirectangular)",
        "family": "Equidistant",
        "scope": "Raw Geographic Grid",
        "lat_min": -90.0, "lat_max": 90.0,
        "areal_formula": lambda lat: 1.0 / math.cos(math.radians(clamp(lat, -89.9, 89.9))),
        "angular_deg": lambda lat: math.degrees(2.0 * math.asin(clamp((1.0 - math.cos(math.radians(clamp(lat, -89.9, 89.9)))) / (1.0 + math.cos(math.radians(clamp(lat, -89.9, 89.9)))), 0, 1))),
    },
    {
        "auth_id": "EPSG:3035",
        "name": "ETRS89-extended / LAEA Europe",
        "family": "Equal-Area",
        "scope": "European Statistical & Census Mapping",
        "lat_min": 30.0, "lat_max": 75.0,
        "lon_min": -25.0, "lon_max": 45.0,
        "regional": True,
        "areal_formula": lambda lat: 1.0,  # Equal-Area
        "angular_deg": lambda lat: abs(lat - 52.0) * 0.25,
    },
    {
        "auth_id": "EPSG:5637",
        "name": "TUREF / TM30 (Türkiye Regional Conformal)",
        "family": "Conformal",
        "scope": "Türkiye & Aegean Cadastral / Urban Planning",
        "lat_min": 34.0, "lat_max": 43.5,
        "lon_min": 25.0, "lon_max": 45.5,
        "regional": True,
        "areal_formula": lambda lat: 1.0008 + abs(lat - 39.0) * 0.0002,
        "angular_deg": 0.0,
    },
    {
        "auth_id": "EPSG:3413",
        "name": "WGS 84 / NSIDC Polar Stereographic North",
        "family": "Conformal",
        "scope": "Arctic & High-Latitude Mapping",
        "lat_min": 55.0, "lat_max": 90.0,
        "regional": True,
        "areal_formula": lambda lat: ((1.0 + math.sin(math.radians(70.0))) / (1.0 + math.sin(math.radians(clamp(lat, 50.0, 90.0))))) ** 2,
        "angular_deg": 0.0,
    },
]


def evaluate_projection_for_extent(proj: dict, min_lat: float, max_lat: float,
                                   samples: int = 7) -> dict:
    """Evaluate distortion metrics of a projection over a given latitude range."""
    lats = [min_lat + i * (max_lat - min_lat) / max(1, samples - 1) for i in range(samples)]
    areals = []
    omegas = []

    for lat in lats:
        # Areal factor
        areal_fn = proj.get("areal_formula")
        if callable(areal_fn):
            with suppress(Exception):
                a_val = float(areal_fn(lat))
                if math.isfinite(a_val) and a_val > 0:
                    areals.append(a_val)
        # Angular deformation
        ang_fn = proj.get("angular_deg")
        if callable(ang_fn):
            with suppress(Exception):
                o_val = float(ang_fn(lat))
                if math.isfinite(o_val):
                    omegas.append(o_val)
        elif isinstance(ang_fn, (int, float)):
            omegas.append(float(ang_fn))

    if not areals:
        areals = [1.0]
    if not omegas:
        omegas = [0.0]

    area_spread = max(areals) / max(1e-6, min(areals))
    max_omega = max(omegas)
    area_grade = _grade(area_spread, AREA_BANDS)
    shape_grade = _grade(max_omega, SHAPE_BANDS)

    # Combined score out of 100
    area_penalty = min(50.0, (area_spread - 1.0) * 15.0)
    shape_penalty = min(50.0, max_omega * 0.8)
    honesty_score = max(0, min(100, int(round(100.0 - area_penalty - shape_penalty))))

    return {
        "auth_id": proj["auth_id"],
        "name": proj["name"],
        "family": proj["family"],
        "scope": proj["scope"],
        "regional": bool(proj.get("regional", False)),
        "area_spread": round(area_spread, 2),
        "max_omega_deg": round(max_omega, 1),
        "area_grade": area_grade,
        "shape_grade": shape_grade,
        "score": honesty_score,
    }


def recommend_projections(min_lat: float = -60.0, max_lat: float = 70.0,
                          purpose: str = "All",
                          min_lon: float | None = None,
                          max_lon: float | None = None) -> list[dict]:
    """Return ranked projection recommendations for a given latitude/longitude extent and purpose."""
    results = []
    lat_span = abs(max_lat - min_lat)
    for proj in PROJECTION_CATALOG:
        p_min_lat = float(proj.get("lat_min", -90.0))
        p_max_lat = float(proj.get("lat_max", 90.0))
        is_regional = bool(proj.get("regional", False))

        if is_regional:
            # Regional CRS only applies if extent fits reasonably within its latitude band
            if min_lat < p_min_lat - 6.0 or max_lat > p_max_lat + 6.0 or lat_span > (p_max_lat - p_min_lat + 12.0):
                continue
            if min_lon is not None and max_lon is not None and "lon_min" in proj and "lon_max" in proj:
                if min_lon < float(proj["lon_min"]) - 8.0 or max_lon > float(proj["lon_max"]) + 8.0:
                    continue

        eval_res = evaluate_projection_for_extent(proj, min_lat, max_lat)
        if purpose != "All" and eval_res["family"].lower() != purpose.lower():
            continue
        results.append(eval_res)

    # Sort by overall honesty score descending, breaking ties by lower area_spread then lower max_omega_deg
    results.sort(key=lambda r: (r["score"], -r["area_spread"], -r["max_omega_deg"]), reverse=True)
    return results
