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

from tricc_oo.converters.fhir.structuremap import (
    ExtractionRule,
    build_extraction_fml,
    build_procedure_extraction_rule,
    merge_extraction_rules,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAML_DIR = os.path.join(REPO, "tests", "data", "yaml")
ENABLE_WHEN = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-enableWhenExpression"
CALCULATED = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-calculatedExpression"
HIDDEN = "http://hl7.org/fhir/StructureDefinition/questionnaire-hidden"
INITIAL = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression"
NOT_DONE_BEFORE = "(%resource.item.where(linkId='module_c_done_prev').answer.where($this.exists()).value = true).not()"
PROCESSES = ("triage", "history-and-physical")


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


def _export(fixture, output_strategy="FHIRStrategy"):
    """({Questionnaire file: {linkId: item}}, {StructureMap .map file: FML}) of a build."""
    with tempfile.TemporaryDirectory() as out:
        _build(fixture, output_strategy, out)
        questionnaires, maps = {}, {}
        for path in glob.glob(os.path.join(out, "**", "Questionnaire-*.json"), recursive=True):
            with open(path) as f:
                q = json.load(f)
            questionnaires[os.path.basename(path)] = {item["linkId"]: item for item in _items(q.get("item"))}
        for path in glob.glob(os.path.join(out, "**", "StructureMap-*.map"), recursive=True):
            with open(path) as f:
                maps[os.path.basename(path)] = f.read()
    return questionnaires, maps


def _questionnaires(fixture, output_strategy="FHIRStrategy"):
    """{file name: {linkId: item}} for each Questionnaire the build writes."""
    return _export(fixture, output_strategy)[0]


def _by_process(named, process):
    """The entry of a {file name: …} dict whose file is for ``process``."""
    (value,) = [v for k, v in named.items() if f"-{process}" in k]
    return value


def _expression(item, url):
    for ext in item.get("extension", []):
        if ext.get("url") == url:
            return ext["valueExpression"]["expression"]
    return None


def _enable_when(item):
    return _expression(item, ENABLE_WHEN)


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

    def test_no_procedure_when_every_call_is_in_one_questionnaire(self):
        # nothing to carry to another Questionnaire: no _done item, no Procedure
        self.assertNotIn("module_c_done", self.items)


class TestRecordedAsProcedure(unittest.TestCase):
    """§1b: a Questionnaire that shows the activity records it as a Procedure."""

    @classmethod
    def setUpClass(cls):
        cls.questionnaires, cls.maps = _export("activity_called_across_processes.yaml")

    def test_done_item_is_true_when_the_group_is_shown(self):
        for process in PROCESSES:
            items = _by_process(self.questionnaires, process)
            group = next(i for i in items.values() if i["type"] == "group" and i["linkId"].startswith("module_c"))
            done = items["module_c_done"]
            self.assertEqual(done["type"], "boolean")
            self.assertIn({"url": HIDDEN, "valueBoolean": True}, done["extension"])
            # the group's whole enableWhen: a call skipped because it was done before records nothing
            own = _enable_when(group).split(f" and {NOT_DONE_BEFORE}")[0]
            self.assertEqual(_expression(done, CALCULATED), f"({own}) and {NOT_DONE_BEFORE}", process)

    def test_procedure_written_only_when_shown(self):
        for process in PROCESSES:
            fml = _by_process(self.maps, process)
            self.assertIn(
                "item as q where(linkId = 'module_c_done' and answer.valueBoolean = true) then {\n"
                "    q.answer as answer then extract_procedure_module_c(answer, src, bundle)",
                fml,
            )
            group = fml[fml.index("group extract_procedure_module_c("):]
            self.assertIn("create('Procedure') as tgt", group)
            self.assertIn("src -> tgt.status = 'completed' \"status\";", group)
            self.assertIn("cc('https://fhir.tricc.io/CodeSystem/tricc', 'module_c', 'Danger signs')", group)
            self.assertIn("src.encounter as enc -> tgt.encounter = enc", group)
            self.assertIn("src.authored as authored -> tgt.performed = authored", group)
            self.assertNotIn("observation-repeat-index", group)


class TestReadBack(unittest.TestCase):
    """§1c: a Questionnaire skips the activity when this encounter already has its Procedure."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as out:
            _build("activity_called_across_processes.yaml", "FHIRStrategy", out)
            cls.questionnaires = {}
            for path in glob.glob(os.path.join(out, "**", "Questionnaire-*.json"), recursive=True):
                with open(path) as f:
                    cls.questionnaires[os.path.basename(path)] = json.load(f)
            cls.cql = {}
            for path in glob.glob(os.path.join(out, "**", "library", "*.cql"), recursive=True):
                with open(path) as f:
                    cls.cql[os.path.basename(path)] = f.read()

    def test_populate_reads_the_procedure_of_this_encounter(self):
        # both ways: the process order of a visit is not fixed, whichever runs first records it
        for process in PROCESSES:
            q = _by_process(self.questionnaires, process)
            items = {i["linkId"]: i for i in _items(q["item"])}
            prev = items["module_c_done_prev"]
            self.assertEqual(prev["type"], "boolean")
            self.assertIn({"url": HIDDEN, "valueBoolean": True}, prev["extension"])
            self.assertEqual(_expression(prev, INITIAL), "ActivityDone_module_c_done_prev")
            self.assertIn(
                "define ActivityDone_module_c_done_prev: Helper.GetEncounterProcedureValue('module_c', null)",
                _by_process(self.cql, process),
            )

    def test_group_is_skipped_when_done_before(self):
        for process, trigger in zip(PROCESSES, ("trigger_a", "trigger_d")):
            items = {i["linkId"]: i for i in _items(_by_process(self.questionnaires, process)["item"])}
            group = next(i for i in items.values() if i["type"] == "group" and i["linkId"].startswith("module_c"))
            expr = _enable_when(group)
            self.assertIn(_trigger(trigger), expr)
            self.assertTrue(expr.endswith(f" and {NOT_DONE_BEFORE}"), expr)

    def test_no_read_back_when_every_call_is_in_one_questionnaire(self):
        (items,) = _questionnaires("activity_called_twice.yaml").values()
        self.assertNotIn("module_c_done_prev", items)


class TestCodeClash(unittest.TestCase):
    """§2: two activities with one code are not recorded (they would skip each other)."""

    def test_neither_is_recorded(self):
        questionnaires = _questionnaires("activity_code_clash.yaml")
        for process in PROCESSES:
            items = _by_process(questionnaires, process)
            self.assertFalse([lid for lid in items if lid.endswith(("_done", "_done_prev"))], process)


class TestProcedureExtractionRule(unittest.TestCase):
    """Procedure rules keep the repeat slot and their own group name."""

    def test_repeat_slot_is_stamped(self):
        rule = build_procedure_extraction_rule("module_c_Rr_2_done", "module_c", "Danger signs", 2)
        fml = build_extraction_fml([rule], "https://example.org/StructureMap/x", "x")
        self.assertIn("group extract_procedure_module_c_Rr_2(", fml)
        self.assertIn("observation-repeat-index", fml)
        self.assertIn("ext.valueInteger = 2", fml)

    def test_never_merged_with_an_observation_of_the_same_code(self):
        procedure = build_procedure_extraction_rule("module_c_done", "module_c", "Danger signs", 1)
        observation = ExtractionRule(
            link_id="module_c", concept_code="module_c", display="x", concept_type="finding",
            kind="observation", qr_value_field="valueBoolean", item_type="boolean", repeat=None,
            code_system_url="https://fhir.tricc.io/CodeSystem/tricc", group_name="extract_module_c",
        )
        names = sorted(r.group_name for r in merge_extraction_rules([procedure, observation]))
        self.assertEqual(names, ["extract_module_c", "extract_procedure_module_c"])


if __name__ == "__main__":
    unittest.main()
