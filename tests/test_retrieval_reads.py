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


# --- #75 medication: MedicationRequest ----------------------------------------------------

MEDICATION = "medication"
# an open prescription, or else a completed dispense
ON_TREATMENT_ENCOUNTER = (
    "GetEncounterMedicationRequestValue('weight') or exists(GetEncounterMedicationDispenses('weight'))"
)
ON_TREATMENT_P6M = (
    "exists(GetActiveMedicationRequests('weight', Now() - 6 months))"
    " or exists(GetMedicationDispenses('weight', Now() - 6 months))"
)
ON_TREATMENT_EVER = (
    "exists(GetActiveMedicationRequests('weight', null)) or exists(GetMedicationDispenses('weight', null))"
)


@pytest.mark.parametrize(
    "function, context, period, expected",
    [
        ("Latest", "encounter", None, ON_TREATMENT_ENCOUNTER),
        ("Exists", "encounter", None, ON_TREATMENT_ENCOUNTER),
        ("Count", "encounter", None, "Count(GetEncounterMedicationRequests('weight'))"),
        ("ActiveDrugs", "encounter", None, "GetEncounterMedicationCodes()"),
        ("Latest", "history", "P6M", ON_TREATMENT_P6M),
        ("Exists", "history", None, ON_TREATMENT_EVER),
        ("Count", "history", "P1Y", "Count(GetActiveMedicationRequests('weight', Now() - 1 year))"),
        ("ActiveDrugs", "history", "P6M", "GetActiveMedicationCodesSince(Now() - 6 months)"),
    ],
)
def test_medication_request_reads(function, context, period, expected):
    assert retrieval_cql_expression(_retrieval(function, context, MEDICATION, period)) == expected


def test_on_treatment_is_yes_no_and_active_drugs_coded():
    assert _retrieval("Latest", concept_type=MEDICATION).value_type == "boolean"
    assert _retrieval("ActiveDrugs", concept_type=MEDICATION).value_type == "coded"


@pytest.mark.parametrize("function", ["ActiveDrugs"])
def test_medication_function_on_another_resource_fails(function):
    from tricc_oo.converters.retrieval import check_reads_resource

    with pytest.raises(TriccRetrievalError, match=f"{function} reads medication records"):
        check_reads_resource(_retrieval(function, concept_type=OBSERVATION))
    with pytest.raises(TriccRetrievalError, match="has no mapping"):
        retrieval_cql_expression(_retrieval(function, concept_type=CONDITION))
    check_reads_resource(_retrieval(function, concept_type=MEDICATION))


# --- #75 phase 2: OpenDosage and LatestDate -------------------------------------------------


@pytest.mark.parametrize(
    "function, context, period, expected",
    [
        ("OpenDosage", "encounter", None, "GetEncounterMedicationDosage('weight')"),
        ("OpenDosage", "history", "P6M", "GetMedicationDosageSince('weight', Now() - 6 months)"),
        ("LatestDate", "encounter", None, "GetEncounterMedicationRequestDate('weight')"),
        ("LatestDate", "history", None, "GetMedicationRequestDate('weight', null)"),
    ],
)
def test_medication_dosage_and_date(function, context, period, expected):
    assert retrieval_cql_expression(_retrieval(function, context, MEDICATION, period)) == expected


def test_open_dosage_is_text_and_rejected_on_other_resources():
    from tricc_oo.converters.retrieval import check_reads_resource

    assert _retrieval("OpenDosage", concept_type=MEDICATION).value_type == "string"
    with pytest.raises(TriccRetrievalError, match="OpenDosage reads medication records"):
        check_reads_resource(_retrieval("OpenDosage", concept_type=PROCEDURE))


def test_open_dosage_of_a_select_multiple_warns(caplog):
    from types import SimpleNamespace

    from tricc_oo.converters.retrieval import _warn_dosage_of_multiple

    page = SimpleNamespace(nodes={"n": SimpleNamespace(tricc_type="select_multiple", name="weight")})
    with caplog.at_level("WARNING", logger="default"):
        dosage = _retrieval("OpenDosage", concept_type=MEDICATION)
        _warn_dosage_of_multiple(SimpleNamespace(pages={"p": page}), [dosage])
    assert "select_multiple" in caplog.text


# --- #75 phase 3: MedicationDispense -------------------------------------------------------

DISPENSE = "dispense"


@pytest.mark.parametrize(
    "function, context, period, expected",
    [
        ("Latest", "encounter", None, "exists(GetEncounterMedicationDispenses('weight'))"),
        ("Count", "encounter", None, "Count(GetEncounterMedicationDispenses('weight'))"),
        ("LatestDate", "encounter", None, "GetEncounterMedicationDispenseDate('weight')"),
        ("Exists", "history", "P3M", "exists(GetMedicationDispenses('weight', Now() - 3 months))"),
        ("Count", "history", None, "Count(GetMedicationDispenses('weight', null))"),
        ("LatestDate", "history", "P1Y", "GetLastMedicationDispenseDate('weight', Now() - 1 year)"),
    ],
)
def test_medication_dispense_reads(function, context, period, expected):
    assert retrieval_cql_expression(_retrieval(function, context, DISPENSE, period)) == expected


def test_dispense_concept_type_maps_to_medication_dispense():
    from tricc_oo.converters.fhir.concept_mapper import get_fhir_resource

    assert get_fhir_resource("dispense")[0] == "MedicationDispense"
    assert _retrieval("Latest", concept_type=DISPENSE).value_type == "boolean"


@pytest.mark.parametrize("function", ["ActiveDrugs", "OpenDosage"])
def test_drugs_and_dosage_read_prescriptions_only(function):
    with pytest.raises(TriccRetrievalError, match="has no mapping"):
        retrieval_cql_expression(_retrieval(function, concept_type=DISPENSE))
