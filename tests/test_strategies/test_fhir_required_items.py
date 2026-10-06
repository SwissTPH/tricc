"""Required is a boolean or a boolean expression, from input through FHIR export.

Tokens ``1`` / ``yes`` / ``true`` and ``0`` / ``no`` / ``false`` become
``TriccStatic(bool)``. Any other value becomes a boolean ``TriccOperation``.
A static bool is ``Questionnaire.item.required`` (only when true). An operation
is the SDC ``cqf-expression`` on ``_required``. Constant-false relevance hides
the item and leaves ``required`` in place.

Run with:
    python -m pytest tests/test_strategies/test_fhir_required_items.py -v
"""

import unittest
from unittest.mock import MagicMock

from tricc_oo.converters.fhir.questionnaire_item_mapper import (
    CQF_EXPRESSION_EXT,
    SDC_EXT_HIDDEN,
)
from tricc_oo.converters.xml_to_tricc import shield_required
from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference, TriccStatic
from tricc_oo.models.calculate import TriccNodeCalculate
from tricc_oo.models.tricc import (
    TriccNodeInteger,
    TriccNodeMainStart,
    TriccNodeNote,
    TriccNodeTrigger,
)
from tricc_oo.strategies.input.yaml import YamlActivity, YamlNode, YamlStrategy
from tricc_oo.strategies.output.fhir_form import FHIRStrategy


def _make_strategy():
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    return FHIRStrategy(project, "/tmp/fhir_required_test_out")


def _integer(name="weight"):
    return TriccNodeInteger(id=name, name=name, label=name)


class TestShieldRequired(unittest.TestCase):
    def test_tokens_cast_to_static_bool(self):
        for token in (True, 1, 1.0, "1", "true", "TRUE", " yes "):
            shielded = shield_required(token)
            self.assertIsInstance(shielded, TriccStatic, token)
            self.assertIs(shielded.value, True, token)
        for token in (False, 0, 0.0, "0", "false", "no", "NO"):
            shielded = shield_required(token)
            self.assertIsInstance(shielded, TriccStatic, token)
            self.assertIs(shielded.value, False, token)

    def test_blank_is_unset(self):
        self.assertIsNone(shield_required(None))
        self.assertIsNone(shield_required(""))

    def test_static_token_and_bool_are_normalised(self):
        self.assertIs(shield_required(TriccStatic("yes")).value, True)
        self.assertIs(shield_required(TriccStatic(False)).value, False)
        again = shield_required(TriccStatic(True))
        self.assertIsInstance(again, TriccStatic)
        self.assertIs(again.value, True)

    def test_reference_named_yes_stays_a_boolean_expression(self):
        ref = TriccReference("yes")
        shielded = shield_required(ref)
        self.assertIsInstance(shielded, TriccOperation)
        self.assertEqual(shielded.operator, TriccOperator.ISTRUE)
        self.assertIs(shielded.reference[0], ref)

    def test_isnull_is_not_wrapped(self):
        op = TriccOperation(TriccOperator.ISNULL, [TriccReference("age")])
        shielded = shield_required(op)
        self.assertEqual(shielded.operator, TriccOperator.ISNULL)
        self.assertIs(shielded, op)

    def test_comparison_stays_boolean(self):
        op = TriccOperation(TriccOperator.MORE, [TriccReference("age"), TriccStatic(1)])
        shielded = shield_required(op)
        self.assertEqual(shielded.operator, TriccOperator.MORE)
        self.assertEqual(shielded.get_datatype(), "boolean")

    def test_number_operation_is_cast_with_istrue(self):
        op = TriccOperation(TriccOperator.PLUS, [TriccReference("age"), TriccStatic(1)])
        shielded = shield_required(op)
        self.assertEqual(shielded.operator, TriccOperator.ISTRUE)
        self.assertEqual(shielded.get_datatype(), "boolean")
        self.assertIs(shielded.reference[0], op)

    def test_authored_comparison_string_parses_to_boolean_operation(self):
        shielded = shield_required("age > 1")
        self.assertIsInstance(shielded, TriccOperation)
        self.assertEqual(shielded.get_datatype(), "boolean")

    def test_unparsable_string_is_returned(self):
        self.assertEqual(shield_required("???"), "???")


class TestYamlRequiredShield(unittest.TestCase):
    def _node(self, **kwargs):
        strategy = YamlStrategy([])
        activity = YamlActivity(id="a", title="A", nodes=[])
        node = strategy._create_node(
            YamlNode(type="integer", label="Q", **kwargs),
            activity,
            MagicMock(),
        )
        strategy._apply_expressions(node)
        return node

    def test_yes_and_expression_and_default(self):
        yes = self._node(id="q_yes", name="q_yes", required="yes")
        self.assertIsInstance(yes.required, TriccStatic)
        self.assertIs(yes.required.value, True)

        no = self._node(id="q_no", name="q_no", required=0)
        self.assertIsInstance(no.required, TriccStatic)
        self.assertIs(no.required.value, False)

        expr = self._node(id="q_expr", name="q_expr", required="age > 1")
        self.assertIsInstance(expr.required, TriccOperation)
        self.assertEqual(expr.required.get_datatype(), "boolean")

        default = self._node(id="q_default", name="q_default")
        self.assertIsInstance(default.required, TriccStatic)
        self.assertIs(default.required.value, True)


class TestFhirRequiredEmission(unittest.TestCase):
    def setUp(self):
        self.strategy = _make_strategy()

    def _item(self, node):
        self.assertTrue(self.strategy.generate_base(node))
        return self.strategy.questionnaires["main"]["item"][0]

    def test_default_and_true_tokens_emit_required_true(self):
        for required in (None, "1", "yes", True, TriccStatic(True)):
            self.strategy = _make_strategy()
            node = _integer()
            if required is not None:
                node.required = required
            elif required is None and node.required != "1":
                self.fail("input default required is no longer the token '1'")
            item = self._item(node)
            self.assertIs(item.get("required"), True)
            self.assertNotIn("_required", item)

    def test_false_tokens_omit_required(self):
        for required in ("0", "no", False, TriccStatic(False), None):
            self.strategy = _make_strategy()
            node = _integer()
            node.required = required
            item = self._item(node)
            self.assertNotIn("required", item)
            self.assertNotIn("_required", item)

    def test_operation_emits_cqf_expression(self):
        node = _integer("age")
        node.required = TriccOperation(
            TriccOperator.MORE, [TriccReference("age"), TriccStatic(1)]
        )
        item = self._item(node)
        self.assertNotIn("required", item)
        ext = item["_required"]["extension"][0]
        self.assertEqual(ext["url"], CQF_EXPRESSION_EXT)
        value = ext["valueExpression"]
        self.assertEqual(value["language"], "text/fhirpath")
        self.assertIn("age", value["expression"])
        self.assertIn(">", value["expression"])

    def test_number_operation_is_a_boolean_expression(self):
        node = _integer("age")
        node.required = TriccOperation(
            TriccOperator.PLUS, [TriccReference("age"), TriccStatic(1)]
        )
        item = self._item(node)
        expression = item["_required"]["extension"][0]["valueExpression"]["expression"]
        self.assertIn("= true", expression)
        self.assertNotIn("required", item)

    def test_display_group_hidden_and_trigger_omit_required(self):
        cases = [
            TriccNodeNote(id="n", name="note", label="Note"),
            TriccNodeMainStart(id="s", name="start", label="Start"),
            TriccNodeCalculate(id="c", name="flag", label="Flag"),
            TriccNodeTrigger(id="t", name="go", label="Go"),
        ]
        for node in cases:
            self.strategy = _make_strategy()
            if hasattr(node, "required"):
                node.required = "1"
            item = self._item(node)
            self.assertNotIn("required", item, node)
            self.assertNotIn("_required", item, node)

    def test_false_relevance_hides_item_and_keeps_required(self):
        node = _integer()
        node.relevance = TriccStatic(False)
        item = self._item(node)
        self.assertTrue(self.strategy.generate_relevance(node))
        self.assertIs(item.get("required"), True)
        urls = [ext.get("url") for ext in item.get("extension") or []]
        self.assertIn(SDC_EXT_HIDDEN, urls)

    def test_false_relevance_keeps_required_expression(self):
        node = _integer("age")
        node.required = TriccOperation(
            TriccOperator.ISNULL, [TriccReference("age")]
        )
        node.relevance = TriccStatic(False)
        item = self._item(node)
        self.strategy.generate_relevance(node)
        self.assertNotIn("required", item)
        self.assertIn("_required", item)
        expression = item["_required"]["extension"][0]["valueExpression"]["expression"]
        self.assertIn("empty()", expression)
        self.assertNotIn("= true", expression)
        urls = [ext.get("url") for ext in item.get("extension") or []]
        self.assertIn(SDC_EXT_HIDDEN, urls)
