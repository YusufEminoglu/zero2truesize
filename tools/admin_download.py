# -*- coding: utf-8 -*-
"""Asynchronous ADM0/ADM1 vector download from the geoBoundaries API."""
from __future__ import annotations

import json
from pathlib import Path

from qgis.PyQt.QtCore import QByteArray, QObject, QUrl, QVariant, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import (
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

from ..core.admin_data import metadata_url

USER_AGENT = "02truesize/0.3.1 (+https://github.com/YusufEminoglu/zero2truesize)"
LAYER_PROPERTY = "zero2truesize/admin_download"


def _first_attribute(feature, field_names: set[str], candidates: tuple[str, ...]) -> str:
    for name in candidates:
        if name in field_names:
            value = feature.attribute(name)
            if value is not None and str(value):
                return str(value)
    return ""


def load_boundary_geojson(path: Path, layer_name: str, metadata: dict) -> QgsVectorLayer | None:
    """Copy a downloaded boundary GeoJSON into a self-contained memory layer."""
    source = QgsVectorLayer(str(path), layer_name, "ogr")
    if not source.isValid():
        raise RuntimeError("QGIS/GDAL could not read the downloaded boundary GeoJSON.")
    output = QgsVectorLayer(
        "MultiPolygon?crs=EPSG:4326", f"{layer_name} — 02truesize", "memory")
    fields = QgsFields()
    for name in ("name", "boundary_id", "adm_level", "source", "year", "license"):
        fields.append(QgsField(name, QVariant.String))
    output.dataProvider().addAttributes(fields)
    output.updateFields()
    source_fields = {field.name() for field in source.fields()}
    features = []
    for source_feature in source.getFeatures():
        geometry = source_feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        geometry = geometry.makeValid()
        if geometry.isEmpty():
            continue
        geometry.convertToMultiType()
        feature = QgsFeature(output.fields())
        feature.setGeometry(geometry)
        name = _first_attribute(
            source_feature, source_fields,
            ("shapeName", "shapeName_EN", "name", "NAME_1", "NAME_0"))
        boundary_id = _first_attribute(
            source_feature, source_fields, ("shapeID", "shapeISO", "boundaryID"))
        feature.setAttributes([
            name or str(metadata.get("boundaryName") or "Administrative unit"),
            boundary_id or str(metadata.get("boundaryID") or ""),
            str(metadata.get("boundaryType") or ""),
            str(metadata.get("boundarySource") or ""),
            str(metadata.get("boundaryYearRepresented") or ""),
            str(metadata.get("boundaryLicense") or ""),
        ])
        features.append(feature)
    if not features:
        return None
    output.dataProvider().addFeatures(features)
    output.updateExtents()
    output.setCustomProperty(LAYER_PROPERTY, True)
    output.setCustomProperty("zero2truesize/admin_metadata", json.dumps(metadata))
    symbol = QgsFillSymbol.createSimple({
        "color": "0,137,123,45",
        "outline_color": "0,105,92,210",
        "outline_width": "0.35",
    })
    output.setRenderer(QgsSingleSymbolRenderer(symbol))
    return output


class AdminDownloadManager(QObject):
    """Fetch geoBoundaries metadata and its vector GeoJSON asynchronously."""

    started = pyqtSignal(str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reply = None
        self._cancelled = False
        self._stage = ""
        self._layer_id: str | None = None
        self._metadata: dict = {}
        self._pending_layer_name = "Administrative boundaries"

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

    def download(self, iso3: str, level: str, country_name: str) -> None:
        if self.busy:
            raise RuntimeError("An administrative-boundary download is already running.")
        url = metadata_url(iso3, level)
        level_title = "country boundary" if level == "ADM0" else "first-level units"
        self._pending_layer_name = f"{country_name} — {level}"
        self._cancelled = False
        self._metadata = {}
        self.started.emit(f"{country_name} — {level_title}")
        self._request(url, "metadata")

    def _request(self, url: str, stage: str) -> None:
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(
            QByteArray(b"User-Agent"), QByteArray(USER_AGENT.encode("ascii")))
        self._stage = stage
        self._reply = QgsNetworkAccessManager.instance().get(request)
        self._reply.finished.connect(self._on_finished)

    def cancel(self) -> None:
        if self._reply is not None:
            self._cancelled = True
            self._reply.abort()

    def _on_finished(self) -> None:
        reply = self._reply
        stage = self._stage
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
            self.failed.emit("Administrative-boundary download cancelled.")
            return
        if error_code or not payload or status not in (None, 200):
            self.failed.emit(
                f"Boundary download failed (HTTP {status or 'unknown'}): {error_text}")
            return
        if stage == "metadata":
            self._handle_metadata(payload)
        else:
            self._handle_geojson(payload)

    def _handle_metadata(self, payload: bytes) -> None:
        try:
            metadata = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.failed.emit(f"Boundary catalogue returned invalid metadata: {exc}")
            return
        if not isinstance(metadata, dict):
            self.failed.emit("No boundary dataset is available for that country and level.")
            return
        url = str(
            metadata.get("simplifiedGeometryGeoJSON")
            or metadata.get("gjDownloadURL")
            or "")
        if not url.startswith("https://"):
            self.failed.emit("Boundary catalogue did not provide a secure GeoJSON URL.")
            return
        self._metadata = metadata
        self._request(url, "geojson")

    def _handle_geojson(self, payload: bytes) -> None:
        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.failed.emit(f"Downloaded boundary data is not valid GeoJSON: {exc}")
            return
        if document.get("type") != "FeatureCollection" or not document.get("features"):
            self.failed.emit("Downloaded GeoJSON contains no administrative boundaries.")
            return
        try:
            path = Path(QgsProcessingUtils.generateTempFilename("02truesize.geojson"))
            path.write_bytes(payload)
            layer = load_boundary_geojson(
                path, self._pending_layer_name, self._metadata)
        except (OSError, RuntimeError, ValueError) as exc:
            self.failed.emit(f"Boundary data could not be converted: {exc}")
            return
        if layer is None:
            self.failed.emit("Downloaded GeoJSON contains no usable polygon boundaries.")
            return
        project = QgsProject.instance()
        previous = self.layer()
        if previous is not None:
            project.removeMapLayer(previous.id())
        project.addMapLayer(layer, False)
        project.layerTreeRoot().insertLayer(0, layer)
        self._layer_id = layer.id()
        self.finished.emit(layer)
