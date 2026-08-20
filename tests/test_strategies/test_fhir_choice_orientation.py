"""OpenSRP horizontal Yes/No orientation on visible boolean items.

See feature/20260819-boolean-choice-orientation.md.
"""

import unittest
from unittest.mock import MagicMock

from tricc_oo.converters.fhir.questionnaire_item_mapper import (
    SDC_EXT_CHOICE_ORIENTATION,
    SDC_EXT_HIDDEN,
    build_choice_orientation_extension,
)
from tricc_oo.models.base import TriccNodeType
from tricc_oo.models.calculate import TriccNodeProposedDiagnosis
from tricc_oo.models.tricc import TriccNodeSelectOne, TriccNodeSelectOption, TriccNodeSelectYesNo
from tricc_oo.strategies.output.fhir_form import FHIRStrategy
from tricc_oo.strategies.output.opensrp import OpenSRPStrategy


def _make_project():
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    project.images = []
    return project


def _orientation_exts(item):
    return [e for e in item.get("extension", []) if e.get("url") == SDC_EXT_CHOICE_ORIENTATION]


def _yesno_options(select):
    yes = TriccNodeSelectOption(
        id="opt_yes", name="yes", label="Yes", select=select, list_name=select.list_name
    )
    no = TriccNodeSelectOption(
        id="opt_no", name="no", label="No", select=select, list_name=select.list_name
    )
    select.options = {0: yes, 1: no}


class TestBuildChoiceOrientationExtension(unittest.TestCase):
    def test_default_is_horizontal(self):
        ext = build_choice_orientation_extension()
        self.assertEqual(ext["url"], SDC_EXT_CHOICE_ORIENTATION)
        self.assertEqual(ext["valueCode"], "horizontal")


class TestOpenSRPBooleanChoiceOrientation(unittest.TestCase):
    def setUp(self):
        self.strategy = OpenSRPStrategy(_make_project(), "/tmp/opensrp_choice_orientation_out")

    def test_select_yesno_emits_horizontal_orientation(self):
        node = TriccNodeSelectYesNo(
            id="happy",
            name="demo_is_happy",
            label="Are you happy",
            list_name="yesno",
            tricc_type=TriccNodeType.select_yesno,
        )
        _yesno_options(node)

        self.strategy.generate_base(node)
        item = self.strategy.questionnaires["main"]["item"][0]

        self.assertEqual(item["type"], "boolean")
        exts = _orientation_exts(item)
        self.assertEqual(len(exts), 1)
        self.assertEqual(exts[0]["valueCode"], "horizontal")
        self.assertFalse(any(e.get("url") == SDC_EXT_HIDDEN for e in item.get("extension", [])))

    def test_yesno_style_select_one_emits_horizontal_orientation(self):
        node = TriccNodeSelectOne(
            id="fever",
            name="has_fever",
            label="Fever",
            list_name="yesno",
        )
        _yesno_options(node)

        self.strategy.generate_base(node)
        item = self.strategy.questionnaires["main"]["item"][0]

        self.assertEqual(item["type"], "boolean")
        exts = _orientation_exts(item)
        self.assertEqual(len(exts), 1)
        self.assertEqual(exts[0]["valueCode"], "horizontal")

    def test_hidden_boolean_does_not_emit_orientation(self):
        node = TriccNodeProposedDiagnosis(
            id="pd1",
            name="suspected_malaria",
            label="Suspected malaria",
        )

        self.strategy.generate_base(node)
        item = self.strategy.questionnaires["main"]["item"][0]

        self.assertEqual(item["type"], "boolean")
        self.assertTrue(any(e.get("url") == SDC_EXT_HIDDEN for e in item.get("extension", [])))
        self.assertEqual(_orientation_exts(item), [])

    def test_choice_select_one_does_not_emit_orientation(self):
        node = TriccNodeSelectOne(id="sex", name="sex", label="Sex", list_name="sex")
        male = TriccNodeSelectOption(
            id="opt_male", name="male", label="Male", select=node, list_name="sex"
        )
        female = TriccNodeSelectOption(
            id="opt_female", name="female", label="Female", select=node, list_name="sex"
        )
        node.options = {0: male, 1: female}

        self.strategy.generate_base(node)
        item = self.strategy.questionnaires["main"]["item"][0]

        self.assertEqual(item["type"], "choice")
        self.assertEqual(_orientation_exts(item), [])


class TestFHIRStrategyDoesNotEmitOrientation(unittest.TestCase):
    def test_select_yesno_has_no_orientation_on_fhir_strategy(self):
        strategy = FHIRStrategy(_make_project(), "/tmp/fhir_choice_orientation_out")
        node = TriccNodeSelectYesNo(
            id="happy",
            name="demo_is_happy",
            label="Are you happy",
            list_name="yesno",
            tricc_type=TriccNodeType.select_yesno,
        )
        _yesno_options(node)

        strategy.generate_base(node)
        item = strategy.questionnaires["main"]["item"][0]

        self.assertEqual(item["type"], "boolean")
        self.assertEqual(_orientation_exts(item), [])


if __name__ == "__main__":
    unittest.main()
