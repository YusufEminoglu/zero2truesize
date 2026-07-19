# Changelog

All notable changes to **02truesize — Map Truth Lab** are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: [SemVer](https://semver.org/).

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
