"""Tests for XLSForm aggregate operation serialization (max/min/sum)."""

import unittest
from unittest.mock import MagicMock

from tricc_oo.models.base import TriccOperator, TriccOperation, TriccStatic
from tricc_oo.strategies.output.xls_form import XLSFormStrategy


class TestXLSFormAggregateOps(unittest.TestCase):
    def setUp(self):
        self.strategy = XLSFormStrategy(MagicMock(), "/tmp")

    def test_max_serializes_all_arguments(self):
        op = TriccOperation(
            TriccOperator.MAX,
            [TriccStatic(2520), TriccStatic(1260), TriccStatic(1)],
        )
        self.assertEqual(
            self.strategy.get_tricc_operation_expression(op),
            "max(2520, 1260, 1)",
        )

    def test_min_serializes_all_arguments(self):
        self.assertEqual(
            self.strategy.tricc_operation_min(["a", "b"], None),
            "min(a, b)",
        )

    def test_sum_serializes_all_arguments(self):
        self.assertEqual(
            self.strategy.tricc_operation_sum(["1", "2", "3"], None),
            "sum(1, 2, 3)",
        )


if __name__ == "__main__":
    unittest.main()
