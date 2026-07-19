# Administrative Boundary Data Plan

## Goal

Provide predictable ADM0 country boundaries and ADM1 first-level units as
downloadable vector layers for True Size comparisons. Downloads must be based
on an explicit country and administrative level, never on the current canvas
extent.

## Source decision

The implemented source is the geoBoundaries `gbOpen` API:

`https://www.geoboundaries.org/api/current/gbOpen/{ISO3}/{ADM0|ADM1}/`

It provides current per-country metadata and direct GeoJSON links, requires no
account or API key, and is designed for programmatic access. Attribution and
the original source, year, and license returned by the catalogue are preserved
as layer fields and custom metadata.

The simplified GeoJSON is preferred for responsive interactive dragging, with
the full GeoJSON used as a fallback.

## Workflow

1. Select a country from the bundled world-country list.
2. Select **ADM0** (country) or **ADM1** (first-level unit).
3. Fetch catalogue metadata asynchronously.
4. Fetch the advertised GeoJSON asynchronously.
5. Validate the FeatureCollection and copy polygon features into a styled,
   self-contained EPSG:4326 memory layer.
6. Add the layer at the top of the project and switch True Size to it.

Only the downloader's previous successful result is replaced. Failed refreshes
leave the existing layer available. The request can be cancelled.

## Why FAO GAUL is not fetched directly

FAO GAUL 2015 level 0 and level 1 exist as vector FeatureCollections in Google
Earth Engine. They require Earth Engine access/authentication and are subject
to FAO GAUL distribution and non-commercial-use conditions for authorized
institutions. They are therefore not a dependable anonymous download backend
for a general QGIS Hub plugin.

## Why raw Overpass relations are not used

Administrative boundaries in OSM are usually relations assembled from many
ways. Large country relations can return multi-megabyte XML responses that the
generic GDAL OSM driver does not consistently reconstruct as multipolygons.
geoBoundaries provides already assembled, validated vector files and records
the underlying source in its metadata (for example, Turkey ADM0/ADM1 currently
identify OpenStreetMap as their source).

## Built-in world source

Selecting **Built-in world countries** immediately checks its visibility box,
adds the bundled 238-country layer at the top of the project, and zooms to a
safe global extent. If the layer is removed directly from the project while the
checkbox remains checked, selecting the source repairs it.

