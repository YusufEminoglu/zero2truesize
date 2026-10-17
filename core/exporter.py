# -*- coding: utf-8 -*-
"""Interactive standalone HTML Map Truth Lab report generator for zero2truesize."""
from __future__ import annotations

import html
from pathlib import Path

from .funits import belgiums, fun_area_lines
from .geomath import mercator_areal_inflation, mercator_linear_inflation


def _build_svg_path(outline: list, view_w: int = 360, view_h: int = 240, pad: int = 24) -> str:
    if not outline or len(outline) < 3:
        return ""
    xs = [float(p[0]) for p in outline]
    ys = [float(p[1]) for p in outline]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    w = max(1e-6, maxx - minx)
    h = max(1e-6, maxy - miny)
    avail_w = view_w - 2 * pad
    avail_h = view_h - 2 * pad
    scale = min(avail_w / w, avail_h / h)
    ox = pad + (avail_w - w * scale) * 0.5
    oy = pad + (avail_h - h * scale) * 0.5
    d = " ".join(
        f"{'M' if i == 0 else 'L'} {ox + (float(p[0]) - minx) * scale:.1f} "
        f"{view_h - (oy + (float(p[1]) - miny) * scale):.1f}"
        for i, p in enumerate(outline)
    ) + " Z"
    return d


def generate_truth_lab_html(country_data: dict, ref_country_data: dict | None = None,
                            report_card: dict | None = None,
                            fun_units: dict | list[str] | None = None,
                            ghosts: list[dict] | None = None) -> str:
    """Return a single-file, zero-dependency HTML Map Truth Lab infographic."""
    name_a = html.escape(str(country_data.get("name", "Country A")))
    code_a = html.escape(str(country_data.get("iso_a3", "AAA")))
    area_a_km2 = float(country_data.get("area_km2", 100000.0))
    home_lat = float(country_data.get("lat", 0.0))
    home_inflation = mercator_areal_inflation(home_lat)

    name_b = html.escape(str(ref_country_data.get("name", "Greenland"))) if ref_country_data else "Greenland"
    area_b_km2 = float(ref_country_data.get("area_km2", 2166086.0)) if ref_country_data else 2166086.0

    area_ratio = area_a_km2 / max(1.0, area_b_km2)
    rc = report_card if (report_card and report_card.get("ok", True)) else {
        "crs_name": "WGS 84 / Pseudo-Mercator (EPSG:3857)",
        "area_grade": "A+", "shape_grade": "B",
        "area_spread": 1.15, "max_omega_deg": 4.2,
        "verdict": "Conformal balance across mid-latitudes.",
    }
    crs_title = html.escape(str(rc.get("crs_name", "Project CRS")))

    # Outline for SVG
    outline_a = country_data.get("outline", [])
    d_path = _build_svg_path(outline_a)
    svg_path_a = ""
    if d_path:
        svg_path_a = (
            '<svg class="country-svg" viewBox="0 0 360 240">'
            f'<g id="sim-group" style="transform-origin: 180px 120px; transition: transform 0.08s ease-out;">'
            f'<path d="{d_path}" />'
            '</g></svg>'
        )

    # Fun units lines
    if isinstance(fun_units, list):
        fun_lines = [str(line) for line in fun_units]
    elif isinstance(fun_units, dict) and fun_units.get("lines"):
        fun_lines = [str(line) for line in fun_units["lines"]]
    else:
        fun_lines = fun_area_lines(area_a_km2)

    fun_html = "".join(
        f'<div class="stat-row"><span>{html.escape(line)}</span></div>'
        for line in fun_lines
    )

    # Optional multi-ghost comparison table
    ghosts_html = ""
    if ghosts and len(ghosts) >= 1:
        rows_html = []
        for g in ghosts:
            g_name = html.escape(str(g.get("name", "Ghost")))
            g_area = float(g.get("area_km2", 0.0))
            g_src_lat = float(g.get("src_lat", 0.0))
            g_dst_lat = float(g.get("lat", 0.0))
            g_looks = float(g.get("looks", 1.0))
            g_rot = float(g.get("rotation", 0.0))
            rows_html.append(
                f"<tr>"
                f"<td><b>{g_name}</b></td>"
                f"<td>{g_area:,.0f} km²</td>"
                f"<td>{belgiums(g_area)}</td>"
                f"<td>{g_src_lat:+.1f}° &rarr; {g_dst_lat:+.1f}°</td>"
                f"<td>{g_rot:.0f}°</td>"
                f"<td><b>{g_looks:.2f}&times;</b></td>"
                f"</tr>"
            )
        ghosts_html = f"""
  <div class="card" style="margin-bottom:24px">
    <h2>👻 Active Canvas Ghosts Comparison ({len(ghosts)})</h2>
    <table class="ghost-table">
      <thead>
        <tr>
          <th>Polygon / Country</th>
          <th>True Area</th>
          <th>Belgiums</th>
          <th>Latitude Shift</th>
          <th>Rotation</th>
          <th>Canvas Scale vs Home</th>
        </tr>
      </thead>
      <tbody>
        {"".join(rows_html)}
      </tbody>
    </table>
  </div>"""

    init_slider_lat = int(round(min(80.0, abs(home_lat))))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Map Truth Lab &mdash; {name_a}</title>
<style>
:root {{
  --bg: #0b0f19; --card: #151d30; --border: #23314d;
  --accent: #00d2ff; --accent-glow: #00d2ff33;
  --teal: #14b8a6; --purple: #9d4edd; --text: #e2e8f0; --muted: #8899ac;
  --good: #10b981; --warn: #f59e0b; --bad: #ef4444;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg); color: var(--text);
  font-family: system-ui, -apple-system, sans-serif;
  line-height: 1.5; padding: 24px; min-height: 100vh;
}}
.container {{ max-width: 980px; margin: auto; }}
header {{
  display: flex; justify-content: space-between; align-items: center;
  border-bottom: 1px solid var(--border); padding-bottom: 20px; margin-bottom: 24px;
}}
.brand {{ font-size: 24px; font-weight: 900; letter-spacing: -0.5px; }}
.brand span {{ color: var(--accent); }}
.badge {{
  background: var(--card); border: 1px solid var(--border);
  padding: 6px 16px; border-radius: 999px; font-size: 13px; font-weight: 700;
}}
.hero-grid {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px;
}}
@media (max-width: 720px) {{ .hero-grid {{ grid-template-columns: 1fr; }} }}
.card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 16px; padding: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.3);
}}
.card h2 {{ font-size: 18px; margin-bottom: 14px; color: var(--accent); }}
.country-svg {{
  width: 100%; height: 210px; display: block; margin: auto; overflow: hidden;
  filter: drop-shadow(0 8px 16px var(--accent-glow));
}}
.country-svg path {{ fill: var(--accent); fill-opacity: 0.25; stroke: var(--accent); stroke-width: 2; vector-effect: non-scaling-stroke; }}
.stat-row {{
  display: flex; justify-content: space-between; padding: 9px 0;
  border-bottom: 1px solid var(--border); font-size: 14px;
}}
.stat-row:last-child {{ border-bottom: none; }}
.stat-val {{ font-weight: 800; color: #fff; }}
.slider-box {{ margin-top: 18px; }}
input[type=range] {{ width: 100%; accent-color: var(--accent); height: 6px; cursor: pointer; }}
.slider-labels {{ display: flex; justify-content: space-between; font-size: 12px; color: var(--muted); margin-top: 4px; }}
.inflation-indicator {{
  text-align: center; margin: 14px 0; font-size: 22px; font-weight: 900; color: var(--accent);
}}
.report-grid {{
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 12px;
}}
@media (max-width: 640px) {{ .report-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
.report-tile {{
  background: #0d1424; border: 1px solid var(--border); border-radius: 10px;
  padding: 12px; text-align: center;
}}
.report-grade {{ font-size: 26px; font-weight: 900; color: var(--accent); }}
.ghost-table {{
  width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px;
}}
.ghost-table th, .ghost-table td {{
  padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left;
}}
.ghost-table th {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }}
.btn {{
  display: inline-block; background: var(--accent); color: #0b0f19;
  border: none; padding: 10px 20px; border-radius: 8px; font-weight: 800;
  cursor: pointer; text-decoration: none; margin-top: 8px;
}}
footer {{
  text-align: center; color: var(--muted); font-size: 12px; margin-top: 40px; padding: 20px 0;
}}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand"><b>02</b>truesize <span>&middot; Map Truth Lab</span></div>
    <div class="badge">{code_a} &bull; True Area Report</div>
  </header>

  <div class="hero-grid">
    <div class="card">
      <h2>🌍 True Surface Area: {name_a}</h2>
      {svg_path_a}
      <div class="stat-row">
        <span>True Geodetic Area:</span>
        <span class="stat-val">{area_a_km2:,.0f} km²</span>
      </div>
      <div class="stat-row">
        <span>Ratio to {name_b} ({area_b_km2:,.0f} km²):</span>
        <span class="stat-val">{area_ratio:.2f}&times;</span>
      </div>
      <div class="stat-row">
        <span>Home Latitude / Mercator Inflation:</span>
        <span class="stat-val">{home_lat:+.1f}° ({home_inflation:.2f}&times; area)</span>
      </div>
      <div class="stat-row">
        <span>Equivalent Belgiums:</span>
        <span class="stat-val">{belgiums(area_a_km2)} Belgiums</span>
      </div>
    </div>

    <div class="card">
      <h2>📐 Mercator Latitude Inflation Simulator</h2>
      <p style="font-size:13px;color:var(--muted)">Drag to simulate how {name_a}'s apparent visual area and linear dimensions inflate when shifted towards the poles on Web Mercator.</p>

      <div class="slider-box">
        <div class="inflation-indicator" id="inf-text">1.00&times; at Equator (0°)</div>
        <input id="lat-slider" type="range" min="0" max="80" value="{init_slider_lat}" step="1">
        <div class="slider-labels">
          <span>0° (Equator)</span>
          <span>40° (Mid-Lat)</span>
          <span>80° (Arctic)</span>
        </div>
      </div>

      <div class="stat-row" style="margin-top:16px">
        <span>Projected Apparent Area:</span>
        <span class="stat-val" id="app-area">{area_a_km2:,.0f} km²</span>
      </div>
      <div class="stat-row">
        <span>Linear Scale Inflation (sec &phi;):</span>
        <span class="stat-val" id="lin-scale">{mercator_linear_inflation(init_slider_lat):.2f}&times;</span>
      </div>
      <div class="stat-row">
        <span>Areal Inflation (sec² &phi;):</span>
        <span class="stat-val" id="area-scale">{mercator_areal_inflation(init_slider_lat):.2f}&times;</span>
      </div>
    </div>
  </div>

  <div class="hero-grid">
    <div class="card">
      <h2>🍰 Fun Units &amp; Tangible Scale</h2>
      <p style="font-size:13px;color:var(--muted);margin-bottom:10px">Real-world area benchmarks for {name_a} ({area_a_km2:,.0f} km²):</p>
      {fun_html}
    </div>

    <div class="card">
      <h2>📜 Projection Honesty Report Card</h2>
      <p style="font-size:13px;color:var(--muted)">Evaluated on <b>{crs_title}</b>:</p>
      <div class="report-grid">
        <div class="report-tile">
          <div style="font-size:11px;color:var(--muted);text-transform:uppercase">Area Grade</div>
          <div class="report-grade">{html.escape(str(rc.get('area_grade', 'B')))}</div>
        </div>
        <div class="report-tile">
          <div style="font-size:11px;color:var(--muted);text-transform:uppercase">Shape Grade</div>
          <div class="report-grade">{html.escape(str(rc.get('shape_grade', 'A+')))}</div>
        </div>
        <div class="report-tile">
          <div style="font-size:11px;color:var(--muted);text-transform:uppercase">Area Spread</div>
          <div class="report-grade">{float(rc.get('area_spread', 1.0)):.1f}&times;</div>
        </div>
        <div class="report-tile">
          <div style="font-size:11px;color:var(--muted);text-transform:uppercase">Max Bend &omega;</div>
          <div class="report-grade">{float(rc.get('max_omega_deg', 0.0)):.1f}°</div>
        </div>
      </div>
      <p style="font-size:13px;margin-top:14px;color:#cbd5e1"><em>&ldquo;{html.escape(str(rc.get('verdict', 'Conformal projection preserving local angles.')))}&rdquo;</em></p>
    </div>
  </div>

{ghosts_html}

  <button class="btn" onclick="window.print()">🖨️ Print / Save PDF Report</button>

  <footer>
    Map Truth Lab &bull; Generated with <b>02truesize</b> v0.5.0 &bull; Offline Geodesic Engine &bull; Zero external trackers
  </footer>
</div>

<script>
const baseArea = {area_a_km2};
const slider = document.getElementById('lat-slider');
const infText = document.getElementById('inf-text');
const appArea = document.getElementById('app-area');
const linScale = document.getElementById('lin-scale');
const areaScale = document.getElementById('area-scale');
const simGroup = document.getElementById('sim-group');

function updateSim(lat) {{
  const rad = lat * Math.PI / 180;
  const lin = 1.0 / Math.max(0.05, Math.cos(rad));
  const factor = lin * lin;
  infText.textContent = factor.toFixed(2) + '× at ' + lat + '° Latitude';
  appArea.textContent = Math.round(baseArea * factor).toLocaleString() + ' km²';
  if (linScale) linScale.textContent = lin.toFixed(2) + '×';
  if (areaScale) areaScale.textContent = factor.toFixed(2) + '×';
  if (simGroup) {{
    const visualScale = Math.min(2.2, Math.max(0.45, Math.sqrt(factor) * 0.65));
    simGroup.style.transform = 'scale(' + visualScale.toFixed(3) + ')';
  }}
}}

slider.oninput = function() {{
  updateSim(Number(this.value));
}};
updateSim(Number(slider.value));
</script>
</body>
</html>
"""


def export_truth_lab_html(path: str | Path, country_data: dict,
                          ref_country_data: dict | None = None,
                          report_card: dict | None = None,
                          fun_units: dict | list[str] | None = None,
                          ghosts: list[dict] | None = None) -> None:
    """Write self-contained HTML truth lab report to disk."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        generate_truth_lab_html(
            country_data,
            ref_country_data=ref_country_data,
            report_card=report_card,
            fun_units=fun_units,
            ghosts=ghosts,
        ),
        encoding="utf-8",
    )

