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


#: the shared records list of `weight` per window (feature/20261125-requires-and-implied-retrievals.md §4)
ENC, EVER, P3M, P6M, P1Y = (f'"#weight@{w}:records"' for w in ("encounter", "", "P3M", "P6M", "P1Y"))


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
        (OBSERVATION, "encounter", None, f"(First({ENC}).effective as FHIR.dateTime).value"),
        (OBSERVATION, "history", "P3M", f"(First({P3M}).effective as FHIR.dateTime).value"),
        (OBSERVATION, "history", None, f"(First({EVER}).effective as FHIR.dateTime).value"),
        (CONDITION, "encounter", None, f"Max(({ENC}) C return ConditionDate(C))"),
        (CONDITION, "history", "P1Y", f"Max(({P1Y}) C return ConditionDate(C))"),
        (CONDITION, "history", None, f"Max(({EVER}) C return ConditionDate(C))"),
    ],
)
def test_latest_date_per_resource_and_context(concept_type, context, period, expected):
    assert retrieval_cql_expression(_retrieval("LatestDate", context, concept_type, period)) == expected


@pytest.mark.parametrize(
    "concept_type, context, period, source, window",
    [
        (OBSERVATION, "encounter", None, '("EncounterObservations") O', None),
        (OBSERVATION, "history", "P3M", '("HistoryObservations") O',
         "(O.effective as FHIR.dateTime).value >= Now() - 3 months"),
        (OBSERVATION, "history", None, '("HistoryObservations") O', None),
        (CONDITION, "encounter", None, '("EncounterConditions") C', None),
        (CONDITION, "history", "P1Y", '("HistoryConditions") C', "ConditionDate(C) >= Now() - 1 year"),
        ("procedure", "history", "P6M", '("HistoryProcedures") P', "ProcedureTime(P) >= Now() - 6 months"),
        ("medication", "history", "P6M", '("HistoryMedicationRequests") M', "M.authoredOn.value >= Now() - 6 months"),
        ("dispense", "encounter", None, '("EncounterMedicationDispenses") D', None),
    ],
)
def test_records_list_per_concept_and_window(concept_type, context, period, source, window):
    from tricc_oo.converters.fhir.populate_helper import retrieval_records

    ((name, body),) = retrieval_records(_retrieval("Count", context, concept_type, period))[:1]
    assert name == "#weight@" + ("encounter" if context == "encounter" else period or "") + ":records"
    assert body.startswith(source) and "'weight'" in body and " desc" in body
    assert (window in body) if window else (">=" not in body)


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
        ("Latest", "encounter", None, f"exists({ENC})"),
        ("Exists", "encounter", None, f"exists({ENC})"),
        ("Count", "encounter", None, f"Count({ENC})"),
        ("LatestDate", "encounter", None, f"Max(({ENC}) P return ProcedureTime(P))"),
        ("Latest", "history", "P6M", f"exists({P6M})"),
        ("Exists", "history", None, f"exists({EVER})"),
        ("Count", "history", "P1Y", f"Count({P1Y})"),
        ("LatestDate", "history", "P1Y", f"Max(({P1Y}) P return ProcedureTime(P))"),
    ],
)
def test_procedure_reads(function, context, period, expected):
    assert retrieval_cql_expression(_retrieval(function, context, PROCEDURE, period)) == expected


def test_procedure_latest_is_done_yes_no():
    assert _retrieval("Latest", concept_type=PROCEDURE).value_type == "boolean"
    assert _retrieval("Latest").value_type == "decimal"  # an Observation keeps the concept's type


# --- #75 medication: MedicationRequest ----------------------------------------------------

MEDICATION = "medication"
OPEN_ENC = f"(({ENC}) M where IsOpenMedicationRequest(M))"
OPEN_P6M = f"(({P6M}) M where IsOpenMedicationRequest(M))"
# an open prescription, or else a completed dispense
ON_TREATMENT_ENCOUNTER = f'exists(({ENC}) M where IsOpenMedicationRequest(M)) or exists("#weight@encounter:dispenses")'
ON_TREATMENT_P6M = f'exists(({P6M}) M where IsOpenMedicationRequest(M)) or exists("#weight@P6M:dispenses")'
ON_TREATMENT_EVER = f'exists(({EVER}) M where IsOpenMedicationRequest(M)) or exists("#weight@:dispenses")'


@pytest.mark.parametrize(
    "function, context, period, expected",
    [
        ("Latest", "encounter", None, ON_TREATMENT_ENCOUNTER),
        ("Exists", "encounter", None, ON_TREATMENT_ENCOUNTER),
        ("Count", "encounter", None, f"Count(({ENC}) M where IsOpenMedicationRequest(M))"),
        ("ActiveDrugs", "encounter", None, "GetEncounterMedicationCodes()"),
        ("Latest", "history", "P6M", ON_TREATMENT_P6M),
        ("Exists", "history", None, ON_TREATMENT_EVER),
        ("Count", "history", "P1Y", f"Count(({P1Y}) M where IsOpenMedicationRequest(M))"),
        ("ActiveDrugs", "history", "P6M", "GetActiveMedicationCodesSince(Now() - 6 months)"),
    ],
)
def test_medication_request_reads(function, context, period, expected):
    assert retrieval_cql_expression(_retrieval(function, context, MEDICATION, period)) == expected


def test_on_treatment_reads_the_dispenses_of_the_same_window():
    from tricc_oo.converters.fhir.populate_helper import retrieval_records

    names = [name for name, _ in retrieval_records(_retrieval("Exists", "history", MEDICATION, "P6M"))]
    assert names == ["#weight@P6M:records", "#weight@P6M:dispenses"]


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
        ("OpenDosage", "encounter", None, f"MedicationRequestDosage(First{OPEN_ENC})"),
        ("OpenDosage", "history", "P6M", f"MedicationRequestDosage(First{OPEN_P6M})"),
        ("LatestDate", "encounter", None, f"Max(({ENC}) M return M.authoredOn.value)"),
        ("LatestDate", "history", None, f"Max(({EVER}) M return M.authoredOn.value)"),
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
        ("Latest", "encounter", None, f"exists({ENC})"),
        ("Count", "encounter", None, f"Count({ENC})"),
        ("LatestDate", "encounter", None, f"Max(({ENC}) D return D.whenHandedOver.value)"),
        ("Exists", "history", "P3M", f"exists({P3M})"),
        ("Count", "history", None, f"Count({EVER})"),
        ("LatestDate", "history", "P1Y", f"Max(({P1Y}) D return D.whenHandedOver.value)"),
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
