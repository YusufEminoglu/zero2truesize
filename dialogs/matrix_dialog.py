# -*- coding: utf-8 -*-
"""Interactive 2D Origin-Destination (OD) Matrix Grid Dialog for Area Ratios and Distortion."""
from __future__ import annotations

import csv
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..core.geomath import od_matrix_grid


# Canonical benchmark entities if canvas has fewer than 2 ghosts
BENCHMARK_ENTITIES = [
    {"name": "Greenland", "area_km2": 2166086.0, "lat": 72.0},
    {"name": "Algeria (Africa)", "area_km2": 2381741.0, "lat": 28.0},
    {"name": "Brazil", "area_km2": 8515767.0, "lat": -10.0},
    {"name": "Australia", "area_km2": 7692024.0, "lat": -25.0},
    {"name": "Turkey", "area_km2": 783562.0, "lat": 39.0},
    {"name": "Russia", "area_km2": 17098242.0, "lat": 60.0},
    {"name": "Madagascar", "area_km2": 587041.0, "lat": -19.0},
]


class AreaRatioMatrixDialog(QDialog):
    """2D Origin-Destination Matrix Grid Dialog comparing True Area vs Mercator Apparent Area."""

    def __init__(self, entities: list[dict] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚖️ Area Ratio & Mercator Distortion Matrix (OD Grid)")
        self.resize(880, 620)
        self.setMinimumSize(700, 480)

        # Use provided entities or canonical benchmarks
        if entities and len(entities) >= 2:
            self._entities = list(entities)
            self._is_benchmark = False
        else:
            self._entities = list(BENCHMARK_ENTITIES)
            self._is_benchmark = True

        self._grid_data = od_matrix_grid(self._entities)
        self._build_ui()
        self._populate_table()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header card
        header = QFrame(self)
        header.setStyleSheet(
            "QFrame { background-color: rgba(14, 165, 233, 0.08); border: 1px solid rgba(14, 165, 233, 0.3); "
            "border-radius: 10px; padding: 8px; }"
        )
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(10, 8, 10, 8)
        h_layout.setSpacing(3)

        title = QLabel("<b>⚖️ Pairwise Area Ratio & Mercator Distortion Matrix (OD Grid)</b>")
        title.setStyleSheet("font-size: 11pt; color: #0284c7;")
        h_layout.addWidget(title)

        source_info = (
            "Computed from your active canvas ghosts."
            if not self._is_benchmark
            else "Showing Global Benchmark Countries (drop ghosts onto canvas for custom layers)."
        )
        subtitle = QLabel(
            f"Origin (Rows: Numerator A) vs Destination (Columns: Denominator B). {source_info}"
        )
        subtitle.setStyleSheet("color: #64748b; font-size: 9pt;")
        subtitle.setWordWrap(True)
        h_layout.addWidget(subtitle)
        layout.addWidget(header)

        # Controls row
        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel("<b>Matrix View Mode:</b>"))

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "📊 Combined OD View (True Ratio, Mercator Ratio & Distortion)",
            "⚡ Distortion Multiplier Matrix (Mercator Lie Factor)",
            "🌍 True Geodetic Area Ratio Matrix (Area A ÷ Area B)",
            "🗺️ Mercator Apparent Ratio Matrix (Mercator A ÷ Mercator B)",
        ])
        self.mode_combo.currentIndexChanged.connect(self._populate_table)
        ctrl_row.addWidget(self.mode_combo, 1)

        layout.addLayout(ctrl_row)

        # Matrix Table Widget
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.setStyleSheet(
            "QTableWidget { gridline-color: rgba(148, 163, 184, 0.3); font-size: 9pt; } "
            "QHeaderView::section { background-color: rgba(100, 116, 139, 0.15); font-weight: bold; padding: 6px; border: 1px solid rgba(148, 163, 184, 0.2); }"
        )
        layout.addWidget(self.table, 1)

        # Detail Inspector Card
        self.detail_card = QFrame(self)
        self.detail_card.setStyleSheet(
            "QFrame { background-color: rgba(100, 116, 139, 0.08); border: 1px solid rgba(148, 163, 184, 0.3); "
            "border-radius: 8px; padding: 6px; }"
        )
        d_layout = QVBoxLayout(self.detail_card)
        d_layout.setContentsMargins(10, 6, 10, 6)
        self.detail_label = QLabel("👉 Click any matrix cell above to inspect the full pairwise geodetic breakdown.")
        self.detail_label.setStyleSheet("font-size: 9pt;")
        self.detail_label.setWordWrap(True)
        d_layout.addWidget(self.detail_label)
        layout.addWidget(self.detail_card)

        # Action Buttons
        btn_row = QHBoxLayout()
        export_csv_btn = QPushButton("💾 Export Matrix to CSV…")
        export_csv_btn.clicked.connect(self._export_csv)
        copy_btn = QPushButton("📋 Copy to Clipboard")
        copy_btn.clicked.connect(self._copy_clipboard)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        btn_row.addWidget(export_csv_btn)
        btn_row.addWidget(copy_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _populate_table(self) -> None:
        names = self._grid_data["names"]
        areas = self._grid_data["areas_km2"]
        lats = self._grid_data["lats"]
        true_m = self._grid_data["true_matrix"]
        merc_m = self._grid_data["merc_matrix"]
        dist_m = self._grid_data["dist_matrix"]

        n = len(names)
        self.table.clear()
        self.table.setRowCount(n)
        self.table.setColumnCount(n)

        # Set Headers
        headers = []
        for i in range(n):
            lat_str = f"{abs(lats[i]):.0f}°{'N' if lats[i] >= 0 else 'S'}"
            area_str = f"{areas[i]:,.0f} km²"
            headers.append(f"{names[i]}\n({area_str}, {lat_str})")

        self.table.setHorizontalHeaderLabels(headers)
        self.table.setVerticalHeaderLabels(headers)

        mode_idx = self.mode_combo.currentIndex()

        for r in range(n):
            for c in range(n):
                t_val = true_m[r][c]
                m_val = merc_m[r][c]
                d_val = dist_m[r][c]

                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if r == c:
                    item.setText("1.00×\n(Identity)")
                    item.setBackground(QColor(100, 116, 139, 30))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                else:
                    if mode_idx == 0:  # Combined
                        item.setText(f"True: {t_val:.2f}×\nMerc: {m_val:.2f}×\n⚡ Dist: {d_val:.2f}×")
                    elif mode_idx == 1:  # Distortion
                        item.setText(f"{d_val:.2f}×")
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                    elif mode_idx == 2:  # True
                        item.setText(f"{t_val:.2f}×")
                    elif mode_idx == 3:  # Mercator
                        item.setText(f"{m_val:.2f}×")

                    # Color coding based on distortion factor
                    if 0.90 <= d_val <= 1.10:
                        item.setBackground(QColor(34, 197, 94, 45))  # Soft Green (Honest)
                    elif d_val > 3.0:
                        item.setBackground(QColor(239, 68, 68, 65))  # Strong Red (Huge Inflation)
                    elif d_val > 1.5:
                        item.setBackground(QColor(245, 158, 11, 55))  # Amber
                    elif d_val < 0.33:
                        item.setBackground(QColor(6, 182, 212, 65))  # Cyan (High Deflation)
                    elif d_val < 0.70:
                        item.setBackground(QColor(6, 182, 212, 40))  # Soft Cyan

                self.table.setItem(r, c, item)

        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()

    def _on_cell_clicked(self, row: int, col: int) -> None:
        names = self._grid_data["names"]
        areas = self._grid_data["areas_km2"]
        lats = self._grid_data["lats"]
        true_val = self._grid_data["true_matrix"][row][col]
        merc_val = self._grid_data["merc_matrix"][row][col]
        dist_val = self._grid_data["dist_matrix"][row][col]

        if row == col:
            self.detail_label.setText(
                f"<b>📍 {names[row]} (Identity cell)</b>: True Ground Area is <b>{areas[row]:,.0f} km²</b> "
                f"at latitude {lats[row]:.1f}°."
            )
            return

        row_name = names[row]
        col_name = names[col]
        row_lat_str = f"{abs(lats[row]):.1f}°{'N' if lats[row] >= 0 else 'S'}"
        col_lat_str = f"{abs(lats[col]):.1f}°{'N' if lats[col] >= 0 else 'S'}"

        comparison_text = (
            f"<b>🔍 Origin [{row_name}] (Numerator) vs Destination [{col_name}] (Denominator):</b><br>"
            f"• <b>True Ground Area Ratio:</b> <code>{row_name}</code> ({areas[row]:,.0f} km² at {row_lat_str}) is "
            f"<b>{true_val:.2f}×</b> the true ground size of <code>{col_name}</code> ({areas[col]:,.0f} km² at {col_lat_str}).<br>"
            f"• <b>Mercator Apparent Ratio:</b> On standard Web Mercator, <code>{row_name}</code> is drawn "
            f"<b>{merc_val:.2f}×</b> the pixel size of <code>{col_name}</code>.<br>"
            f"• <b>⚡ Mercator Lie Factor:</b> Mercator distorts this ratio by <b>{dist_val:.2f}×</b> "
            f"({'overstating' if dist_val > 1.05 else 'understating' if dist_val < 0.95 else 'preserving'} {row_name}'s relative prominence)."
        )
        self.detail_label.setText(comparison_text)

    def _export_csv(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export OD Area Ratio Matrix to CSV",
            "Area_Ratio_OD_Matrix.csv", "CSV Files (*.csv)"
        )
        if not filename:
            return
        if not filename.lower().endswith(".csv"):
            filename += ".csv"

        names = self._grid_data["names"]
        areas = self._grid_data["areas_km2"]
        lats = self._grid_data["lats"]
        true_m = self._grid_data["true_matrix"]
        merc_m = self._grid_data["merc_matrix"]
        dist_m = self._grid_data["dist_matrix"]
        n = len(names)

        try:
            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                # Section 1: True Geodetic Ratio Matrix
                writer.writerow(["=== TRUE GEODETIC AREA RATIO MATRIX (Row / Column) ==="])
                writer.writerow(["Origin / Destination"] + [f"{names[j]} ({areas[j]:,.0f}km2)" for j in range(n)])
                for i in range(n):
                    writer.writerow([f"{names[i]} ({areas[i]:,.0f}km2)"] + [f"{true_m[i][j]:.3f}" for j in range(n)])

                writer.writerow([])
                # Section 2: Mercator Apparent Ratio Matrix
                writer.writerow(["=== MERCATOR APPARENT RATIO MATRIX (Row / Column) ==="])
                writer.writerow(["Origin / Destination"] + [f"{names[j]} ({lats[j]:.1f}deg)" for j in range(n)])
                for i in range(n):
                    writer.writerow([f"{names[i]} ({lats[i]:.1f}deg)"] + [f"{merc_m[i][j]:.3f}" for j in range(n)])

                writer.writerow([])
                # Section 3: Mercator Distortion Multiplier Matrix
                writer.writerow(["=== MERCATOR DISTORTION FACTOR MATRIX (Mercator Ratio / True Ratio) ==="])
                writer.writerow(["Origin / Destination"] + names)
                for i in range(n):
                    writer.writerow([names[i]] + [f"{dist_m[i][j]:.3f}" for j in range(n)])

            QMessageBox.information(self, "Export Successful", f"OD Matrix successfully saved to:\n{filename}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"Could not write CSV: {exc}")

    def _copy_clipboard(self) -> None:
        names = self._grid_data["names"]
        dist_m = self._grid_data["dist_matrix"]
        n = len(names)

        lines = ["Origin\t" + "\t".join(names)]
        for i in range(n):
            lines.append(names[i] + "\t" + "\t".join(f"{dist_m[i][j]:.2f}x" for j in range(n)))
        tsv = "\n".join(lines)
        QApplication.clipboard().setText(tsv)
        QMessageBox.information(self, "Copied", "Distortion Factor Matrix copied to clipboard as TSV table.")
