# -*- coding: utf-8 -*-
"""Pure validation helpers for administrative boundary selection."""
from __future__ import annotations

import re

def validate_iso3(iso3: str) -> str:
    """Return a normalized ISO alpha-3 code or reject invalid input."""
    code = str(iso3 or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError("A valid three-letter country code is required.")
    return code


def validate_request(iso3: str, level: str) -> tuple[str, str]:
    """Validate a country code and supported administrative level."""
    code = validate_iso3(iso3)
    if level not in ("ADM0", "ADM1"):
        raise ValueError("Administrative level must be ADM0 or ADM1.")
    return code, level
