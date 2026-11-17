"""An activity called twice runs once per encounter on openSRP.

See feature/20261117-activity-procedure-dedup.md.
"""

import glob
import json
import os
import subprocess
import sys
import tempfile
import unittest

import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAML_DIR = os.path.join(REPO, "tests", "data", "yaml")
ENABLE_WHEN = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-enableWhenExpression"


def _build(fixture, output_strategy, out):
    """Build a YAML fixture in a fresh interpreter into ``out``."""
    subprocess.run(
        [
            sys.executable, "tests/build.py", "-i", os.path.join(YAML_DIR, fixture), "-o", out,
            "-I", "YamlStrategy", "-O", output_strategy,
        ],
        cwd=REPO,
        check=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": REPO},
    )


def _items(items):
    """Every Questionnaire item, depth first."""
    for item in items or []:
        yield item
        yield from _items(item.get("item"))


def _questionnaires(fixture, output_strategy="FHIRStrategy"):
    """{file name: {linkId: item}} for each Questionnaire the build writes."""
    with tempfile.TemporaryDirectory() as out:
        _build(fixture, output_strategy, out)
        result = {}
        for path in glob.glob(os.path.join(out, "**", "Questionnaire-*.json"), recursive=True):
            with open(path) as f:
                q = json.load(f)
            result[os.path.basename(path)] = {item["linkId"]: item for item in _items(q.get("item"))}
    return result


def _enable_when(item):
    for ext in item.get("extension", []):
        if ext.get("url") == ENABLE_WHEN:
            return ext["valueExpression"]["expression"]
    return None


def _trigger(name):
    return f"item.where(linkId='{name}').answer.where($this.exists()).value = true"


class TestSameQuestionnaire(unittest.TestCase):
    """§1a: the XLSForm previous-instance rule inside one Questionnaire."""

    @classmethod
    def setUpClass(cls):
        (cls.items,) = _questionnaires("activity_called_twice.yaml").values()
        groups = [i for i in cls.items.values() if i["type"] == "group" and i["linkId"].startswith("module_c")]
        cls.first, cls.second = groups

    def test_first_call_keeps_its_own_condition(self):
        expr = _enable_when(self.first)
        self.assertIn(_trigger("trigger_a"), expr)
        self.assertNotIn("trigger_d", expr)

    def test_second_call_is_skipped_when_the_first_was_shown(self):
        expr = _enable_when(self.second)
        self.assertIn(_trigger("trigger_d"), expr)
        self.assertIn(f"({'%resource'}.item.where(linkId='start_parent').{_trigger('trigger_a')}).not()", expr)

    def test_matches_xlsform(self):
        with tempfile.TemporaryDirectory() as out:
            _build("activity_called_twice.yaml", "XLSFormStrategy", out)
            xlsx = glob.glob(os.path.join(out, "**", "*.xlsx"), recursive=True)[0]
            survey = pd.read_excel(xlsx, sheet_name="survey").fillna("")
        groups = survey[(survey["type"] == "begin group") & survey["name"].str.startswith("module_c")]
        self.assertNotIn("not(", groups.iloc[0]["relevance"])
        self.assertIn("not(coalesce(${trigger_a},'')=1)", groups.iloc[1]["relevance"])


if __name__ == "__main__":
    unittest.main()
