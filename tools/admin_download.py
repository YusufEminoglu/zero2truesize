# -*- coding: utf-8 -*-
"""ADM0 from bundled data and asynchronous Natural Earth ADM1 acquisition."""
from __future__ import annotations

import json
from pathlib import Path

from qgis.PyQt.QtCore import QByteArray, QObject, QTimer, QUrl, QVariant, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsFields,
    QgsFillSymbol,
    QgsGeometry,
    QgsNetworkAccessManager,
    QgsProcessingUtils,
    QgsProject,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)

from ..core.admin_data import validate_request

ADM1_URL = (
    "https://naturalearth.s3.amazonaws.com/10m_cultural/"
    "ne_10m_admin_1_states_provinces.zip")
ADM1_SHP = "ne_10m_admin_1_states_provinces.shp"
USER_AGENT = "02truesize/0.3.2 (+https://github.com/YusufEminoglu/zero2truesize)"
LAYER_PROPERTY = "zero2truesize/admin_download"


def _memory_layer(layer_name: str) -> QgsVectorLayer:
    output = QgsVectorLayer(
        "MultiPolygon?crs=EPSG:4326", f"{layer_name} — 02truesize", "memory")
    fields = QgsFields()
    for name in ("name", "boundary_id", "adm_level", "source", "version", "license"):
        fields.append(QgsField(name, QVariant.String))
    output.dataProvider().addAttributes(fields)
    output.updateFields()
    output.setCustomProperty(LAYER_PROPERTY, True)
    symbol = QgsFillSymbol.createSimple({
        "color": "0,137,123,45",
        "outline_color": "0,105,92,210",
        "outline_width": "0.35",
    })
    output.setRenderer(QgsSingleSymbolRenderer(symbol))
    return output


def _finish_layer(output: QgsVectorLayer, features: list[QgsFeature], metadata: dict):
    if not features:
        return None
    output.dataProvider().addFeatures(features)
    output.updateExtents()
    output.setCustomProperty("zero2truesize/admin_metadata", json.dumps(metadata))
    return output


def load_bundled_adm0(world, iso3: str, country_name: str) -> QgsVectorLayer | None:
    """Create a one-country memory layer from the bundled offline world data."""
    source_feature = world.country_feature_by_iso(iso3)
    if source_feature is None:
        return None
    output = _memory_layer(f"{country_name} — ADM0")
    feature = QgsFeature(output.fields())
    geometry = QgsGeometry(source_feature.geometry()).makeValid()
    geometry.convertToMultiType()
    feature.setGeometry(geometry)
    feature.setAttributes([
        country_name,
        iso3,
        "ADM0",
        "Bundled Natural Earth",
        "generalized",
        "Public domain",
    ])
    return _finish_layer(output, [feature], {
        "source": "Bundled Natural Earth-derived world countries",
        "level": "ADM0",
        "license": "Public domain",
    })


def load_natural_earth_adm1(
        archive_path: Path, iso3: str, country_name: str) -> QgsVectorLayer | None:
    """Filter the official Natural Earth 10m ADM1 archive to one country."""
    vsi_path = f"/vsizip/{archive_path.as_posix()}/{ADM1_SHP}"
    source = QgsVectorLayer(vsi_path, "Natural Earth ADM1", "ogr")
    if not source.isValid():
        raise RuntimeError("QGIS/GDAL could not read the Natural Earth ADM1 archive.")
    source_code = "KOS" if iso3 == "XKX" else iso3
    output = _memory_layer(f"{country_name} — ADM1")
    features = []
    for source_feature in source.getFeatures():
        if str(source_feature.attribute("adm0_a3") or "") != source_code:
            continue
        geometry = source_feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        geometry = geometry.makeValid()
        if geometry.isEmpty():
            continue
        geometry.convertToMultiType()
        feature = QgsFeature(output.fields())
        feature.setGeometry(geometry)
        feature.setAttributes([
            str(source_feature.attribute("name") or "Administrative unit"),
            str(source_feature.attribute("iso_3166_2")
                or source_feature.attribute("adm1_code") or ""),
            "ADM1",
            "Natural Earth",
            "5.1.1",
            "Public domain",
        ])
        features.append(feature)
    return _finish_layer(output, features, {
        "source": "Natural Earth Admin 1 — States, Provinces",
        "version": "5.1.1",
        "scale": "1:10m",
        "license": "Public domain",
        "url": ADM1_URL,
    })


class AdminDownloadManager(QObject):
    """Create ADM0 locally or fetch Natural Earth's global ADM1 archive once."""

    started = pyqtSignal(str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, world, parent=None):
        super().__init__(parent)
        self._world = world
        self._reply = None
        self._cancelled = False
        self._layer_id: str | None = None
        self._archive_path: Path | None = None
        self._iso3 = ""
        self._country_name = ""

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
        code, level = validate_request(iso3, level)
        self._iso3 = code
        self._country_name = country_name
        if level == "ADM0":
            self.started.emit(f"{country_name} — country boundary (offline)")
            QTimer.singleShot(0, self._load_adm0)
            return
        self.started.emit(f"{country_name} — first-level units")
        if self._archive_path is not None and self._archive_path.exists():
            QTimer.singleShot(0, self._load_adm1)
            return
        request = QNetworkRequest(QUrl(ADM1_URL))
        request.setRawHeader(
            QByteArray(b"User-Agent"), QByteArray(USER_AGENT.encode("ascii")))
        self._cancelled = False
        self._reply = QgsNetworkAccessManager.instance().get(request)
        self._reply.finished.connect(self._on_finished)

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
            self.failed.emit("Administrative-boundary download cancelled.")
            return
        if error_code or not payload or status not in (None, 200):
            self.failed.emit(
                f"Natural Earth ADM1 download failed "
                f"(HTTP {status or 'unknown'}): {error_text}")
            return
        if not payload.startswith(b"PK"):
            self.failed.emit("Natural Earth returned an unexpected file instead of a ZIP archive.")
            return
        try:
            path = Path(QgsProcessingUtils.generateTempFilename("02truesize_adm1.zip"))
            path.write_bytes(payload)
            self._archive_path = path
        except OSError as exc:
            self.failed.emit(f"ADM1 archive could not be stored: {exc}")
            return
        self._load_adm1()

    def _load_adm0(self) -> None:
        layer = load_bundled_adm0(self._world, self._iso3, self._country_name)
        if layer is None:
            self.failed.emit(f"No ADM0 boundary is available for {self._country_name}.")
            return
        self._publish(layer)

    def _load_adm1(self) -> None:
        if self._archive_path is None:
            self.failed.emit("The Natural Earth ADM1 archive is not available.")
            return
        try:
            layer = load_natural_earth_adm1(
                self._archive_path, self._iso3, self._country_name)
        except RuntimeError as exc:
            self.failed.emit(str(exc))
            return
        if layer is None:
            self.failed.emit(
                f"Natural Earth publishes no ADM1 units for {self._country_name}. "
                "Try ADM0 instead.")
            return
        self._publish(layer)

    def _publish(self, layer: QgsVectorLayer) -> None:
        project = QgsProject.instance()
        previous = self.layer()
        if previous is not None:
            project.removeMapLayer(previous.id())
        project.addMapLayer(layer, False)
        project.layerTreeRoot().insertLayer(0, layer)
        self._layer_id = layer.id()
        self.finished.emit(layer)
