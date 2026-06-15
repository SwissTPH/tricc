"""Tests for rhombus out-edges labelled with integer (+/-) factors."""

import unittest

from tricc_oo.converters.xml_to_tricc import is_factor_edge_label


class TestRhombusFactorEdgeLabel(unittest.TestCase):
    def test_factor_edge_pattern_accepts_signed_integers(self):
        for label in ("-1", "+2", "3", "-1.5", "+0.5"):
            with self.subTest(label=label):
                self.assertTrue(is_factor_edge_label(label))

    def test_factor_edge_pattern_rejects_non_numeric(self):
        for label in ("oui", "yes", "no", "follow", "+/-", "abc"):
            with self.subTest(label=label):
                self.assertFalse(is_factor_edge_label(label))


if __name__ == "__main__":
    unittest.main()