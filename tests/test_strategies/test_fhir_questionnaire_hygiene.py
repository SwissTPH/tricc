"""Regression tests for OpenSRP / FHIR Questionnaire item hygiene.

Covers three export bugs that ballooned the IMCI registration Questionnaire
to 22 MB of unused empty duplicate calculates
(fix/20260821-opensrp-questionnaire-duplicate-calculates.md):

A. ``generate_base`` must emit each ``linkId`` at most once per Questionnaire
   (diamond / fan-in revisits, and distinct clones sharing an export name).
B. ``generate_calculate`` / ``generate_relevance`` attach expressions on the
   Questionnaire that already holds the item, not ``node.segment or "main"``.
C. Unused hidden calculates (no reader in *this* Questionnaire, not an
   extraction source *of this process*) are pruned — including items that
   only carry a CQL ``initialExpression``.

Run with:
    python -m pytest tests/test_strategies/test_fhir_questionnaire_hygiene.py -v
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from tricc_oo.converters.fhir.questionnaire_item_mapper import (
    SDC_EXT_CALCULATED_EXPR,
    SDC_EXT_ENABLE_WHEN_EXPR,
    build_calculated_expression_fhirpath,
    build_enable_when_expression,
    build_hidden_extension,
    build_initial_expression,
)
from tricc_oo.converters.tricc_to_xls_form import get_export_name
from tricc_oo.models.base import TriccOperation, TriccOperator
from tricc_oo.models.calculate import TriccNodeCalculate
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.models.tricc import (
    TriccNodeActivity,
    TriccNodeInteger,
    TriccNodeMainStart,
    TriccNodeSelectYesNo,
)
from tricc_oo.strategies.output.fhir_form import FHIRStrategy


def _make_strategy():
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    return FHIRStrategy(project, "/tmp/fhir_questionnaire_hygiene_out")


def _registration_activity():
    root = TriccNodeMainStart(id="s1", name="s", label="S", process="registration")
    return TriccNodeActivity(id="a1", name="act", label="Act", root=root)


def _hidden_item(link_id, item_type="string", **extra):
    item = {
        "linkId": link_id,
        "type": item_type,
        "text": link_id,
        "extension": [build_hidden_extension()],
    }
    item.update(extra)
    return item


class TestQuestionnaireItemOrder(unittest.TestCase):
    """First authored edge must appear first in the Questionnaire.

    See fix/20260823-questionnaire-item-order.md.
    """

    def test_sibling_edges_from_start_keep_edge_order(self):
        from tests.helpers import load_yaml_project

        project = load_yaml_project("tests/data/yaml/sibling_order.yaml")
        strategy = FHIRStrategy(project, "/tmp/fhir_item_order_out")
        strategy.process_base(project.start_pages, pages=project.pages)
        q = strategy.questionnaires.get("main") or next(iter(strategy.questionnaires.values()))
        labels = []

        def collect(items):
            for it in items or []:
                text = it.get("text") or ""
                if it.get("type") != "group":
                    labels.append(text)
                collect(it.get("item"))

        collect(q.get("item"))
        self.assertIn("Clinician Script", labels)
        self.assertIn("Later assessment", labels)
        self.assertLess(
            labels.index("Clinician Script"),
            labels.index("Later assessment"),
            labels,
        )


class TestGenerateBaseDeduplicatesItems(unittest.TestCase):
    """Phase A: one item per node / linkId, even when the walk revisits."""

    def test_same_node_revisited_via_processed_nodes_is_not_appended_again(self):
        strategy = _make_strategy()
        node = TriccNodeCalculate(id="c1", name="needs_test", label="needs_test")
        processed = OrderedSet()

        self.assertTrue(strategy.generate_base(node, processed_nodes=processed))
        processed.add(node)
        self.assertTrue(strategy.generate_base(node, processed_nodes=processed))

        items = strategy.questionnaires["main"]["item"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["linkId"], "needs_test")

    def test_diamond_two_paths_same_link_id_emits_one_item(self):
        """Two distinct calculate clones that share an export name (last version)."""
        strategy = _make_strategy()
        left = TriccNodeCalculate(id="c1", name="needs_test", label="needs_test")
        right = TriccNodeCalculate(id="c2", name="needs_test", label="needs_test")

        strategy.generate_base(left)
        strategy.generate_base(right)

        items = strategy.questionnaires["main"]["item"]
        link_ids = [it["linkId"] for it in items]
        self.assertEqual(link_ids.count("needs_test"), 1)
        self.assertEqual(len(items), 1)

    def test_still_one_questionnaire_per_process(self):
        strategy = _make_strategy()
        activity = _registration_activity()
        node = TriccNodeCalculate(
            id="c1", name="needs_test", label="needs_test", activity=activity
        )
        strategy.generate_base(node)
        self.assertEqual(list(strategy.questionnaires.keys()), ["registration"])
        self.assertEqual(len(strategy.questionnaires["registration"]["item"]), 1)


class TestExpressionAttachesToHoldingQuestionnaire(unittest.TestCase):
    """Phase B: ``node.segment`` unset must not hide the item on another process."""

    def test_calculate_expression_on_registration_when_segment_unset(self):
        strategy = _make_strategy()
        activity = _registration_activity()
        weight = TriccNodeInteger(
            id="w1", name="weight", label="Weight", activity=activity
        )
        height = TriccNodeInteger(
            id="h1", name="height", label="Height", activity=activity
        )
        bmi = TriccNodeCalculate(id="bmi1", name="bmi", label="BMI", activity=activity)
        bmi.expression_reference = TriccOperation(TriccOperator.DIVIDED, [weight, height])
        self.assertIsNone(getattr(bmi, "segment", None))

        strategy.questionnaires["registration"] = {
            "resourceType": "Questionnaire",
            "item": [
                {"linkId": "weight", "type": "integer"},
                {"linkId": "height", "type": "integer"},
                {"linkId": "bmi", "type": "decimal"},
            ],
        }
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [],
        }

        strategy.generate_calculate(bmi)

        item = strategy._find_item_by_link_id(
            strategy.questionnaires["registration"]["item"], "bmi"
        )
        ext = [e for e in item.get("extension", []) if e.get("url") == SDC_EXT_CALCULATED_EXPR]
        self.assertEqual(len(ext), 1)
        self.assertEqual(ext[0]["valueExpression"]["language"], "text/fhirpath")
        self.assertEqual(strategy.questionnaires["main"]["item"], [])

    def test_relevance_on_registration_when_segment_unset(self):
        strategy = _make_strategy()
        activity = _registration_activity()
        flag = TriccNodeSelectYesNo(
            id="q1",
            name="ask_disclaimer",
            label="Disclaimer?",
            list_name="yes_no",
            activity=activity,
        )
        flag.relevance = TriccOperation(
            TriccOperator.EQUAL, [TriccNodeInteger(id="age1", name="p_age_years"), 1]
        )
        self.assertIsNone(getattr(flag, "segment", None))

        strategy.questionnaires["registration"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": get_export_name(flag), "type": "boolean"}],
        }
        strategy.questionnaires["main"] = {"resourceType": "Questionnaire", "item": []}

        strategy.generate_relevance(flag)

        item = strategy.questionnaires["registration"]["item"][0]
        ext = [e for e in item.get("extension", []) if e.get("url") == SDC_EXT_ENABLE_WHEN_EXPR]
        self.assertEqual(len(ext), 1)
        self.assertEqual(strategy.questionnaires["main"]["item"], [])


class TestPruneUnusedHiddenCalculates(unittest.TestCase):
    """Phase C: drop unused empty (or live-but-unread) hidden calculates."""

    def test_unused_empty_hidden_calculate_is_dropped(self):
        strategy = _make_strategy()
        strategy.questionnaires["registration"] = {
            "resourceType": "Questionnaire",
            "item": [
                {
                    "linkId": "ask_disclaimer",
                    "type": "boolean",
                    "text": "Disclaimer?",
                },
                _hidden_item("needs_test"),
            ],
        }

        strategy._prune_unused_hidden_calculates()

        link_ids = [it["linkId"] for it in strategy.questionnaires["registration"]["item"]]
        self.assertEqual(link_ids, ["ask_disclaimer"])

    def test_referenced_hidden_calculate_is_kept(self):
        strategy = _make_strategy()
        flag_expr = (
            "%resource.repeat(item).where(linkId='needs_test').answer.value = true"
        )
        question = {
            "linkId": "ask_disclaimer",
            "type": "boolean",
            "extension": [build_enable_when_expression(flag_expr)],
        }
        strategy.questionnaires["registration"] = {
            "resourceType": "Questionnaire",
            "item": [question, _hidden_item("needs_test", "boolean")],
        }

        strategy._prune_unused_hidden_calculates()

        link_ids = [it["linkId"] for it in strategy.questionnaires["registration"]["item"]]
        self.assertEqual(link_ids, ["ask_disclaimer", "needs_test"])

    def test_unused_initial_expression_is_dropped(self):
        """CQL ``true`` routing calculates must not stay just because they have initialExpression."""
        strategy = _make_strategy()
        unused = _hidden_item("pnZZBCRahaURgJo3I0mLJ_58", "boolean")
        unused["extension"].append(build_initial_expression("Calc_pnZZBCRahaURgJo3I0mLJ_58"))
        strategy.cql_defines["registration"] = [
            "define Calc_pnZZBCRahaURgJo3I0mLJ_58: true",
            "define Dedup_ask_disclaimer: Helper.GetObservationValue('ask_disclaimer')",
        ]
        strategy.questionnaires["registration"] = {
            "resourceType": "Questionnaire",
            "item": [
                {
                    "linkId": "ask_disclaimer",
                    "type": "boolean",
                    "extension": [build_initial_expression("Dedup_ask_disclaimer")],
                },
                unused,
            ],
        }

        strategy._prune_unused_hidden_calculates()

        link_ids = [it["linkId"] for it in strategy.questionnaires["registration"]["item"]]
        self.assertEqual(link_ids, ["ask_disclaimer"])
        self.assertEqual(
            strategy.cql_defines["registration"],
            ["define Dedup_ask_disclaimer: Helper.GetObservationValue('ask_disclaimer')"],
        )

    def test_extracted_initial_expression_is_kept(self):
        strategy = _make_strategy()
        populate = _hidden_item("load_weight")
        populate["extension"].append(build_initial_expression("Dedup_load_weight"))
        strategy.extraction_rules["registration"] = [
            SimpleNamespace(link_id="load_weight")
        ]
        strategy.questionnaires["registration"] = {
            "resourceType": "Questionnaire",
            "item": [populate, _hidden_item("needs_test")],
        }

        strategy._prune_unused_hidden_calculates()

        link_ids = [it["linkId"] for it in strategy.questionnaires["registration"]["item"]]
        self.assertEqual(link_ids, ["load_weight"])

    def test_extraction_source_is_kept(self):
        strategy = _make_strategy()
        strategy.extraction_rules["registration"] = [
            SimpleNamespace(link_id="needs_test")
        ]
        strategy.questionnaires["registration"] = {
            "resourceType": "Questionnaire",
            "item": [_hidden_item("needs_test"), _hidden_item("unused_bridge")],
        }

        strategy._prune_unused_hidden_calculates()

        link_ids = [it["linkId"] for it in strategy.questionnaires["registration"]["item"]]
        self.assertEqual(link_ids, ["needs_test"])

    def test_other_process_extraction_does_not_keep_item(self):
        strategy = _make_strategy()
        strategy.extraction_rules["determine-diagnosis"] = [
            SimpleNamespace(link_id="CHE_B23_DE85_Vv_1")
        ]
        strategy.questionnaires["registration"] = {
            "resourceType": "Questionnaire",
            "item": [
                {"linkId": "ask_disclaimer", "type": "boolean"},
                _hidden_item("CHE_B23_DE85_Vv_1", "boolean"),
            ],
        }

        strategy._prune_unused_hidden_calculates()

        link_ids = [it["linkId"] for it in strategy.questionnaires["registration"]["item"]]
        self.assertEqual(link_ids, ["ask_disclaimer"])

    def test_unused_calculated_expression_is_dropped(self):
        """Live FHIRPath that nobody in this form reads is still unused."""
        unused = _hidden_item("needs_test", "boolean")
        unused["extension"].append(
            build_calculated_expression_fhirpath(
                "%resource.repeat(item).where(linkId='weight').answer.value > 0"
            )
        )
        strategy = _make_strategy()
        strategy.questionnaires["registration"] = {
            "resourceType": "Questionnaire",
            "item": [
                {"linkId": "weight", "type": "decimal"},
                unused,
            ],
        }

        strategy._prune_unused_hidden_calculates()

        link_ids = [it["linkId"] for it in strategy.questionnaires["registration"]["item"]]
        self.assertEqual(link_ids, ["weight"])

    def test_unused_chain_is_dropped_iteratively(self):
        """B reads A; nobody reads B → both go."""
        a = _hidden_item("flag_a", "boolean")
        a["extension"].append(
            build_calculated_expression_fhirpath(
                "%resource.repeat(item).where(linkId='weight').answer.value > 0"
            )
        )
        b = _hidden_item("flag_b", "boolean")
        b["extension"].append(
            build_calculated_expression_fhirpath(
                "%resource.repeat(item).where(linkId='flag_a').answer.value = true"
            )
        )
        strategy = _make_strategy()
        strategy.questionnaires["registration"] = {
            "resourceType": "Questionnaire",
            "item": [
                {"linkId": "weight", "type": "decimal"},
                a,
                b,
            ],
        }

        strategy._prune_unused_hidden_calculates()

        link_ids = [it["linkId"] for it in strategy.questionnaires["registration"]["item"]]
        self.assertEqual(link_ids, ["weight"])

    def test_other_process_keeps_its_own_copy(self):
        strategy = _make_strategy()
        strategy.questionnaires["registration"] = {
            "resourceType": "Questionnaire",
            "item": [_hidden_item("needs_test")],
        }
        used = _hidden_item("needs_test", "boolean")
        used["extension"].append(
            build_calculated_expression_fhirpath("true")
        )
        question = {
            "linkId": "do_test",
            "type": "boolean",
            "extension": [
                build_enable_when_expression(
                    "%resource.repeat(item).where(linkId='needs_test').answer.value = true"
                )
            ],
        }
        strategy.questionnaires["diagnostic-testing"] = {
            "resourceType": "Questionnaire",
            "item": [question, used],
        }

        strategy._prune_unused_hidden_calculates()

        self.assertEqual(strategy.questionnaires["registration"]["item"], [])
        diag_ids = [
            it["linkId"] for it in strategy.questionnaires["diagnostic-testing"]["item"]
        ]
        self.assertEqual(diag_ids, ["do_test", "needs_test"])

    def test_visible_item_is_never_pruned(self):
        strategy = _make_strategy()
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [
                {"linkId": "p_age_years", "type": "integer", "text": "Age"},
            ],
        }
        strategy._prune_unused_hidden_calculates()
        self.assertEqual(
            [it["linkId"] for it in strategy.questionnaires["main"]["item"]],
            ["p_age_years"],
        )


def _expression_urls(item, url):
    return [e for e in item.get("extension", []) if e.get("url") == url]


class TestSingletonSdcExpressions(unittest.TestCase):
    """openSRP FHIR Data Capture crashes on a second calculatedExpression.

    See fix/20260821-sdc-singleton-expressions.md.
    """

    def test_second_generate_calculate_does_not_append_another_calculated_expression(self):
        strategy = _make_strategy()
        weight = TriccNodeInteger(id="w1", name="weight", label="Weight")
        height = TriccNodeInteger(id="h1", name="height", label="Height")
        bmi = TriccNodeCalculate(id="bmi1", name="bmi", label="BMI")
        bmi.expression_reference = TriccOperation(TriccOperator.DIVIDED, [weight, height])
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [
                {"linkId": "weight", "type": "integer"},
                {"linkId": "height", "type": "integer"},
                {"linkId": "bmi", "type": "decimal"},
            ],
        }

        strategy.generate_calculate(bmi)
        strategy.generate_calculate(bmi)

        item = strategy.questionnaires["main"]["item"][2]
        self.assertEqual(len(_expression_urls(item, SDC_EXT_CALCULATED_EXPR)), 1)

    def test_two_clones_same_link_id_share_one_calculated_expression(self):
        strategy = _make_strategy()
        weight = TriccNodeInteger(id="w1", name="weight", label="Weight")
        a = TriccNodeCalculate(id="c1", name="flag", label="flag")
        b = TriccNodeCalculate(id="c2", name="flag", label="flag")
        a.expression_reference = TriccOperation(TriccOperator.MORE, [weight, 0])
        b.expression_reference = TriccOperation(TriccOperator.MORE, [weight, 0])
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [
                {"linkId": "weight", "type": "integer"},
                {"linkId": "flag", "type": "boolean"},
            ],
        }

        strategy.generate_calculate(a)
        strategy.generate_calculate(b)

        item = strategy.questionnaires["main"]["item"][1]
        self.assertEqual(len(_expression_urls(item, SDC_EXT_CALCULATED_EXPR)), 1)

    def test_second_generate_relevance_does_not_append_another_enable_when(self):
        strategy = _make_strategy()
        activity = _registration_activity()
        flag = TriccNodeSelectYesNo(
            id="q1",
            name="ask_disclaimer",
            label="Disclaimer?",
            list_name="yes_no",
            activity=activity,
        )
        flag.relevance = TriccOperation(
            TriccOperator.EQUAL, [TriccNodeInteger(id="age1", name="p_age_years"), 1]
        )
        strategy.questionnaires["registration"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": get_export_name(flag), "type": "boolean"}],
        }

        strategy.generate_relevance(flag)
        strategy.generate_relevance(flag)

        item = strategy.questionnaires["registration"]["item"][0]
        self.assertEqual(len(_expression_urls(item, SDC_EXT_ENABLE_WHEN_EXPR)), 1)

    def test_sanitize_collapses_duplicate_calculated_expressions(self):
        from tricc_oo.converters.fhir.questionnaire_item_mapper import (
            build_calculated_expression_fhirpath,
        )

        strategy = _make_strategy()
        expr = build_calculated_expression_fhirpath("true")
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [
                {
                    "linkId": "flag",
                    "type": "boolean",
                    "extension": [expr, dict(expr)],
                }
            ],
        }
        strategy._sanitize_questionnaires()
        item = strategy.questionnaires["main"]["item"][0]
        self.assertEqual(len(_expression_urls(item, SDC_EXT_CALCULATED_EXPR)), 1)


if __name__ == "__main__":
    unittest.main()
