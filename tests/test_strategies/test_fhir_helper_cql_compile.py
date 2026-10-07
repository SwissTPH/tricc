"""Regression tests for the generated Helper CQL and the Questionnaire's content links.

Before ``fix/20260930-helper-cql-compile.md`` the emitted CQL could not be
translated by cql-to-elm at all, and the Questionnaire carried neither of the two
links a client needs to *use* the generated content:

A. Helper CQL constructs that cql-to-elm rejects — a retrieve code selector fed a
   ``String`` argument, an unparenthesized function-invocation query source, an
   ``as Integer`` cast of a FHIR choice, ``skip``/``take`` query clauses, and a
   ``sort by`` over a choice element.
B. No ``cqf-library`` extension, so a CQL ``initialExpression`` had no library to
   evaluate against and was silently ignored by FHIR-Core.
C. No ``sdc-questionnaire-targetStructureMap`` extension, so the Questionnaire
   could not be StructureMap-extracted however complete the emitted ``.map`` was.
D. A ``Library.url`` ending in the UUID resource id — the CQL engine resolves a
   library source by the canonical's id part, which must be the CQL library name.

The authoritative compile check lives in the android repo, which has cql-to-elm on
its test classpath (``TriccEncounterPopulateE2ETest.compileCql``). These tests pin
the emission rules that made it compile, so a regression here is caught without a
JVM.

Run with:
    python -m pytest tests/test_strategies/test_fhir_helper_cql_compile.py -v
"""

import re
import unittest
from unittest.mock import MagicMock

from tricc_oo.converters.fhir.populate_helper import cql_helper_populate_block
from tricc_oo.converters.fhir.repeat_helper import cql_helper_repeat_block
from tricc_oo.strategies.output.fhir_form import (
    CQF_LIBRARY_EXT,
    CQL_HELPER_TEMPLATE,
    FHIR_VERSION,
    FHIRStrategy,
)
from tricc_oo.converters.fhir.structuremap import SDC_EXT_TARGET_STRUCTUREMAP


def _helper_cql() -> str:
    return CQL_HELPER_TEMPLATE.format(
        library_id="demo-Helper",
        fhir_version=FHIR_VERSION,
        repeat_helpers=cql_helper_repeat_block(FHIR_VERSION),
        populate_helpers=cql_helper_populate_block(),
    )


def _strategy() -> FHIRStrategy:
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    return FHIRStrategy(project, "/tmp/fhir-out")


class TestHelperCqlIsTranslatable(unittest.TestCase):
    """Each assertion maps to one construct cql-to-elm rejected."""

    def setUp(self):
        self.helper = _helper_cql()

    def test_no_retrieve_terminology_clause(self):
        # `[Observation: Code code from "…"]` needs a string literal plus a declared
        # codesystem; `code` is a String function argument.
        self.assertNotIn("Code code from", self.helper)
        self.assertNotIn('from "http://snomed.info/sct"', self.helper)

    def test_no_undeclared_codesystem_reference(self):
        # Nothing may reference a `codesystem` the library does not declare.
        self.assertNotIn("codesystem", self.helper.lower().split("define")[0])
        self.assertNotIn('~ "active"', self.helper)

    def test_codes_matched_against_coding_at_runtime(self):
        self.assertIn("define function ObservationHasCode(O Observation, code String)", self.helper)
        self.assertIn("define function ConditionHasCode(C Condition, code String)", self.helper)
        self.assertIn("exists (O.code.coding C where C.code = code)", self.helper)

    def test_function_query_sources_are_parenthesized(self):
        # `GetObservations(code) O where …` is a syntax error; the source needs parens.
        bad = re.findall(r"^\s*Get\w+\((?:[^()]*)\)\s+[A-Z]\b", self.helper, re.MULTILINE)
        self.assertEqual([], bad, f"unparenthesized query sources: {bad}")
        self.assertIn("(GetObservations(code)) O", self.helper)
        self.assertIn("(GetActiveConditions(code)) C", self.helper)

    def test_repeat_index_casts_through_fhir_integer(self):
        # `extension.value as Integer` cannot cast a FHIR choice to System.Integer.
        self.assertNotIn("value as Integer", self.helper)
        self.assertIn("(E.value as FHIR.integer).value", self.helper)

    def test_sort_by_casts_choice_elements(self):
        self.assertNotIn("sort by effective", self.helper)
        self.assertIn("sort by (effective as FHIR.dateTime)", self.helper)
        self.assertIn("sort by (recordedDate as FHIR.dateTime)", self.helper)

    def test_history_lookback_uses_skip_function_not_query_clauses(self):
        # CQL has no `skip`/`take` query clauses.
        self.assertNotRegex(self.helper, r"\n\s*skip\s")
        self.assertNotRegex(self.helper, r"\n\s*take\s")
        self.assertIn("Skip(", self.helper)

    def test_verification_status_compared_as_string(self):
        self.assertIn("First(C.verificationStatus.coding CC return CC.code.value)", self.helper)

    def test_public_accessor_surface_is_unchanged(self):
        # The author-facing accessors are what generated Questionnaires reference;
        # fixing the bodies must not rename them.
        for fn in (
            "GetObservations",
            "GetObservation",
            "GetObservationValue",
            "GetRepeated",
            "GetRepeatedValue",
            "GetNumberOfRepeat",
            "GetHistoryObservation",
            "GetHistoryObservationValue",
            "GetConditions",
            "GetCondition",
            "GetConditionValue",
            "GetActiveConditions",
            "GetHistoryCondition",
            "GetHistoryConditionValue",
            "HasProvisionalCondition",
            "HasConfirmedCondition",
            "HasRefutedCondition",
            "HasCondition",
            "GetPatientValue",
            "GetEncounterObservationValue",
            "GetEncounterConditionValue",
            "GetEncounterValue",
        ):
            self.assertIn(f"define function {fn}(", self.helper, f"missing {fn}")

    def test_encounter_scoping_preserved(self):
        self.assertIn("parameter encounterid String default null", self.helper)
        self.assertIn("O.encounter.reference = 'Encounter/' + encounterid", self.helper)
        self.assertIn("C.encounter.reference = 'Encounter/' + encounterid", self.helper)


class TestLibraryCanonicalUrl(unittest.TestCase):
    def test_canonical_ends_with_cql_library_name_not_uuid(self):
        strategy = _strategy()
        library = strategy._make_library_resource(
            "7beea8d4-1c4b-5455-ac07-d03fe8cebc91",
            'library "demo-triage" version \'1.0.0\'',
            "demo",
            name="demo-triage",
        )
        # REST id stays a UUID for idempotent PUT …
        self.assertEqual("7beea8d4-1c4b-5455-ac07-d03fe8cebc91", library["id"])
        # … but the canonical must end in the CQL library name so the engine can
        # resolve the library source from the url.
        self.assertTrue(
            library["url"].endswith("/Library/demo-triage"),
            library["url"],
        )
        self.assertEqual("demo-triage", library["name"])


class TestQuestionnaireContentLinks(unittest.TestCase):
    def setUp(self):
        self.strategy = _strategy()
        self.strategy.questionnaires = {
            "triage": {"resourceType": "Questionnaire", "id": "q-triage", "item": []},
            "assess": {"resourceType": "Questionnaire", "id": "q-assess", "item": []},
        }

    def test_cqf_library_points_at_the_segment_library(self):
        self.strategy.libraries = {
            "triage": {"resourceType": "Library", "url": "http://x/Library/demo-triage"},
            "Helper": {"resourceType": "Library", "url": "http://x/Library/demo-Helper"},
        }
        self.strategy._attach_cqf_library_extensions()

        triage = self.strategy.questionnaires["triage"]["extension"]
        self.assertEqual(
            [{"url": CQF_LIBRARY_EXT, "valueCanonical": "http://x/Library/demo-triage"}],
            triage,
        )
        # No library for `assess` → no dangling extension.
        self.assertNotIn("extension", self.strategy.questionnaires["assess"])

    def test_target_structuremap_points_at_the_segment_map(self):
        self.strategy.extraction_maps = {
            "triage": {"resourceType": "StructureMap", "url": "http://x/StructureMap/sm-triage"},
        }
        self.strategy._attach_target_structuremap_extensions()

        self.assertEqual(
            [
                {
                    "url": SDC_EXT_TARGET_STRUCTUREMAP,
                    "valueCanonical": "http://x/StructureMap/sm-triage",
                }
            ],
            self.strategy.questionnaires["triage"]["extension"],
        )

    def test_both_links_coexist_and_are_idempotent(self):
        self.strategy.libraries = {
            "triage": {"resourceType": "Library", "url": "http://x/Library/demo-triage"},
        }
        self.strategy.extraction_maps = {
            "triage": {"resourceType": "StructureMap", "url": "http://x/StructureMap/sm-triage"},
        }
        for _ in range(2):
            self.strategy._attach_target_structuremap_extensions()
            self.strategy._attach_cqf_library_extensions()

        urls = [e["url"] for e in self.strategy.questionnaires["triage"]["extension"]]
        self.assertEqual([SDC_EXT_TARGET_STRUCTUREMAP, CQF_LIBRARY_EXT], urls)


if __name__ == "__main__":
    unittest.main()