# -*- coding: utf-8 -*-
"""Asynchronous, small-area OSM polygon acquisition through QGIS networking."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlencode

from qgis.PyQt.QtCore import QByteArray, QObject, QUrl, QVariant, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsFillSymbol,
    QgsNetworkAccessManager,
    QgsProcessingUtils,
    QgsProject,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)

from ..core.osm import overpass_query, validate_bbox

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "02truesize/0.3 (+https://github.com/YusufEminoglu/zero2truesize)"
LAYER_PROPERTY = "zero2truesize/osm_download"


def _tag(feature, field_names: set[str], key: str) -> str:
    if key in field_names:
        value = feature.attribute(key)
        if value is not None:
            text = str(value)
            if text and text.lower() != "null":
                return text
    if "other_tags" not in field_names:
        return ""
    other = str(feature.attribute("other_tags") or "")
    match = re.search(rf'"{re.escape(key)}"=>"([^"\\]*(?:\\.[^"\\]*)*)"', other)
    return match.group(1).replace('\\"', '"') if match else ""


def _polygon_kind(feature, field_names: set[str]) -> tuple[str, str]:
    for key in ("boundary", "building", "leisure", "landuse", "natural", "water", "waterway"):
        value = _tag(feature, field_names, key)
        if value:
            return key, value
    return "", ""


def load_osm_polygons(path: Path) -> QgsVectorLayer | None:
    """Copy relevant OGR OSM multipolygons into one self-contained memory layer."""
    source = QgsVectorLayer(f"{path}|layername=multipolygons", "OSM polygons", "ogr")
    if not source.isValid():
        raise RuntimeError("QGIS/GDAL could not read the downloaded OSM XML.")
    output = QgsVectorLayer(
        "MultiPolygon?crs=EPSG:4326", "OSM polygons — 02truesize", "memory")
    fields = QgsFields()
    for name in ("osm_id", "name", "kind", "class"):
        fields.append(QgsField(name, QVariant.String))
    output.dataProvider().addAttributes(fields)
    output.updateFields()
    source_fields = {field.name() for field in source.fields()}
    features = []
    for source_feature in source.getFeatures():
        kind, class_value = _polygon_kind(source_feature, source_fields)
        geometry = source_feature.geometry()
        if not kind or geometry is None or geometry.isEmpty():
            continue
        geometry = geometry.makeValid()
        if geometry.isEmpty():
            continue
        geometry.convertToMultiType()
        feature = QgsFeature(output.fields())
        feature.setGeometry(geometry)
        osm_id = source_feature.attribute("osm_id") if "osm_id" in source_fields else ""
        name = _tag(source_feature, source_fields, "name")
        feature.setAttributes([str(osm_id or ""), name, kind, class_value])
        features.append(feature)
    if not features:
        return None
    output.dataProvider().addFeatures(features)
    output.updateExtents()
    output.setCustomProperty(LAYER_PROPERTY, True)
    symbol = QgsFillSymbol.createSimple({
        "color": "0,137,123,45",
        "outline_color": "0,105,92,210",
        "outline_width": "0.35",
    })
    output.setRenderer(QgsSingleSymbolRenderer(symbol))
    return output


class OsmDownloadManager(QObject):
    """Own one asynchronous Overpass request and its latest result layer."""

    started = pyqtSignal(str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reply = None
        self._cancelled = False
        self._layer_id: str | None = None

    @property
    def busy(self) -> bool:
        return self._reply is not None

    def layer(self) -> QgsVectorLayer | None:
        if not self._layer_id:
            return None
        layer = QgsProject.instance().mapLayer(self._layer_id)
        if isinstance(layer, QgsVectorLayer):
            return layer
        self._layer_id = None
        return None

    def download(self, rectangle, crs) -> None:
        if self.busy:
            raise RuntimeError("An OSM download is already running.")
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(crs, wgs84, QgsProject.instance())
        bbox = transform.transformBoundingBox(rectangle)
        south, west = bbox.yMinimum(), bbox.xMinimum()
        north, east = bbox.yMaximum(), bbox.xMaximum()
        metrics = validate_bbox(south, west, north, east)
        query = overpass_query(south, west, north, east)
        request = QNetworkRequest(QUrl(OVERPASS_URL))
        request.setRawHeader(
            QByteArray(b"User-Agent"), QByteArray(USER_AGENT.encode("ascii")))
        request.setRawHeader(
            QByteArray(b"Content-Type"),
            QByteArray(b"application/x-www-form-urlencoded; charset=UTF-8"))
        self._cancelled = False
        body = QByteArray(urlencode({"data": query}).encode("utf-8"))
        self._reply = QgsNetworkAccessManager.instance().post(request, body)
        self._reply.finished.connect(self._on_finished)
        self.started.emit(
            f"{metrics['width_km']:.2f} x {metrics['height_km']:.2f} km "
            f"({metrics['area_km2']:.2f} km²)")

    def cancel(self) -> None:
        if self._reply is not None:
            self._cancelled = True
            self._reply.abort()

    def _on_finished(self) -> None:
        reply = self._reply
        self._reply = None
        if reply is None:
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        network_error = reply.error()
        error_code = int(getattr(network_error, "value", network_error))
        payload = bytes(reply.readAll())
        error_text = reply.errorString()
        reply.deleteLater()
        if self._cancelled:
            self._cancelled = False
            self.failed.emit("OSM download cancelled.")
            return
        if error_code or not payload:
            if status in (429, 504):
                self.failed.emit(
                    f"Overpass returned HTTP {status}. The public server is busy; "
                    "wait briefly, zoom in further, and retry.")
            else:
                self.failed.emit(
                    f"OSM download failed (HTTP {status or 'unknown'}): {error_text}")
            return
        start = payload.lstrip()[:64].lower()
        if not (start.startswith(b"<?xml") or start.startswith(b"<osm")):
            self.failed.emit("Overpass returned an unexpected response instead of OSM XML.")
            return
        try:
            path = Path(QgsProcessingUtils.generateTempFilename("02truesize.osm"))
            path.write_bytes(payload)
            layer = load_osm_polygons(path)
        except (OSError, RuntimeError, ValueError) as exc:
            self.failed.emit(f"OSM data could not be converted: {exc}")
            return
        if layer is None:
            self.failed.emit("No usable OSM polygons were found in this view.")
            return
        project = QgsProject.instance()
        previous = self.layer()
        if previous is not None:
            project.removeMapLayer(previous.id())
        project.addMapLayer(layer, False)
        project.layerTreeRoot().insertLayer(0, layer)
        self._layer_id = layer.id()
        self.finished.emit(layer)
