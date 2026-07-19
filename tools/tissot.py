# -*- coding: utf-8 -*-
"""Distortion lab: Tissot indicatrix circles, a live distortion HUD and the
projection honesty report card — all driven by the numeric distortion core."""
from __future__ import annotations

from contextlib import suppress

from qgis.PyQt.QtCore import QEvent, QObject, Qt, QTimer
from qgis.PyQt.QtWidgets import QLabel
from qgis.core import (
    QgsFeature,
    QgsFillSymbol,
    QgsGeometry,
    QgsPointXY,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)

from ..core import distortion
from ..core.geomath import circle_ring, crosses_antimeridian
from .support import canvas_projector, to_wgs84

_HUD_QSS = (
    "QLabel { background: rgba(23, 32, 42, 210); color: #eceff1;"
    " border-radius: 6px; padding: 4px 10px; font-size: 9pt; }"
)


def make_tissot_layer(radius_km: float = 500.0, lat_step: int = 30,
                      lon_step: int = 30, lat_limit: int = 60) -> QgsVectorLayer:
    """Memory layer of constant ground-radius circles on a lon/lat grid.

    Rendered in the project CRS they become the classic Tissot indicatrix:
    equal circles on the ground, telling shapes on the map.
    """
    uri = ("Polygon?crs=EPSG:4326&field=center_lat:double"
           "&field=center_lon:double&field=radius_km:double")
    layer = QgsVectorLayer(uri, f"Tissot circles {radius_km:g} km — 02truesize", "memory")
    features = []
    for lat in range(-lat_limit, lat_limit + 1, lat_step):
        for lon in range(-180, 180, lon_step):
            ring = circle_ring(float(lat), float(lon), radius_km, 72)
            if crosses_antimeridian(ring):
                continue
            points = [QgsPointXY(x, y) for x, y in ring]
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromPolygonXY([points]))
            feature.setAttributes([float(lat), float(lon), float(radius_km)])
            features.append(feature)
    layer.dataProvider().addFeatures(features)
    layer.updateExtents()
    symbol = QgsFillSymbol.createSimple({
        "color": "229,57,53,60",
        "outline_color": "183,28,28,200",
        "outline_width": "0.4",
    })
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    return layer


def crs_report_card(canvas) -> dict:
    """Grade the canvas' current projection for area and shape honesty."""
    crs = canvas.mapSettings().destinationCrs()
    card = {"ok": False, "rows": []}
    with suppress(Exception):
        card = distortion.report_card(canvas_projector(canvas))
    card["crs_name"] = crs.userFriendlyIdentifier() if crs.isValid() else "Unknown CRS"
    return card


class DistortionHUD(QObject):
    """Small always-on-top canvas overlay: how stretched is the map right here?"""

    def __init__(self, canvas):
        super().__init__(canvas)
        self._canvas = canvas
        self._label = QLabel(canvas.viewport())
        self._label.setStyleSheet(_HUD_QSS)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._label.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._refresh)
        self._enabled = False
        canvas.viewport().installEventFilter(self)

    def set_enabled(self, enabled: bool) -> None:
        if enabled == self._enabled:
            return
        self._enabled = enabled
        if enabled:
            self._canvas.extentsChanged.connect(self._schedule)
            self._canvas.destinationCrsChanged.connect(self._schedule)
            self._refresh()
        else:
            with suppress(TypeError, RuntimeError):
                self._canvas.extentsChanged.disconnect(self._schedule)
            with suppress(TypeError, RuntimeError):
                self._canvas.destinationCrsChanged.disconnect(self._schedule)
            self._label.hide()

    def _schedule(self) -> None:
        self._timer.start()

    def _refresh(self) -> None:
        if not self._enabled:
            return
        text = None
        with suppress(Exception):
            center_map = self._canvas.center()
            wgs = to_wgs84(self._canvas.mapSettings().destinationCrs()).transform(center_map)
            projector = canvas_projector(self._canvas)
            here = distortion.tissot(projector, wgs.x(), wgs.y())
            rel = None
            with suppress(Exception):
                rel = distortion.relative_areal(projector, wgs.x(), wgs.y(), wgs.x(), 0.0)
            if rel is not None and rel > 0:
                text = (f"Map truth @ {wgs.y():.1f}°: areas ×{rel:.2f} vs the equator · "
                        f"shapes bent {here['omega_deg']:.0f}°")
            else:
                text = f"Map truth: shapes bent {here['omega_deg']:.0f}° here"
        if text is None:
            self._label.hide()
            return
        self._label.setText(text)
        self._reposition()
        self._label.show()

    def _reposition(self) -> None:
        self._label.adjustSize()
        viewport = self._canvas.viewport()
        self._label.move(max(4, viewport.width() - self._label.width() - 10), 8)

    def eventFilter(self, obj, event):  # noqa: N802 (Qt API)
        if event.type() == QEvent.Type.Resize and self._label.isVisible():
            self._reposition()
        return False

    def dispose(self) -> None:
        self.set_enabled(False)
        with suppress(RuntimeError):
            self._canvas.viewport().removeEventFilter(self)
        self._label.deleteLater()
