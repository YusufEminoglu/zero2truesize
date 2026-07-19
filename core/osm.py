# -*- coding: utf-8 -*-
"""Pure helpers for the bounded OpenStreetMap acquisition workflow."""
from __future__ import annotations

import math

from .geomath import haversine_km

MAX_SIDE_KM = 6.0
MAX_AREA_KM2 = 25.0


def validate_bbox(south: float, west: float, north: float, east: float) -> dict:
    """Validate a WGS84 bbox and return its approximate physical dimensions."""
    values = (south, west, north, east)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("The map canvas has no valid download area.")
    if south >= north or west >= east:
        raise ValueError("The map canvas has no valid download area.")
    if south < -85.0 or north > 85.0:
        raise ValueError("OSM download is limited to latitudes between 85 S and 85 N.")
    if west < -180.0 or east > 180.0:
        raise ValueError("Downloads crossing the antimeridian are not supported.")
    middle_lat = (south + north) / 2.0
    middle_lon = (west + east) / 2.0
    width_km = haversine_km(middle_lat, west, middle_lat, east)
    height_km = haversine_km(south, middle_lon, north, middle_lon)
    area_km2 = width_km * height_km
    if (width_km > MAX_SIDE_KM or height_km > MAX_SIDE_KM
            or area_km2 > MAX_AREA_KM2):
        raise ValueError(
            f"Zoom in before downloading. Current view is {width_km:.1f} x "
            f"{height_km:.1f} km ({area_km2:.1f} km2); maximum is "
            f"{MAX_SIDE_KM:g} x {MAX_SIDE_KM:g} km and {MAX_AREA_KM2:g} km2.")
    return {"width_km": width_km, "height_km": height_km, "area_km2": area_km2}


def overpass_query(south: float, west: float, north: float, east: float) -> str:
    """Build the deliberately bounded query for useful true-size polygons."""
    validate_bbox(south, west, north, east)
    box = f"{south:.7f},{west:.7f},{north:.7f},{east:.7f}"
    selectors = (
        '["boundary"="administrative"]',
        '["building"]',
        '["landuse"]',
        '["leisure"]',
        '["natural"]',
        '["water"]',
        '["waterway"="riverbank"]',
    )
    lines = ["[out:xml][timeout:60][maxsize:134217728];", "("]
    for selector in selectors:
        lines.append(f"  way{selector}({box});")
        lines.append(f"  relation{selector}({box});")
    lines.extend((");", "(._;>;);", "out body qt;"))
    return "\n".join(lines)
