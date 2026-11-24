"""WHO LMS tables (data/anthro). Zscore itself: tests/test_dmn_instance.py."""

import unittest

from tricc_oo.data.anthro.ranges import points_to_ranges
from tricc_oo.data.anthro.registry import (
    get_choice_rows,
    is_supported_table,
    normalize_table_id,
)


class TestAnthroRanges(unittest.TestCase):
    def test_half_open_bins(self):
        points = [
            {"y": 0.0, "l": 0.3, "s": 0.1, "m": 3.0},
            {"y": 1.0, "l": 0.3, "s": 0.1, "m": 3.1},
            {"y": 2.0, "l": 0.3, "s": 0.1, "m": 3.2},
        ]
        rows = points_to_ranges(points, sex="male", list_name="wfa")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["y_min"], 0.0)
        self.assertEqual(rows[0]["y_max"], 1.0)
        self.assertEqual(rows[1]["y_min"], 1.0)
        self.assertEqual(rows[1]["y_max"], 2.0)
        self.assertEqual(rows[2]["y_min"], 2.0)
        # last bin has positive width
        self.assertGreater(rows[2]["y_max"], rows[2]["y_min"])

    def test_single_bin_match(self):
        points = [
            {"y": 0.0, "l": 0.3, "s": 0.1, "m": 3.0},
            {"y": 7.0, "l": 0.3, "s": 0.1, "m": 3.5},
            {"y": 14.0, "l": 0.3, "s": 0.1, "m": 4.0},
        ]
        rows = points_to_ranges(points, sex="female", list_name="wfa")
        # x=3 must hit only the [0, 7) row
        matches = [r for r in rows if r["y_min"] <= 3.0 < r["y_max"]]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["y_min"], 0.0)
        self.assertEqual(matches[0]["m"], 3.0)


class TestAnthroRegistry(unittest.TestCase):
    def test_normalize_table_id(self):
        self.assertEqual(normalize_table_id("'wfa'"), "wfa")
        self.assertEqual(normalize_table_id('"WFA"'), "wfa")
        self.assertEqual(normalize_table_id(" wfa "), "wfa")

    def test_wfa_supported(self):
        self.assertTrue(is_supported_table("wfa"))
        self.assertFalse(is_supported_table("nope"))

    def test_wfa_rows_have_schema(self):
        rows = get_choice_rows("wfa")
        self.assertGreater(len(rows), 100)
        sample = rows[0]
        for key in ("list_name", "value", "sex", "y_min", "y_max", "l", "m", "s"):
            self.assertIn(key, sample)
        sexes = {r["sex"] for r in rows}
        self.assertEqual(sexes, {"male", "female"})

    def test_unknown_table_raises(self):
        with self.assertRaises(ValueError):
            get_choice_rows("not_a_table")

    def test_median_newborn_male_near_zero_z(self):
        """At age 0, y=m should yield Z≈0 with LMS formula."""
        rows = get_choice_rows("wfa")
        male0 = next(r for r in rows if r["sex"] == "male" and r["y_min"] == 0.0)
        y, m, l, s = male0["m"], male0["m"], male0["l"], male0["s"]
        # ((y/m)^l - 1) / (s * l) with y==m → 0
        z = (((y / m) ** l) - 1) / (s * l)
        self.assertAlmostEqual(z, 0.0, places=10)


if __name__ == "__main__":
    unittest.main()
