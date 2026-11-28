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
        ("medication", "history", "P6M", '("HistoryMedicationRequests") M',
         "IsValidMedicationRequest(M, Now() - 6 months, Now())"),
        ("dispense", "encounter", None, '("EncounterMedicationDispenses") D', None),
    ],
)
def test_records_list_per_concept_and_window(concept_type, context, period, source, window):
    from tricc_oo.converters.fhir.populate_helper import retrieval_records

    ((name, body),) = retrieval_records(_retrieval("Count", context, concept_type, period))[:1]
    assert name == "#weight@" + ("encounter" if context == "encounter" else period or "") + ":records"
    assert body.startswith(source) and "'weight'" in body and " desc" in body
    assert (window in body) if window else (">=" not in body)
    if concept_type == "medication":
        assert "authoredOn.value >=" not in body  # the window is the validity rule's


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


# --- #75 medication: one drug per read, its latest valid MedicationRequest ------------------

MEDICATION = "medication"
#: the prescription fields: catalogue function -> (Helper accessor, value type)
PRESCRIPTION_FIELDS = {
    "Dosage": ("MedicationRequestDosage", "string"),
    "Drug": ("MedicationRequestCode", "coded"),
    "Duration": ("MedicationRequestDuration", "integer"),
    "Quantity": ("MedicationRequestQuantity", "decimal"),
    "Dispensed": ("MedicationRequestDispensed", "decimal"),
}


@pytest.mark.parametrize(
    "function, context, period, expected",
    [
        # active: a valid prescription; no dispense fallback any more
        ("Latest", "encounter", None, f"exists({ENC})"),
        ("Exists", "encounter", None, f"exists({ENC})"),
        ("Count", "encounter", None, f"Count({ENC})"),
        ("LatestDate", "encounter", None, f"First({ENC}).authoredOn.value"),
        ("Latest", "history", "P6M", f"exists({P6M})"),
        ("Exists", "history", None, f"exists({EVER})"),
        ("Count", "history", "P1Y", f"Count({P1Y})"),
        ("LatestDate", "history", None, f"First({EVER}).authoredOn.value"),
    ],
)
def test_medication_request_reads(function, context, period, expected):
    assert retrieval_cql_expression(_retrieval(function, context, MEDICATION, period)) == expected


@pytest.mark.parametrize("function", sorted(PRESCRIPTION_FIELDS))
@pytest.mark.parametrize("context, period, records", [("encounter", None, ENC), ("history", "P6M", P6M),
                                                      ("history", None, EVER)])
def test_prescription_fields_read_the_latest_valid_request(function, context, period, records):
    accessor, value_type = PRESCRIPTION_FIELDS[function]
    retrieval = _retrieval(function, context, MEDICATION, period)
    assert retrieval_cql_expression(retrieval) == f"{accessor}(First({records}))"
    assert retrieval.value_type == value_type


@pytest.mark.parametrize(
    "context, period, source, rule",
    [
        # no window / the encounter: valid now; a window: valid at some time in it
        ("history", None, '("HistoryMedicationRequests") M', "IsValidMedicationRequest(M, Now(), Now())"),
        ("history", "P6M", '("HistoryMedicationRequests") M', "IsValidMedicationRequest(M, Now() - 6 months, Now())"),
        ("encounter", None, '("EncounterMedicationRequests") M', "IsValidMedicationRequest(M, Now(), Now())"),
    ],
)
def test_a_drugs_records_are_its_valid_requests(context, period, source, rule):
    from tricc_oo.converters.fhir.populate_helper import retrieval_records

    ((name, body),) = retrieval_records(_retrieval("Dispensed", context, MEDICATION, period))
    where = f"where MedicationRequestHasCode(M, 'weight') and {rule}"
    assert body == f"{source}\n    {where}\n    sort by authoredOn.value desc"


def test_active_is_yes_no():
    assert _retrieval("Latest", concept_type=MEDICATION).value_type == "boolean"


@pytest.mark.parametrize("function", sorted(PRESCRIPTION_FIELDS))
def test_prescription_field_on_another_resource_fails(function):
    from tricc_oo.converters.retrieval import check_reads_resource

    for other in (OBSERVATION, PROCEDURE, "dispense"):
        with pytest.raises(TriccRetrievalError, match=f"{function} reads prescriptions"):
            check_reads_resource(_retrieval(function, concept_type=other))
    with pytest.raises(TriccRetrievalError, match="has no mapping"):
        retrieval_cql_expression(_retrieval(function, concept_type=CONDITION))
    check_reads_resource(_retrieval(function, concept_type=MEDICATION))


@pytest.mark.parametrize("field", ["drugs", "foo"])
def test_removed_and_unknown_fields_are_refused(field):
    from tricc_oo.converters.retrieval import RETRIEVE_FIELDS

    assert field not in RETRIEVE_FIELDS
    assert "ActiveDrugs" not in RETRIEVAL_FUNCTIONS and "OpenDosage" not in RETRIEVAL_FUNCTIONS


def test_dosage_of_a_select_multiple_warns(caplog):
    from types import SimpleNamespace

    from tricc_oo.converters.retrieval import _warn_dosage_of_multiple

    page = SimpleNamespace(nodes={"n": SimpleNamespace(tricc_type="select_multiple", name="weight")})
    with caplog.at_level("WARNING", logger="default"):
        dosage = _retrieval("Dosage", concept_type=MEDICATION)
        _warn_dosage_of_multiple(SimpleNamespace(pages={"p": page}), [dosage])
    assert "select_multiple" in caplog.text


def test_a_drugs_default_field_is_active():
    from tricc_oo.converters.retrieval import retrieval_field

    assert retrieval_field(_retrieval("Latest", concept_type=MEDICATION)) == "active"
    assert retrieval_field(_retrieval("Latest")) == "value"
    assert retrieval_field(_retrieval("Dispensed", concept_type=MEDICATION)) == "dispensed"


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


@pytest.mark.parametrize("function", sorted(PRESCRIPTION_FIELDS))
def test_prescription_fields_read_prescriptions_only(function):
    with pytest.raises(TriccRetrievalError, match="has no mapping"):
        retrieval_cql_expression(_retrieval(function, concept_type=DISPENSE))


def test_cht_reports_that_the_contact_summary_must_provide_dispensed(caplog):
    """CHT has no dispense-to-prescription link: the gap is reported, the key read as usual."""
    from tricc_oo.strategies.output.xlsform_cht import XLSFormCHTStrategy

    strategy = XLSFormCHTStrategy.__new__(XLSFormCHTStrategy)
    retrieval = Retrieval(code="#metformin@P6M.dispensed", context="history", function="Dispensed",
                          reads_code="metformin", period="P6M", reads_concept_type=MEDICATION)
    with caplog.at_level("WARNING", logger="default"):
        expression = strategy.retrieval_expression(retrieval)
        strategy.retrieval_expression(retrieval)  # once per retrieval
    assert expression == "coalesce(instance('contact-summary')/context/metformin_P6M_dispensed,'')"
    assert caplog.text.count("quantity dispensed against the latest valid prescription of 'metformin'") == 1
