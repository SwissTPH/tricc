"""Regression tests for merging `TriccNodeInput` into `TriccNodePopulate`.

`input` and `populate` were two node classes for the same thing: a pre-loaded
value, never a question, always hidden. `TriccNodeInput` is gone; the drawio
`input` keyword now builds a `TriccNodePopulate` whose context defaults to
`encounter` (what the old input path fetched).

The CHT side follows the *data source*, not the node class: values CHT injects
through the form `inputs` group get a hidden field named after the source
document field plus a calculate reading it, while contact-summary backed values
get the calculate only.

See fix/20260821-merge-input-into-populate.md.

Run with:
    python -m pytest tests/test_populate_input_merge.py -v
"""

import unittest

import pandas as pd
from lxml import etree

from tricc_oo.converters.drawio_type_map import TYPE_MAP
from tricc_oo.converters.fhir.populate_helper import (
    cql_helper_populate_block,
    populate_uses_inputs_group,
    resolve_populate_reference,
)
from tricc_oo.converters.fhir.questionnaire_item_mapper import (
    CALCULATE_NODE_TYPES,
    SKIP_NODE_TYPES,
    get_fhir_item_type,
    is_hidden,
)
from tricc_oo.converters.tricc_to_xls_form import get_export_name
from tricc_oo.converters.xml_to_tricc import add_tricc_base_node
from tricc_oo.models.base import TriccNodeType
from tricc_oo.models.calculate import TriccNodePopulate
from tricc_oo.models.tricc import TriccNodeActivity, TriccNodeMainStart
from tricc_oo.serializers.xls_form import (
    SURVEY_MAP,
    get_input_calc_line,
    get_input_line,
    get_populate_calc_line,
)


def _parse_node(keyword, extra_attributes=""):
    """Build one node the way the drawio parser does, for a given odk_type."""
    diagram = etree.fromstring('<diagram id="d1"><root/></diagram>')
    activity = TriccNodeActivity(
        id="a1", name="act", label="Act", root=TriccNodeMainStart(id="s1", name="s", label="S")
    )
    entry = TYPE_MAP[keyword]
    elm = etree.fromstring(
        f'<object id="n1" odk_type="{keyword}" name="weight" label="Weight" {extra_attributes}/>'
    )
    nodes = {}
    add_tricc_base_node(
        diagram,
        nodes,
        entry["model"],
        [elm],
        activity,
        attributes=entry["attributes"],
        mandatory_attributes=entry["mandatory_attributes"],
        defaults=entry.get("defaults"),
    )
    return list(nodes.values())[0]


class TestInputKeywordBuildsPopulate(unittest.TestCase):
    def test_class_is_gone(self):
        import tricc_oo.models.calculate as calculate

        self.assertFalse(hasattr(calculate, "TriccNodeInput"))

    def test_input_keyword_maps_to_populate_model(self):
        self.assertIs(TYPE_MAP[TriccNodeType.input]["model"], TriccNodePopulate)

    def test_input_keyword_defaults_to_encounter_context(self):
        node = _parse_node(TriccNodeType.input)
        self.assertIsInstance(node, TriccNodePopulate)
        self.assertEqual(node.tricc_type, TriccNodeType.populate)
        self.assertEqual(node.context, "encounter")

    def test_authored_context_overrides_the_default(self):
        node = _parse_node(TriccNodeType.input, 'context="history" period="P2Y"')
        self.assertEqual(node.context, "history")
        self.assertEqual(node.period, "P2Y")

    def test_populate_keyword_unchanged(self):
        self.assertEqual(_parse_node(TriccNodeType.populate).context, "patient")

    def test_encounter_cql_is_the_old_input_accessor(self):
        """The encounter accessor is GetObservationValue scoped to this encounter."""
        node = _parse_node(TriccNodeType.input)
        self.assertEqual(
            resolve_populate_reference(node, qualified=True),
            "Helper.GetEncounterObservationValue('weight', null, null)",
        )

    def test_encounter_accessor_is_resource_specific(self):
        """A Condition-typed populate must not read an Observation value."""
        node = _parse_node(TriccNodeType.input, 'concept_type="diagnosis"')
        self.assertEqual(
            resolve_populate_reference(node, qualified=True),
            "Helper.GetEncounterConditionValue('weight')",
        )

    def test_history_accessor_is_resource_specific(self):
        obs = _parse_node(TriccNodeType.populate, 'context="history" period="P2Y"')
        cond = _parse_node(
            TriccNodeType.populate, 'context="history" period="P2Y" concept_type="proposed_diagnosis"'
        )
        self.assertEqual(
            resolve_populate_reference(obs, qualified=True),
            "Helper.GetHistoryObservationValue('weight', 'P2Y', 1, null)",
        )
        self.assertEqual(
            resolve_populate_reference(cond, qualified=True),
            "Helper.GetHistoryConditionValue('weight')",
        )

    def test_helper_defines_the_encounter_accessors(self):
        """Both resource-specific accessors exist, and the old name still resolves."""
        block = cql_helper_populate_block()
        self.assertIn(
            "define function GetEncounterObservationValue(code String, repeatIndex Integer, period String):",
            block,
        )
        self.assertIn("define function GetEncounterConditionValue(code String):", block)
        self.assertIn("define function GetEncounterValue(", block)  # deprecated alias

    def test_encounter_scoping_comes_from_the_observation_helpers(self):
        """GetEncounter*Value delegates to helpers filtered on the encounterid parameter."""
        from tricc_oo.converters.fhir.repeat_helper import cql_helper_repeat_block

        repeat_block = cql_helper_repeat_block("4.0.1")
        self.assertIn("O.encounter.reference = 'Encounter/' + encounterid", repeat_block)
        self.assertIn("C.encounter.reference = 'Encounter/' + encounterid", repeat_block)
        populate_block = cql_helper_populate_block()
        self.assertIn("then GetObservationValue(code)", populate_block)
        self.assertIn("GetConditionValue(code)", populate_block)


class TestChtEmissionFollowsDataSource(unittest.TestCase):
    def test_inputs_group_only_for_encounter_context(self):
        self.assertTrue(populate_uses_inputs_group(_parse_node(TriccNodeType.input)))
        for context in ("patient", "history", "facility", "practitioner", "location"):
            node = _parse_node(TriccNodeType.populate, f'context="{context}"')
            self.assertFalse(populate_uses_inputs_group(node), context)

    def test_load_prefix_only_where_an_inputs_field_shares_the_name(self):
        self.assertEqual(get_export_name(_parse_node(TriccNodeType.input)), "load_weight")
        self.assertEqual(get_export_name(_parse_node(TriccNodeType.populate)), "weight")

    def test_every_cht_row_matches_the_survey_columns(self):
        """get_populate_calc_line was 16 wide against 19 columns → CHT export crashed."""
        node = _parse_node(TriccNodeType.populate)
        df = pd.DataFrame(columns=SURVEY_MAP.keys())
        for builder in (get_input_line, get_input_calc_line, get_populate_calc_line):
            row = builder(node)
            self.assertEqual(len(row), len(SURVEY_MAP), builder.__name__)
            df.loc[len(df)] = row  # the exact call that used to raise
        self.assertEqual(len(df), 3)

    def test_calculation_cells_match_the_mechanism(self):
        calc_col = list(SURVEY_MAP).index("calculation")
        inputs_node = _parse_node(TriccNodeType.input)
        summary_node = _parse_node(TriccNodeType.populate)
        self.assertEqual(
            get_input_calc_line(inputs_node)[calc_col], "../inputs/contact/weight"
        )
        self.assertIn(
            "instance('contact-summary')/context/weight",
            get_populate_calc_line(summary_node)[calc_col],
        )


class TestFhirRegistriesAgree(unittest.TestCase):
    def test_input_type_is_no_longer_skipped(self):
        self.assertNotIn(TriccNodeType.input, SKIP_NODE_TYPES)

    def test_populate_is_a_hidden_calculate_item(self):
        self.assertEqual(get_fhir_item_type(TriccNodeType.populate), "string")
        self.assertTrue(is_hidden(TriccNodeType.populate))
        self.assertIn(TriccNodeType.populate, CALCULATE_NODE_TYPES)

    def test_parsed_input_node_needs_no_input_type_mapping(self):
        """Nothing carries tricc_type 'input' any more, so the mapper is never asked."""
        self.assertEqual(_parse_node(TriccNodeType.input).tricc_type, TriccNodeType.populate)


if __name__ == "__main__":
    unittest.main()
