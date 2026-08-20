"""Tests for populate node context validation and export helpers."""

import unittest

from tricc_oo.converters.fhir.populate_helper import (
    DEFAULT_HISTORY_PERIOD,
    cql_helper_populate_block,
    get_cht_contact_summary_expression,
    is_valid_period,
    normalize_populate_node,
    populate_participates_in_skip,
    resolve_populate_reference,
)
from tricc_oo.converters.fhir.repeat_helper import cql_helper_repeat_block
from tricc_oo.models.calculate import TriccNodePopulate
from tricc_oo.models.tricc import TriccNodeInteger
from tricc_oo.strategies.input.yaml import YamlStrategy
from tricc_oo.visitors.tricc import get_version_inheritance


class TestPopulateValidation(unittest.TestCase):
    def test_invalid_context_defaults_to_patient(self):
        node = TriccNodePopulate(id="p1", name="x", label="X", context="bogus")
        normalize_populate_node(node)
        self.assertEqual(node.context, "patient")

    def test_history_without_period_defaults_p1y(self):
        node = TriccNodePopulate(id="p2", name="bp", label="BP", context="history")
        normalize_populate_node(node)
        self.assertEqual(node.period, DEFAULT_HISTORY_PERIOD)

    def test_encounter_period_optional_no_default(self):
        node = TriccNodePopulate(id="p3", name="weight", label="W", context="encounter")
        normalize_populate_node(node)
        self.assertIsNone(node.period)

    def test_master_context_ignores_period(self):
        node = TriccNodePopulate(
            id="p4", name="fid", label="F", context="facility", period="P14D"
        )
        normalize_populate_node(node)
        self.assertIsNone(node.period)

    def test_is_valid_period(self):
        self.assertTrue(is_valid_period("P14D"))
        self.assertTrue(is_valid_period("2024-01-01/2024-12-31"))
        self.assertFalse(is_valid_period("not-a-period"))


class TestPopulateReferences(unittest.TestCase):
    def test_patient_reference(self):
        node = TriccNodePopulate(id="r1", name="p_age", label="Age", context="patient")
        normalize_populate_node(node)
        self.assertEqual(resolve_populate_reference(node), "GetPatientValue('p_age')")

    def test_history_reference_with_period(self):
        node = TriccNodePopulate(
            id="r2", name="bp", label="BP", context="history", period="P14D"
        )
        normalize_populate_node(node)
        self.assertEqual(
            resolve_populate_reference(node, qualified=True),
            "Helper.GetHistoryObservationValue('bp', 'P14D', 1, null)",
        )

    def test_encounter_reference_qualified(self):
        node = TriccNodePopulate(id="r3", name="weight", label="W", context="encounter")
        normalize_populate_node(node)
        self.assertEqual(
            resolve_populate_reference(node, qualified=True),
            "Helper.GetEncounterValue('weight', null, null)",
        )

    def test_cht_contact_summary_expression(self):
        node = TriccNodePopulate(id="r4", name="p_age", label="Age", context="patient")
        expr = get_cht_contact_summary_expression(node)
        self.assertIn("instance('contact-summary')/context/p_age", expr)


class TestPopulateVisitors(unittest.TestCase):
    def test_history_skips_version_inheritance(self):
        node = TriccNodePopulate(id="v1", name="bp", label="BP", context="history")
        normalize_populate_node(node)
        get_version_inheritance(node, [], set())
        self.assertTrue(node.last)

    def test_history_populate_does_not_participate_in_skip(self):
        node = TriccNodePopulate(id="v2", name="bp", label="BP", context="history")
        self.assertFalse(populate_participates_in_skip(node))

    def test_encounter_populate_participates_in_skip(self):
        node = TriccNodePopulate(id="v3", name="weight", label="W", context="encounter")
        self.assertTrue(populate_participates_in_skip(node))

    def test_repeat_zero_populate_does_not_skip(self):
        node = TriccNodePopulate(
            id="v4", name="temp", label="T", context="encounter", repeat=0
        )
        self.assertFalse(populate_participates_in_skip(node))


class TestPopulateYamlFixtures(unittest.TestCase):
    def _load_activity(self, path: str):
        import pathlib

        content = pathlib.Path(path).read_text(encoding="utf-8")
        strategy = YamlStrategy(path)
        project = strategy.execute([content], media_path="/tmp")
        self.assertIsNotNone(project)
        return next(iter(project.pages.values()))

    def test_yaml_patient_populate(self):
        activity = self._load_activity("tests/data/yaml/populate_patient.yaml")
        populate_nodes = [
            n for n in activity.nodes.values() if isinstance(n, TriccNodePopulate)
        ]
        self.assertEqual(len(populate_nodes), 1)
        self.assertEqual(populate_nodes[0].context, "patient")

    def test_yaml_history_populate(self):
        activity = self._load_activity("tests/data/yaml/populate_history.yaml")
        node = next(n for n in activity.nodes.values() if isinstance(n, TriccNodePopulate))
        self.assertEqual(node.period, "P14D")


class TestPopulateCqlHelpers(unittest.TestCase):
    def test_repeat_block_uses_get_history_not_get_last(self):
        block = cql_helper_repeat_block()
        self.assertIn("GetHistoryObservationValue", block)
        self.assertNotIn("GetLast", block)

    def test_populate_block_has_context_accessors(self):
        block = cql_helper_populate_block()
        self.assertIn("GetPatientValue", block)
        self.assertIn("GetEncounterValue", block)
        self.assertNotIn("GetHistory", block)


if __name__ == "__main__":
    unittest.main()