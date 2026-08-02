# Changelog

All notable changes to **02truesize — Map Truth Lab** are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: [SemVer](https://semver.org/).

## [0.3.3] - 2026-08-03

### Changed
- Replace the hardcoded light-only stylesheet with palette-derived colour tokens so
  the entire dock stays readable under QGIS light, dark and high-contrast themes.
  The dock now listens for PaletteChange and re-applies the theme automatically.
- The "Pick up & drag" button is now a large primary action visually separated from
  the other tool buttons — the true-size drag is the heart of the plugin.
- Per-tool card accent colours are automatically adjusted for dark and light themes.

### Added
- `dialogs/theme.py` with WCAG contrast-ratio checks, palette-aware colour tokens,
  per-tool accent colours, and `apply_adaptive_theme()` entry point.

## [0.3.2] - 2026-07-20

### Fixed
- Removed the stale geoBoundaries GitHub/LFS links that returned HTTP 404/500
  even while their catalogue entries were valid.
- ADM0 now comes instantly from the bundled 238-country world dataset; ADM1 is
  filtered from Natural Earth's official 10m states/provinces vector archive.
- The 14.2 MB global ADM1 archive is downloaded at most once per panel session
  and then reused when another country is selected.
- Missing ADM1 coverage now produces a clear suggestion to use ADM0.
- Mapped Kosovo consistently between the bundled data and Natural Earth ADM1.

## [0.3.1] - 2026-07-20

### Fixed
- Selecting **Built-in world countries** now immediately checks its visibility
  control, adds the bundled 238-country layer and zooms to the world. Selecting
  it also repairs a layer removed directly from the project tree.
- Replaced the unsuitable current-canvas Overpass polygon query with explicit
  country + ADM0/ADM1 administrative vector selection.

### Changed
- Administrative downloads now use the programmatic geoBoundaries `gbOpen`
  catalogue and its direct GeoJSON vectors. The resulting memory layer stores
  the dataset's source, year and license metadata.
- The downloader contains only country and first-level administrative units;
  buildings, land use, leisure, natural and water polygons were removed.
- Documented why authenticated/licensed FAO GAUL Earth Engine collections and
  raw multipart Overpass relations are not used as the anonymous backend.

## [0.3.0] - 2026-07-20

### Added
- **Bounded OpenStreetMap polygon download** in the True Size tab. The current
  view can supply administrative boundaries, buildings, land use, leisure,
  natural and water polygons without QuickOSM or third-party Python packages.
- Asynchronous Overpass requests through QGIS networking, cancellation,
  neighbourhood-scale request limits, HTTP/rate-limit feedback, response
  validation, and automatic conversion to a styled memory layer.
- The successful OSM layer becomes a dedicated True Size source immediately,
  ready for pick-up and drag; refresh replaces only the previous successful
  plugin download.
- Pure-Python tests for bbox safety limits and Overpass query construction.
- [OSM_DATA_PLAN.md](OSM_DATA_PLAN.md), documenting scope, data flow, safety
  constraints, attribution and deliberate non-goals.

## [0.2.1] - 2026-07-20

### Fixed
- The built-in world layer now opens at the top of the layer tree, zooms to a
  safe world extent, and is created automatically when the world pick tool is
  started.
- Added a raw-GeoJSON memory-layer fallback when OGR cannot open the bundled
  country file, plus actionable missing-data feedback.
- Tab captions no longer truncate because their bold font is now included in
  Qt's width calculation; variable-width emoji moved to tooltips.

## [0.2.0] - 2026-07-20

Icon redesign + GUI overhaul.

### Changed
- **New icon** in the 02-family visual language (dark-teal panel, soft mint border, glowing mint outline landmass vs its solid coral true size, bold arrow). The previous icon traced the real Greenland coastline, which collapsed into noise at toolbar sizes; the new stylised landmass stays crisp at 24 px.
- **Dock redesigned around a pinned light design system** that reads identically under the QGIS 3 light and QGIS 4 dark application themes: a header row with the plugin icon and tagline, teal tab badges with emoji, white card panels with a per-tool accent stripe (True Size teal, antipode indigo, great circle blue, fun units green, report card coral), consistently styled buttons (the active map tool is now unmistakably highlighted), and theme-proof combos, lists and checkboxes.
- **Projection report card grades render as coloured chips** — green A+ down to red F — instead of plain text.
- **Size Duel polish**: white silhouette cards with a teal hover highlight, click cursors only while a guess is open, a round counter in the stats line, and the action button now reads "Skip round" before a guess and "▶ Next round" after, in the accent style.
- Ghost list entries now carry full-detail tooltips.

## [0.1.0] - 2026-07-19

First release.

### Added
- **True Size drag tool** — pick up any country from the bundled offline Natural Earth layer, or any polygon from your own layers, and drag it anywhere: the ghost outline is re-centred through a Lambert azimuthal equal-area projection so it always shows its true ground size in the current project CRS. Live cursor label (true area, Belgiums, how much larger/smaller the map draws it than at home), `R`/`E` rotation, multiple coloured ghosts, per-ghost removal, export to a memory layer.
- **Size Duel** — guessing game with silhouettes drawn exactly as web Mercator draws them (deception-biased pair selection), score/streak/best-streak (persisted), and a per-round confession of how much the projection lied.
- **Projection honesty report card** — numeric Tissot analysis of the current project CRS along a meridian: area and shape grades (A+ to F), per-latitude inflation row and a plain-language verdict.
- **Tissot indicatrix circles** — constant ground-radius circles (250/500/1000 km; 15/30/45° grid) as a styled memory layer, generated with pure spherical geodesy; antimeridian-crossing circles are skipped cleanly.
- **Live distortion HUD** — on-canvas overlay reporting areal inflation vs the equator and angular deformation at the view centre, updating as you pan/zoom or change the CRS.
- **Antipode tunnel** — click to see where you'd surface after digging straight through the Earth: markers at both ends, land-or-ocean verdict against the bundled countries, witty one-liner and a fly-to button.
- **Great-circle truth** — geodesic line (antimeridian-safe) vs the map's straight segment, with both true ground lengths and the wasted kilometres/percent.
- **Fun units** — distance paths and clicked polygon areas in accurate playful units (football pitches, Central Parks, Manhattans, Belgiums, marathons, Bosphorus bridges, laps of the equator, fractions of the way to the Moon), plus a rotating map-truth fact footer.
- Bundled generalized world countries GeoJSON (238 countries, from QGIS's Natural Earth-derived world map, public domain) with precomputed geodesic areas — fully offline.
- Verified end-to-end on QGIS 3.44 LTR and QGIS 4 (Qt6-ready: scoped enums, no QVariant types, no top-level menu — toolbar icon only).
