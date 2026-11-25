"""
Populate context helpers for FHIR CQL and XLSForm/CHT export.

Author-facing accessors use *Value suffix (scalars). Resource-level names
(GetHistory, …) exist only in generated Helper CQL.
"""

from __future__ import annotations

import logging
import re
from typing import Optional, TYPE_CHECKING

from tricc_oo.models.base import get_repeat

if TYPE_CHECKING:
    from tricc_oo.models.calculate import TriccNodePopulate

logger = logging.getLogger("default")

MASTER_CONTEXTS = frozenset({"patient", "facility", "practitioner", "location"})
ENCOUNTER_CONTEXT = "encounter"
HISTORY_CONTEXT = "history"
ALLOWED_CONTEXTS = MASTER_CONTEXTS | {ENCOUNTER_CONTEXT, HISTORY_CONTEXT}
# CHT injects external data two ways: the form's ``inputs`` group (contact-doc
# fields and task ``modifyContent`` keys, read as ``../inputs/contact/<field>``)
# and the contact-summary instance (``instance('contact-summary')/context/<key>``,
# the only route for anything derived from previous reports). Encounter values are
# the task-injected ones; every other context is contact-summary backed.
INPUTS_GROUP_CONTEXTS = frozenset({ENCOUNTER_CONTEXT})
DEFAULT_HISTORY_PERIOD = "P1Y"
# populate `data_type` → FHIR Questionnaire item type. Authors write the value shape
# they expect back; the item type has to agree with it for SDC to seed `initial`.
_POPULATE_DATA_TYPE_TO_FHIR_ITEM = {
    "quantity": "quantity",
    "decimal": "decimal",
    "integer": "integer",
    "boolean": "boolean",
    "string": "string",
    "text": "string",
    "date": "date",
    "datetime": "dateTime",
    "code": "choice",
    "coding": "choice",
    "choice": "choice",
}

_ISO_DURATION_RE = re.compile(
    r"^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$",
    re.IGNORECASE,
)
_ISO_PERIOD_RE = re.compile(r"^.+/.+$")


def is_valid_period(value: str) -> bool:
    """Return True if *value* looks like an ISO Duration or Period start/end."""
    if not value or not str(value).strip():
        return False
    v = str(value).strip()
    return bool(_ISO_DURATION_RE.match(v) or _ISO_PERIOD_RE.match(v))


def normalize_populate_node(node: "TriccNodePopulate") -> None:
    """Validate and normalize context / period on a populate node (in-place)."""
    ctx = (getattr(node, "context", None) or "patient").strip().lower()
    if ctx not in ALLOWED_CONTEXTS:
        logger.error(f"Invalid populate context '{ctx}' on {node.get_name()}; defaulting to patient")
        ctx = "patient"
    node.context = ctx

    period = getattr(node, "period", None)
    if period is not None:
        period = str(period).strip() or None

    if ctx in MASTER_CONTEXTS:
        if period:
            logger.warning(
                f"period ignored for populate context={ctx} on {node.get_name()}"
            )
        node.period = None
    elif ctx == ENCOUNTER_CONTEXT:
        if period and not is_valid_period(period):
            logger.error(f"Unparseable period '{period}' on {node.get_name()}; ignoring")
            node.period = None
        else:
            node.period = period
    elif ctx == HISTORY_CONTEXT:
        if not period:
            logger.warning(
                f"populate context=history without period on {node.get_name()}; defaulting to {DEFAULT_HISTORY_PERIOD}"
            )
            node.period = DEFAULT_HISTORY_PERIOD
        elif not is_valid_period(period):
            logger.error(f"Unparseable period '{period}' on {node.get_name()}; using {DEFAULT_HISTORY_PERIOD}")
            node.period = DEFAULT_HISTORY_PERIOD
        else:
            node.period = period


def populate_participates_in_skip(node) -> bool:
    """Return True when a populate node may satisfy skip / last-version for capture nodes."""
    from tricc_oo.models.calculate import TriccNodePopulate

    if not isinstance(node, TriccNodePopulate):
        return True
    if node.context == HISTORY_CONTEXT:
        return False
    if get_repeat(node) == 0:
        return False
    return True


def _cql_string_literal(value: Optional[str]) -> str:
    if value is None:
        return "null"
    safe = str(value).replace("'", "\\'")
    return f"'{safe}'"


def _repeat_cql_arg(node) -> str:
    repeat = get_repeat(node)
    return "null" if repeat == 1 else str(repeat)


def populate_fhir_target(node) -> str:
    """FHIR resource a populate node reads from (``Observation`` by default).

    Encounter / history accessors are resource-specific — an Observation is read by
    value, a Condition by existence — so the accessor name has to follow the node's
    ``concept_type`` rather than assuming Observation.
    """
    from tricc_oo.converters.fhir.concept_mapper import get_fhir_resource

    resource, _, _ = get_fhir_resource(
        getattr(node, "concept_type", None), getattr(node, "tricc_type", None)
    )
    return resource


_CQL_DURATION_UNITS = (("year", "years"), ("month", "months"), ("week", "weeks"), ("day", "days"))


def cql_lookback_start(period: Optional[str]) -> Optional[str]:
    """CQL DateTime for the start of an ISO 8601 duration window ending now.

    ``P3M`` → ``Now() - 3 months``; ``P1Y6M`` → ``Now() - 1 year - 6 months``. Returns None
    for durations with a time part, explicit start/end periods, and unparseable values — the
    lookup then has no window.

    Args:
        period: ISO 8601 duration such as ``P3M``.

    Returns:
        CQL expression, or None.
    """
    match = _ISO_DURATION_RE.match(str(period or "").strip())
    if not match or any(match.groups()[4:]):
        return None
    parts = []
    for amount, (singular, plural) in zip(match.groups()[:4], _CQL_DURATION_UNITS):
        if amount and int(amount):
            parts.append(f"{int(amount)} {singular if int(amount) == 1 else plural}")
    if not parts:
        return None
    return "Now() - " + " - ".join(parts)


def populate_source_concept(node: "TriccNodePopulate") -> str:
    """Concept a populate node reads: its ``source`` attribute, else its own name.

    ``source`` lets a "previous value" node (``t_weight``) read the concept the question
    records (``weight_c``) while keeping its own name for in-form references — the same
    name would make the two nodes versions of one concept.
    See feature/20260929-cql-populate-wiring.md §5.
    """
    return (getattr(node, "source", None) or node.name or "").strip()


# context=patient: concept name -> (Helper define, CQL result type).
# See feature/20260929-cql-populate-wiring.md §9.
PATIENT_FIELDS = {
    "sex": ("PatientGender", "string"),
    "gender": ("PatientGender", "string"),
    "age": ("AgeInYears", "integer"),
    "birthdate": ("PatientBirthDate", "date"),
    "dob": ("PatientBirthDate", "date"),
    "date_of_birth": ("PatientBirthDate", "date"),
}


def patient_field(node: "TriccNodePopulate") -> Optional[tuple]:
    """(Helper define, result type) a ``context=patient`` node reads, or None if unsupported."""
    if (getattr(node, "context", None) or "").strip().lower() != "patient":
        return None
    return PATIENT_FIELDS.get(populate_source_concept(node).lower())


def populate_value_type(node: "TriccNodePopulate") -> Optional[str]:
    """Known CQL result type of a populate node's accessor (None: Observation value / unknown)."""
    retrieval = getattr(node, "retrieval", None)
    if retrieval is not None:
        return retrieval_cql_type(retrieval)
    field = patient_field(node)
    if field:
        return field[1]
    return _procedure_value_type(node)


def _procedure_value_type(node) -> Optional[str]:
    """``boolean`` (done this encounter) or ``date`` (last done) for a Procedure populate (#74)."""
    if getattr(node, "context", None) not in (ENCOUNTER_CONTEXT, HISTORY_CONTEXT):
        return None
    if populate_fhir_target(node) != "Procedure":
        return None
    return "boolean" if node.context == ENCOUNTER_CONTEXT else "date"


def populate_reads_multiple(node: "TriccNodePopulate", select_multiple_concepts=None) -> bool:
    """True when a populate node reads a select_multiple concept (a list of option codes).

    Declared with ``data_type="select_multiple"`` or detected from the project's
    select_multiple questions. See feature/20260929-cql-populate-wiring.md §10.
    """
    if (getattr(node, "data_type", None) or "").strip().lower() == "select_multiple":
        return True
    return populate_source_concept(node) in (select_multiple_concepts or ())


def resolve_populate_reference(
    node: "TriccNodePopulate", qualified: bool = False, multiple: bool = False
) -> str:
    """Return author-facing CQL accessor for a populate node (*Value helpers only).

    ``multiple``: the concept is a select_multiple, read as the space-separated option codes
    of its latest answer (``context=history`` only).
    """
    prefix = "Helper." if qualified else ""
    retrieval = getattr(node, "retrieval", None)
    if retrieval is not None:
        # a project retrieval: its define in the Helper library (retrieval_cql_defines)
        return f'{prefix}"{retrieval.code}"'
    code = populate_source_concept(node).replace("'", "\\'")
    ctx = node.context
    repeat_arg = _repeat_cql_arg(node)

    if ctx == "patient":
        field = patient_field(node)
        if field:
            return f"{prefix}{field[0]}"
        logger.warning(
            "populate %s: context=patient concept '%s' is not a supported Patient field (%s); "
            "it stays empty",
            node.get_name(),
            code,
            ", ".join(sorted(PATIENT_FIELDS)),
        )
        return f"{prefix}GetPatientValue('{code}')"
    if ctx == "facility":
        return f"{prefix}GetFacilityValue('{code}')"
    if ctx == "location":
        return f"{prefix}GetLocationValue('{code}')"
    if ctx == "practitioner":
        return f"{prefix}GetPractitionerValue('{code}')"
    target = populate_fhir_target(node)
    if ctx == ENCOUNTER_CONTEXT:
        if target == "Condition":
            return f"{prefix}GetEncounterConditionValue('{code}')"
        if target == "Procedure":
            return f"{prefix}GetEncounterProcedureValue('{code}', {repeat_arg})"
        return (
            f"{prefix}GetEncounterObservationValue('{code}', {repeat_arg}, "
            f"{_cql_string_literal(node.period)})"
        )
    if ctx == HISTORY_CONTEXT:
        period = node.period or DEFAULT_HISTORY_PERIOD
        if target == "Condition":
            return f"{prefix}GetHistoryConditionValue('{code}')"
        if target == "Procedure":
            return f"{prefix}GetHistoryProcedureDate('{code}')"
        since = cql_lookback_start(period)
        if multiple and target == "Observation":
            return f"{prefix}GetHistoryObservationCodesSince('{code}', {since or 'null'})"
        if since is None:
            logger.warning(
                "populate %s: period '%s' is not a date-only ISO duration; reading without a window",
                node.get_name(),
                period,
            )
        return (
            f"{prefix}GetHistoryObservationValueSince("
            f"'{code}', {since or 'null'}, 1, {repeat_arg})"
        )
    return f"{prefix}GetPatientValue('{code}')"


def populate_fhir_item_type(node) -> Optional[str]:
    """FHIR Questionnaire item type for a populate node, or None to keep the default.

    A populate node's item is seeded with an ``initial`` value produced by its CQL
    accessor, and SDC requires that value's type to match the item type — a
    ``Quantity`` cannot seed a ``string`` item. The author declares the shape with
    ``data_type``; without it the generic hidden-``string`` default stands, which is
    right for the boolean/coded cases that dominate.

    Args:
        node: A ``TriccNodePopulate``.

    A Procedure populate has a fixed shape (#74): ``boolean`` in the encounter, ``date``
    in history.

    Returns:
        FHIR item type string (e.g. ``"quantity"``), or None when unset/unknown.
    """
    declared = (getattr(node, "data_type", None) or "").strip().lower()
    if not declared:
        return _procedure_value_type(node)
    item_type = _POPULATE_DATA_TYPE_TO_FHIR_ITEM.get(declared)
    if item_type is None:
        logger.warning(
            f"Unknown populate data_type '{declared}' on {node.get_name()}; keeping default item type"
        )
    return item_type


def populate_unit(node) -> Optional[str]:
    """Unit of measure declared on a populate node (``quantity`` data_type only)."""
    if populate_fhir_item_type(node) != "quantity":
        return None
    unit = getattr(node, "unit", None)
    return str(unit).strip() or None if unit else None


def populate_uses_inputs_group(node) -> bool:
    """True when CHT delivers this populate value through the form ``inputs`` group.

    Those nodes need a hidden field named after the source document field plus a
    calculate that reads it; contact-summary backed nodes need the calculate only
    (see ``get_cht_contact_summary_expression``).
    """
    return getattr(node, "context", None) in INPUTS_GROUP_CONTEXTS


def get_cht_contact_summary_expression(node: "TriccNodePopulate", replace_dots: bool = True) -> str:
    """XLSForm/CHT calculate binding against contact-summary context."""
    from tricc_oo.converters.tricc_to_xls_form import _concept_export_base_name

    key = _concept_export_base_name(node, replace_dots=replace_dots)
    return f"coalesce(instance('contact-summary')/context/{key},'')"


def cql_helper_populate_block() -> str:
    """CQL definitions for populate context accessors (included in Helper library)."""
    return """\
// ── Populate context helpers ─────────────────────────────────────────────────

define function GetPatientValue(code String):
  null

// Patient demographics for context=patient populate nodes (sex / gender, birth date; age is
// AgeInYears below). Gender is the FHIR code: female | male | other | unknown.
// Read with First([Patient]), not the implicit `Patient` (a singleton): fhircore passes the
// patient in its data bundle while it is also in the local database, and the duplicate made
// every expression of the form fail. See feature/20260929-cql-populate-wiring.md §9.
define PatientRecord:
  First([Patient])

define PatientGender:
  PatientRecord.gender.value

define PatientBirthDate:
  PatientRecord.birthDate.value

define function GetFacilityValue(code String):
  null

define function GetLocationValue(code String):
  null

define function GetPractitionerValue(code String):
  null

// Current-encounter accessors. GetObservations/GetConditions already filter on the
// `encounterid` parameter, so these are GetObservationValue / GetConditionValue
// scoped to this encounter; the names stay resource-specific so a populate node with
// a Condition concept_type does not read an Observation value
// (fix/20260821-merge-input-into-populate.md).

define function GetEncounterObservationValue(code String, repeatIndex Integer, period String):
  if repeatIndex is null or repeatIndex = 1 then GetObservationValue(code)
  else GetRepeatedValue(code, repeatIndex)

define function GetEncounterConditionValue(code String):
  GetConditionValue(code)

// Deprecated alias: resource-agnostic name kept for previously generated libraries.
define function GetEncounterValue(code String, repeatIndex Integer, period String):
  GetEncounterObservationValue(code, repeatIndex, period)

// ── Medication reads (feature/20261125-populate-medication.md) ────────────────
// A drug is matched by code across any system, on medicationCodeableConcept or on the
// code of the Medication a medicationReference points to. An open prescription is an
// active MedicationRequest whose dispense validity period has not ended; the history
// window applies to authoredOn.

define function MedicationRequestHasCode(M MedicationRequest, conceptCode String):
  exists(((M.medication as FHIR.CodeableConcept).coding) C where C.code = conceptCode)
    or exists(
      [Medication] Med
        where (M.medication as FHIR.Reference).reference = 'Medication/' + Med.id
          and exists(Med.code.coding C where C.code = conceptCode)
    )

define function MedicationRequestCode(M MedicationRequest):
  Coalesce(
    First((M.medication as FHIR.CodeableConcept).coding).code.value,
    First(
      First([Medication] Med where (M.medication as FHIR.Reference).reference = 'Medication/' + Med.id).code.coding
    ).code.value
  )

define function IsOpenMedicationRequest(M MedicationRequest):
  M.status = 'active'
    and (
      M.dispenseRequest.validityPeriod.end is null
        or M.dispenseRequest.validityPeriod.end.value >= Now()
    )

define function GetEncounterOpenMedicationRequests():
  if encounterid is null then {} as List<MedicationRequest>
  else
    [MedicationRequest] M
      where IsOpenMedicationRequest(M)
        and M.encounter.reference = 'Encounter/' + encounterid

define function GetEncounterMedicationRequests(code String):
  (GetEncounterOpenMedicationRequests()) M where MedicationRequestHasCode(M, code)

define function GetEncounterMedicationRequestValue(code String):
  exists(GetEncounterMedicationRequests(code))

define function GetOpenMedicationRequestsSince(since DateTime):
  [MedicationRequest] M
    where IsOpenMedicationRequest(M)
      and (since is null or M.authoredOn.value >= since)

define function GetActiveMedicationRequests(code String, since DateTime):
  (GetOpenMedicationRequestsSince(since)) M where MedicationRequestHasCode(M, code)

define function GetActiveMedicationRequest(code String, since DateTime):
  First((GetActiveMedicationRequests(code, since)) M sort by authoredOn.value desc)

// ActiveDrugs: the drug codes of the open prescriptions, space-separated like an XLSForm
// select_multiple answer; null when there is none.
define function GetEncounterMedicationCodes():
  Combine(distinct((GetEncounterOpenMedicationRequests()) M return MedicationRequestCode(M)), ' ')

define function GetActiveMedicationCodesSince(since DateTime):
  Combine(distinct((GetOpenMedicationRequestsSince(since)) M return MedicationRequestCode(M)), ' ')

// OpenDosage: the code of a coded dosageInstruction.doseAndRate type, else the dosage text.
define function MedicationRequestDosage(M MedicationRequest):
  Coalesce(
    First(First(M.dosageInstruction).doseAndRate.type.coding).code.value,
    First(M.dosageInstruction).text.value
  )

define function GetEncounterMedicationDosage(code String):
  MedicationRequestDosage(First((GetEncounterMedicationRequests(code)) M sort by authoredOn.value desc))

define function GetMedicationDosageSince(code String, since DateTime):
  MedicationRequestDosage(GetActiveMedicationRequest(code, since))

// LatestDate: when the drug was last prescribed (authoredOn), open or not; a cancelled,
// entered-in-error or draft request was never prescribed.
define function IsPrescribedMedicationRequest(M MedicationRequest):
  not (M.status in {'cancelled', 'entered-in-error', 'draft'})

define function GetEncounterMedicationRequestDate(code String):
  if encounterid is null then null as DateTime
  else
    Max(
      (
        [MedicationRequest] M
          where IsPrescribedMedicationRequest(M)
            and MedicationRequestHasCode(M, code)
            and M.encounter.reference = 'Encounter/' + encounterid
          return M.authoredOn.value
      )
    )

// MedicationDispense: a completed dispense of the drug (context = the encounter); the
// history window and the date are whenHandedOver.
define function MedicationDispenseHasCode(D MedicationDispense, conceptCode String):
  exists(((D.medication as FHIR.CodeableConcept).coding) C where C.code = conceptCode)
    or exists(
      [Medication] Med
        where (D.medication as FHIR.Reference).reference = 'Medication/' + Med.id
          and exists(Med.code.coding C where C.code = conceptCode)
    )

define function GetEncounterMedicationDispenses(code String):
  if encounterid is null then {} as List<MedicationDispense>
  else
    [MedicationDispense] D
      where D.status = 'completed'
        and MedicationDispenseHasCode(D, code)
        and D.context.reference = 'Encounter/' + encounterid

define function GetMedicationDispenses(code String, since DateTime):
  [MedicationDispense] D
    where D.status = 'completed'
      and MedicationDispenseHasCode(D, code)
      and (since is null or D.whenHandedOver.value >= since)

define function GetEncounterMedicationDispenseDate(code String):
  Max((GetEncounterMedicationDispenses(code)) D return D.whenHandedOver.value)

define function GetLastMedicationDispenseDate(code String, since DateTime):
  Max((GetMedicationDispenses(code, since)) D return D.whenHandedOver.value)

define function GetMedicationRequestDate(code String, since DateTime):
  Max(
    (
      [MedicationRequest] M
        where IsPrescribedMedicationRequest(M)
          and MedicationRequestHasCode(M, code)
        return M.authoredOn.value
    ) D
      where since is null or D >= since
  )
"""


# ── Project retrievals (feature/20261109-project-retrievals.md) ──────────────────────
# One Helper define per used retrieval, named by its code ("#age_months"). Patient
# functions reuse the defines context=patient populate nodes read; encounter / history
# functions the Observation / Condition accessors, with the period as a lookback window.

#: patient function -> CQL (Helper library, unqualified)
RETRIEVAL_PATIENT_CQL = {
    "AgeInDays": "AgeInDays",
    "AgeInWeeks": "CalculateAgeInWeeks(PatientBirthDate)",
    "AgeInMonths": "AgeInMonths",
    "AgeInYears": "AgeInYears",
    "DateOfBirth": "PatientBirthDate",
    "Sex": "PatientGender",
    "DeceasedDateTime": "(PatientRecord.deceased as FHIR.dateTime).value",
    "FullName": (
        "Combine((First(PatientRecord.name).given) G return G.value, ' ')"
        " & ' ' & First(PatientRecord.name).family.value"
    ),
    "FirstName": "First(First(PatientRecord.name).given).value",
    "MiddleName": "First(Skip(First(PatientRecord.name).given, 1)).value",
    "LastName": "First(PatientRecord.name).family.value",
    "Telecom": "First(PatientRecord.telecom).value.value",
    "Photo": "First(PatientRecord.photo).url.value",
}
#: master-data function -> Helper accessor taking the concept code
RETRIEVAL_VALUE_CQL = {
    "FacilityValue": "GetFacilityValue",
    "PractitionerValue": "GetPractitionerValue",
    "LocationValue": "GetLocationValue",
}
# TRICC data type -> (Questionnaire item type the Observation value is read as, CQL type)
_RETRIEVAL_VALUE_TYPES = {
    "integer": ("integer", "integer"),
    "decimal": ("decimal", "decimal"),
    "quantity": ("decimal", "decimal"),
    "boolean": ("boolean", "boolean"),
    "date": ("date", "date"),
    "coded": ("string", "string"),
    "string": ("string", "string"),
    "text": ("string", "string"),
}


#: (FHIR resource, context, catalogue function) -> Helper CQL, ``{code}`` the concept code and
#: ``{since}`` the start of the history window (``null``: no window). A resource missing here is
#: read as an Observation (the historical fallback); a function missing for a known resource is
#: unsupported. ``Latest`` of an Observation is converted to the value type
#: (``_retrieval_observation_value``).
_TIMED_CQL = {
    ("Observation", ENCOUNTER_CONTEXT): {
        "Latest": "GetEncounterObservationValue('{code}', null, null)",
        "Exists": "exists(GetObservations('{code}'))",
        "Count": "Count(GetObservations('{code}'))",
        "LatestDate": "GetEncounterObservationTime('{code}')",
    },
    ("Observation", HISTORY_CONTEXT): {
        "Latest": "GetHistoryObservationValueSince('{code}', {since}, 1, null)",
        "Exists": "GetHistoryObservationSince('{code}', {since}, 1, null) is not null",
        "Count": (
            "Count([Observation] O where ObservationHasCode(O, '{code}')"
            " and O.status in {{'final', 'amended', 'corrected'}}"
            " and ({since} is null or (O.effective as FHIR.dateTime).value >= {since}))"
        ),
        "LatestDate": "LatestObservationTime('{code}', {since})",
    },
    ("Condition", ENCOUNTER_CONTEXT): {
        "Latest": "GetEncounterConditionValue('{code}')",
        "Exists": "GetConditionValue('{code}')",
        "Count": "Count(GetActiveConditions('{code}'))",
        "LatestDate": "GetEncounterConditionDate('{code}')",
    },
    ("Condition", HISTORY_CONTEXT): {
        "Latest": "GetHistoryConditionValue('{code}')",
        "Exists": "GetHistoryConditionValue('{code}')",
        "Count": (
            "Count([Condition] C where ConditionHasCode(C, '{code}')"
            " and ConditionVerificationCode(C) != 'refuted'"
            " and ConditionVerificationCode(C) != 'entered-in-error')"
        ),
        "LatestDate": "GetHistoryConditionDate('{code}', {since})",
    },
    # done: completed and not Unsuccessful (#74); Latest is "done", like Exists
    ("Procedure", ENCOUNTER_CONTEXT): {
        "Latest": "GetEncounterProcedureValue('{code}', null)",
        "Exists": "GetEncounterProcedureValue('{code}', null)",
        "Count": "Count(GetProcedures('{code}'))",
        "LatestDate": "GetEncounterProcedureDate('{code}')",
    },
    ("Procedure", HISTORY_CONTEXT): {
        "Latest": "GetHistoryProcedureDate('{code}', {since}) is not null",
        "Exists": "GetHistoryProcedureDate('{code}', {since}) is not null",
        "Count": "Count(GetHistoryProcedures('{code}', {since}))",
        "LatestDate": "GetHistoryProcedureDate('{code}', {since})",
    },
    # open prescriptions (feature/20261125-populate-medication.md); Latest is "on treatment"
    ("MedicationRequest", ENCOUNTER_CONTEXT): {
        "Latest": "{on_treatment_encounter}",
        "Exists": "{on_treatment_encounter}",
        "Count": "Count(GetEncounterMedicationRequests('{code}'))",
        "ActiveDrugs": "GetEncounterMedicationCodes()",
        "OpenDosage": "GetEncounterMedicationDosage('{code}')",
        "LatestDate": "GetEncounterMedicationRequestDate('{code}')",
    },
    ("MedicationRequest", HISTORY_CONTEXT): {
        "Latest": "{on_treatment_history}",
        "Exists": "{on_treatment_history}",
        "Count": "Count(GetActiveMedicationRequests('{code}', {since}))",
        "ActiveDrugs": "GetActiveMedicationCodesSince({since})",
        "OpenDosage": "GetMedicationDosageSince('{code}', {since})",
        "LatestDate": "GetMedicationRequestDate('{code}', {since})",
    },
    # completed dispenses (feature/20261125-populate-medication.md phase 3)
    ("MedicationDispense", ENCOUNTER_CONTEXT): {
        "Latest": "exists(GetEncounterMedicationDispenses('{code}'))",
        "Exists": "exists(GetEncounterMedicationDispenses('{code}'))",
        "Count": "Count(GetEncounterMedicationDispenses('{code}'))",
        "LatestDate": "GetEncounterMedicationDispenseDate('{code}')",
    },
    ("MedicationDispense", HISTORY_CONTEXT): {
        "Latest": "exists(GetMedicationDispenses('{code}', {since}))",
        "Exists": "exists(GetMedicationDispenses('{code}', {since}))",
        "Count": "Count(GetMedicationDispenses('{code}', {since}))",
        "LatestDate": "GetLastMedicationDispenseDate('{code}', {since})",
    },
}
#: "on treatment": an open prescription, or else a completed dispense (decision 2026-11-25)
_ON_TREATMENT = {
    "on_treatment_encounter": (
        "GetEncounterMedicationRequestValue('{code}') or exists(GetEncounterMedicationDispenses('{code}'))"
    ),
    "on_treatment_history": (
        "exists(GetActiveMedicationRequests('{code}', {since})) or exists(GetMedicationDispenses('{code}', {since}))"
    ),
}


def retrieval_cql_type(retrieval) -> Optional[str]:
    """CQL result type of a retrieval's define, or None when unknown (custom, dateTime)."""
    if retrieval.effective_function is None:
        return None
    return _RETRIEVAL_VALUE_TYPES.get(retrieval.value_type or "string", (None, None))[1]


def _retrieval_observation_value(retrieval, accessor: str) -> str:
    """An Observation value accessor converted to the retrieval's value type."""
    from tricc_oo.converters.fhir.cql_value import wrap_cql_for_item_type

    item_type = _RETRIEVAL_VALUE_TYPES.get(retrieval.value_type or "string", ("string", None))[0]
    return wrap_cql_for_item_type(accessor, item_type, qualified=False)


def retrieval_cql_expression(retrieval, strategy: str = "FHIRStrategy") -> str:
    """CQL body of a retrieval's Helper define (catalogue mapping).

    Args:
        retrieval: A ``tricc_oo.converters.retrieval.Retrieval``.
        strategy: Strategy name, for errors.

    Returns:
        The CQL expression, unqualified (it lives in the Helper library).

    Raises:
        TriccRetrievalError: No mapping for the function, or a custom retrieval without a
            ``text/cql`` expression.
    """
    from tricc_oo.converters.fhir.concept_mapper import get_fhir_resource
    from tricc_oo.converters.retrieval import CQL_LANGUAGE, custom_expression, unsupported

    function = retrieval.effective_function
    if function is None:
        return custom_expression(retrieval, CQL_LANGUAGE, strategy)
    code = (retrieval.reads_code or "").replace("'", "\\'")
    if function in RETRIEVAL_PATIENT_CQL:
        return RETRIEVAL_PATIENT_CQL[function]
    if function == "PatientValue":
        field = PATIENT_FIELDS.get(code.lower())
        if field:
            return field[0]
        logger.warning(
            f"retrieval {retrieval.code}: patient concept '{code}' is not a supported Patient field "
            f"({', '.join(sorted(PATIENT_FIELDS))}); it stays empty"
        )
        return f"GetPatientValue('{code}')"
    if function in RETRIEVAL_VALUE_CQL:
        return f"{RETRIEVAL_VALUE_CQL[function]}('{code}')"
    resource, _, _ = get_fhir_resource(retrieval.reads_concept_type, None)
    if (resource, retrieval.context) not in _TIMED_CQL:
        resource = "Observation"
    templates = _TIMED_CQL.get((resource, retrieval.context), {})
    if function not in templates:
        raise unsupported(retrieval, strategy)
    since = None
    if retrieval.context == HISTORY_CONTEXT and retrieval.period:
        since = cql_lookback_start(retrieval.period)
        if since is None:
            logger.warning(
                f"retrieval {retrieval.code}: period '{retrieval.period}' is not a date-only ISO duration; "
                "reading without a window"
            )
    template = templates[function]
    for name, value in _ON_TREATMENT.items():
        template = template.replace("{" + name + "}", value)
    expression = template.format(code=code, since=since or "null")
    if resource == "Observation" and function == "Latest":
        return _retrieval_observation_value(retrieval, expression)
    return expression


def retrieval_cql_defines(retrievals, strategy: str = "FHIRStrategy") -> str:
    """The Helper defines of the used retrievals (empty when there is none)."""
    defines = [
        f'define "{retrieval.code}":\n  {retrieval_cql_expression(retrieval, strategy)}'
        for retrieval in retrievals
    ]
    if not defines:
        return ""
    header = "// ── Project retrievals (feature/20261109-project-retrievals.md) ─────────────"
    return header + "\n\n" + "\n\n".join(defines) + "\n"
