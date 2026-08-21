# -*- coding: utf-8 -*-
"""Pure-Python unit tests for zero2truesize.core — no QGIS required.

Run with any CPython:  py -3 zero2truesize/tests/test_pure.py
The core package is loaded straight from file paths so importing it never
touches the QGIS-dependent plugin package.
"""
import importlib
import importlib.util
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(os.path.dirname(HERE), "core")


def _load_core():
    spec = importlib.util.spec_from_file_location(
        "z2core", os.path.join(CORE, "__init__.py"),
        submodule_search_locations=[CORE])
    module = importlib.util.module_from_spec(spec)
    sys.modules["z2core"] = module
    spec.loader.exec_module(module)
    return (importlib.import_module("z2core.geomath"),
            importlib.import_module("z2core.funits"),
            importlib.import_module("z2core.quiz"),
            importlib.import_module("z2core.distortion"),
            importlib.import_module("z2core.admin_data"),
            importlib.import_module("z2core.recommender"),
            importlib.import_module("z2core.exporter"))


geomath, funits, quiz, distortion, admin_data, recommender, exporter = _load_core()


class TestAdminData(unittest.TestCase):
    def test_request_validation(self):
        self.assertEqual(admin_data.validate_request("tur", "ADM0"), ("TUR", "ADM0"))
        self.assertEqual(admin_data.validate_request("TUR", "ADM1"), ("TUR", "ADM1"))

    def test_url_validation(self):
        with self.assertRaisesRegex(ValueError, "three-letter"):
            admin_data.validate_request("TR", "ADM0")
        with self.assertRaisesRegex(ValueError, "level"):
            admin_data.validate_request("TUR", "ADM2")


class TestGeomath(unittest.TestCase):
    def test_antipode(self):
        lat, lon = geomath.antipode(41.0, 29.0)
        self.assertAlmostEqual(lat, -41.0)
        self.assertAlmostEqual(lon, -151.0)
        lat, lon = geomath.antipode(10.0, 170.0)
        self.assertAlmostEqual(lon, -10.0)

    def test_normalize_lon(self):
        self.assertAlmostEqual(geomath.normalize_lon(190.0), -170.0)
        self.assertAlmostEqual(geomath.normalize_lon(-190.0), 170.0)
        self.assertAlmostEqual(geomath.normalize_lon(0.0), 0.0)

    def test_haversine_istanbul_ankara(self):
        km = geomath.haversine_km(41.0082, 28.9784, 39.9334, 32.8597)
        self.assertAlmostEqual(km, 351.0, delta=6.0)

    def test_destination_roundtrip(self):
        lat, lon = geomath.destination(10.0, 20.0, 45.0, 1000.0)
        back = geomath.haversine_km(10.0, 20.0, lat, lon)
        self.assertAlmostEqual(back, 1000.0, delta=1.0)

    def test_circle_ring(self):
        ring = geomath.circle_ring(40.0, 30.0, 500.0, 72)
        self.assertEqual(len(ring), 73)
        self.assertEqual(ring[0], ring[-1])
        for lon, lat in ring[:-1]:
            self.assertAlmostEqual(
                geomath.haversine_km(40.0, 30.0, lat, lon), 500.0, delta=1.0)

    def test_unwrap_and_antimeridian(self):
        ring = [(179.0, 0.0), (179.5, 1.0), (-179.5, 1.0), (-179.0, 0.0), (179.0, 0.0)]
        unwrapped = geomath.unwrap_ring(ring)
        lons = [p[0] for p in unwrapped]
        self.assertTrue(all(abs(lons[i + 1] - lons[i]) < 180 for i in range(len(lons) - 1)))
        self.assertTrue(geomath.crosses_antimeridian(ring))
        self.assertFalse(geomath.crosses_antimeridian([(0, 0), (1, 0), (1, 1), (0, 0)]))

    def test_mercator(self):
        x180, _ = geomath.mercator_xy(0.0, 180.0)
        self.assertAlmostEqual(x180, math.pi * geomath.R_EARTH_KM * 1000.0, delta=1.0)
        _, y_top = geomath.mercator_xy(geomath.MERCATOR_MAX_LAT, 0.0)
        self.assertAlmostEqual(y_top / x180, 1.0, delta=0.01)  # square world
        self.assertAlmostEqual(geomath.mercator_areal_inflation(60.0), 4.0, delta=0.01)

    def test_shoelace_and_area(self):
        square = [(0, 0), (1, 0), (1, 1), (0, 1)]
        self.assertAlmostEqual(geomath.shoelace_area(square), 1.0)
        # 1x1 degree cell at the equator is ~12,300 km2
        ring = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
        self.assertAlmostEqual(geomath.approx_ring_area_km2(ring), 12300, delta=200)

    def test_largest_ring_and_decimate(self):
        geometry = {"type": "MultiPolygon", "coordinates": [
            [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            [[[10, 10], [15, 10], [15, 15], [10, 15], [10, 10]]],
        ]}
        largest = geomath.largest_outer_ring(geometry)
        self.assertEqual(largest[0], (10.0, 10.0))
        big = [(math.cos(i / 500.0), math.sin(i / 500.0)) for i in range(1000)]
        thin = geomath.decimate_ring(big, 300)
        self.assertLessEqual(len(thin), 302)
        self.assertEqual(thin[0], thin[-1])

    def test_lcg(self):
        a = geomath.LCG(42)
        b = geomath.LCG(42)
        self.assertEqual([a.next_int() for _ in range(5)],
                         [b.next_int() for _ in range(5)])
        for _ in range(100):
            value = a.randint(7)
            self.assertTrue(0 <= value < 7)
        items = list(range(20))
        shuffled = geomath.LCG(7).shuffled(items)
        self.assertEqual(sorted(shuffled), items)
        self.assertNotEqual(shuffled, items)


class TestFunits(unittest.TestCase):
    def test_format_count(self):
        self.assertEqual(funits.format_count(0.005), "1/200")
        self.assertEqual(funits.format_count(1234567.0), "1,234,567")
        self.assertEqual(funits.format_count(1.0), "1")

    def test_area_lines(self):
        lines = funits.fun_area_lines(30528.0)
        joined = " ".join(lines)
        self.assertIn("Belgium", joined)
        self.assertTrue(any("1 Belgiums" in line for line in lines))
        self.assertTrue(3 <= len(lines) <= 5)

    def test_distance_lines(self):
        lines = funits.fun_distance_lines(42.195)
        self.assertTrue(any("1 marathon — spot on" in line for line in lines))
        far = funits.fun_distance_lines(20000.0)
        self.assertTrue(any("equator" in line for line in far))
        self.assertTrue(any("Moon" in line for line in far))

    def test_antipode_lines(self):
        rng = geomath.LCG(1)
        self.assertIn("Spain", funits.antipode_line("Spain", rng))
        self.assertTrue(len(funits.antipode_line(None, rng)) > 10)

    def test_formats(self):
        self.assertEqual(funits.format_area_km2(2170000.0), "2.17M km2")
        self.assertEqual(funits.format_km(42.195), "42.20 km")


class TestQuiz(unittest.TestCase):
    def _countries(self):
        return [
            {"name": "Bigland", "area_km2": 2_000_000.0, "lat": 0.0, "lon": 0.0},
            {"name": "Northia", "area_km2": 1_000_000.0, "lat": 70.0, "lon": 10.0},
            {"name": "Middling", "area_km2": 900_000.0, "lat": 30.0, "lon": 20.0},
            {"name": "Southoria", "area_km2": 1_500_000.0, "lat": -45.0, "lon": 30.0},
            {"name": "Equatoria", "area_km2": 800_000.0, "lat": 5.0, "lon": 40.0},
            {"name": "Polaria", "area_km2": 300_000.0, "lat": 75.0, "lon": 50.0},
        ]

    def test_rounds_and_guessing(self):
        engine = quiz.SizeDuel(self._countries(), seed=99)
        for _ in range(20):
            rnd = engine.next_round()
            self.assertIsNotNone(rnd)
            self.assertEqual(set(rnd.keys()), {"a", "b", "c", "d"})
            names = [rnd[k]["name"] for k in ("a", "b", "c", "d")]
            self.assertEqual(len(set(names)), 4)
            winner_key = max(("a", "b", "c", "d"), key=lambda k: rnd[k]["area_km2"])
            result = engine.guess(winner_key)
            self.assertTrue(result["correct"])
            self.assertEqual(result["winner_key"], winner_key)
        self.assertEqual(engine.streak, 20)
        self.assertEqual(engine.best_streak, 20)

    def test_wrong_guess_resets_streak(self):
        engine = quiz.SizeDuel(self._countries(), seed=5)
        rnd = engine.next_round()
        winner_key = max(("a", "b", "c", "d"), key=lambda k: rnd[k]["area_km2"])
        loser_key = [k for k in ("a", "b", "c", "d") if k != winner_key][0]
        result = engine.guess(loser_key)
        self.assertFalse(result["correct"])
        self.assertEqual(engine.streak, 0)

    def test_visual_inflation(self):
        visual = quiz.visual_area_km2({"name": "x", "area_km2": 100.0, "lat": 60.0})
        self.assertAlmostEqual(visual, 400.0, delta=1.0)

    def test_deception_preference(self):
        engine = quiz.SizeDuel(self._countries(), seed=123)
        deceptive = 0
        for _ in range(30):
            rnd = engine.next_round()
            countries = [rnd[k] for k in ("a", "b", "c", "d")]
            if quiz.SizeDuel._is_deceptive_quad(countries):
                deceptive += 1
            winner_key = max(("a", "b", "c", "d"), key=lambda k: rnd[k]["area_km2"])
            engine.guess(winner_key)
        self.assertGreater(deceptive, 15)


class TestDistortion(unittest.TestCase):
    @staticmethod
    def _mercator(lon, lat):
        return geomath.mercator_xy(lat, lon)

    @staticmethod
    def _equirect(lon, lat):
        return lon, lat

    def test_singular_values(self):
        a, b = distortion.singular_values((2.0, 0.0, 0.0, 1.0))
        self.assertAlmostEqual(a, 2.0, places=6)
        self.assertAlmostEqual(b, 1.0, places=6)

    def test_mercator_tissot(self):
        rel = distortion.relative_areal(self._mercator, 10.0, 60.0, 10.0, 0.0)
        self.assertAlmostEqual(rel, 4.0, delta=0.2)
        here = distortion.tissot(self._mercator, 10.0, 60.0)
        self.assertLess(here["omega_deg"], 0.6)  # conformal

    def test_report_cards(self):
        card = distortion.report_card(self._mercator)
        self.assertTrue(card["ok"])
        self.assertEqual(card["shape_grade"], "A+")
        self.assertIn(card["area_grade"], ("E", "F"))
        self.assertIn("Conformal", card["verdict"])

        card = distortion.report_card(self._equirect)
        self.assertTrue(card["ok"])
        self.assertGreater(card["max_omega_deg"], 20.0)
        self.assertGreater(card["area_spread"], 3.0)


class TestRecommender(unittest.TestCase):
    def test_recommend_projections(self):
        recs = recommender.recommend_projections(min_lat=30.0, max_lat=60.0, purpose="All")
        self.assertGreater(len(recs), 3)
        # Verify scores are sorted descending
        scores = [r["score"] for r in recs]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_equal_area_recommendation(self):
        ea_recs = recommender.recommend_projections(min_lat=-40.0, max_lat=50.0, purpose="Equal-Area")
        self.assertTrue(all(r["family"] == "Equal-Area" for r in ea_recs))
        self.assertTrue(any("Mollweide" in r["name"] or "Eckert" in r["name"] for r in ea_recs))


class TestAreaMatrix(unittest.TestCase):
    def test_pairwise_ratio_and_distortion(self):
        entities = [
            {"name": "Equator Island", "area_km2": 1000.0, "lat": 0.0},
            {"name": "Arctic Island", "area_km2": 1000.0, "lat": 60.0},
        ]
        matrix = geomath.area_ratio_matrix(entities)
        self.assertEqual(len(matrix), 1)
        row = matrix[0]
        self.assertEqual(row["true_ratio"], 1.0)
        # At 60 deg lat, Mercator inflates area by 4x
        self.assertAlmostEqual(row["mercator_ratio"], 0.25, delta=0.05)
        self.assertAlmostEqual(row["distortion_factor"], 0.25, delta=0.05)


class TestHtmlExporter(unittest.TestCase):
    def test_truth_lab_html_output(self):
        country = {
            "name": "Greenland",
            "iso_a3": "GRL",
            "area_km2": 2166086.0,
            "outline": [[-40.0, 60.0], [-30.0, 70.0], [-50.0, 75.0], [-40.0, 60.0]],
        }
        html_doc = exporter.generate_truth_lab_html(country)
        self.assertIn("<!doctype html>", html_doc)
        self.assertIn("Greenland", html_doc)
        self.assertIn("Map Truth Lab", html_doc)
        self.assertIn("Mercator Latitude Inflation Simulator", html_doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
