"""Tests for CDSS Zscore/Izscore LMS secondary instances."""

import unittest
from unittest.mock import MagicMock

import pandas as pd

from tricc_oo.data.anthro.ranges import points_to_ranges
from tricc_oo.data.anthro.registry import (
    get_choice_rows,
    is_supported_table,
    normalize_table_id,
)
from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference, TriccStatic
from tricc_oo.serializers.xls_form import CHOICE_MAP
from tricc_oo.strategies.output.xlsform_cdss import XLSFormCDSSStrategy


def _fresh_cdss() -> XLSFormCDSSStrategy:
    """Build a CDSS strategy with isolated dataframes (class attrs are shared)."""
    project = MagicMock()
    strategy = XLSFormCDSSStrategy(project, "/tmp")
    strategy.df_survey = pd.DataFrame(columns=strategy.df_survey.columns)
    strategy.df_choice = pd.DataFrame(columns=list(CHOICE_MAP.keys()))
    strategy.df_calculate = pd.DataFrame(columns=strategy.df_calculate.columns)
    strategy._used_zscore_tables = set()
    return strategy


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


class TestCdssZscoreOps(unittest.TestCase):
    def test_formula_and_y_min_max_filter(self):
        strategy = _fresh_cdss()
        refs = ["'wfa'", "${sex}", "${age_days}", "${weight}"]
        expr = strategy.tricc_operation_zscore(refs)
        self.assertIn("instance('wfa')", expr)
        self.assertIn("y_min<=", expr)
        self.assertIn("y_max>", expr)
        self.assertNotIn("x_min", expr)
        self.assertNotIn("x_max", expr)
        # WHO formula shape: (pow - 1) div (s * l)
        self.assertIn("pow(", expr)
        self.assertIn(") * (", expr)
        self.assertIn("wfa", strategy._used_zscore_tables)

    def test_izscore_formula(self):
        strategy = _fresh_cdss()
        refs = ["'wfa'", "${sex}", "${age_days}", "${z}"]
        expr = strategy.tricc_operation_izscore(refs)
        self.assertIn("instance('wfa')", expr)
        self.assertIn("y_min<=", expr)
        # reverse: m * pow(z*s*l + 1, 1/l)
        self.assertIn("+ 1", expr)
        self.assertIn("1 div (", expr)

    def test_unknown_table_raises(self):
        strategy = _fresh_cdss()
        with self.assertRaises(ValueError):
            strategy.tricc_operation_zscore(["'nope'", "1", "2", "3"])

    def test_lazy_injection_only_when_used(self):
        strategy = _fresh_cdss()
        strategy.inject_used_zscore_tables()
        self.assertEqual(len(strategy.df_choice), 0)

        strategy.tricc_operation_zscore(["'wfa'", "${sex}", "${age}", "${wt}"])
        strategy.inject_used_zscore_tables()
        self.assertGreater(len(strategy.df_choice), 0)
        self.assertTrue((strategy.df_choice["list_name"] == "wfa").all())
        self.assertIn("sex", strategy.df_choice.columns)
        self.assertIn("y_min", strategy.df_choice.columns)
        self.assertIn("y_max", strategy.df_choice.columns)

    def test_no_injection_without_register(self):
        strategy = _fresh_cdss()
        # Parent path without CDSS register would not inject; CDSS requires register
        self.assertEqual(strategy._used_zscore_tables, set())
        strategy.inject_used_zscore_tables()
        self.assertEqual(len(strategy.df_choice), 0)

    def test_operation_expression_end_to_end(self):
        strategy = _fresh_cdss()
        op = TriccOperation(
            operator=TriccOperator.ZSCORE,
            reference=[
                TriccStatic(value="wfa"),
                TriccReference("sex"),
                TriccReference("age_days"),
                TriccReference("weight"),
            ],
        )
        expr = strategy.get_tricc_operation_expression(op)
        self.assertIn("instance('wfa')", expr)
        self.assertIn("y_min", expr)
        self.assertEqual(strategy._used_zscore_tables, {"wfa"})


if __name__ == "__main__":
    unittest.main()
