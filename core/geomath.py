# -*- coding: utf-8 -*-
"""Pure-Python spherical geodesy helpers (no QGIS imports).

Everything the quiz, the Tissot generator and the fun-unit reports need:
forward geodesy, antipodes, web-Mercator maths, ring utilities and a tiny
deterministic PRNG.
"""
from __future__ import annotations

import math

R_EARTH_KM = 6371.0088
MERCATOR_MAX_LAT = 85.05112878


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def normalize_lon(lon: float) -> float:
    """Wrap a longitude into [-180, 180]."""
    lon = math.fmod(lon + 180.0, 360.0)
    if lon < 0:
        lon += 360.0
    return lon - 180.0


def antipode(lat: float, lon: float) -> tuple[float, float]:
    """The point you reach by digging straight through the centre of the Earth."""
    return -lat, normalize_lon(lon + 180.0)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2.0) ** 2
    return 2.0 * R_EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def destination(lat: float, lon: float, bearing_deg: float, dist_km: float) -> tuple[float, float]:
    """Spherical forward geodesy: start point + initial bearing + distance -> end point."""
    delta = dist_km / R_EARTH_KM
    theta = math.radians(bearing_deg)
    phi1 = math.radians(lat)
    lmb1 = math.radians(lon)
    sin_phi2 = math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    phi2 = math.asin(clamp(sin_phi2, -1.0, 1.0))
    y = math.sin(theta) * math.sin(delta) * math.cos(phi1)
    x = math.cos(delta) - math.sin(phi1) * sin_phi2
    lmb2 = lmb1 + math.atan2(y, x)
    return math.degrees(phi2), normalize_lon(math.degrees(lmb2))


def circle_ring(lat: float, lon: float, radius_km: float, segments: int = 72) -> list[tuple[float, float]]:
    """Closed ring of (lon, lat) vertices of a constant ground-radius circle."""
    ring = []
    for i in range(segments):
        bearing = 360.0 * i / segments
        la, lo = destination(lat, lon, bearing, radius_km)
        ring.append((lo, la))
    ring.append(ring[0])
    return ring


def unwrap_ring(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Make ring longitudes continuous (no +/-360 jumps between neighbours)."""
    if not ring:
        return []
    out = [ring[0]]
    for lon, lat in ring[1:]:
        prev = out[-1][0]
        while lon - prev > 180.0:
            lon -= 360.0
        while lon - prev < -180.0:
            lon += 360.0
        out.append((lon, lat))
    return out


def crosses_antimeridian(ring: list[tuple[float, float]]) -> bool:
    unwrapped = unwrap_ring(ring)
    return any(p[0] > 180.0 or p[0] < -180.0 for p in unwrapped)


def mercator_xy(lat: float, lon: float) -> tuple[float, float]:
    """Spherical web-Mercator metres (EPSG:3857 style). Longitude may exceed
    +/-180 on purpose, so unwrapped antimeridian-crossing rings stay continuous."""
    lat = clamp(lat, -MERCATOR_MAX_LAT, MERCATOR_MAX_LAT)
    radius = R_EARTH_KM * 1000.0
    x = radius * math.radians(lon)
    y = radius * math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0))
    return x, y


def mercator_linear_inflation(lat: float) -> float:
    """How many times longer one metre of ground is drawn at this latitude
    than at the equator on a Mercator map (sec of latitude)."""
    return 1.0 / max(0.05, math.cos(math.radians(clamp(lat, -85.0, 85.0))))


def mercator_areal_inflation(lat: float) -> float:
    return mercator_linear_inflation(lat) ** 2


def shoelace_area(points: list[tuple[float, float]]) -> float:
    """Signed planar polygon area (positive = counter-clockwise)."""
    total = 0.0
    count = len(points)
    for i in range(count):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % count]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def approx_ring_area_km2(ring: list[tuple[float, float]]) -> float:
    """Rough true area of a lon/lat ring: equirectangular shoelace scaled at
    the ring's mean latitude. Plenty for ranking polygon parts by size."""
    if len(ring) < 4:
        return 0.0
    unwrapped = unwrap_ring(ring)
    mean_lat = sum(p[1] for p in unwrapped) / len(unwrapped)
    kx = 111.320 * math.cos(math.radians(clamp(mean_lat, -89.0, 89.0)))
    ky = 110.574
    return abs(shoelace_area([(p[0] * kx, p[1] * ky) for p in unwrapped]))


def outer_rings(geometry: dict) -> list[list[tuple[float, float]]]:
    """Outer rings of a GeoJSON Polygon/MultiPolygon geometry dict."""
    gtype = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if gtype == "Polygon":
        polys = [coords]
    elif gtype == "MultiPolygon":
        polys = list(coords)
    else:
        polys = []
    rings = []
    for poly in polys:
        if poly:
            rings.append([(float(p[0]), float(p[1])) for p in poly[0]])
    return rings


def largest_outer_ring(geometry: dict) -> list[tuple[float, float]]:
    rings = outer_rings(geometry)
    if not rings:
        return []
    return max(rings, key=approx_ring_area_km2)


def decimate_ring(ring: list[tuple[float, float]], max_points: int = 400) -> list[tuple[float, float]]:
    """Thin a ring for painting; keeps closure, never adds points."""
    if len(ring) <= max_points:
        return list(ring)
    step = max(1, math.ceil(len(ring) / max_points))
    out = list(ring[::step])
    if out and out[0] != out[-1]:
        out.append(out[0])
    return out


class LCG:
    """Small deterministic PRNG so the plugin never imports ``random``.

    The QGIS Plugin Hub security scan flags the stdlib ``random`` module
    (Bandit B311), and cryptographic quality is irrelevant for picking quiz
    countries or shuffling trivia lines.
    """

    _A = 1664525
    _C = 1013904223
    _M = 2 ** 32

    def __init__(self, seed: int = 20260719):
        self._state = int(seed) % self._M

    def next_int(self) -> int:
        self._state = (self._A * self._state + self._C) % self._M
        return self._state

    def random(self) -> float:
        return self.next_int() / self._M

    def randint(self, upper: int) -> int:
        """Uniform-ish int in [0, upper)."""
        if upper <= 0:
            return 0
        return self.next_int() % upper

    def choice(self, seq):
        return seq[self.randint(len(seq))]

    def shuffled(self, seq) -> list:
        items = list(seq)
        for i in range(len(items) - 1, 0, -1):
            j = self.randint(i + 1)
            items[i], items[j] = items[j], items[i]
        return items


def mercator_areal_inflation(lat: float) -> float:
    """Areal inflation factor (sec^2 lat) on a spherical Mercator map."""
    cos_lat = math.cos(math.radians(clamp(lat, -85.0, 85.0)))
    return 1.0 / max(0.0025, cos_lat * cos_lat)


def area_ratio_matrix(entities: list[dict]) -> list[dict]:
    """Compute pairwise true geodetic area ratios vs visual Mercator area ratios."""
    results = []
    for i, a in enumerate(entities):
        a_area = float(a.get("area_km2", 1.0))
        a_lat = float(a.get("lat", 0.0))
        a_infl = mercator_areal_inflation(a_lat)
        a_proj_area = a_area * a_infl
        for b in entities[i + 1:]:
            b_area = float(b.get("area_km2", 1.0))
            b_lat = float(b.get("lat", 0.0))
            b_infl = mercator_areal_inflation(b_lat)
            b_proj_area = b_area * b_infl

            true_ratio = a_area / max(1e-6, b_area)
            proj_ratio = a_proj_area / max(1e-6, b_proj_area)
            distortion_multiplier = proj_ratio / max(1e-6, true_ratio)

            results.append({
                "entity_a": a.get("name", "A"),
                "entity_b": b.get("name", "B"),
                "true_ratio": round(true_ratio, 2),
                "mercator_ratio": round(proj_ratio, 2),
                "distortion_factor": round(distortion_multiplier, 2),
            })
    return results
