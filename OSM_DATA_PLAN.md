# OSM Data Plan

## Goal

Let a user compare the true size of local OpenStreetMap polygons without
requiring QuickOSM, a pip package, or a permanent data download. The workflow
must stay small, polite to the public Overpass service, cancellable, and useful
immediately from the True Size tab.

## Implemented workflow (v0.3.0)

1. The user zooms the QGIS canvas to a neighbourhood-scale view.
2. **Download polygons in current view** transforms that extent to WGS84 and
   rejects invalid, polar, antimeridian-crossing, or oversized requests.
3. QGIS's shared network manager posts a bounded Overpass XML query.
4. QGIS/GDAL reads the response; relevant multipolygons are copied into one
   self-contained EPSG:4326 memory layer.
5. The layer is placed at the top of the layer tree, the True Size source
   switches to it, and its polygons can be picked up and dragged immediately.

The request includes:

- administrative boundaries;
- buildings;
- land-use areas;
- leisure areas;
- natural areas;
- water polygons and riverbanks.

## Safety and reliability decisions

- Hard limit: 6 km per side and 25 km² total approximate bbox area.
- Latitude limit: 85° S to 85° N; no antimeridian-crossing bbox.
- One in-flight request per dock, with explicit cancellation.
- 60-second Overpass query timeout and 128 MiB server-side result ceiling.
- Descriptive handling for HTTP 429/504, malformed responses, conversion
  failures, and empty results.
- The download runs asynchronously through `QgsNetworkAccessManager`; the QGIS
  interface remains responsive.
- Only the latest successful result is owned by the downloader. Refresh replaces
  that result, while failed refreshes leave the previous layer available.
- Downloaded data is a memory layer. Users can make it permanent with QGIS
  **Export > Save Features As**.

## Architecture

- `core/osm.py`: QGIS-free bbox validation and Overpass query construction.
- `tools/osm_download.py`: network lifecycle, XML validation, OGR conversion,
  memory-layer creation and styling.
- `dialogs/dock.py`: controls, progress/error feedback and source switching.
- `tools/truesize.py`: consumes the selected source through one layer-provider
  callback; it has no network responsibility.

## Deliberate non-goals for v0.3.0

- No global/country-scale Overpass downloads.
- No tile basemap is added automatically.
- No disk cache or silent background refresh.
- No address geocoder or place-name search.
- No editing or upload to OpenStreetMap.

These keep the feature focused on transient, small-area true-size comparison
and avoid surprising network or project mutations.

## Attribution

Downloaded features are © OpenStreetMap contributors and subject to the
Open Database License. The dock displays attribution beside the download
control, and the README links to the OSM copyright page.

