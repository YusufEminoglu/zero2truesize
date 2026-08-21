# -*- coding: utf-8 -*-
"""The True Size drag tool.

The classic thetruesize.com trick, done with real projections: the picked
polygon is transformed into a Lambert azimuthal equal-area plane centred on
the grab point, optionally rotated, then inverse-projected through the same
projection re-centred under the cursor. The ghost outline therefore always
covers its true ground area, wherever it is dropped and whatever the
project CRS draws it like.
"""
from __future__ import annotations

from contextlib import suppress

from qgis.PyQt.QtCore import QElapsedTimer, QObject, QPoint, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QLabel
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapTool, QgsRubberBand

from ..core.distortion import relative_areal
from ..core.funits import belgiums, format_area_km2
from .support import (
    WGS84,
    canvas_projector,
    from_wgs84,
    geodesic_calculator,
    is_polygon_layer,
    to_wgs84,
    transform_context,
)

GHOST_COLORS = [
    (0, 137, 123),    # teal
    (244, 81, 30),    # deep orange
    (57, 73, 171),    # indigo
    (216, 27, 96),    # pink
    (67, 160, 71),    # green
    (255, 143, 0),    # amber
]

_INFO_QSS = (
    "QLabel { background: rgba(23, 32, 42, 225); color: #eceff1;"
    " border-radius: 6px; padding: 4px 9px; font-size: 9pt; }"
)


def laea_crs(lon: float, lat: float) -> QgsCoordinateReferenceSystem:
    """Lambert azimuthal equal-area plane centred on the given point."""
    proj = ("+proj=laea +lat_0={:.6f} +lon_0={:.6f} "
            "+datum=WGS84 +units=m +no_defs").format(lat, lon)
    return QgsCoordinateReferenceSystem.fromProj(proj)


def _apply(geom: QgsGeometry, transform: QgsCoordinateTransform) -> bool:
    """Transform in place; True on success on both int and enum-returning APIs."""
    result = geom.transform(transform)
    value = getattr(result, "value", result)
    try:
        return int(value) == 0
    except (TypeError, ValueError):
        return not geom.isNull()


def _unwrap_lons(geom: QgsGeometry, center_lon: float) -> QgsGeometry:
    """Shift longitudes so the polygon is continuous around ``center_lon``;
    stops antimeridian drops from smearing across the whole map."""
    box = geom.boundingBox()
    if box.width() <= 180.0:
        return geom
    multi = geom.asMultiPolygon()
    if not multi:
        single = geom.asPolygon()
        multi = [single] if single else []
    if not multi:
        return geom
    rebuilt = []
    for polygon in multi:
        new_rings = []
        for ring in polygon:
            pts = []
            for pt in ring:
                lon = pt.x()
                while lon - center_lon > 180.0:
                    lon -= 360.0
                while lon - center_lon < -180.0:
                    lon += 360.0
                pts.append(QgsPointXY(lon, pt.y()))
            new_rings.append(pts)
        rebuilt.append(new_rings)
    return QgsGeometry.fromMultiPolygonXY(rebuilt)


def true_size_ghost(geom_wgs84: QgsGeometry, src: QgsPointXY, dst: QgsPointXY,
                    rotation_deg: float = 0.0) -> QgsGeometry | None:
    """Re-centre a WGS84 polygon from ``src`` to ``dst`` preserving true area."""
    ghost = QgsGeometry(geom_wgs84)
    ctx = transform_context()
    if not _apply(ghost, QgsCoordinateTransform(WGS84, laea_crs(src.x(), src.y()), ctx)):
        return None
    if rotation_deg:
        ghost.rotate(rotation_deg, QgsPointXY(0.0, 0.0))
    if not _apply(ghost, QgsCoordinateTransform(laea_crs(dst.x(), dst.y()), WGS84, ctx)):
        return None
    return _unwrap_lons(ghost, dst.x())


class Ghost:
    """One draggable/dropped outline."""

    def __init__(self, name: str, geom_wgs84: QgsGeometry, src_anchor: QgsPointXY,
                 area_km2: float, color: tuple):
        self.name = name
        self.geom_wgs84 = QgsGeometry(geom_wgs84)
        self.src_anchor = QgsPointXY(src_anchor)
        self.dst_anchor = QgsPointXY(src_anchor)
        self.rotation = 0.0
        self.area_km2 = float(area_km2)
        self.color = color
        self.band: QgsRubberBand | None = None
        self.current_wgs84 = QgsGeometry(geom_wgs84)
        self.looks = 1.0

    @property
    def center_lat(self) -> float:
        """Latitude of the ghost's anchor point."""
        return float(self.dst_anchor.y())

    @property
    def wgs84_ring(self) -> list[list[float]]:
        """List of [lon, lat] coordinates representing the polygon outline."""
        geom = self.current_wgs84 if (self.current_wgs84 and not self.current_wgs84.isNull()) else self.geom_wgs84
        if geom and not geom.isNull():
            poly = geom.asPolygon()
            if poly and len(poly) > 0 and len(poly[0]) > 0:
                return [[p.x(), p.y()] for p in poly[0]]
            mpoly = geom.asMultiPolygon()
            if mpoly and len(mpoly) > 0 and len(mpoly[0]) > 0 and len(mpoly[0][0]) > 0:
                return [[p.x(), p.y()] for p in mpoly[0][0]]
        return []

    def label(self) -> str:
        text = f"{self.name} — true size {format_area_km2(self.area_km2)}"
        if self.looks >= 1.05:
            text += f" — this map draws it ×{self.looks:.2f} larger than at home"
        elif self.looks <= 0.95 and self.looks > 0:
            text += f" — this map draws it ×{1.0 / self.looks:.2f} smaller than at home"
        return text


class TrueSizeManager(QObject):
    """Owns the dropped ghosts and their rubber bands."""

    changed = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.ghosts: list[Ghost] = []
        self._color_index = 0
        canvas.destinationCrsChanged.connect(self.refresh_all)

    # ── bands ─────────────────────────────────────────────────────────

    def next_color(self) -> tuple:
        color = GHOST_COLORS[self._color_index % len(GHOST_COLORS)]
        self._color_index += 1
        return color

    def make_band(self, color: tuple) -> QgsRubberBand:
        band = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        r, g, b = color
        band.setStrokeColor(QColor(r, g, b, 235))
        band.setFillColor(QColor(r, g, b, 60))
        band.setWidth(2)
        return band

    def discard_band(self, band: QgsRubberBand | None) -> None:
        if band is not None:
            band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            with suppress(RuntimeError):
                self.canvas.scene().removeItem(band)

    # ── ghost lifecycle ───────────────────────────────────────────────

    def update_ghost(self, ghost: Ghost) -> bool:
        wgs = true_size_ghost(ghost.geom_wgs84, ghost.src_anchor,
                              ghost.dst_anchor, ghost.rotation)
        if wgs is None or wgs.isNull():
            return False
        ghost.current_wgs84 = wgs
        display = QgsGeometry(wgs)
        if not _apply(display, from_wgs84(self.canvas.mapSettings().destinationCrs())):
            return False
        if ghost.band is not None:
            ghost.band.setToGeometry(display, None)
        with suppress(Exception):
            ghost.looks = relative_areal(
                canvas_projector(self.canvas),
                ghost.dst_anchor.x(), ghost.dst_anchor.y(),
                ghost.src_anchor.x(), ghost.src_anchor.y())
        return True

    def adopt(self, ghost: Ghost) -> None:
        if ghost.band is None:
            ghost.band = self.make_band(ghost.color)
            self.update_ghost(ghost)
        self.ghosts.append(ghost)
        self.changed.emit()

    def remove_at(self, index: int) -> None:
        if 0 <= index < len(self.ghosts):
            ghost = self.ghosts.pop(index)
            self.discard_band(ghost.band)
            ghost.band = None
            self.changed.emit()

    def clear(self) -> None:
        for ghost in self.ghosts:
            self.discard_band(ghost.band)
            ghost.band = None
        self.ghosts.clear()
        self.changed.emit()

    def refresh_all(self) -> None:
        for ghost in self.ghosts:
            self.update_ghost(ghost)

    def dispose(self) -> None:
        self.clear()
        with suppress(TypeError, RuntimeError):
            self.canvas.destinationCrsChanged.disconnect(self.refresh_all)

    # ── export ────────────────────────────────────────────────────────

    def export_layer(self) -> QgsVectorLayer | None:
        if not self.ghosts:
            return None
        uri = ("MultiPolygon?crs=EPSG:4326"
               "&field=name:string(100)&field=true_area_km2:double"
               "&field=rotation_deg:double&field=dropped_lon:double&field=dropped_lat:double")
        layer = QgsVectorLayer(uri, "True Size ghosts — 02truesize", "memory")
        features = []
        for ghost in self.ghosts:
            geom = QgsGeometry(ghost.current_wgs84)
            geom.convertToMultiType()
            feature = QgsFeature(layer.fields())
            feature.setGeometry(geom)
            feature.setAttributes([
                ghost.name,
                round(ghost.area_km2, 1),
                round(ghost.rotation, 1),
                round(ghost.dst_anchor.x(), 5),
                round(ghost.dst_anchor.y(), 5),
            ])
            features.append(feature)
        layer.dataProvider().addFeatures(features)
        layer.updateExtents()
        layer.setOpacity(0.75)
        QgsProject.instance().addMapLayer(layer)
        return layer


class TrueSizePickTool(QgsMapTool):
    """Click a polygon to pick it up, move, click to drop. R/E rotate,
    right-click or Esc cancels."""

    message = pyqtSignal(str)

    def __init__(self, canvas, manager: TrueSizeManager, world, source_mode, source_layer):
        super().__init__(canvas)
        self._manager = manager
        self._world = world
        self._source_mode = source_mode          # () -> "world" | "active"
        self._source_layer = source_layer        # () -> QgsMapLayer | None
        self._carry: Ghost | None = None
        self._throttle = QElapsedTimer()
        self._throttle.start()
        self._info = QLabel(canvas.viewport())
        self._info.setStyleSheet(_INFO_QSS)
        self._info.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._info.hide()
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    # ── helpers ───────────────────────────────────────────────────────

    def _click_to_wgs84(self, event) -> QgsPointXY | None:
        map_point = self.toMapCoordinates(event.pos())
        transform = to_wgs84(self.canvas().mapSettings().destinationCrs())
        with suppress(Exception):
            return transform.transform(map_point)
        return None

    @staticmethod
    def _feature_title(layer: QgsVectorLayer, feature: QgsFeature) -> str:
        for field in ("name", "NAME", "Name", "NAME_EN", "ad", "label"):
            if layer.fields().indexOf(field) >= 0:
                value = feature.attribute(field)
                if value:
                    return str(value)
        return f"{layer.name()} #{feature.id()}"

    def _move_info(self, pos: QPoint) -> None:
        self._info.adjustSize()
        viewport = self.canvas().viewport()
        x = min(pos.x() + 16, max(0, viewport.width() - self._info.width() - 4))
        y = min(pos.y() + 18, max(0, viewport.height() - self._info.height() - 4))
        self._info.move(x, y)
        self._info.show()

    # ── picking / dropping ────────────────────────────────────────────

    def _pick(self, wgs: QgsPointXY, map_point: QgsPointXY) -> None:
        if self._source_mode() == "world":
            feature = self._world.country_feature_at(wgs.x(), wgs.y())
            if feature is None:
                self.message.emit("No country under the click — is the world layer visible? "
                                  "(Enable it above, or switch the source to your active layer.)")
                return
            name = str(feature.attribute("name") or "Unnamed")
            area_km2 = float(feature.attribute("area_km2") or 0.0)
            geom = QgsGeometry(feature.geometry())
        else:
            layer = self._source_layer()
            if not is_polygon_layer(layer):
                if self._source_mode() == "admin":
                    self.message.emit(
                        "No downloaded administrative layer is available — choose a "
                        "country and boundary set, then download it first.")
                else:
                    self.message.emit(
                        "The active layer is not a polygon layer — select one in the layers "
                        "panel, or switch the source to the world countries.")
                return
            found = self._find_in_layer(layer, wgs, map_point)
            if found is None:
                self.message.emit("No polygon of the active layer under the click.")
                return
            feature, geom = found
            name = self._feature_title(layer, feature)
            calc = geodesic_calculator()
            area_km2 = 0.0
            with suppress(Exception):
                area_km2 = calc.measureArea(geom) / 1e6
        geom = geom.makeValid()
        ghost = Ghost(name, geom, wgs, area_km2, self._manager.next_color())
        ghost.band = self._manager.make_band(ghost.color)
        self._carry = ghost
        self._manager.update_ghost(ghost)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.message.emit(f"Carrying {name} ({format_area_km2(area_km2)} ≈ "
                          f"{belgiums(area_km2)} Belgiums). Click to drop, R/E to rotate, "
                          "right-click to cancel.")

    def _find_in_layer(self, layer: QgsVectorLayer, wgs: QgsPointXY, map_point: QgsPointXY):
        ctx = transform_context()
        with suppress(Exception):
            to_layer = QgsCoordinateTransform(WGS84, layer.crs(), ctx)
            point = to_layer.transform(wgs)
            tolerance = self.canvas().mapUnitsPerPixel() * 2.0
            map_to_layer = QgsCoordinateTransform(
                self.canvas().mapSettings().destinationCrs(), layer.crs(), ctx)
            rect = map_to_layer.transformBoundingBox(QgsRectangle(
                map_point.x() - tolerance, map_point.y() - tolerance,
                map_point.x() + tolerance, map_point.y() + tolerance))
            request = QgsFeatureRequest().setFilterRect(rect)
            for feature in layer.getFeatures(request):
                geom = feature.geometry()
                if geom is not None and geom.contains(point):
                    out = QgsGeometry(geom)
                    if not layer.crs().isValid() or layer.crs() == WGS84 or _apply(
                            out, QgsCoordinateTransform(layer.crs(), WGS84, ctx)):
                        return QgsFeature(feature), out
        return None

    def _drop(self, wgs: QgsPointXY) -> None:
        ghost = self._carry
        self._carry = None
        ghost.dst_anchor = wgs
        self._manager.update_ghost(ghost)
        self._manager.adopt(ghost)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._info.hide()
        self.message.emit(f"Dropped: {ghost.label()}. Pick up another, or manage ghosts below.")

    def _cancel(self) -> None:
        if self._carry is not None:
            self._manager.discard_band(self._carry.band)
            self._carry = None
        self._info.hide()
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    # ── QgsMapTool events ─────────────────────────────────────────────

    def canvasReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.MouseButton.RightButton:
            if self._carry is not None:
                self._cancel()
                self.message.emit("Cancelled.")
            return
        wgs = self._click_to_wgs84(event)
        if wgs is None:
            self.message.emit("That point does not exist on the globe in this projection.")
            return
        if self._carry is None:
            self._pick(wgs, self.toMapCoordinates(event.pos()))
        else:
            self._drop(wgs)

    def canvasMoveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self._carry is None:
            return
        if self._throttle.elapsed() < 16:
            return
        self._throttle.restart()
        wgs = self._click_to_wgs84(event)
        if wgs is None:
            return
        self._carry.dst_anchor = wgs
        if self._manager.update_ghost(self._carry):
            self._info.setText(self._carry.label())
            self._move_info(event.pos())

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self._carry is None:
            return
        key = event.key()
        if key == Qt.Key.Key_R:
            self._carry.rotation = (self._carry.rotation + 10.0) % 360.0
        elif key == Qt.Key.Key_E:
            self._carry.rotation = (self._carry.rotation - 10.0) % 360.0
        elif key == Qt.Key.Key_Escape:
            self._cancel()
            self.message.emit("Cancelled.")
            return
        else:
            return
        if self._manager.update_ghost(self._carry):
            self._info.setText(self._carry.label())

    def cancel_carry(self) -> None:
        self._cancel()

    def deactivate(self) -> None:
        self._cancel()
        if hasattr(self, "_info") and self._info is not None:
            self._info.hide()
        super().deactivate()
