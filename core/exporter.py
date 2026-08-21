# -*- coding: utf-8 -*-
"""Interactive standalone HTML Map Truth Lab report generator for zero2truesize."""
from __future__ import annotations

import html
import json
import math
from pathlib import Path


def generate_truth_lab_html(country_data: dict, ref_country_data: dict | None = None,
                            report_card: dict | None = None,
                            fun_units: dict | None = None) -> str:
    """Return a single-file, zero-dependency HTML Map Truth Lab infographic."""
    name_a = html.escape(str(country_data.get("name", "Country A")))
    code_a = html.escape(str(country_data.get("iso_a3", "AAA")))
    area_a_km2 = float(country_data.get("area_km2", 100000.0))

    name_b = html.escape(str(ref_country_data.get("name", "Reference Country"))) if ref_country_data else "Greenland"
    area_b_km2 = float(ref_country_data.get("area_km2", 2166086.0)) if ref_country_data else 2166086.0

    area_ratio = area_a_km2 / max(1.0, area_b_km2)
    rc = report_card or {
        "area_grade": "A+", "shape_grade": "B",
        "area_spread": 1.15, "max_omega_deg": 4.2,
        "verdict": "Conformal balance across mid-latitudes."
    }

    # Outline for SVG
    outline_a = country_data.get("outline", [])
    svg_path_a = ""
    if outline_a and len(outline_a) >= 3:
        xs = [p[0] for p in outline_a]
        ys = [p[1] for p in outline_a]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        w, h = max(1e-6, maxx - minx), max(1e-6, maxy - miny)
        d = " ".join(f"{'M' if i == 0 else 'L'} {20 + (p[0] - minx) / w * 320:.1f} {220 - (p[1] - miny) / h * 200:.1f}"
                     for i, p in enumerate(outline_a)) + " Z"
        svg_path_a = f'<svg class="country-svg" viewBox="0 0 360 240"><path d="{d}" /></svg>'

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
  --purple: #9d4edd; --text: #e2e8f0; --muted: #8899ac;
  --good: #10b981; --warn: #f59e0b; --bad: #ef4444;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg); color: var(--text);
  font-family: system-ui, -apple-system, sans-serif;
  line-height: 1.5; padding: 24px; min-height: 100vh;
}}
.container {{ max-width: 960px; margin: auto; }}
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
.card h2 {{ font-size: 18px; margin-bottom: 16px; color: var(--accent); }}
.country-svg {{
  width: 100%; height: 200px; display: block; margin: auto;
  filter: drop-shadow(0 8px 16px var(--accent-glow));
}}
.country-svg path {{ fill: var(--accent); fill-opacity: 0.25; stroke: var(--accent); stroke-width: 2; }}
.stat-row {{
  display: flex; justify-content: space-between; padding: 10px 0;
  border-bottom: 1px solid var(--border); font-size: 14px;
}}
.stat-row:last-child {{ border-bottom: none; }}
.stat-val {{ font-weight: 800; color: #fff; }}
.slider-box {{ margin-top: 20px; }}
input[type=range] {{ width: 100%; accent-color: var(--accent); height: 6px; cursor: pointer; }}
.slider-labels {{ display: flex; justify-content: space-between; font-size: 12px; color: var(--muted); margin-top: 4px; }}
.inflation-indicator {{
  text-align: center; margin: 16px 0; font-size: 22px; font-weight: 900; color: var(--purple);
}}
.report-grid {{
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 12px;
}}
.report-tile {{
  background: #0d1424; border: 1px solid var(--border); border-radius: 10px;
  padding: 12px; text-align: center;
}}
.report-grade {{ font-size: 28px; font-weight: 900; color: var(--accent); }}
.btn {{
  display: inline-block; background: var(--accent); color: #0b0f19;
  border: none; padding: 10px 20px; border-radius: 8px; font-weight: 800;
  cursor: pointer; text-decoration: none; margin-top: 16px;
}}
footer {{
  text-align: center; color: var(--muted); font-size: 12px; margin-top: 40px; padding: 20px 0;
}}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand"><b>02</b>truesize <span>· Map Truth Lab</span></div>
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
        <span>Ratio to {name_b}:</span>
        <span class="stat-val">{area_ratio:.2f}×</span>
      </div>
    </div>

    <div class="card">
      <h2>📐 Mercator Latitude Inflation Simulator</h2>
      <p style="font-size:13px;color:var(--muted)">Drag to simulate how {name_a}'s apparent visual size inflates when shifted towards the poles on Web Mercator.</p>
      
      <div class="slider-box">
        <div class="inflation-indicator" id="inf-text">1.00× at Equator (0°)</div>
        <input id="lat-slider" type="range" min="0" max="80" value="0" step="1">
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
    </div>
  </div>

  <div class="card" style="margin-bottom:24px">
    <h2>📜 Projection Honesty Report Card</h2>
    <p style="font-size:13px;color:var(--muted)">Local deformation parameters under Web Mercator:</p>
    <div class="report-grid">
      <div class="report-tile">
        <div style="font-size:11px;color:var(--muted);text-transform:uppercase">Area Grade</div>
        <div class="report-grade">{rc.get('area_grade', 'B')}</div>
      </div>
      <div class="report-tile">
        <div style="font-size:11px;color:var(--muted);text-transform:uppercase">Shape Grade</div>
        <div class="report-grade">{rc.get('shape_grade', 'A+')}</div>
      </div>
      <div class="report-tile">
        <div style="font-size:11px;color:var(--muted);text-transform:uppercase">Area Spread</div>
        <div class="report-grade">{rc.get('area_spread', 1.0):.1f}×</div>
      </div>
    </div>
    <p style="font-size:13px;margin-top:14px;color:#cbd5e1"><em>&ldquo;{rc.get('verdict', 'Conformal projection preserving local angles.')}&rdquo;</em></p>
  </div>

  <button class="btn" onclick="window.print()">🖨️ Print / Save Report</button>

  <footer>
    Map Truth Lab &bull; Generated with <b>02truesize</b> v0.4.0 &bull; Local data &bull; Zero external trackers
  </footer>
</div>

<script>
const baseArea = {area_a_km2};
const slider = document.getElementById('lat-slider');
const infText = document.getElementById('inf-text');
const appArea = document.getElementById('app-area');

slider.oninput = function() {{
  const lat = Number(this.value);
  const rad = lat * Math.PI / 180;
  const factor = 1.0 / Math.pow(Math.cos(rad), 2);
  infText.textContent = factor.toFixed(2) + '× at ' + lat + '° Latitude';
  appArea.textContent = Math.round(baseArea * factor).toLocaleString() + ' km²';
}};
</script>
</body>
</html>
"""


def export_truth_lab_html(path: str | Path, country_data: dict,
                          ref_country_data: dict | None = None,
                          report_card: dict | None = None) -> None:
    """Write self-contained HTML truth lab report to disk."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(generate_truth_lab_html(country_data, ref_country_data, report_card), encoding="utf-8")
