"""Option relevance must keep the choice row (XLSForm choice_filter).

See fix/20260921-option-relevance-dropped-choice.md.
"""

import os
import tempfile
import unittest

import pandas as pd

from tests.helpers import load_yaml_project
from tricc_oo.serializers.xls_form import CHOICE_MAP, SURVEY_MAP
from tricc_oo.strategies.output.xls_form import XLSFormStrategy
from tricc_oo.strategies.registry import get_output_strategy

FIXTURE = os.path.join(os.path.dirname(__file__), "data", "yaml", "option_relevance_forward_ref.yaml")
CONTROL = os.path.join(os.path.dirname(__file__), "data", "yaml", "select_with_options.yaml")


def _reset_shared_frames():
    XLSFormStrategy.df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
    XLSFormStrategy.df_calculate = pd.DataFrame(columns=SURVEY_MAP.keys())
    XLSFormStrategy.df_choice = pd.DataFrame(columns=CHOICE_MAP.keys())


def _export_xlsx(yaml_path, form_id):
    _reset_shared_frames()
    with tempfile.TemporaryDirectory() as out_dir:
        project = load_yaml_project(yaml_path)
        project.start_pages["main"].root.form_id = form_id
        strategy = get_output_strategy("XLSFormStrategy")(project, out_dir)
        strategy.execute()
        xls = os.path.join(out_dir, f"{form_id}.xlsx")
        choices = pd.read_excel(xls, sheet_name="choices").fillna("")
        survey = pd.read_excel(xls, sheet_name="survey").fillna("")
    return choices, survey


class TestOptionRelevanceChoice(unittest.TestCase):
    def test_forward_ref_option_is_on_choices_sheet(self):
        choices, survey = _export_xlsx(FIXTURE, "option-relevance-forward-ref")
        listed = choices[choices["list_name"] == "drip_rate"]
        values = set(listed["value"].astype(str))
        self.assertEqual(values, {"slow", "fast"})

        slow = listed[listed["value"].astype(str) == "slow"].iloc[0]
        fast = listed[listed["value"].astype(str) == "fast"].iloc[0]
        self.assertTrue(str(slow["choice_filter"]).strip())
        self.assertFalse(str(fast["choice_filter"]).strip())

        question = survey[survey["name"] == "drip_rate"]
        self.assertEqual(len(question), 1)
        choice_filter = str(question.iloc[0]["choice_filter"])
        self.assertIn(str(slow["choice_filter"]), choice_filter)
        self.assertIn("${later_calc}", choice_filter)

    def test_options_without_relevance_still_list_both(self):
        choices, _survey = _export_xlsx(CONTROL, "select_example")
        listed = choices[choices["list_name"] == "fever"]
        values = set(listed["value"].astype(str))
        self.assertEqual(values, {"yes", "no"})
        self.assertTrue((listed["choice_filter"].astype(str).str.strip() == "").all())


if __name__ == "__main__":
    unittest.main()
