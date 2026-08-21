# -*- coding: utf-8 -*-
"""Size Duel: which country is REALLY biggest?

Pure-Python 4-choice game engine. Four countries are shown exactly the way
a web-Mercator map would draw them (areas inflated by sec^2 of latitude).
The player picks which one is truly the largest in ground area. The engine
favors deceptive sets where a smaller country is drawn visually bigger
than the true winner due to polar Mercator inflation.
"""
from __future__ import annotations

from .geomath import LCG, mercator_areal_inflation

MIN_AREA_KM2 = 15000.0
CHOICE_KEYS = ("a", "b", "c", "d")


def visual_area_km2(country: dict) -> float:
    """Area as a Mercator map draws it at the country's home latitude."""
    return float(country["area_km2"]) * mercator_areal_inflation(float(country["lat"]))


class SizeDuel:
    """Rounds of 4 countries; ``guess`` scores and keeps streaks.

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
        self._current: dict[str, dict] | None = None

    # ── round generation ──────────────────────────────────────────────

    def _random_quad(self) -> list[dict]:
        chosen: list[dict] = []
        names: set[str] = set()
        while len(chosen) < 4:
            c = self._rng.choice(self._pool)
            if c["name"] not in names:
                names.add(c["name"])
                chosen.append(c)
        return chosen

    @staticmethod
    def _is_deceptive_quad(items: list[dict]) -> bool:
        """True if the visually largest country on Mercator is NOT the actual ground area winner."""
        true_winner = max(items, key=lambda c: float(c["area_km2"]))
        visual_winner = max(items, key=lambda c: visual_area_km2(c))
        return true_winner["name"] != visual_winner["name"]

    def next_round(self) -> dict[str, dict] | None:
        if len(self._pool) < 4:
            return None
        quad = None
        # Preference: a deceptive set where Mercator visually points at a false winner.
        for _ in range(400):
            cand = self._random_quad()
            if self._is_deceptive_quad(cand):
                quad = cand
                break
        if quad is None:
            quad = self._random_quad()

        self._current = {
            k: dict(country, visual_km2=visual_area_km2(country))
            for k, country in zip(CHOICE_KEYS, quad)
        }
        return dict(self._current)

    # ── guessing ──────────────────────────────────────────────────────

    def guess(self, key: str) -> dict | None:
        if self._current is None or key not in CHOICE_KEYS:
            return None

        # Identify true winner and visual winner
        winner_key = max(CHOICE_KEYS, key=lambda k: float(self._current[k]["area_km2"]))
        visual_winner_key = max(CHOICE_KEYS, key=lambda k: float(self._current[k]["visual_km2"]))

        correct = (key == winner_key)
        self.rounds += 1
        if correct:
            self.correct_count += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
        else:
            self.streak = 0

        winner = self._current[winner_key]
        visual_winner = self._current[visual_winner_key]

        # Calculate ratio of winner to player's choice or runner-up
        sorted_keys = sorted(CHOICE_KEYS, key=lambda k: float(self._current[k]["area_km2"]), reverse=True)
        runner_up_key = sorted_keys[1]
        runner_up = self._current[runner_up_key]
        ratio_vs_runner_up = float(winner["area_km2"]) / max(1.0, float(runner_up["area_km2"]))

        result = {
            "correct": correct,
            "winner_key": winner_key,
            "guessed_key": key,
            "winner": dict(winner),
            "runner_up": dict(runner_up),
            "ratio_vs_runner_up": ratio_vs_runner_up,
            "visual_winner_key": visual_winner_key,
            "visual_winner": dict(visual_winner),
            "deceptive": visual_winner_key != winner_key,
            "countries": {k: dict(v) for k, v in self._current.items()},
            "streak": self.streak,
            "best_streak": self.best_streak,
            "rounds": self.rounds,
            "correct_count": self.correct_count,
        }
        self._current = None
        return result
