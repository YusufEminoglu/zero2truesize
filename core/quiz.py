# -*- coding: utf-8 -*-
"""Size Duel: which country is REALLY bigger?

Pure-Python game engine. Countries are shown the way a web-Mercator map
would draw them (areas inflated by sec^2 of latitude), the player guesses
which is truly larger, and the engine confesses how much the projection
lied. Pair selection has a taste for deception: rounds where the visually
bigger country is actually the smaller one.
"""
from __future__ import annotations

from .geomath import LCG, mercator_areal_inflation

MIN_AREA_KM2 = 15000.0
MAX_TRUE_RATIO = 8.0


def visual_area_km2(country: dict) -> float:
    """Area as a Mercator map draws it at the country's home latitude."""
    return float(country["area_km2"]) * mercator_areal_inflation(float(country["lat"]))


class SizeDuel:
    """Rounds of two countries; ``guess`` scores and keeps streaks.

    ``countries``: iterable of dicts with at least name, area_km2, lat.
    """

    def __init__(self, countries, seed: int | None = None, best_streak: int = 0):
        pool = [c for c in countries if float(c.get("area_km2", 0.0)) >= MIN_AREA_KM2]
        self._pool = sorted(pool, key=lambda c: c["name"])
        self._rng = LCG(20260719 if seed is None else seed)
        self.rounds = 0
        self.correct_count = 0
        self.streak = 0
        self.best_streak = int(best_streak)
        self._current: dict | None = None

    # ── round generation ──────────────────────────────────────────────

    def _random_pair(self) -> tuple[dict, dict]:
        first = self._rng.choice(self._pool)
        second = self._rng.choice(self._pool)
        while second["name"] == first["name"]:
            second = self._rng.choice(self._pool)
        return first, second

    @staticmethod
    def _is_deceptive(a: dict, b: dict) -> bool:
        true_bigger_is_a = float(a["area_km2"]) > float(b["area_km2"])
        visual_bigger_is_a = visual_area_km2(a) > visual_area_km2(b)
        return true_bigger_is_a != visual_bigger_is_a

    @staticmethod
    def _ratio(a: dict, b: dict) -> float:
        big = max(float(a["area_km2"]), float(b["area_km2"]))
        small = max(1.0, min(float(a["area_km2"]), float(b["area_km2"])))
        return big / small

    def next_round(self) -> dict | None:
        if len(self._pool) < 2:
            return None
        pair = None
        # First taste: a deceptive pair (Mercator points at the wrong winner).
        for _ in range(300):
            a, b = self._random_pair()
            if self._ratio(a, b) <= MAX_TRUE_RATIO and self._is_deceptive(a, b):
                pair = (a, b)
                break
        if pair is None:
            # Fall back to a close call, then to anything sane.
            for _ in range(300):
                a, b = self._random_pair()
                if self._ratio(a, b) <= 2.5:
                    pair = (a, b)
                    break
        if pair is None:
            pair = self._random_pair()
        a, b = pair
        self._current = {
            "a": dict(a, visual_km2=visual_area_km2(a)),
            "b": dict(b, visual_km2=visual_area_km2(b)),
        }
        return dict(self._current)

    # ── guessing ──────────────────────────────────────────────────────

    def guess(self, key: str) -> dict | None:
        if self._current is None or key not in ("a", "b"):
            return None
        a = self._current["a"]
        b = self._current["b"]
        winner_key = "a" if float(a["area_km2"]) >= float(b["area_km2"]) else "b"
        correct = key == winner_key
        self.rounds += 1
        if correct:
            self.correct_count += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
        else:
            self.streak = 0
        winner = self._current[winner_key]
        loser = self._current["b" if winner_key == "a" else "a"]
        visual_winner_key = "a" if a["visual_km2"] >= b["visual_km2"] else "b"
        result = {
            "correct": correct,
            "winner_key": winner_key,
            "winner": dict(winner),
            "loser": dict(loser),
            "true_ratio": float(winner["area_km2"]) / max(1.0, float(loser["area_km2"])),
            "deceptive": visual_winner_key != winner_key,
            "visual_winner_key": visual_winner_key,
            "streak": self.streak,
            "best_streak": self.best_streak,
            "rounds": self.rounds,
            "correct_count": self.correct_count,
        }
        self._current = None
        return result
