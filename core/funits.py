# -*- coding: utf-8 -*-
"""Fun-but-accurate unit conversions, trivia facts and witty one-liners.

Pure Python. All reference values are real published figures (rounded);
the humour is in the phrasing, not in the numbers.
"""
from __future__ import annotations

import math

from .geomath import LCG

# name (plural ready), km2
AREA_UNITS: list[tuple[str, float]] = [
    ("Olympic swimming pools", 0.00125),          # 50 m x 25 m
    ("football pitches", 0.00714),                # FIFA standard 105 m x 68 m
    ("Vatican Cities", 0.49),
    ("Monacos", 2.02),
    ("Central Parks", 3.41),
    ("Manhattans", 59.1),
    ("Paris-es (city proper)", 105.4),
    ("Lake Genevas", 580.0),
    ("Luxembourgs", 2586.0),
    ("Waleses", 20779.0),
    ("Belgiums", 30528.0),
    ("Lake Superiors", 82103.0),
    ("Texases", 695662.0),
]

# plural, singular, km
DISTANCE_UNITS: list[tuple[str, str, float]] = [
    ("football pitches (goal to goal)", "football pitch", 0.105),
    ("Eiffel Towers laid flat", "Eiffel Tower laid flat", 0.33),
    ("Bosphorus bridges", "Bosphorus bridge", 1.56),
    ("Mount Everests stacked up", "Mount Everest", 8.849),
    ("Manhattans end to end", "Manhattan", 21.6),
    ("English Channel swims (Dover-Calais)", "English Channel swim", 33.3),
    ("marathons", "marathon", 42.195),
    ("Istanbul-Ankara flights (great circle)", "Istanbul-Ankara flight", 351.0),
    ("Great Walls of China (main Ming line)", "Great Wall of China", 8850.0),
]

EQUATOR_KM = 40075.0
MOON_KM = 384400.0
BELGIUM_KM2 = 30528.0

FACTS: list[str] = [
    "Africa (30.4M km2) is larger than the USA, China, India, Japan and most of "
    "Europe combined. Mercator just refuses to admit it.",
    "Greenland looks about the size of Africa on web maps. Africa is roughly 14 times larger.",
    "Brazil is larger than the contiguous United States.",
    "Antarctica is about twice the size of Australia, and on a Mercator map it "
    "looks bigger than everything else put together.",
    "Australia is wider east-west (about 4,000 km) than the Moon's diameter (3,474 km).",
    "Fewer than 15 percent of all land points have land at their antipode. "
    "Dig straight down and you will almost certainly get wet.",
    "Mercator drew his map in 1569 so sailors could follow a constant compass "
    "bearing as a straight line. Honest areas were never part of the deal.",
    "A 'straight' line on a web map is almost never the shortest route. "
    "That is why long flights look curved.",
    "Web maps draw Alaska about as large as Brazil. Brazil is nearly five times larger.",
    "Norway's mainland coastline is about 29,000 km, and over 100,000 km if you "
    "count the islands. Coastline length depends on your ruler (the coastline paradox).",
    "Point Nemo, the loneliest spot in the ocean, is about 2,688 km from the "
    "nearest land. The nearest humans are often astronauts passing overhead.",
    "Russia spans about 170 degrees of longitude, yet its true area (17.1M km2) "
    "is just over half of Africa's.",
    "The Sahara desert alone (9.2M km2) is nearly the size of the entire United States.",
    "Canada is the second-largest country on Earth, yet most Canadians live "
    "within 250 km of its southern border.",
]

ANTIPODE_WET = [
    "Splash. You surface in open water — bring a boat.",
    "It's ocean. It is almost always ocean.",
    "You emerge treading water; the nearest land is a rumour.",
    "Wet again. The antipode of nearly everywhere is the sea.",
]

ANTIPODE_DRY = [
    "Land ho! You surface in {name}. Apologise for the hole.",
    "A dry landing in {name} — a rare privilege on this planet.",
    "You pop out in {name}. Mind the locals.",
]


def format_area_km2(km2: float) -> str:
    if km2 >= 1e6:
        return f"{km2 / 1e6:.2f}M km2"
    if km2 >= 100:
        return f"{km2:,.0f} km2"
    if km2 >= 1:
        return f"{km2:,.2f} km2"
    return f"{km2 * 1e6:,.0f} m2"


def format_km(km: float) -> str:
    if km >= 100:
        return f"{km:,.0f} km"
    if km >= 1:
        return f"{km:,.2f} km"
    return f"{km * 1000.0:,.0f} m"


def format_count(count: float) -> str:
    """Human count: big -> thousands separators, small -> a readable fraction."""
    if count >= 1000:
        return f"{count:,.0f}"
    if count >= 100:
        return f"{count:.0f}"
    if count >= 1:
        return f"{count:.1f}".rstrip("0").rstrip(".")
    if count > 0:
        return f"1/{round(1.0 / count):,}"
    return "0"


def _pick_units(units: list[tuple[str, float]], value: float, wanted: int) -> list[tuple[str, float]]:
    """Prefer units whose count lands in a fun, graspable range (~2 to ~50,000)."""
    scored = []
    for name, size in units:
        count = value / size
        if count <= 0:
            continue
        # Distance from the sweet spot of ~200 units, in log space.
        score = abs(math.log10(count) - math.log10(200.0))
        usable = 0.05 <= count <= 200000.0
        scored.append((0 if usable else 1, score, name, size))
    scored.sort()
    return [(name, size) for _usable, _score, name, size in scored[:wanted]]


def fun_area_lines(km2: float, rng: LCG | None = None) -> list[str]:
    """3-5 playful equivalences for an area, always ending with Belgiums."""
    del rng  # phrasing is deterministic; the parameter keeps the API symmetric
    lines = []
    picked = [u for u in _pick_units(AREA_UNITS, km2, 4) if u[0] != "Belgiums"]
    for name, size in picked[:3]:
        lines.append(f"≈ {format_count(km2 / size)} {name}")
    count = km2 / BELGIUM_KM2
    if count >= 0.01:
        lines.append(f"≈ {format_count(count)} Belgiums (the official unit of area)")
    else:
        lines.append(f"≈ {format_count(count)} of a Belgium (keep at it)")
    return lines


def fun_distance_lines(km: float, rng: LCG | None = None) -> list[str]:
    """3-5 playful equivalences for a distance, spanning magnitudes.

    A near-exact unit match ("that was 1 marathon, spot on") always wins a
    line of its own — the whole point of measuring 42.195 km.
    """
    del rng  # phrasing is deterministic; the parameter keeps the API symmetric
    lines = []
    usable = [(plural, singular, km / size)
              for plural, singular, size in DISTANCE_UNITS
              if 0.05 <= km / size <= 200000.0]
    exact = next((u for u in usable if 0.93 <= u[2] <= 1.07), None)
    if exact is not None:
        lines.append(f"≈ 1 {exact[1]} — spot on")
        usable = [u for u in usable if u[0] != exact[0]]
    usable.sort(key=lambda u: -u[2])
    picks = []
    if usable:
        picks.append(usable[0])
        if len(usable) > 2:
            picks.append(usable[len(usable) // 2])
        if len(usable) > 1 and usable[-1] not in picks:
            picks.append(usable[-1])
    for plural, _singular, count in picks[:3]:
        lines.append(f"≈ {format_count(count)} {plural}")
    if km >= 1000.0:
        lines.append(f"≈ {km / EQUATOR_KM:.2f} of a full lap around the equator")
    if km >= 4000.0:
        lines.append(f"≈ {km / MOON_KM:.3f} of the way to the Moon")
    return lines


def belgiums(km2: float) -> str:
    return format_count(km2 / BELGIUM_KM2)


def antipode_line(country_name: str | None, rng: LCG) -> str:
    if country_name:
        return rng.choice(ANTIPODE_DRY).format(name=country_name)
    return rng.choice(ANTIPODE_WET)


def fact(index: int) -> str:
    return FACTS[index % len(FACTS)]
