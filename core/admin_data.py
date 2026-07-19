# -*- coding: utf-8 -*-
"""Pure helpers for country-based administrative boundary downloads."""
from __future__ import annotations

import re

API_ROOT = "https://www.geoboundaries.org/api/current/gbOpen"


def validate_iso3(iso3: str) -> str:
    """Return a normalized ISO alpha-3 code or reject unsafe URL input."""
    code = str(iso3 or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError("A valid three-letter country code is required.")
    return code


def metadata_url(iso3: str, level: str) -> str:
    """Return the geoBoundaries gbOpen metadata endpoint for ADM0 or ADM1."""
    code = validate_iso3(iso3)
    if level not in ("ADM0", "ADM1"):
        raise ValueError("Administrative level must be ADM0 or ADM1.")
    return f"{API_ROOT}/{code}/{level}/"

