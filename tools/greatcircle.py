# -*- coding: utf-8 -*-
"""Great-circle truth: the genuinely shortest path between two clicks,
drawn against the 'straight' line the flat map suggests, with the wasted
kilometres spelled out."""
from __future__ import annotations

from contextlib import suppress

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsGeometry, QgsPointXY, QgsWkbTypes
from qgis.gui import QgsMapTool, QgsRubberBand, QgsVertexMarker

from ..core.geomath import (
    compass_direction,
    initial_bearing_deg,
    rhumb_bearing_deg,
    rhumb_distance_km,
)
from .support import from_wgs84, geodesic_calculator, to_wgs84

GEODESIC_COLOR = QColor(21, 101, 192)   # blue: the honest path
STRAIGHT_COLOR = QColor(229, 57, 53)    # red: the map's suggestion


class GreatCircleTool(QgsMapTool):
    result = pyqtSignal(dict)
    message = pyqtSignal(str)

    def __init__(self, canvas):
        super().__init__(canvas)
        self._first: QgsPointXY | None = None      # WGS84
        self._geo_band: QgsRubberBand | None = None
        self._straight_band: QgsRubberBand | None = None
        self._markers: list[QgsVertexMarker] = []
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ── events ────────────────────────────────────────────────────────

    def canvasReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.MouseButton.RightButton:
            self.reset()
            self.message.emit("Reset. Click a start point.")
            return
        map_point = self.toMapCoordinates(event.pos())
        transform = to_wgs84(self.canvas().mapSettings().destinationCrs())
        wgs = None
        with suppress(Exception):
            wgs = transform.transform(map_point)
        if wgs is None:
            self.message.emit("That point does not exist on the globe in this projection.")
            return
        if self._first is None:
            self.reset()
            self._first = QgsPointXY(wgs)
            self._add_marker(map_point)
            self.message.emit("Now click the destination.")
        else:
            self._add_marker(map_point)
            self._build(self._first, QgsPointXY(wgs))
            self._first = None

    # ── construction ──────────────────────────────────────────────────

    def _build(self, a: QgsPointXY, b: QgsPointXY) -> None:
        calc = geodesic_calculator()
        geodesic_m = calc.measureLine([a, b])
        parts = calc.geodesicLine(a, b, 25000.0, True)
        canvas_crs = self.canvas().mapSettings().destinationCrs()
        to_canvas = from_wgs84(canvas_crs)
        multiline = []
        for part in parts:
            pts = []
            for point in part:
                with suppress(Exception):
                    pts.append(to_canvas.transform(point))
            if len(pts) >= 2:
                multiline.append(pts)
        if multiline:
            self._geo_band = self._line_band(GEODESIC_COLOR, 3)
            self._geo_band.setToGeometry(QgsGeometry.fromMultiPolylineXY(multiline), None)

        a_map = b_map = None
        with suppress(Exception):
            a_map = to_canvas.transform(a)
            b_map = to_canvas.transform(b)
        straight_km = None
        if a_map is not None and b_map is not None:
            self._straight_band = self._line_band(STRAIGHT_COLOR, 2, dashed=True)
            self._straight_band.setToGeometry(
                QgsGeometry.fromPolylineXY([a_map, b_map]), None)
            straight_km = self._straight_ground_km(a_map, b_map, calc)

        geodesic_km = geodesic_m / 1000.0
        gc_brg = initial_bearing_deg(a.y(), a.x(), b.y(), b.x())
        rh_brg = rhumb_bearing_deg(a.y(), a.x(), b.y(), b.x())
        rh_km = rhumb_distance_km(a.y(), a.x(), b.y(), b.x())
        payload = {
            "a_lon": a.x(), "a_lat": a.y(), "b_lon": b.x(), "b_lat": b.y(),
            "geodesic_km": geodesic_km,
            "straight_km": straight_km,
            "gc_bearing_deg": gc_brg,
            "gc_cardinal": compass_direction(gc_brg),
            "rhumb_bearing_deg": rh_brg,
            "rhumb_cardinal": compass_direction(rh_brg),
            "rhumb_km": rh_km,
        }
        if straight_km is not None and geodesic_km > 0:
            saved = max(0.0, straight_km - geodesic_km)
            payload["saved_km"] = saved
            payload["saved_pct"] = 100.0 * saved / geodesic_km
        self.result.emit(payload)

    def _straight_ground_km(self, a_map: QgsPointXY, b_map: QgsPointXY, calc) -> float | None:
        """True ground length of the straight segment as drawn on this map."""
        samples = 256
        to_wgs = to_wgs84(self.canvas().mapSettings().destinationCrs())
        line_wgs: list[QgsPointXY] = []
        for i in range(samples + 1):
            t = i / samples
            x = a_map.x() + (b_map.x() - a_map.x()) * t
            y = a_map.y() + (b_map.y() - a_map.y()) * t
            with suppress(Exception):
                line_wgs.append(to_wgs.transform(QgsPointXY(x, y)))
        if len(line_wgs) < 2:
            return None
        with suppress(Exception):
            return calc.measureLine(line_wgs) / 1000.0
        return None

    # ── plumbing ──────────────────────────────────────────────────────

    def _line_band(self, color: QColor, width: int, dashed: bool = False) -> QgsRubberBand:
        band = QgsRubberBand(self.canvas(), QgsWkbTypes.GeometryType.LineGeometry)
        band.setColor(color)
        band.setWidth(width)
        if dashed:
            band.setLineStyle(Qt.PenStyle.DashLine)
        return band

    def _add_marker(self, map_point: QgsPointXY) -> None:
        marker = QgsVertexMarker(self.canvas())
        marker.setCenter(map_point)
        marker.setColor(GEODESIC_COLOR)
        marker.setIconType(QgsVertexMarker.IconType.ICON_CIRCLE)
        marker.setIconSize(10)
        marker.setPenWidth(3)
        self._markers.append(marker)

    def reset(self) -> None:
        self._first = None
        for band in (self._geo_band, self._straight_band):
            if band is not None:
                with suppress(RuntimeError):
                    self.canvas().scene().removeItem(band)
        self._geo_band = self._straight_band = None
        for marker in self._markers:
            with suppress(RuntimeError):
                self.canvas().scene().removeItem(marker)
        self._markers.clear()

    def dispose(self) -> None:
        self.reset()
