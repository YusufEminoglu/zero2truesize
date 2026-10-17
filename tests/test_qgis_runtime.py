# -*- coding: utf-8 -*-
"""Headless QGIS runtime smoke & geodesic verification suite for zero2truesize."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PLUGINS_ROOT = Path(__file__).resolve().parents[2]
if str(PLUGINS_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGINS_ROOT))

from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsPointXY,
    QgsProject,
)
from qgis.gui import QgsMapCanvas  # noqa: E402

from zero2truesize.dialogs.duel_widget import DuelWidget  # noqa: E402
from zero2truesize.dialogs.matrix_dialog import AreaRatioMatrixDialog  # noqa: E402
from zero2truesize.tools.support import geodesic_calculator  # noqa: E402
from zero2truesize.tools.tissot import crs_report_card, make_tissot_layer  # noqa: E402
from zero2truesize.tools.truesize import Ghost, TrueSizeManager, true_size_ghost  # noqa: E402
from zero2truesize.tools.worlddata import WorldData  # noqa: E402


class TestZero2TrueSizeQgisRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.qgs = QgsApplication([], False)
        cls.qgs.initQgis()

    @classmethod
    def tearDownClass(cls):
        QgsProject.instance().removeAllMapLayers()

    def test_01_world_data_and_point_lookup(self):
        world = WorldData.instance()
        records = world.records()
        self.assertGreater(len(records), 150)
        tur = world.country_feature_by_iso("TUR")
        self.assertIsNotNone(tur)
        at_ankara = world.country_name_at(32.85, 39.93)
        self.assertIsNotNone(at_ankara)

    def test_02_true_size_ghost_area_conservation(self):
        world = WorldData.instance()
        grl = world.country_feature_by_iso("GRL")
        self.assertIsNotNone(grl)
        geom_orig = grl.geometry()
        calc = geodesic_calculator()
        area_orig_km2 = calc.measureArea(geom_orig) / 1e6
        self.assertGreater(area_orig_km2, 1_500_000.0)

        reprojected = true_size_ghost(
            geom_orig,
            QgsPointXY(-42.0, 72.0),
            QgsPointXY(20.0, 0.0),
            rotation_deg=25.0,
        )
        self.assertIsNotNone(reprojected)
        self.assertFalse(reprojected.isNull())
        area_reproj_km2 = calc.measureArea(reprojected) / 1e6
        rel_err = abs(area_reproj_km2 - area_orig_km2) / area_orig_km2
        self.assertLess(rel_err, 0.02)

    def test_03_manager_rotate_and_export_layer(self):
        canvas = QgsMapCanvas()
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        manager = TrueSizeManager(canvas)
        world = WorldData.instance()
        tur = world.country_feature_by_iso("TUR")
        self.assertIsNotNone(tur)

        ghost = Ghost("Turkey", tur.geometry(), QgsPointXY(35.0, 39.0), 783562.0, manager.next_color())
        ghost.dst_anchor = QgsPointXY(10.0, 55.0)
        manager.adopt(ghost)
        self.assertEqual(len(manager.ghosts), 1)

        ok = manager.rotate_at(0, delta_deg=30.0)
        self.assertTrue(ok)
        self.assertAlmostEqual(manager.ghosts[0].rotation, 30.0)
        self.assertIn("rotated 30°", manager.ghosts[0].label())

        exported = manager.export_layer()
        self.assertIsNotNone(exported)
        self.assertEqual(exported.featureCount(), 1)
        field_names = [f.name() for f in exported.fields()]
        self.assertIn("belgiums", field_names)
        self.assertIn("apparent_scale_vs_home", field_names)
        manager.dispose()

    def test_04_tissot_and_report_card(self):
        layer = make_tissot_layer(radius_km=500.0, lat_step=30, lon_step=60)
        self.assertTrue(layer.isValid())
        self.assertGreater(layer.featureCount(), 15)

        canvas = QgsMapCanvas()
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        card = crs_report_card(canvas)
        self.assertTrue(card.get("ok"))
        self.assertEqual(card.get("shape_grade"), "A+")

    def test_05_dialogs_and_duel_widget(self):
        world = WorldData.instance()
        duel = DuelWidget()
        duel.set_countries(world.records())
        self.assertIsNotNone(duel._round)
        duel._on_guess("a")
        self.assertTrue(duel.compare_button.isEnabled())

        matrix_dlg = AreaRatioMatrixDialog()
        self.assertEqual(matrix_dlg.table.rowCount(), 7)
        matrix_dlg._on_cell_clicked(0, 1)
        self.assertIn("Mercator Lie Factor", matrix_dlg.detail_label.text())


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestZero2TrueSizeQgisRuntime)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    sys.exit(0 if res.wasSuccessful() else 1)
