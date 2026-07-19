# -*- coding: utf-8 -*-
"""Shared QGIS helpers: CRS transforms, geodesic measurement, enum compat."""
from __future__ import annotations

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)

WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")


def enum_value(enum_or_int) -> int:
    """Integer value of a possibly-scoped enum, on both Qt5 and Qt6 bindings."""
    return int(getattr(enum_or_int, "value", enum_or_int))


def is_polygon_layer(layer) -> bool:
    if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
        return False
    polygon = enum_value(QgsWkbTypes.GeometryType.PolygonGeometry)
    return enum_value(layer.geometryType()) == polygon


def transform_context():
    return QgsProject.instance().transformContext()


def to_wgs84(crs: QgsCoordinateReferenceSystem) -> QgsCoordinateTransform:
    return QgsCoordinateTransform(crs, WGS84, transform_context())


def from_wgs84(crs: QgsCoordinateReferenceSystem) -> QgsCoordinateTransform:
    return QgsCoordinateTransform(WGS84, crs, transform_context())


def geodesic_calculator() -> QgsDistanceArea:
    """WGS84-ellipsoid measurer; lengths/areas come back in metres/square metres."""
    calc = QgsDistanceArea()
    calc.setSourceCrs(WGS84, transform_context())
    calc.setEllipsoid("WGS84")
    return calc


def canvas_projector(canvas):
    """A pure ``(lon, lat) -> (x, y)`` callable for the canvas destination CRS,
    suitable for the numeric distortion module. Raises on transform failure."""
    transform = from_wgs84(canvas.mapSettings().destinationCrs())

    def project(lon: float, lat: float):
        point = transform.transform(QgsPointXY(lon, lat))
        return point.x(), point.y()

    return project
