# -*- coding: utf-8 -*-
"""Size Duel UI: two countries drawn exactly the way a web-Mercator map
draws them; the player guesses which is truly bigger, the engine confesses
how much the projection lied."""
from __future__ import annotations

import time

from qgis.PyQt.QtCore import QPointF, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPainterPath, QPen
from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsSettings

from ..core.funits import format_area_km2
from ..core.geomath import mercator_xy
from ..core.quiz import SizeDuel

BEST_STREAK_KEY = "zero2truesize/duel_best_streak"

CARD_BG = QColor(245, 247, 250)
CARD_BORDER = QColor(176, 190, 197)
SHAPE_FILL = QColor(69, 90, 100, 215)
WIN_BORDER = QColor(46, 125, 50)
LOSE_BORDER = QColor(198, 40, 40)


class ShapePanel(QWidget):
    """One clickable silhouette, drawn at a shared metres-per-pixel scale."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path: QPainterPath | None = None
        self._state: str | None = None
        self.setMinimumSize(140, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_shape(self, merc_points: list[tuple[float, float]], scale: float) -> None:
        path = QPainterPath()
        if merc_points and scale > 0:
            xs = [p[0] for p in merc_points]
            ys = [p[1] for p in merc_points]
            cx = (min(xs) + max(xs)) / 2.0
            cy = (min(ys) + max(ys)) / 2.0
            first = True
            for x, y in merc_points:
                px = (x - cx) / scale
                py = -(y - cy) / scale
                if first:
                    path.moveTo(QPointF(px, py))
                    first = False
                else:
                    path.lineTo(QPointF(px, py))
            path.closeSubpath()
        self._path = path
        self._state = None
        self.update()

    def set_state(self, state: str | None) -> None:
        self._state = state
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(2, 2, -2, -2)
        border = CARD_BORDER
        width = 1
        if self._state == "win":
            border, width = WIN_BORDER, 3
        elif self._state == "lose":
            border, width = LOSE_BORDER, 3
        painter.setPen(QPen(border, width))
        painter.setBrush(CARD_BG)
        painter.drawRoundedRect(rect, 8, 8)
        if self._path is not None:
            painter.save()
            painter.translate(rect.center())
            painter.setPen(QPen(SHAPE_FILL.darker(130), 1))
            painter.setBrush(SHAPE_FILL)
            painter.drawPath(self._path)
            painter.restore()
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        del event
        self.clicked.emit()


class DuelWidget(QWidget):
    """The full Size Duel tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine: SizeDuel | None = None
        self._round: dict | None = None
        self._accepting = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        title = QLabel("<b>Which one is REALLY bigger?</b><br>"
                       "<span style='color:#78909c;'>Both are drawn exactly the way a "
                       "web-Mercator map draws them.</span>")
        title.setWordWrap(True)
        root.addWidget(title)

        row = QHBoxLayout()
        self.panel_a = ShapePanel(self)
        self.panel_b = ShapePanel(self)
        self.panel_a.clicked.connect(lambda: self._on_guess("a"))
        self.panel_b.clicked.connect(lambda: self._on_guess("b"))
        col_a = QVBoxLayout()
        col_a.addWidget(self.panel_a)
        self.label_a = QLabel("")
        self.label_a.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_a.setWordWrap(True)
        col_a.addWidget(self.label_a)
        col_b = QVBoxLayout()
        col_b.addWidget(self.panel_b)
        self.label_b = QLabel("")
        self.label_b.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_b.setWordWrap(True)
        col_b.addWidget(self.label_b)
        row.addLayout(col_a)
        vs = QLabel("<b>vs</b>")
        vs.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(vs)
        row.addLayout(col_b)
        root.addLayout(row)

        self.result = QLabel("")
        self.result.setWordWrap(True)
        self.result.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self.result)

        self.stats = QLabel("")
        self.stats.setStyleSheet("color: #78909c;")
        root.addWidget(self.stats)

        self.next_button = QPushButton("▶ New round")
        self.next_button.clicked.connect(self.new_round)
        root.addWidget(self.next_button)
        root.addStretch(1)

    # ── engine wiring ─────────────────────────────────────────────────

    def set_countries(self, records: list[dict]) -> None:
        playable = [r for r in records if len(r.get("ring") or []) >= 4]
        best = 0
        try:
            best = int(QgsSettings().value(BEST_STREAK_KEY, 0))
        except (TypeError, ValueError):
            best = 0
        seed = time.time_ns() & 0xFFFFFFFF
        self._engine = SizeDuel(playable, seed=seed, best_streak=best)
        self.new_round()

    def new_round(self) -> None:
        if self._engine is None:
            return
        self._round = self._engine.next_round()
        if self._round is None:
            self.result.setText("Not enough countries to play with.")
            return
        a = self._round["a"]
        b = self._round["b"]
        merc_a = [mercator_xy(lat, lon) for lon, lat in a["ring"]]
        merc_b = [mercator_xy(lat, lon) for lon, lat in b["ring"]]
        scale = self._common_scale(merc_a, merc_b)
        self.panel_a.set_shape(merc_a, scale)
        self.panel_b.set_shape(merc_b, scale)
        self.label_a.setText(f"<b>{a['name']}</b>")
        self.label_b.setText(f"<b>{b['name']}</b>")
        self.result.setText("Click the one you think is truly bigger…")
        self._update_stats()
        self._accepting = True

    def _common_scale(self, merc_a, merc_b) -> float:
        target_px = 120.0
        largest = 1.0
        for pts in (merc_a, merc_b):
            if not pts:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            largest = max(largest, max(xs) - min(xs), max(ys) - min(ys))
        return largest / target_px

    def _on_guess(self, key: str) -> None:
        if not self._accepting or self._engine is None:
            return
        result = self._engine.guess(key)
        if result is None:
            return
        self._accepting = False
        winner_key = result["winner_key"]
        self.panel_a.set_state("win" if winner_key == "a" else "lose")
        self.panel_b.set_state("win" if winner_key == "b" else "lose")
        winner = result["winner"]
        loser = result["loser"]
        self.label_a.setText(self._area_label(result, "a"))
        self.label_b.setText(self._area_label(result, "b"))
        verdict = ("<span style='color:#2e7d32;'><b>✔ Correct!</b></span>" if result["correct"]
                   else "<span style='color:#c62828;'><b>✘ Not this time.</b></span>")
        text = (f"{verdict} {winner['name']} is ×{result['true_ratio']:.1f} bigger "
                f"than {loser['name']}.")
        if result["deceptive"]:
            visual = self._round_country(result, result["visual_winner_key"])
            text += (f"<br><i>The map was lying: it drew {visual['name']} bigger. "
                     "Mercator strikes again.</i>")
        self.result.setText(text)
        self._update_stats()
        QgsSettings().setValue(BEST_STREAK_KEY, self._engine.best_streak)

    def _round_country(self, result: dict, key: str) -> dict:
        return result["winner"] if key == result["winner_key"] else result["loser"]

    def _area_label(self, result: dict, key: str) -> str:
        country = self._round_country(result, key)
        return f"<b>{country['name']}</b><br>{format_area_km2(float(country['area_km2']))}"

    def _update_stats(self) -> None:
        if self._engine is None:
            return
        self.stats.setText(
            f"Score {self._engine.correct_count}/{self._engine.rounds} · "
            f"streak {self._engine.streak} · best {self._engine.best_streak}")
