# -*- coding: utf-8 -*-
"""Bundled world-countries data: lazy loading, point lookup and styling.

Two views of the same GeoJSON: a QgsVectorLayer (for map tools and the
optional on-canvas layer) and a pure-Python record list (for the Size Duel
game, which needs no QGIS geometry at all).
"""
from __future__ import annotations

import json
import os

from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsFillSymbol,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsSingleSymbolRenderer,
    QgsSpatialIndex,
    QgsVectorLayer,
)

from ..core.geomath import decimate_ring, largest_outer_ring, unwrap_ring

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "countries.geojson")
WORLD_LAYER_NAME = "World countries — 02truesize"


class WorldData:
    """Singleton access to the bundled Natural Earth countries."""

    _instance = None

    @classmethod
    def instance(cls) -> "WorldData":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._layer: QgsVectorLayer | None = None
        self._index: QgsSpatialIndex | None = None
        self._records: list[dict] | None = None
        self._project_layer_id: str | None = None

    # ── QGIS layer view ───────────────────────────────────────────────

    def layer(self) -> QgsVectorLayer | None:
        """The utility layer used for picking; never added to the project."""
        if self._layer is None:
            layer = QgsVectorLayer(DATA_PATH, WORLD_LAYER_NAME, "ogr")
            if not layer.isValid():
                return None
            self._layer = layer
        return self._layer

    def _spatial_index(self) -> QgsSpatialIndex | None:
        if self._index is None:
            layer = self.layer()
            if layer is None:
                return None
            self._index = QgsSpatialIndex(layer.getFeatures())
        return self._index

    def country_feature_at(self, lon: float, lat: float) -> QgsFeature | None:
        layer = self.layer()
        index = self._spatial_index()
        if layer is None or index is None:
            return None
        probe = QgsRectangle(lon - 1e-6, lat - 1e-6, lon + 1e-6, lat + 1e-6)
        point = QgsPointXY(lon, lat)
        for fid in index.intersects(probe):
            request = QgsFeatureRequest().setFilterFid(fid)
            for feature in layer.getFeatures(request):
                geom = feature.geometry()
                if geom is not None and geom.contains(point):
                    return QgsFeature(feature)
        return None

    def country_name_at(self, lon: float, lat: float) -> str | None:
        feature = self.country_feature_at(lon, lat)
        if feature is None:
            return None
        name = feature.attribute("name")
        return str(name) if name else None

    # ── pure record view (for the quiz) ───────────────────────────────

    def records(self) -> list[dict]:
        if self._records is None:
            with open(DATA_PATH, encoding="utf-8") as handle:
                data = json.load(handle)
            records = []
            for feature in data.get("features", []):
                props = feature.get("properties") or {}
                geometry = feature.get("geometry") or {}
                if not props.get("name"):
                    continue
                ring = decimate_ring(unwrap_ring(largest_outer_ring(geometry)), 350)
                records.append({
                    "name": str(props["name"]),
                    "area_km2": float(props.get("area_km2") or 0.0),
                    "lat": float(props.get("lat") or 0.0),
                    "lon": float(props.get("lon") or 0.0),
                    "ring": ring,
                })
            self._records = records
        return self._records

    # ── optional visible layer in the project ─────────────────────────

    def project_layer(self) -> QgsVectorLayer | None:
        if self._project_layer_id:
            layer = QgsProject.instance().mapLayer(self._project_layer_id)
            if layer is not None:
                return layer
            self._project_layer_id = None
        return None

    def add_world_layer_to_project(self) -> QgsVectorLayer | None:
        existing = self.project_layer()
        if existing is not None:
            return existing
        layer = QgsVectorLayer(DATA_PATH, WORLD_LAYER_NAME, "ogr")
        if not layer.isValid():
            return None
        symbol = QgsFillSymbol.createSimple({
            "color": "236,239,241,255",
            "outline_color": "96,125,139,255",
            "outline_width": "0.25",
        })
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        QgsProject.instance().addMapLayer(layer)
        self._project_layer_id = layer.id()
        return layer

    def remove_world_layer_from_project(self) -> None:
        layer = self.project_layer()
        if layer is not None:
            QgsProject.instance().removeMapLayer(layer.id())
        self._project_layer_id = None
