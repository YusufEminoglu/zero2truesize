# -*- coding: utf-8 -*-
"""Antipode tunnel: click anywhere, learn where you'd surface if you dug
straight through the centre of the Earth (spoiler: usually the ocean)."""
from __future__ import annotations

from contextlib import suppress

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.gui import QgsMapTool, QgsVertexMarker
from qgis.core import QgsPointXY

from ..core.funits import antipode_line
from ..core.geomath import LCG, antipode
from .support import from_wgs84, to_wgs84


class AntipodeTool(QgsMapTool):
    result = pyqtSignal(dict)
    message = pyqtSignal(str)

    def __init__(self, canvas, world):
        super().__init__(canvas)
        self._world = world
        self._rng = LCG(987654321)
        self._markers: list[QgsVertexMarker] = []
        self.last_antipode: tuple[float, float] | None = None  # (lon, lat)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def canvasReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.MouseButton.RightButton:
            self.clear_markers()
            return
        map_point = self.toMapCoordinates(event.pos())
        transform = to_wgs84(self.canvas().mapSettings().destinationCrs())
        wgs = None
        with suppress(Exception):
            wgs = transform.transform(map_point)
        if wgs is None:
            self.message.emit("That point does not exist on the globe in this projection.")
            return
        anti_lat, anti_lon = antipode(wgs.y(), wgs.x())
        origin_country = self._world.country_name_at(wgs.x(), wgs.y())
        target_country = self._world.country_name_at(anti_lon, anti_lat)
        self.last_antipode = (anti_lon, anti_lat)
        visible = self._place_markers(map_point, anti_lon, anti_lat)
        self.result.emit({
            "from_lon": wgs.x(), "from_lat": wgs.y(),
            "to_lon": anti_lon, "to_lat": anti_lat,
            "origin_country": origin_country,
            "country": target_country,
            "line": antipode_line(target_country, self._rng),
            "marker_visible": visible,
        })

    def _place_markers(self, origin_map: QgsPointXY, anti_lon: float, anti_lat: float) -> bool:
        self.clear_markers()
        origin = QgsVertexMarker(self.canvas())
        origin.setCenter(origin_map)
        origin.setColor(QColor(21, 101, 192))
        origin.setIconType(QgsVertexMarker.IconType.ICON_CIRCLE)
        origin.setIconSize(12)
        origin.setPenWidth(3)
        self._markers.append(origin)
        shown = False
        transform = from_wgs84(self.canvas().mapSettings().destinationCrs())
        with suppress(Exception):
            target_map = transform.transform(QgsPointXY(anti_lon, anti_lat))
            target = QgsVertexMarker(self.canvas())
            target.setCenter(target_map)
            target.setColor(QColor(198, 40, 40))
            target.setIconType(QgsVertexMarker.IconType.ICON_X)
            target.setIconSize(16)
            target.setPenWidth(3)
            self._markers.append(target)
            shown = True
        return shown

    def clear_markers(self) -> None:
        for marker in self._markers:
            with suppress(RuntimeError):
                self.canvas().scene().removeItem(marker)
        self._markers.clear()

    def dispose(self) -> None:
        self.clear_markers()
