"""GetContentVersion(): the content version through an authored calculate.

A calculate ``content_version = GetContentVersion()`` returns the build version:
``version()`` in XLSForm, ``Helper.GetContentVersion()`` in CQL (defined in the
Helper library with the build version), a string literal in FHIRPath.

See fix/20261116-content-version-reference.md.

Run with:
    python -m pytest tests/test_content_version.py -v
"""

import glob
import json
import os
import tempfile
import unittest

import pandas as pd

from tests.helpers import load_yaml_project
from tricc_oo.converters.cql_to_operation import transform_cql_to_operation
from tricc_oo.models.base import TriccOperation, TriccOperator
from tricc_oo.serializers.xls_form import CHOICE_MAP, SURVEY_MAP
from tricc_oo.strategies.output.fhir_form import FHIRStrategy
from tricc_oo.strategies.output.xls_form import XLSFormStrategy
from tricc_oo.strategies.registry import get_output_strategy

FIXTURE = os.path.join(os.path.dirname(__file__), "data", "yaml", "content_version.yaml")


def _find_item(items, link_id):
    for item in items:
        if item.get("linkId") == link_id:
            return item
        found = _find_item(item.get("item", []), link_id)
        if found:
            return found
    return None


class TestContentVersionOperator(unittest.TestCase):
    def test_cql_name_parses_to_operator(self):
        operation = transform_cql_to_operation("GetContentVersion()", "test")
        self.assertIsInstance(operation, TriccOperation)
        self.assertEqual(operation.operator, TriccOperator.CONTENT_VERSION)
        self.assertEqual(operation.get_datatype(), "string")

    def test_fhirpath_is_build_version_literal(self):
        strategy = FHIRStrategy(load_yaml_project(FIXTURE), "/tmp/content_version_out")
        operation = TriccOperation(operator=TriccOperator.CONTENT_VERSION, reference=[])
        self.assertEqual(
            strategy.get_tricc_operation_expression_fhirpath(operation),
            f"'{strategy.content_version}'",
        )


class TestContentVersionFhirExport(unittest.TestCase):
    def test_calculate_reads_helper_function(self):
        with tempfile.TemporaryDirectory() as out_dir:
            strategy = get_output_strategy("FHIRStrategy")(load_yaml_project(FIXTURE), out_dir)
            strategy.execute()
            base = os.path.join(out_dir, "content_version")
            helper = open(glob.glob(os.path.join(base, "library", "*-Helper.cql"))[0]).read()
            main = open(glob.glob(os.path.join(base, "library", "*-main.cql"))[0]).read()
            q_path = glob.glob(os.path.join(base, "questionnaire", "*.json"))[0]
            questionnaire = json.load(open(q_path))

        self.assertIn(
            f"define function GetContentVersion():\n  '{strategy.content_version}'", helper
        )
        self.assertIn("define Calc_content_version: Helper.GetContentVersion()", main)
        item = _find_item(questionnaire["item"], "content_version")
        self.assertIsNotNone(item)
        self.assertEqual(item["type"], "string")


class TestContentVersionXlsForm(unittest.TestCase):
    def test_calculation_is_version_function(self):
        XLSFormStrategy.df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
        XLSFormStrategy.df_calculate = pd.DataFrame(columns=SURVEY_MAP.keys())
        XLSFormStrategy.df_choice = pd.DataFrame(columns=CHOICE_MAP.keys())
        with tempfile.TemporaryDirectory() as out_dir:
            strategy = get_output_strategy("XLSFormStrategy")(load_yaml_project(FIXTURE), out_dir)
            strategy.execute()
            xls = glob.glob(os.path.join(out_dir, "*.xlsx"))[0]
            survey = pd.read_excel(xls, sheet_name="survey")
        rows = survey[survey["name"] == "content_version"]
        self.assertEqual(list(rows["calculation"]), ["version()"])


if __name__ == "__main__":
    unittest.main()
