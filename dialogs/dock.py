# -*- coding: utf-8 -*-
"""The 02truesize dock: True Size, Size Duel, Truth Tools and Distortion tabs.

The dock is pure UI plus the state owners (ghost manager, world data, HUD);
map tools live in ``tools`` and are instantiated by the main plugin, which
routes their signals into the slots below.
"""
from __future__ import annotations

from contextlib import suppress

from qgis.PyQt.QtCore import QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsPointXY, QgsProject

from ..core.funits import FACTS, format_area_km2, format_km
from ..core.geomath import LCG
from ..tools.support import from_wgs84
from ..tools.tissot import DistortionHUD, crs_report_card, make_tissot_layer
from ..tools.truesize import TrueSizeManager
from ..tools.worlddata import WorldData

PLUGIN_TITLE = "02truesize — Map Truth Lab"

_HINT_QSS = "color: #78909c; font-size: 8pt;"
_STATUS_QSS = ("QLabel { background: #eceff1; color: #263238; border-radius: 5px;"
               " padding: 5px 7px; }")


def _tool_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setCheckable(True)
    return button


class TrueSizeDockWidget(QDockWidget):
    """Dockable panel; emits which map tool the user wants active."""

    request_tool = pyqtSignal(str)
    request_deactivate = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(PLUGIN_TITLE, parent)
        self.iface = iface
        canvas = iface.mapCanvas()
        self.world = WorldData.instance()
        self.manager = TrueSizeManager(canvas)
        self.manager.changed.connect(self._refresh_ghost_list)
        self.hud = DistortionHUD(canvas)
        self._tool_buttons: dict[str, QPushButton] = {}
        self._last_antipode: tuple[float, float] | None = None
        self._funits_plain = ""
        self._fact_rng = LCG(24601)
        self._fact_order = self._fact_rng.shuffled(range(len(FACTS)))
        self._fact_index = 0
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._build_ui()
        self._fact_timer = QTimer(self)
        self._fact_timer.setInterval(30000)
        self._fact_timer.timeout.connect(self._next_fact)
        self._fact_timer.start()
        self._next_fact()

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_truesize_tab(), "True Size")
        self.tabs.addTab(self._build_duel_tab(), "Size Duel")
        self.tabs.addTab(self._build_truth_tab(), "Truth Tools")
        self.tabs.addTab(self._build_distortion_tab(), "Distortion")
        root.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        self.fact_label = QLabel("")
        self.fact_label.setWordWrap(True)
        self.fact_label.setStyleSheet("color: #607d8b; font-style: italic; font-size: 8pt;")
        footer.addWidget(self.fact_label, 1)
        about = QPushButton("About")
        about.setFlat(True)
        about.setStyleSheet("color: #607d8b; font-size: 8pt;")
        about.clicked.connect(self._show_about)
        footer.addWidget(about, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(footer)

        self.setWidget(container)

    def _wrap_scroll(self, inner: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(inner)
        return scroll

    def _build_truesize_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(6)

        intro = QLabel("Web maps lie about size. Grab a country and drag it anywhere — "
                       "the outline is re-projected so it always covers its <b>true ground "
                       "area</b>. Watch Greenland deflate.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.world_checkbox = QCheckBox("Show the built-in world layer")
        self.world_checkbox.toggled.connect(self._toggle_world_layer)
        layout.addWidget(self.world_checkbox)

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Grab from:"))
        self.source_combo = QComboBox()
        self.source_combo.addItems(["Built-in world countries", "Active polygon layer"])
        source_row.addWidget(self.source_combo, 1)
        layout.addLayout(source_row)

        pick = _tool_button("🖐  Pick up && drag")
        self._register_tool_button("truesize", pick)
        layout.addWidget(pick)

        hint = QLabel("Click grabs · click again drops · R / E rotates · right-click cancels")
        hint.setWordWrap(True)
        hint.setStyleSheet(_HINT_QSS)
        layout.addWidget(hint)

        self.truesize_status = QLabel("Ready when you are.")
        self.truesize_status.setWordWrap(True)
        self.truesize_status.setStyleSheet(_STATUS_QSS)
        layout.addWidget(self.truesize_status)

        self.ghost_list = QListWidget()
        self.ghost_list.setMaximumHeight(150)
        layout.addWidget(self.ghost_list)

        buttons = QHBoxLayout()
        remove = QPushButton("Remove")
        remove.clicked.connect(self._remove_selected_ghost)
        clear = QPushButton("Clear all")
        clear.clicked.connect(self.manager.clear)
        save = QPushButton("Save as layer")
        save.clicked.connect(self._export_ghosts)
        for b in (remove, clear, save):
            buttons.addWidget(b)
        layout.addLayout(buttons)
        layout.addStretch(1)
        return self._wrap_scroll(page)

    def _build_duel_tab(self) -> QWidget:
        from .duel_widget import DuelWidget

        self.duel = DuelWidget()
        records = self.world.records()
        self.duel.set_countries(records)
        return self._wrap_scroll(self.duel)

    def _build_truth_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(6)

        antipode_box = QGroupBox("Antipode tunnel")
        antipode_layout = QVBoxLayout(antipode_box)
        antipode_button = _tool_button("⛏  Dig straight down (click the map)")
        self._register_tool_button("antipode", antipode_button)
        antipode_layout.addWidget(antipode_button)
        self.antipode_result = QLabel("Where would you surface if you dug straight through "
                                      "the Earth? Click the map to find out.")
        self.antipode_result.setWordWrap(True)
        self.antipode_result.setStyleSheet(_STATUS_QSS)
        antipode_layout.addWidget(self.antipode_result)
        self.fly_button = QPushButton("Fly to the antipode")
        self.fly_button.setEnabled(False)
        self.fly_button.clicked.connect(self._fly_to_antipode)
        antipode_layout.addWidget(self.fly_button)
        layout.addWidget(antipode_box)

        gc_box = QGroupBox("Great circle vs the map's straight line")
        gc_layout = QVBoxLayout(gc_box)
        gc_button = _tool_button("✈  Compare routes (click two points)")
        self._register_tool_button("greatcircle", gc_button)
        gc_layout.addWidget(gc_button)
        self.gc_result = QLabel("The shortest path on the globe is rarely the straight line "
                                "on the map. Click two points to see the difference.")
        self.gc_result.setWordWrap(True)
        self.gc_result.setStyleSheet(_STATUS_QSS)
        gc_layout.addWidget(self.gc_result)
        layout.addWidget(gc_box)

        fun_box = QGroupBox("Fun units")
        fun_layout = QVBoxLayout(fun_box)
        fun_grid = QGridLayout()
        distance_button = _tool_button("📏  Distance in fun units")
        self._register_tool_button("fundist", distance_button)
        fun_grid.addWidget(distance_button, 0, 0)
        area_button = _tool_button("🍰  Area in fun units")
        self._register_tool_button("funarea", area_button)
        fun_grid.addWidget(area_button, 0, 1)
        fun_layout.addLayout(fun_grid)
        self.funits_result = QLabel("Measure a distance in marathons, or click a polygon "
                                    "to get its area in Belgiums.")
        self.funits_result.setWordWrap(True)
        self.funits_result.setTextFormat(Qt.TextFormat.RichText)
        self.funits_result.setStyleSheet(_STATUS_QSS)
        fun_layout.addWidget(self.funits_result)
        copy_button = QPushButton("Copy result")
        copy_button.clicked.connect(self._copy_funits)
        fun_layout.addWidget(copy_button)
        layout.addWidget(fun_box)
        layout.addStretch(1)
        return self._wrap_scroll(page)

    def _build_distortion_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(6)

        card_box = QGroupBox("Projection honesty report card")
        card_layout = QVBoxLayout(card_box)
        grade_button = QPushButton("Grade my current projection")
        grade_button.clicked.connect(self._grade_projection)
        card_layout.addWidget(grade_button)
        self.card_result = QLabel("Every flat map lies somehow. Find out how yours does.")
        self.card_result.setWordWrap(True)
        self.card_result.setTextFormat(Qt.TextFormat.RichText)
        self.card_result.setStyleSheet(_STATUS_QSS)
        card_layout.addWidget(self.card_result)
        layout.addWidget(card_box)

        tissot_box = QGroupBox("Tissot indicatrix circles")
        tissot_layout = QVBoxLayout(tissot_box)
        explain = QLabel("Equal circles on the ground; whatever the map turns them into "
                         "is the distortion, made visible.")
        explain.setWordWrap(True)
        explain.setStyleSheet(_HINT_QSS)
        tissot_layout.addWidget(explain)
        combo_row = QHBoxLayout()
        combo_row.addWidget(QLabel("Radius:"))
        self.tissot_radius = QComboBox()
        self.tissot_radius.addItems(["250 km", "500 km", "1000 km"])
        self.tissot_radius.setCurrentIndex(1)
        combo_row.addWidget(self.tissot_radius)
        combo_row.addWidget(QLabel("Every:"))
        self.tissot_step = QComboBox()
        self.tissot_step.addItems(["15°", "30°", "45°"])
        self.tissot_step.setCurrentIndex(1)
        combo_row.addWidget(self.tissot_step)
        combo_row.addStretch(1)
        tissot_layout.addLayout(combo_row)
        tissot_button = QPushButton("Add Tissot circles layer")
        tissot_button.clicked.connect(self._add_tissot_layer)
        tissot_layout.addWidget(tissot_button)
        self.tissot_status = QLabel("")
        self.tissot_status.setWordWrap(True)
        self.tissot_status.setStyleSheet(_HINT_QSS)
        tissot_layout.addWidget(self.tissot_status)
        layout.addWidget(tissot_box)

        self.hud_checkbox = QCheckBox("Live distortion readout on the canvas")
        self.hud_checkbox.toggled.connect(self.hud.set_enabled)
        layout.addWidget(self.hud_checkbox)
        layout.addStretch(1)
        return self._wrap_scroll(page)

    # ── tool button management ────────────────────────────────────────

    def _register_tool_button(self, key: str, button: QPushButton) -> None:
        self._tool_buttons[key] = button
        button.clicked.connect(lambda checked, k=key: self._on_tool_clicked(k, checked))

    def _on_tool_clicked(self, key: str, checked: bool) -> None:
        if checked:
            for other_key, button in self._tool_buttons.items():
                if other_key != key and button.isChecked():
                    button.blockSignals(True)
                    button.setChecked(False)
                    button.blockSignals(False)
            self.request_tool.emit(key)
        else:
            self.request_deactivate.emit()

    def uncheck_all_tools(self) -> None:
        for button in self._tool_buttons.values():
            if button.isChecked():
                button.blockSignals(True)
                button.setChecked(False)
                button.blockSignals(False)

    def truesize_source_mode(self) -> str:
        return "world" if self.source_combo.currentIndex() == 0 else "active"

    # ── True Size slots ───────────────────────────────────────────────

    def set_tool_message(self, text: str) -> None:
        self.truesize_status.setText(text)

    def _toggle_world_layer(self, checked: bool) -> None:
        if checked:
            layer = self.world.add_world_layer_to_project()
            if layer is None:
                self.truesize_status.setText("Could not load the bundled world layer.")
        else:
            self.world.remove_world_layer_from_project()

    def _refresh_ghost_list(self) -> None:
        self.ghost_list.clear()
        for ghost in self.manager.ghosts:
            r, g, b = ghost.color
            pixmap = QPixmap(QSize(12, 12))
            pixmap.fill(QColor(r, g, b))
            looks = f" · drawn ×{ghost.looks:.2f}" if abs(ghost.looks - 1.0) >= 0.05 else ""
            item = QListWidgetItem(QIcon(pixmap),
                                   f"{ghost.name} · {format_area_km2(ghost.area_km2)}{looks}")
            self.ghost_list.addItem(item)

    def _remove_selected_ghost(self) -> None:
        row = self.ghost_list.currentRow()
        if row >= 0:
            self.manager.remove_at(row)

    def _export_ghosts(self) -> None:
        layer = self.manager.export_layer()
        if layer is None:
            self.truesize_status.setText("Nothing to save yet — drop a ghost first.")
        else:
            self.truesize_status.setText(
                f"Saved {layer.featureCount()} ghost(s) to layer “{layer.name()}”.")

    # ── Truth Tools slots ─────────────────────────────────────────────

    def show_message(self, key: str, text: str) -> None:
        target = {
            "truesize": self.truesize_status,
            "antipode": self.antipode_result,
            "greatcircle": self.gc_result,
            "fundist": self.funits_result,
            "funarea": self.funits_result,
        }.get(key)
        if target is not None:
            target.setText(text)

    def show_antipode(self, res: dict) -> None:
        self._last_antipode = (res["to_lon"], res["to_lat"])
        self.fly_button.setEnabled(True)
        origin = f"{res['from_lat']:.2f}°, {res['from_lon']:.2f}°"
        if res.get("origin_country"):
            origin += f" ({res['origin_country']})"
        target = f"{res['to_lat']:.2f}°, {res['to_lon']:.2f}°"
        where = res.get("country") or "the open ocean"
        text = (f"<b>From</b> {origin}<br><b>you surface at</b> {target} — "
                f"<b>{where}</b>.<br><i>{res['line']}</i>")
        if not res.get("marker_visible", True):
            text += "<br><span style='color:#c62828;'>(The antipode is outside this " \
                    "projection's world — switch to a global CRS to see the marker.)</span>"
        self.antipode_result.setText(text)

    def _fly_to_antipode(self) -> None:
        if self._last_antipode is None:
            return
        lon, lat = self._last_antipode
        canvas = self.iface.mapCanvas()
        with suppress(Exception):
            point = from_wgs84(canvas.mapSettings().destinationCrs()).transform(
                QgsPointXY(lon, lat))
            canvas.setCenter(point)
            canvas.refresh()

    def show_greatcircle(self, res: dict) -> None:
        geodesic = res.get("geodesic_km") or 0.0
        text = f"<b>Great circle:</b> {format_km(geodesic)}."
        straight = res.get("straight_km")
        if straight is not None:
            text += f"<br><b>The map's straight line:</b> {format_km(straight)} of actual ground."
        saved = res.get("saved_km")
        if saved is not None:
            if saved < 5.0:
                text += "<br><i>Nearly identical here — this projection treats this route kindly.</i>"
            else:
                text += (f"<br><i>The 'straight' line is {format_km(saved)} "
                         f"({res.get('saved_pct', 0.0):.1f}%) longer. "
                         "That is why flights look curved.</i>")
        self.gc_result.setText(text)

    def show_funits(self, res: dict) -> None:
        lines = res.get("lines") or []
        headline = res.get("headline", "")
        text = f"<b>{headline}</b>"
        if lines:
            text += "<br>" + "<br>".join(lines)
        self.funits_result.setText(text)
        self._funits_plain = headline + "\n" + "\n".join(lines)

    def _copy_funits(self) -> None:
        if self._funits_plain:
            QApplication.clipboard().setText(self._funits_plain)

    # ── Distortion slots ──────────────────────────────────────────────

    def _grade_projection(self) -> None:
        card = crs_report_card(self.iface.mapCanvas())
        if not card.get("ok"):
            self.card_result.setText(
                f"<b>{card.get('crs_name', 'This projection')}</b><br>"
                "Could not sample this projection along the test meridian — its valid "
                "area may be too small. Try a wider CRS.")
            return
        rows = " · ".join(f"{int(r['lat'])}°: ×{r['areal_rel']:.2f}" for r in card["rows"])
        self.card_result.setText(
            f"<b>{card['crs_name']}</b><br>"
            f"Area honesty: <b>{card['area_grade']}</b> "
            f"(worst inflation ×{card['area_spread']:.1f})<br>"
            f"Shape honesty: <b>{card['shape_grade']}</b> "
            f"(max bend {card['max_omega_deg']:.0f}°)<br>"
            f"<span style='color:#78909c;'>{rows}</span><br>"
            f"<i>{card['verdict']}</i>")

    def _add_tissot_layer(self) -> None:
        radius = float(self.tissot_radius.currentText().split()[0])
        step = int(self.tissot_step.currentText().rstrip("°"))
        layer = make_tissot_layer(radius_km=radius, lat_step=step, lon_step=step)
        QgsProject.instance().addMapLayer(layer)
        self.tissot_status.setText(
            f"Added {layer.featureCount()} equal ground-area circles. However round they "
            "look (or don't) is your projection talking.")

    # ── footer ────────────────────────────────────────────────────────

    def _next_fact(self) -> None:
        index = self._fact_order[self._fact_index % len(self._fact_order)]
        self._fact_index += 1
        self.fact_label.setText("💡 " + FACTS[index])

    def _show_about(self) -> None:
        QMessageBox.about(
            self, PLUGIN_TITLE,
            "<h3>02truesize — Map Truth Lab</h3>"
            "<p><i>Every flat map lies. This panel shows you how, playfully.</i></p>"
            "<p>True-size drag comparisons, a Mercator-lie guessing duel, projection "
            "report cards, Tissot circles, antipodes, great circles and fun units — "
            "fully offline.</p>"
            "<p>World outlines: <a href='https://www.naturalearthdata.com'>Natural Earth</a> "
            "(public domain), bundled. Inspired by "
            "<a href='https://thetruesize.com'>thetruesize.com</a>.</p>"
            "<p><a href='https://github.com/YusufEminoglu/zero2truesize'>"
            "github.com/YusufEminoglu/zero2truesize</a></p>")

    # ── lifecycle ─────────────────────────────────────────────────────

    def dispose(self) -> None:
        self._fact_timer.stop()
        self.hud.dispose()
        self.manager.dispose()
        self.world.remove_world_layer_from_project()
