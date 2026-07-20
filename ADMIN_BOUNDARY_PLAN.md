# Administrative Boundary Data Plan

## Goal

Provide predictable ADM0 country boundaries and ADM1 first-level units as
downloadable vector layers for True Size comparisons. Downloads must be based
on an explicit country and administrative level, never on the current canvas
extent.

## Source decision

- **ADM0:** the bundled generalized 238-country Natural Earth-derived GeoJSON.
  No network request is made.
- **ADM1:** Natural Earth 10m Admin 1 — States, Provinces, version 5.1.1:
  `https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_1_states_provinces.zip`

The ADM1 archive is an official public-domain vector distribution hosted on
Natural Earth's AWS infrastructure. It contains roughly 4,600 first-order
units. The 14.2 MB archive is downloaded once per open panel and reused for
subsequent country selections.

## Workflow

1. Select a country from the bundled world-country list.
2. Select **ADM0** (country) or **ADM1** (first-level unit).
3. For ADM0, copy the selected bundled country into a memory layer.
4. For ADM1, asynchronously fetch and validate the official ZIP archive, open
   its shapefile through GDAL's `/vsizip/` support, and filter by ISO alpha-3.
5. Copy the selected polygons into a styled EPSG:4326 memory layer.
6. Add the layer at the top of the project and switch True Size to it.

Only the downloader's previous successful result is replaced. Failed refreshes
leave the existing layer available. The request can be cancelled.

A missing ADM1 country is reported as unavailable with a suggestion to use
ADM0. Kosovo's source-specific code is mapped explicitly.

## Why FAO GAUL is not fetched directly

FAO GAUL 2015 level 0 and level 1 exist as vector FeatureCollections in Google
Earth Engine. They require Earth Engine access/authentication and are subject
to FAO GAUL distribution and non-commercial-use conditions for authorized
institutions. They are therefore not a dependable anonymous download backend
for a general QGIS Hub plugin.

## Why geoBoundaries and raw Overpass relations are not used

Administrative boundaries in OSM are usually relations assembled from many
ways. Large country relations can return multi-megabyte XML responses that the
generic GDAL OSM driver does not consistently reconstruct as multipolygons.
The tested geoBoundaries catalogue returned valid metadata but its pinned
GitHub/LFS vector links intermittently returned HTTP 404/500. Raw OSM relations
require reconstructing large multipart boundaries from ways. Natural Earth's
official archive is smaller, stable, directly readable by QGIS and public
domain.

## Built-in world source

Selecting **Built-in world countries** immediately checks its visibility box,
adds the bundled 238-country layer at the top of the project, and zooms to a
safe global extent. If the layer is removed directly from the project while the
checkbox remains checked, selecting the source repairs it.
