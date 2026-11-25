"""Retrieval catalogue reads per FHIR resource.

- feature/20261125-populate-read-date.md (#76): ``LatestDate`` and Procedure reads;
- feature/20261125-populate-medication.md (#75): MedicationRequest / MedicationDispense reads.
"""

from __future__ import annotations

import pytest

from tricc_oo.converters.fhir.populate_helper import retrieval_cql_expression
from tricc_oo.converters.retrieval import RETRIEVAL_FUNCTIONS, Retrieval, TriccRetrievalError

#: conceptType -> FHIR resource it maps to (concept_mapper.get_fhir_resource)
OBSERVATION = "Symptom-Finding"
CONDITION = "diagnosis"


def _retrieval(function, context="history", concept_type=OBSERVATION, period=None, data_type="decimal"):
    return Retrieval(
        code="#r", context=context, function=function, reads_code="weight", period=period,
        reads_concept_type=concept_type, reads_data_type=data_type,
    )


# --- #76 LatestDate ----------------------------------------------------------------------


def test_latest_date_is_a_timed_catalogue_function():
    contexts, needs_reads, value_type = RETRIEVAL_FUNCTIONS["LatestDate"]
    assert (contexts, needs_reads, value_type) == (("encounter", "history"), True, "dateTime")
    assert _retrieval("LatestDate").value_type == "dateTime"


@pytest.mark.parametrize(
    "concept_type, context, period, expected",
    [
        (OBSERVATION, "encounter", None, "GetEncounterObservationTime('weight')"),
        (OBSERVATION, "history", "P3M", "LatestObservationTime('weight', Now() - 3 months)"),
        (OBSERVATION, "history", None, "LatestObservationTime('weight', null)"),
        (CONDITION, "encounter", None, "GetEncounterConditionDate('weight')"),
        (CONDITION, "history", "P1Y", "GetHistoryConditionDate('weight', Now() - 1 year)"),
        (CONDITION, "history", None, "GetHistoryConditionDate('weight', null)"),
    ],
)
def test_latest_date_per_resource_and_context(concept_type, context, period, expected):
    assert retrieval_cql_expression(_retrieval("LatestDate", context, concept_type, period)) == expected


def test_latest_date_needs_reads():
    from fhir.resources.codesystem import CodeSystem

    from tricc_oo.converters.retrieval import read_retrieval

    concept = CodeSystem.model_validate(
        {"resourceType": "CodeSystem", "status": "draft", "content": "complete",
         "concept": [{"code": "#d", "property": [{"code": "context", "valueCode": "history"},
                                                 {"code": "function", "valueCode": "LatestDate"}]}]}
    ).concept[0]
    with pytest.raises(TriccRetrievalError, match="LatestDate needs 'reads'"):
        read_retrieval(concept)


def test_latest_date_retrieval_node_is_a_datetime_item():
    from tricc_oo.converters.retrieval import build_retrieval_node

    assert build_retrieval_node(_retrieval("LatestDate")).data_type == "datetime"


# --- #76 phase 2: Procedure ---------------------------------------------------------------

PROCEDURE = "procedure"


@pytest.mark.parametrize(
    "function, context, period, expected",
    [
        ("Latest", "encounter", None, "GetEncounterProcedureValue('weight', null)"),
        ("Exists", "encounter", None, "GetEncounterProcedureValue('weight', null)"),
        ("Count", "encounter", None, "Count(GetProcedures('weight'))"),
        ("LatestDate", "encounter", None, "GetEncounterProcedureDate('weight')"),
        ("Latest", "history", "P6M", "GetHistoryProcedureDate('weight', Now() - 6 months) is not null"),
        ("Exists", "history", None, "GetHistoryProcedureDate('weight', null) is not null"),
        ("Count", "history", "P1Y", "Count(GetHistoryProcedures('weight', Now() - 1 year))"),
        ("LatestDate", "history", "P1Y", "GetHistoryProcedureDate('weight', Now() - 1 year)"),
    ],
)
def test_procedure_reads(function, context, period, expected):
    assert retrieval_cql_expression(_retrieval(function, context, PROCEDURE, period)) == expected


def test_procedure_latest_is_done_yes_no():
    assert _retrieval("Latest", concept_type=PROCEDURE).value_type == "boolean"
    assert _retrieval("Latest").value_type == "decimal"  # an Observation keeps the concept's type
