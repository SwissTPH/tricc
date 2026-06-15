"""Tests for rhombus out-edges labelled with integer (+/-) factors."""

import unittest

from tricc_oo.converters.xml_to_tricc import is_factor_edge_label, process_factor_edge
from tricc_oo.models.base import TriccOperator


class TestRhombusFactorEdgeLabel(unittest.TestCase):
    def test_factor_edge_pattern_accepts_signed_integers(self):
        for label in ("-1", "+2", "3", "-1.5", "+0.5"):
            with self.subTest(label=label):
                self.assertTrue(is_factor_edge_label(label))

    def test_factor_edge_pattern_rejects_non_numeric(self):
        for label in ("oui", "yes", "no", "follow", "+/-", "abc"):
            with self.subTest(label=label):
                self.assertFalse(is_factor_edge_label(label))


class TestProcessFactorEdge(unittest.TestCase):
    def test_factor_one_returns_none(self):
        class _Node:
            name = "src"
            activity = None
            group = None

        class _Edge:
            id = "edge_1"
            value = "1"
            source = "src"

        nodes = {"src": _Node()}
        self.assertIsNone(process_factor_edge(_Edge(), nodes))

    def test_factor_minus_one_returns_calculate(self):
        class _Node:
            name = "src"
            activity = None
            group = None

        class _Edge:
            id = "edge_1"
            value = "-1"
            source = "src"

        nodes = {"src": _Node()}
        calc = process_factor_edge(_Edge(), nodes)
        self.assertIsNotNone(calc)
        self.assertEqual(calc.expression_reference.operator, TriccOperator.MULTIPLIED)
        self.assertEqual(calc.expression_reference.reference[1].value, -1.0)


if __name__ == "__main__":
    unittest.main()