# -*- coding: utf-8 -*-
"""Size Duel UI: 4 countries drawn exactly the way a web-Mercator map
draws them; the player guesses which is truly the largest in ground area,
and the engine confesses how much the projection lied."""
from __future__ import annotations

import time

from qgis.PyQt.QtCore import QPointF, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from qgis.PyQt.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsSettings

from ..core.funits import format_area_km2
from ..core.geomath import mercator_areal_inflation, mercator_xy
from ..core.quiz import CHOICE_KEYS, SizeDuel

BEST_STREAK_KEY = "zero2truesize/duel_best_streak"

CARD_BG_LIGHT = QColor(255, 255, 255)
CARD_BG_DARK = QColor(22, 32, 46)
CARD_BORDER_LIGHT = QColor(215, 224, 231)
CARD_BORDER_DARK = QColor(48, 66, 88)
HOVER_BORDER = QColor(0, 150, 136)
SHAPE_FILL_LIGHT = QColor(55, 71, 79, 215)
SHAPE_FILL_DARK = QColor(77, 182, 172, 210)
WIN_BORDER = QColor(46, 125, 50)
LOSE_BORDER = QColor(198, 40, 40)


class ShapePanel(QWidget):
    """One clickable silhouette, drawn at a shared metres-per-pixel scale."""

    clicked = pyqtSignal()

    def __init__(self, badge: str = "", parent=None):
        super().__init__(parent)
        self._badge = badge
        self._lat_badge = ""
        self._path: QPainterPath | None = None
        self._state: str | None = None
        self._hover = False
        self._clickable = True
        self.setMinimumSize(110, 110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_clickable(self, clickable: bool) -> None:
        self._clickable = clickable
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable
                       else Qt.CursorShape.ArrowCursor)
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt API)
        del event
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        del event
        self._hover = False
        self.update()

    def set_shape(self, merc_points: list[tuple[float, float]], scale: float = 0.0,
                  lat_deg: float | None = None) -> None:
        path = QPainterPath()
        if merc_points:
            xs = [p[0] for p in merc_points]
            ys = [p[1] for p in merc_points]
            dx = max(xs) - min(xs)
            dy = max(ys) - min(ys)
            cx = (min(xs) + max(xs)) / 2.0
            cy = (min(ys) + max(ys)) / 2.0
            if scale <= 0:
                # Zoom to the country's own bounding box so all cards are filled equally
                target_px = 85.0
                scale = max(1.0, max(dx, dy)) / target_px
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
        if lat_deg is not None:
            hemi = "N" if lat_deg >= 0 else "S"
            self._lat_badge = f"{abs(lat_deg):.0f}°{hemi}"
        else:
            self._lat_badge = ""
        self._state = None
        self.update()

    def set_state(self, state: str | None) -> None:
        self._state = state
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
        rect = self.rect().adjusted(2, 2, -2, -2)
        border = CARD_BORDER_DARK if dark else CARD_BORDER_LIGHT
        card_bg = CARD_BG_DARK if dark else CARD_BG_LIGHT
        shape_fill = SHAPE_FILL_DARK if dark else SHAPE_FILL_LIGHT
        width = 1
        if self._state == "win":
            border, width = WIN_BORDER, 3
        elif self._state == "lose":
            border, width = LOSE_BORDER, 3
        elif self._hover and self._clickable:
            border, width = HOVER_BORDER, 2
        painter.setPen(QPen(border, width))
        painter.setBrush(card_bg)
        painter.drawRoundedRect(rect, 8, 8)
        if self._path is not None:
            painter.save()
            painter.translate(rect.center())
            painter.setPen(QPen(shape_fill.darker(135), 1.2))
            painter.setBrush(shape_fill)
            painter.drawPath(self._path)
            painter.restore()
        # Draw subtle choice badge in top-left and revealed latitude in top-right
        badge_color = QColor(144, 164, 174) if dark else QColor(120, 144, 156)
        painter.setPen(badge_color)
        if self._badge:
            painter.drawText(rect.adjusted(7, 4, -6, -4), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, self._badge)
        if self._lat_badge and self._state is not None:
            painter.drawText(rect.adjusted(6, 4, -7, -4), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight, self._lat_badge)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        del event
        if self._clickable:
            self.clicked.emit()


class DuelWidget(QWidget):
    """The 4-choice Size Duel tab."""

    compare_on_map = pyqtSignal(dict, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine: SizeDuel | None = None
        self._round: dict[str, dict] | None = None
        self._last_result: dict | None = None
        self._accepting = False
        self._panels: dict[str, ShapePanel] = {}
        self._labels: dict[str, QLabel] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        title = QLabel("<b>Which of these 4 is REALLY biggest?</b><br>"
                       "<span style='color:#78909c;'>Click the single country with the largest true ground area.</span>")
        title.setWordWrap(True)
        root.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(8)

        for i, key in enumerate(CHOICE_KEYS):
            r, c = divmod(i, 2)
            col = QVBoxLayout()
            panel = ShapePanel(badge=key.upper(), parent=self)
            panel.clicked.connect(lambda k=key: self._on_guess(k))
            self._panels[key] = panel
            col.addWidget(panel)

            lbl = QLabel(f"<b>Choice {key.upper()}</b>")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            self._labels[key] = lbl
            col.addWidget(lbl)
            grid.addLayout(col, r, c)

        root.addLayout(grid)

        self.result = QLabel("")
        self.result.setWordWrap(True)
        self.result.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self.result)

        self.stats = QLabel("")
        self.stats.setStyleSheet("color: #78909c; background: transparent;")
        root.addWidget(self.stats)

        btn_row = QHBoxLayout()
        self.compare_button = QPushButton("🗺 Drop on Map")
        self.compare_button.setToolTip("Drop this round's true winner and Mercator visual trap onto the canvas to compare them side by side.")
        self.compare_button.setEnabled(False)
        self.compare_button.clicked.connect(self._emit_compare_on_map)
        btn_row.addWidget(self.compare_button)

        self.next_button = QPushButton("Skip round")
        self.next_button.setProperty("class", "primary")
        self.next_button.clicked.connect(self.new_round)
        btn_row.addWidget(self.next_button, 1)
        root.addLayout(btn_row)
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
        self._last_result = None
        self.compare_button.setEnabled(False)
        if self._round is None:
            self.result.setText("Not enough countries to play with.")
            return

        for key in CHOICE_KEYS:
            c = self._round[key]
            merc_pts = [mercator_xy(lat, lon) for lon, lat in c["ring"]]
            # Fit each country to its own bounding box so they fill their cards equally
            self._panels[key].set_shape(merc_pts, lat_deg=float(c.get("lat", 0.0)))
            self._panels[key].set_clickable(True)
            self._panels[key].set_state(None)
            self._labels[key].setText(f"<b>{c['name']}</b>")

        self.result.setText("Click the country you think is truly the biggest…")
        self.next_button.setText("Skip round")
        self._accepting = True
        self._update_stats()

    def _on_guess(self, key: str) -> None:
        if not self._accepting or self._engine is None or self._round is None:
            return
        result = self._engine.guess(key)
        if result is None:
            return
        self._accepting = False
        self._last_result = result
        self.compare_button.setEnabled(True)
        for panel in self._panels.values():
            panel.set_clickable(False)
        self.next_button.setText("▶ Next round")

        winner_key = result["winner_key"]
        for k in CHOICE_KEYS:
            if k == winner_key:
                self._panels[k].set_state("win")
            elif k == key and not result["correct"]:
                self._panels[k].set_state("lose")
            else:
                self._panels[k].set_state("revealed")

            c_info = result["countries"][k]
            lat_val = float(c_info.get("lat", 0.0))
            inf_val = mercator_areal_inflation(lat_val)
            self._labels[k].setText(
                f"<b>{c_info['name']}</b><br>{format_area_km2(float(c_info['area_km2']))} "
                f"<span style='color:#78909c; font-size:8pt;'>(×{inf_val:.1f} Merc)</span>"
            )

        winner = result["winner"]
        runner_up = result["runner_up"]
        verdict = ("<span style='color:#2e7d32;'><b>✔ Correct!</b></span>" if result["correct"]
                   else "<span style='color:#c62828;'><b>✘ Not quite!</b></span>")
        text = (f"{verdict} <b>{winner['name']}</b> is the true winner "
                f"({format_area_km2(float(winner['area_km2']))}, "
                f"{result['ratio_vs_runner_up']:.2f}× larger than runner-up {runner_up['name']}).")
        if result["deceptive"]:
            vis_winner = result["visual_winner"]
            text += (f"<br><i>Mercator deception: {vis_winner['name']} was drawn visually largest "
                     "due to high-latitude inflation!</i>")

        self.result.setText(text)
        self._update_stats()
        QgsSettings().setValue(BEST_STREAK_KEY, self._engine.best_streak)

    def _emit_compare_on_map(self) -> None:
        if not self._last_result:
            return
        winner = self._last_result.get("winner")
        other = self._last_result.get("visual_winner")
        if other and winner and other.get("name") == winner.get("name"):
            other = self._last_result.get("runner_up")
        if winner and other:
            self.compare_on_map.emit(dict(winner), dict(other))

    def _update_stats(self) -> None:
        if self._engine is None:
            return
        round_no = self._engine.rounds + 1 if self._accepting else max(1, self._engine.rounds)
        self.stats.setText(
            f"Round {round_no} · score {self._engine.correct_count}/"
            f"{self._engine.rounds} · streak {self._engine.streak} · "
            f"best {self._engine.best_streak}")

