"""One-level FHIR sections (feature/20261120-questionnaire-pages.md, phase 2).

An activity called from another one no longer nests in the caller's group: the caller's
section stops, the called activity gets its own, the caller continues in a new one. Each
activity is a hidden boolean item holding its relevance; its sections are gated on it.
"""

import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAML_DIR = os.path.join(REPO, "tests", "data", "yaml")
ENABLE_WHEN = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-enableWhenExpression"
CALCULATED = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-calculatedExpression"
HIDDEN = "http://hl7.org/fhir/StructureDefinition/questionnaire-hidden"
ITEM_CONTROL = "http://hl7.org/fhir/StructureDefinition/questionnaire-itemControl"
PATH = re.compile(r"%resource((?:\.item\.where\(linkId='[^']+'\))+)")


def build_questionnaires(fixture, output_strategy="FHIRStrategy"):
    """{file name: Questionnaire} of a YAML fixture built in a fresh interpreter."""
    with tempfile.TemporaryDirectory() as out:
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
        result = {}
        for path in glob.glob(os.path.join(out, "**", "Questionnaire-*.json"), recursive=True):
            with open(path) as f:
                result[os.path.basename(path)] = json.load(f)
    return result


def walk(items, depth=1):
    """(item, depth) of every item, depth first."""
    for item in items or []:
        yield item, depth
        yield from walk(item.get("item"), depth + 1)


def expression(item, url):
    for ext in item.get("extension", []):
        if ext.get("url") == url:
            return (ext.get("valueExpression") or {}).get("expression")
    return None


def item_control(item):
    for ext in item.get("extension", []):
        if ext.get("url") == ITEM_CONTROL:
            return ext["valueCodeableConcept"]["coding"][0]["code"]
    return None


def gate(link_id):
    return f"%resource.item.where(linkId='{link_id}').answer.where(value = true).exists()"


def unresolved_paths(questionnaire):
    """``%resource.item…`` chains of the expressions that name no item of the tree."""
    def exists(chain):
        level = questionnaire.get("item") or []
        for link_id in chain:
            found = next((i for i in level if i.get("linkId") == link_id), None)
            if found is None:
                return False
            level = found.get("item") or []
        return True

    missing = []
    for item, _ in walk(questionnaire.get("item")):
        for ext in item.get("extension", []):
            text = (ext.get("valueExpression") or {}).get("expression") or ""
            for match in PATH.finditer(text):
                chain = re.findall(r"linkId='([^']+)'", match.group(1))
                if not exists(chain):
                    missing.append(match.group(0))
    return missing


class TestFlatSections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (cls.q,) = build_questionnaires("flat_sections.yaml").values()
        cls.top = cls.q["item"]
        cls.sections = [i["linkId"] for i in cls.top if i["type"] == "group"]
        cls.items = {i["linkId"]: i for i, _ in walk(cls.top)}

    def test_caller_split_around_called_activity(self):
        # act_p_Ss_1 is taken by an authored name: P's first section gets the next free linkId
        start = self.sections.index("act_p_Ss_1_1")
        self.assertEqual(self.sections[start:start + 3], ["act_p_Ss_1_1", "act_d_Ss_1", "act_p_Ss_2"])
        self.assertEqual([i["linkId"] for i in self.items["act_p_Ss_1_1"]["item"]], ["p_cough"])
        self.assertEqual([i["linkId"] for i in self.items["act_d_Ss_1"]["item"]], ["d_breath"])
        self.assertEqual([i["linkId"] for i in self.items["act_p_Ss_2"]["item"]], ["p_after"])

    def test_no_nesting(self):
        for item, depth in walk(self.top):
            if item["type"] == "group":
                self.assertEqual(depth, 1, item["linkId"])
            self.assertLessEqual(depth, 2, item["linkId"])

    def test_sections_gated_by_hidden_activity_items(self):
        for section, activity in (("act_p_Ss_1_1", "act_p"), ("act_d_Ss_1", "act_d"), ("act_p_Ss_2", "act_p")):
            self.assertEqual(expression(self.items[section], ENABLE_WHEN), gate(activity))
        for activity in ("act_p", "act_d", "act_q", "act_c"):
            item = self.items[activity]
            self.assertEqual(item["type"], "boolean")
            self.assertIn({"url": HIDDEN, "valueBoolean": True}, item["extension"])
            self.assertTrue(expression(item, CALCULATED))
            # the hidden item is a top-level item, before the activity's first section
            self.assertIn(item, self.top)

    def test_called_last_leaves_no_empty_continuation(self):
        self.assertIn("act_q_Ss_1", self.sections)
        self.assertNotIn("act_q_Ss_2", self.sections)

    def test_default_sections_hold_loose_items(self):
        self.assertEqual(self.sections[0], "main_Ss_d1")
        self.assertIsNone(expression(self.items["main_Ss_d1"], ENABLE_WHEN))
        self.assertEqual([i["linkId"] for i in self.items["main_Ss_d1"]["item"]], ["go_p", "act_p_Ss_1"])

    def test_no_link_id_collision(self):
        link_ids = [i["linkId"] for i, _ in walk(self.top)]
        self.assertEqual(len(link_ids), len(set(link_ids)))
        self.assertEqual(self.items["act_p_Ss_1"]["type"], "integer")

    def test_shared_activity_enabled_from_any_call_site(self):
        # act_c is called from act_p and act_q: its relevance is the OR of both call sites,
        # so it is shown when only act_q is reached, while act_p's sections are not
        relevance = expression(self.items["act_c"], CALCULATED)
        self.assertIn(" or ", relevance)
        self.assertIn("p_cough", relevance)
        self.assertIn(".not()", relevance)
        self.assertEqual(expression(self.items["act_c_Ss_1"], ENABLE_WHEN), gate("act_c"))
        self.assertNotIn("act_p", expression(self.items["act_c_Ss_1"], ENABLE_WHEN))

    def test_no_relevance_duplicated_into_items(self):
        # items of a section carry only their own relevance, not the activity's
        self.assertIsNone(expression(self.items["d_breath"], ENABLE_WHEN))
        self.assertIsNone(expression(self.items["c_temp"], ENABLE_WHEN))

    def test_expression_paths_resolve_on_the_flat_tree(self):
        self.assertEqual(unresolved_paths(self.q), [])
        # c_check references p_cough, which moved out of the nested group of act_p
        self.assertIn("item.where(linkId='act_p_Ss_1_1').item.where(linkId='p_cough')",
                      expression(self.items["c_check"], ENABLE_WHEN))

    def test_no_page_no_item_control(self):
        self.assertFalse([i["linkId"] for i, _ in walk(self.top) if item_control(i) == "page"])


class TestFlatSectionsRepeat(unittest.TestCase):
    def test_repeat_activity_called_twice_has_distinct_sections(self):
        (q,) = build_questionnaires("flat_sections_repeat.yaml").values()
        sections = [i["linkId"] for i in q["item"] if i["type"] == "group"]
        repeat_sections = [s for s in sections if s.startswith("act_r_Rr_2")]
        self.assertEqual(len(repeat_sections), 2, sections)
        self.assertEqual(len(set(repeat_sections)), 2)
        link_ids = [i["linkId"] for i, _ in walk(q["item"])]
        self.assertEqual(len(link_ids), len(set(link_ids)))
        self.assertEqual(unresolved_paths(q), [])


class TestFlatSectionsOpenSRP(unittest.TestCase):
    def test_opensrp_inherits_flat_sections(self):
        questionnaires = build_questionnaires("flat_sections.yaml", "OpenSRPStrategy")
        q = next(q for name, q in questionnaires.items() if "main" in name)
        groups = [i["linkId"] for i in q["item"] if i["type"] == "group"]
        self.assertIn("act_d_Ss_1", groups)
        self.assertEqual(unresolved_paths(q), [])


if __name__ == "__main__":
    unittest.main()
