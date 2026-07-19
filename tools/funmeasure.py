# -*- coding: utf-8 -*-
"""Fun-unit measurements: distances in marathons, areas in Belgiums.

Two map tools: a click-path distance measurer and a click-a-polygon area
reader. Both report accurate geodesic numbers first and the fun units after
— the joke is the phrasing, never the maths.
"""
from __future__ import annotations

from contextlib import suppress

from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsWkbTypes,
)
from qgis.gui import QgsMapTool, QgsRubberBand

from ..core.funits import format_area_km2, format_km, fun_area_lines, fun_distance_lines
from .support import WGS84, geodesic_calculator, is_polygon_layer, to_wgs84, transform_context

PATH_COLOR = QColor(46, 125, 50)
FLASH_COLOR = QColor(255, 193, 7)


class FunnyDistanceTool(QgsMapTool):
    """Click a path; right-click (or double-click) to total it up."""

    result = pyqtSignal(dict)
    message = pyqtSignal(str)

    def __init__(self, canvas):
        super().__init__(canvas)
        self._wgs_points: list[QgsPointXY] = []
        self._band: QgsRubberBand | None = None
        self._finished = False
        self.setCursor(Qt.CursorShape.CrossCursor)

    def canvasReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.MouseButton.RightButton:
            self._finish()
            return
        if self._finished:
            self.reset()
        map_point = self.toMapCoordinates(event.pos())
        transform = to_wgs84(self.canvas().mapSettings().destinationCrs())
        wgs = None
        with suppress(Exception):
            wgs = transform.transform(map_point)
        if wgs is None:
            self.message.emit("That point does not exist on the globe in this projection.")
            return
        self._wgs_points.append(QgsPointXY(wgs))
        if self._band is None:
            self._band = QgsRubberBand(self.canvas(), QgsWkbTypes.GeometryType.LineGeometry)
            self._band.setColor(PATH_COLOR)
            self._band.setWidth(3)
        self._band.addPoint(map_point, True)
        if len(self._wgs_points) == 1:
            self.message.emit("Keep clicking; right-click to total it up.")

    def canvasDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt API)
        del event
        self._finish()

    def _finish(self) -> None:
        if len(self._wgs_points) < 2:
            self.reset()
            self.message.emit("Click at least two points first.")
            return
        calc = geodesic_calculator()
        km = 0.0
        with suppress(Exception):
            km = calc.measureLine(self._wgs_points) / 1000.0
        self._finished = True
        self.result.emit({
            "kind": "distance",
            "km": km,
            "headline": format_km(km),
            "lines": fun_distance_lines(km),
        })

    def reset(self) -> None:
        self._wgs_points.clear()
        self._finished = False
        if self._band is not None:
            with suppress(RuntimeError):
                self.canvas().scene().removeItem(self._band)
            self._band = None

    def deactivate(self) -> None:
        self.reset()
        super().deactivate()

    def dispose(self) -> None:
        self.reset()


class FunnyAreaTool(QgsMapTool):
    """Click any visible polygon; get its true area in serious and fun units."""

    result = pyqtSignal(dict)
    message = pyqtSignal(str)

    def __init__(self, canvas):
        super().__init__(canvas)
        self._flash: QgsRubberBand | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def canvasReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.MouseButton.RightButton:
            return
        map_point = self.toMapCoordinates(event.pos())
        transform = to_wgs84(self.canvas().mapSettings().destinationCrs())
        wgs = None
        with suppress(Exception):
            wgs = transform.transform(map_point)
        if wgs is None:
            self.message.emit("That point does not exist on the globe in this projection.")
            return
        hit = self._find_polygon(wgs, map_point)
        if hit is None:
            self.message.emit("No visible polygon under the click.")
            return
        layer, feature, geom_layer_crs = hit
        calc = QgsDistanceArea()
        calc.setSourceCrs(layer.crs(), transform_context())
        calc.setEllipsoid("WGS84")
        km2 = 0.0
        with suppress(Exception):
            km2 = calc.measureArea(geom_layer_crs) / 1e6
        self._flash_geometry(layer, geom_layer_crs)
        title = self._title(layer, feature)
        self.result.emit({
            "kind": "area",
            "km2": km2,
            "name": title,
            "headline": f"{title}: {format_area_km2(km2)}",
            "lines": fun_area_lines(km2),
        })

    def _find_polygon(self, wgs: QgsPointXY, map_point: QgsPointXY):
        ctx = transform_context()
        root = QgsProject.instance().layerTreeRoot()
        tolerance = self.canvas().mapUnitsPerPixel() * 2.0
        for layer in root.layerOrder():
            if not is_polygon_layer(layer):
                continue
            node = root.findLayer(layer.id())
            if node is None or not node.isVisible():
                continue
            with suppress(Exception):
                point = QgsCoordinateTransform(WGS84, layer.crs(), ctx).transform(wgs)
                rect = QgsCoordinateTransform(
                    self.canvas().mapSettings().destinationCrs(), layer.crs(), ctx,
                ).transformBoundingBox(QgsRectangle(
                    map_point.x() - tolerance, map_point.y() - tolerance,
                    map_point.x() + tolerance, map_point.y() + tolerance))
                for feature in layer.getFeatures(QgsFeatureRequest().setFilterRect(rect)):
                    geom = feature.geometry()
                    if geom is not None and geom.contains(point):
                        return layer, feature, QgsGeometry(geom)
        return None

    @staticmethod
    def _title(layer, feature) -> str:
        for field in ("name", "NAME", "Name", "NAME_EN", "ad", "label"):
            if layer.fields().indexOf(field) >= 0:
                value = feature.attribute(field)
                if value:
                    return str(value)
        return f"{layer.name()} #{feature.id()}"

    def _flash_geometry(self, layer, geom_layer_crs: QgsGeometry) -> None:
        self._clear_flash()
        band = QgsRubberBand(self.canvas(), QgsWkbTypes.GeometryType.PolygonGeometry)
        band.setStrokeColor(FLASH_COLOR)
        band.setFillColor(QColor(255, 193, 7, 70))
        band.setWidth(3)
        band.setToGeometry(QgsGeometry(geom_layer_crs), layer)
        self._flash = band
        QTimer.singleShot(1400, self._clear_flash)

    def _clear_flash(self) -> None:
        if self._flash is not None:
            with suppress(RuntimeError):
                self.canvas().scene().removeItem(self._flash)
            self._flash = None

    def deactivate(self) -> None:
        self._clear_flash()
        super().deactivate()

    def dispose(self) -> None:
        self._clear_flash()
