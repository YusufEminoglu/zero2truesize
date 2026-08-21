# -*- coding: utf-8 -*-
"""The 02truesize dock: True Size, Size Duel, Truth Tools and Distortion tabs.

The dock is pure UI plus the state owners (ghost manager, world data, HUD);
map tools live in ``tools`` and are instantiated by the main plugin, which
routes their signals into the slots below.
"""
from __future__ import annotations

import os
from contextlib import suppress

from qgis.PyQt.QtCore import QEvent, QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QIcon, QPalette, QPixmap
from qgis.PyQt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
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
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
)

from ..core.exporter import export_truth_lab_html
from ..core.funits import FACTS, format_area_km2, format_km
from ..core.geomath import LCG, area_ratio_matrix
from ..core.recommender import recommend_projections
from ..tools.support import from_wgs84
from ..tools.tissot import DistortionHUD, crs_report_card, make_tissot_layer
from ..tools.truesize import TrueSizeManager
from ..tools.worlddata import WorldData
from ..tools.admin_download import AdminDownloadManager
from .theme import apply_adaptive_theme, card_accent, dock_color_tokens

PLUGIN_TITLE = "02truesize — Map Truth Lab"

IDLE_STYLE = "font-size: 8pt; background: transparent;"
_GRADE_COLORS = {
    "A+": "#1b5e20", "A": "#2e7d32", "B": "#558b2f",
    "C": "#f9a825", "D": "#ef6c00", "E": "#d84315", "F": "#b71c1c",
}


def _card_qss(tool_key: str = "", fallback: str = "#00897b") -> str:
    """Build a palette-aware card style.  *tool_key* selects a per-tool accent
    that is automatically adjusted for dark/light; *fallback* is used when the
    key is unknown."""
    t = dock_color_tokens()
    dark = QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128
    accent = card_accent(tool_key, dark) if tool_key else fallback
    return (f"QLabel {{ background: {t['card']}; border: 1px solid {t['border']};"
            f" border-left: 4px solid {accent}; border-radius: 6px;"
            f" padding: 6px 8px; color: {t['text']}; }}")


def _grade_chip(grade: str) -> str:
    color = _GRADE_COLORS.get(grade, "#546e7a")
    return (f"<span style='background-color:{color}; color:#ffffff;"
            f" font-weight:bold;'>&nbsp;{grade}&nbsp;</span>")


def _tool_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setCheckable(True)
    button.setProperty("class", "tool")
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
        self.admin = AdminDownloadManager(self.world, self)
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
        self.admin.started.connect(self._admin_started)
        self.admin.finished.connect(self._admin_finished)
        self.admin.failed.connect(self._admin_failed)
        # Keep the default source, checkbox and actual project layer in sync.
        QTimer.singleShot(0, lambda: self._on_source_changed(
            self.source_combo.currentIndex()))
        self._fact_timer = QTimer(self)
        self._fact_timer.setInterval(30000)
        self._fact_timer.timeout.connect(self._next_fact)
        self._fact_timer.start()
        self._next_fact()

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        container = QWidget()
        container.setObjectName("z2tsRoot")
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        container.setMinimumWidth(330)
        root = QVBoxLayout(container)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        header = QHBoxLayout()
        icon_label = QLabel()
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "icons", "icon.png")
        if os.path.exists(icon_path):
            icon_label.setPixmap(QPixmap(icon_path).scaled(
                22, 22, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        header.addWidget(icon_label, 0)
        title = QLabel("<b>02truesize</b> "
                       "<span style='color:#78909c;'>· every flat map lies</span>")
        header.addWidget(title, 1)
        root.addLayout(header)

        self.tabs = QTabWidget()
        # Plain-text labels on purpose: emoji glyphs vary wildly in width per
        # platform/font and were truncating the tab captions.
        self.tabs.addTab(self._build_truesize_tab(), "True Size")
        self.tabs.addTab(self._build_duel_tab(), "Duel")
        self.tabs.addTab(self._build_truth_tab(), "Truth")
        self.tabs.addTab(self._build_distortion_tab(), "Distort")
        self.tabs.setTabToolTip(0, "🗺 Drag countries at their true size")
        self.tabs.setTabToolTip(1, "⚖ Size Duel — which is really bigger?")
        self.tabs.setTabToolTip(2, "🧭 Antipodes, great circles and fun units")
        self.tabs.setTabToolTip(3, "🌐 Report card, Tissot circles and the live HUD")
        self.tabs.setUsesScrollButtons(False)
        # Bold via the widget font, NOT the stylesheet: Qt measures tab widths
        # with the widget font and only paints with the QSS one, so a QSS
        # font-weight silently truncates the captions.
        tab_font = self.tabs.tabBar().font()
        tab_font.setBold(True)
        self.tabs.tabBar().setFont(tab_font)
        root.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        self.fact_label = QLabel("")
        self.fact_label.setWordWrap(True)
        self.fact_label.setStyleSheet(IDLE_STYLE + " font-style: italic;")
        footer.addWidget(self.fact_label, 1)
        about = QPushButton("About")
        about.setFlat(True)
        about.setStyleSheet(IDLE_STYLE)
        about.clicked.connect(self._show_about)
        footer.addWidget(about, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(footer)

        self.setWidget(container)
        self._apply_theme()

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
        self.source_combo.addItems([
            "Built-in world countries",
            "Active polygon layer",
            "Downloaded administrative boundaries",
        ])
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        source_row.addWidget(self.source_combo, 1)
        layout.addLayout(source_row)

        admin_box = QGroupBox("Administrative boundary download")
        admin_layout = QVBoxLayout(admin_box)
        admin_hint = QLabel(
            "Choose a country and download either its national boundary or its "
            "ISO 3166-2 first-level administrative units. The canvas extent is "
            "not used for the query.")
        admin_hint.setWordWrap(True)
        admin_hint.setStyleSheet(IDLE_STYLE)
        admin_layout.addWidget(admin_hint)

        country_row = QHBoxLayout()
        country_row.addWidget(QLabel("Country:"))
        self.admin_country = QComboBox()
        records = sorted(self.world.records(), key=lambda record: record["name"])
        turkey_index = 0
        for index, record in enumerate(records):
            self.admin_country.addItem(record["name"], record.get("iso", ""))
            if record["name"] in ("Turkey", "Türkiye"):
                turkey_index = index
        self.admin_country.setCurrentIndex(turkey_index)
        country_row.addWidget(self.admin_country, 1)
        admin_layout.addLayout(country_row)

        level_row = QHBoxLayout()
        level_row.addWidget(QLabel("Boundary set:"))
        self.admin_level = QComboBox()
        self.admin_level.addItem("Country boundary (ADM0)", "ADM0")
        self.admin_level.addItem("First-level units (ADM1)", "ADM1")
        level_row.addWidget(self.admin_level, 1)
        admin_layout.addLayout(level_row)

        self.admin_button = QPushButton("Download selected administrative boundaries")
        self.admin_button.clicked.connect(self._download_admin)
        admin_layout.addWidget(self.admin_button)
        self.admin_status = QLabel(
            "ADM0 uses the bundled world data. ADM1 downloads Natural Earth "
            "10m states/provinces once per panel session (public domain).")
        self.admin_status.setWordWrap(True)
        self.admin_status.setStyleSheet(IDLE_STYLE)
        admin_layout.addWidget(self.admin_status)
        layout.addWidget(admin_box)

        # ── Primary action: the drag tool is the heart of the plugin ──
        drag_frame = QWidget()
        drag_frame.setObjectName("dragFrame")
        drag_layout = QVBoxLayout(drag_frame)
        drag_layout.setContentsMargins(0, 4, 0, 4)
        drag_layout.setSpacing(4)

        pick = QPushButton("🖐  Pick up & drag  —  click a country and move it")
        pick.setCheckable(True)
        pick.setProperty("class", "primary-drag")
        pick.setToolTip("Grab any country, polygon or administrative boundary and drag it — "
                        "the outline keeps its true ground area wherever it goes")
        self._register_tool_button("truesize", pick)
        drag_layout.addWidget(pick)

        hint = QLabel("Click grabs · click again drops · R / E rotates · right-click cancels")
        hint.setWordWrap(True)
        hint.setStyleSheet(IDLE_STYLE)
        drag_layout.addWidget(hint)
        layout.addWidget(drag_frame)

        self.truesize_status = QLabel("Ready when you are.")
        self.truesize_status.setWordWrap(True)
        self.truesize_status.setStyleSheet(_card_qss("truesize"))
        layout.addWidget(self.truesize_status)

        self.ghost_list = QListWidget()
        self.ghost_list.setMaximumHeight(150)
        layout.addWidget(self.ghost_list)

        ghost_actions = QHBoxLayout()
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_selected_ghost)
        save = QPushButton("Save as layer")
        save.clicked.connect(self._export_ghosts)
        ghost_actions.addWidget(remove)
        ghost_actions.addWidget(save)
        layout.addLayout(ghost_actions)

        self.clear_btn = QPushButton("🧹 Clear All Canvas Ghosts")
        self.clear_btn.setStyleSheet(
            "QPushButton { font-weight: bold; background-color: #d32f2f; color: #ffffff; "
            "border: 1px solid #b71c1c; border-radius: 6px; padding: 6px 12px; font-size: 9pt; } "
            "QPushButton:hover { background-color: #b71c1c; }"
        )
        self.clear_btn.setToolTip("Immediately remove all ghost outlines and temporary comparison overlays from the canvas.")
        self.clear_btn.clicked.connect(self._on_clear_all_clicked)
        layout.addWidget(self.clear_btn)

        adv_row = QHBoxLayout()
        matrix_btn = QPushButton("⚖️ Area Ratio Matrix")
        matrix_btn.setToolTip("Compare geodetic true area ratios vs Mercator visual ratios for all active ghosts.")
        matrix_btn.clicked.connect(self._show_area_matrix)
        export_html_btn = QPushButton("🔬 Export Truth Lab Report…")
        export_html_btn.setToolTip("Export a standalone interactive HTML Map Truth Lab report with real-time latitude slider.")
        export_html_btn.clicked.connect(self._export_truth_lab)
        adv_row.addWidget(matrix_btn)
        adv_row.addWidget(export_html_btn)
        layout.addLayout(adv_row)

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
        self.antipode_result.setStyleSheet(_card_qss("antipode"))
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
        self.gc_result.setStyleSheet(_card_qss("greatcircle"))
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
        self.funits_result.setStyleSheet(_card_qss("fundist"))
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
        grade_button.setProperty("class", "primary")
        grade_button.clicked.connect(self._grade_projection)
        card_layout.addWidget(grade_button)
        self.card_result = QLabel("Every flat map lies somehow. Find out how yours does.")
        self.card_result.setWordWrap(True)
        self.card_result.setTextFormat(Qt.TextFormat.RichText)
        self.card_result.setStyleSheet(_card_qss(fallback="#f4511e"))
        card_layout.addWidget(self.card_result)
        layout.addWidget(card_box)

        tissot_box = QGroupBox("Tissot indicatrix circles")
        tissot_layout = QVBoxLayout(tissot_box)
        explain = QLabel("Equal circles on the ground; whatever the map turns them into "
                         "is the distortion, made visible.")
        explain.setWordWrap(True)
        explain.setStyleSheet(IDLE_STYLE)
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
        tissot_button.setProperty("class", "primary")
        tissot_button.clicked.connect(self._add_tissot_layer)
        tissot_layout.addWidget(tissot_button)
        self.tissot_status = QLabel("")
        self.tissot_status.setWordWrap(True)
        self.tissot_status.setStyleSheet(IDLE_STYLE)
        tissot_layout.addWidget(self.tissot_status)
        layout.addWidget(tissot_box)

        self.hud_checkbox = QCheckBox("Live distortion readout on the canvas")
        self.hud_checkbox.toggled.connect(self.hud.set_enabled)
        layout.addWidget(self.hud_checkbox)

        # ── Projection Recommender ────────────────────────────────────
        rec_box = QGroupBox("Projection Recommender & Optimizer")
        rec_layout = QVBoxLayout(rec_box)
        rec_hint = QLabel("Analyze current canvas latitude bounds and find the most honest projection for your map's purpose.")
        rec_hint.setWordWrap(True)
        rec_hint.setStyleSheet(IDLE_STYLE)
        rec_layout.addWidget(rec_hint)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Purpose:"))
        self.rec_purpose_combo = QComboBox()
        self.rec_purpose_combo.addItems(["All", "Equal-Area", "Conformal", "Compromise"])
        filter_row.addWidget(self.rec_purpose_combo, 1)
        rec_btn = QPushButton("🔍 Recommend")
        rec_btn.clicked.connect(self._recommend_crs)
        filter_row.addWidget(rec_btn)
        rec_layout.addLayout(filter_row)

        self.rec_list = QListWidget()
        self.rec_list.setMaximumHeight(130)
        rec_layout.addWidget(self.rec_list)

        apply_crs_btn = QPushButton("Apply Selected Projection to Canvas")
        apply_crs_btn.setProperty("class", "primary")
        apply_crs_btn.clicked.connect(self._apply_recommended_crs)
        rec_layout.addWidget(apply_crs_btn)
        layout.addWidget(rec_box)

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
        return ("world", "active", "admin")[self.source_combo.currentIndex()]

    def truesize_source_layer(self):
        if self.truesize_source_mode() == "admin":
            return self.admin.layer()
        return self.iface.activeLayer()

    def _on_source_changed(self, index: int) -> None:
        if index != 0:
            return
        if not self.world_checkbox.isChecked():
            self.world_checkbox.setChecked(True)
            return
        # Recover when the layer was removed directly from the layer tree.
        if self.world.project_layer() is None:
            self._toggle_world_layer(True)

    # ── True Size slots ───────────────────────────────────────────────

    def set_tool_message(self, text: str) -> None:
        self.truesize_status.setText(text)

    def _toggle_world_layer(self, checked: bool) -> None:
        if checked:
            layer = self.world.add_world_layer_to_project()
            if layer is None:
                self.world_checkbox.blockSignals(True)
                self.world_checkbox.setChecked(False)
                self.world_checkbox.blockSignals(False)
                from ..tools.worlddata import DATA_PATH

                self.truesize_status.setText(
                    "Could not load the bundled world file — reinstall the plugin? "
                    f"(expected at {DATA_PATH})")
                return
            self._zoom_to_world()
            self.truesize_status.setText(
                f"World layer added on top ({layer.featureCount()} countries). "
                "Now press “Pick up & drag” and click a country.")
        else:
            self.world.remove_world_layer_from_project()
            self.truesize_status.setText("World layer removed.")

    def ensure_world_layer_visible(self) -> None:
        """Called when the pick tool starts in world mode: make sure there is
        something on the canvas to click, without touching the user's extent."""
        if self.world.project_layer() is not None:
            return
        layer = self.world.add_world_layer_to_project()
        if layer is not None:
            self.world_checkbox.blockSignals(True)
            self.world_checkbox.setChecked(True)
            self.world_checkbox.blockSignals(False)
            self.truesize_status.setText(
                "Added the built-in world layer so you can see what you grab. "
                "Click a country to pick it up.")

    def _zoom_to_world(self) -> None:
        canvas = self.iface.mapCanvas()
        with suppress(Exception):
            from qgis.core import QgsRectangle

            from ..tools.support import from_wgs84

            # Clamp to ±85° so Mercator-style canvases do not blow up at the poles.
            extent = from_wgs84(canvas.mapSettings().destinationCrs()).transformBoundingBox(
                QgsRectangle(-179.9, -85.0, 179.9, 85.0))
            canvas.setExtent(extent)
            canvas.refresh()

    def _download_admin(self) -> None:
        if self.admin.busy:
            self.admin.cancel()
            return
        iso3 = self.admin_country.currentData()
        level = self.admin_level.currentData()
        country_name = self.admin_country.currentText()
        try:
            self.admin.download(iso3, level, country_name)
        except (RuntimeError, ValueError) as exc:
            self._admin_failed(str(exc))

    def _admin_started(self, summary: str) -> None:
        self.admin_button.setText("Cancel download")
        self.admin_status.setText(f"Downloading administrative boundaries: {summary}…")

    def _admin_finished(self, layer) -> None:
        self.admin_button.setText("Refresh selected administrative boundaries")
        self.source_combo.setCurrentIndex(2)
        self.iface.setActiveLayer(layer)
        self.admin_status.setText(
            f"Ready: {layer.featureCount()} administrative units. Source switched "
            "to the downloaded layer; press “Pick up & drag” and click a boundary.")

    def _admin_failed(self, message: str) -> None:
        self.admin_button.setText(
            "Refresh selected administrative boundaries"
            if self.admin.layer() is not None
            else "Download selected administrative boundaries")
        self.admin_status.setText(message)

    def _refresh_ghost_list(self) -> None:
        self.ghost_list.clear()
        for ghost in self.manager.ghosts:
            r, g, b = ghost.color
            pixmap = QPixmap(QSize(12, 12))
            pixmap.fill(QColor(r, g, b))
            looks = f" · drawn ×{ghost.looks:.2f}" if abs(ghost.looks - 1.0) >= 0.05 else ""
            item = QListWidgetItem(QIcon(pixmap),
                                   f"{ghost.name} · {format_area_km2(ghost.area_km2)}{looks}")
            item.setToolTip(ghost.label())
            self.ghost_list.addItem(item)

    def _remove_selected_ghost(self) -> None:
        row = self.ghost_list.currentRow()
        if row >= 0:
            self.manager.remove_at(row)

    def _on_clear_all_clicked(self) -> None:
        count = len(self.manager.ghosts)
        self.manager.clear()
        self.truesize_status.setText(f"Cleared {count} ghost outline(s) from canvas." if count else "Canvas is clean.")

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
            f"Area honesty: {_grade_chip(card['area_grade'])} "
            f"<span style='color:#78909c;'>(worst inflation ×{card['area_spread']:.1f})</span><br>"
            f"Shape honesty: {_grade_chip(card['shape_grade'])} "
            f"<span style='color:#78909c;'>(max bend {card['max_omega_deg']:.0f}°)</span><br>"
            f"<span style='color:#78909c; font-size:8pt;'>{rows}</span><br>"
            f"<i>{card['verdict']}</i>")

    def _add_tissot_layer(self) -> None:
        radius = float(self.tissot_radius.currentText().split()[0])
        step = int(self.tissot_step.currentText().rstrip("°"))
        layer = make_tissot_layer(radius_km=radius, lat_step=step, lon_step=step)
        QgsProject.instance().addMapLayer(layer)
        self.tissot_status.setText(
            f"Added {layer.featureCount()} equal ground-area circles. However round they "
            "look (or don't) is your projection talking.")

    def _show_area_matrix(self) -> None:
        from .matrix_dialog import AreaRatioMatrixDialog

        ghosts = self.manager.ghosts
        entities = []
        for g in ghosts:
            lat = getattr(g, "center_lat", None)
            if lat is None:
                lat = g.dst_anchor.y() if hasattr(g, "dst_anchor") else 0.0
            entities.append({"name": g.name, "area_km2": g.area_km2, "lat": float(lat)})

        dialog = AreaRatioMatrixDialog(entities if len(entities) >= 2 else None, parent=self)
        dialog.exec_()

    def _export_truth_lab(self) -> None:
        current_ghost = self.manager.ghosts[0] if self.manager.ghosts else None
        outline = []
        name = "Greenland"
        area = 2166086.0
        if current_ghost is not None:
            name = getattr(current_ghost, "name", "Country")
            area = getattr(current_ghost, "area_km2", 100000.0)
            if hasattr(current_ghost, "wgs84_ring") and current_ghost.wgs84_ring:
                outline = current_ghost.wgs84_ring
            else:
                geom = getattr(current_ghost, "current_wgs84", None) or getattr(current_ghost, "geom_wgs84", None)
                if geom and not geom.isNull():
                    with suppress(Exception):
                        if geom.isMultipart():
                            mpoly = geom.asMultiPolygon()
                            if mpoly and mpoly[0] and mpoly[0][0]:
                                outline = [[float(p.x()), float(p.y())] for p in mpoly[0][0]]
                        else:
                            poly = geom.asPolygon()
                            if poly and poly[0]:
                                outline = [[float(p.x()), float(p.y())] for p in poly[0]]
        else:
            records = self.world.records()
            rec = records[0] if records else {"name": "Greenland", "area_km2": 2166086.0, "ring": []}
            name = rec.get("name", "Greenland")
            area = rec.get("area_km2", 2166086.0)
            outline = rec.get("ring", [])

        country_data = {
            "name": name,
            "iso_a3": name[:3].upper(),
            "area_km2": float(area),
            "outline": outline,
        }
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Map Truth Lab HTML Report",
            f"Map_Truth_Lab_{country_data['name'].replace(' ', '_')}.html",
            "HTML File (*.html)")
        if not filename:
            return
        if not filename.lower().endswith(".html"):
            filename += ".html"
        try:
            export_truth_lab_html(filename, country_data)
            self.truesize_status.setText(f"Truth Lab HTML saved to: {filename}")
        except Exception as exc:
            QMessageBox.critical(self, PLUGIN_TITLE, f"Export failed: {exc}")

    def _recommend_crs(self) -> None:
        canvas = self.iface.mapCanvas()
        extent = canvas.extent()
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        canvas_crs = canvas.mapSettings().destinationCrs()
        tr = QgsCoordinateTransform(canvas_crs, wgs84, QgsProject.instance())
        with suppress(Exception):
            wgs84_extent = tr.transformBoundingBox(extent)
            min_lat = max(-80.0, min(80.0, wgs84_extent.yMinimum()))
            max_lat = max(-80.0, min(80.0, wgs84_extent.yMaximum()))
            if min_lat >= max_lat:
                min_lat, max_lat = -50.0, 60.0
            purpose = self.rec_purpose_combo.currentText()
            recs = recommend_projections(min_lat, max_lat, purpose=purpose)
            self.rec_list.clear()
            for r in recs:
                item = QListWidgetItem(
                    f"[{r['score']} pts] {r['auth_id']} · {r['name']} ({r['family']})\n"
                    f"   Area: {r['area_grade']} (×{r['area_spread']}) · Shape: {r['shape_grade']} (max {r['max_omega_deg']}°)")
                item.setData(Qt.ItemDataRole.UserRole, r["auth_id"])
                self.rec_list.addItem(item)

    def _apply_recommended_crs(self) -> None:
        item = self.rec_list.currentItem()
        if not item:
            return
        auth_id = str(item.data(Qt.ItemDataRole.UserRole))
        if auth_id:
            crs = QgsCoordinateReferenceSystem(auth_id)
            if crs.isValid():
                QgsProject.instance().setCrs(crs)
                self.iface.mapCanvas().refresh()

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

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        ):
            self._apply_theme()

    def _apply_theme(self) -> None:
        root = self.widget()
        if root is None or getattr(self, "_theme_refreshing", False):
            return
        self._theme_refreshing = True
        try:
            apply_adaptive_theme(root)
        finally:
            self._theme_refreshing = False

    def clean_up(self) -> None:
        """Clean up all canvas rubber bands, ghosts, HUD, tool artifacts, and temporary layers."""
        with suppress(Exception):
            self.manager.clear()
        with suppress(Exception):
            self.hud.set_enabled(False)
            if hasattr(self, "hud_checkbox"):
                self.hud_checkbox.blockSignals(True)
                self.hud_checkbox.setChecked(False)
                self.hud_checkbox.blockSignals(False)
        with suppress(Exception):
            self.request_deactivate.emit()
        with suppress(Exception):
            self.uncheck_all_tools()
        with suppress(Exception):
            if hasattr(self, "fly_button"):
                self.fly_button.setEnabled(False)
            self._last_antipode = None
        with suppress(Exception):
            self.world.remove_world_layer_from_project()
            if hasattr(self, "world_checkbox"):
                self.world_checkbox.blockSignals(True)
                self.world_checkbox.setChecked(False)
                self.world_checkbox.blockSignals(False)
        with suppress(Exception):
            project = QgsProject.instance()
            for lyr_id, lyr in list(project.mapLayers().items()):
                if "Tissot" in lyr.name() or "indicatrix" in lyr.name().lower():
                    project.removeMapLayer(lyr_id)
        with suppress(Exception):
            if hasattr(self.iface, "actionPan") and self.iface.actionPan() is not None:
                self.iface.actionPan().trigger()
        with suppress(Exception):
            self.iface.mapCanvas().refresh()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.clean_up()
        super().closeEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.clean_up()
        super().hideEvent(event)

    def dispose(self) -> None:
        self.clean_up()
        self._fact_timer.stop()
        self.admin.cancel()
        self.hud.dispose()
        self.manager.dispose()
        self.world.remove_world_layer_from_project()
