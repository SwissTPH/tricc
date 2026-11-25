"""
Concept repeat support for FHIR / CQL export.

Repeat index is stored as an extension on extracted Observations and declared on
Questionnaire items when repeat != 1 (default slot).
"""

from __future__ import annotations

from typing import Optional, Union

from tricc_oo.models.base import get_repeat

# Extension URLs (TRICC namespace — replace with project-specific canonical when published)
TRICC_OBSERVATION_REPEAT_EXT = "https://fhir.tricc.io/StructureDefinition/observation-repeat-index"
TRICC_QUESTIONNAIRE_REPEAT_EXT = "https://fhir.tricc.io/StructureDefinition/questionnaire-concept-repeat"


def build_questionnaire_repeat_extension(repeat: int) -> dict:
    """SDC-compatible extension marking the concept capture slot on a Questionnaire item."""
    return {
        "url": TRICC_QUESTIONNAIRE_REPEAT_EXT,
        "valueInteger": int(repeat),
    }


def build_observation_repeat_extension(repeat: int) -> dict:
    """Extension persisted on extracted Observation resources."""
    return {
        "url": TRICC_OBSERVATION_REPEAT_EXT,
        "valueInteger": int(repeat),
    }


def should_emit_repeat_metadata(node) -> bool:
    """Return True when repeat should be emitted on FHIR artifacts (repeat != 1)."""
    return get_repeat(node) != 1


def get_observation_cql_accessor(code: str, repeat: Optional[int] = None) -> str:
    """Return a CQL expression reading an Observation value for code + repeat slot.

    Args:
        code: Concept / observation code string.
        repeat: Repeat index; None or 1 uses GetObservationValue (default slot).

    Returns:
        CQL expression delegating to the Helper library.
    """
    safe_code = code.replace("'", "\\'")
    slot = 1 if repeat is None else int(repeat)
    if slot == 1:
        return f"Helper.GetObservationValue('{safe_code}')"
    return f"Helper.GetRepeatedValue('{safe_code}', {slot})"


def get_observation_cql_accessor_for_node(node) -> str:
    """Build Helper CQL accessor for a TRICC node with a concept name."""
    code = getattr(node, "name", None) or ""
    return get_observation_cql_accessor(code, get_repeat(node))


def fml_repeat_extension_rule(link_id: str, content_type: str, repeat: int) -> str:
    """Executable FML rule that stamps the repeat-index extension onto the target resource.

    Without this, ``ObservationRepeatIndex``/``GetRepeated*``/``GetNumberOfRepeat`` (the CQL
    read side) have nothing to match against — extracted Observations would carry no
    repeat-slot marker at all. Appended after the field-mapping rule for *link_id* in the
    same ``map`` block (see ``FHIRStrategy.generate_export``).
    """
    return (
        f"  {link_id} -> {content_type}.extension as ext then {{\n"
        f"    ext.url = '{TRICC_OBSERVATION_REPEAT_EXT}';\n"
        f"    ext.value = {int(repeat)};\n"
        f'  }} "{link_id}_repeat_ext";\n'
    )


def fml_repeat_extension_on_target(target_var: str, repeat: int, rule_name: str) -> str:
    """FML fragment that stamps the repeat-index extension inside an Observation group.

    Used by the QuestionnaireResponse → Bundle extraction StructureMap (nested
    ``create('Observation') as obs`` block).
    """
    return (
        f"      src -> {target_var}.extension as ext then {{\n"
        f"        src -> ext.url = '{TRICC_OBSERVATION_REPEAT_EXT}' \"url\";\n"
        f"        src -> ext.valueInteger = {int(repeat)} \"slot\";\n"
        f'      }} "{rule_name}_repeat";\n'
    )


def cql_helper_repeat_block(fhir_version: str = "4.0.1") -> str:
    """CQL definitions for repeat-aware Observation/Condition access (Helper library).

    ``GetObservation*``/``GetCondition*`` are scoped to the **current encounter**
    (``encounterid`` parameter, populated by the client at ``$populate`` time — null on
    a visit's first process, which is expected: nothing has been recorded yet this
    encounter). ``GetHistoryObservation*``/``GetHistoryCondition*`` are the deliberate
    any-time/"outside the encounter" lookback, unscoped by ``encounterid``, used by the
    ``history`` populate context. See feature/20260812-intervention-order-and-dedup.md.

    Concepts are matched by **code alone, across any system**: the write side resolves a
    concept's system per concept (``structuremap._concept_system_url``), so one project
    spreads codes over several CodeSystems and a single declared code system on the read
    side matches nothing. See fix/20260914-cql-retrieve-codesystem.md.

    Every construct must be accepted by cql-to-elm 3.12.0 (the translator fhircore ships):
    function-call query sources are parenthesised, sorts use comparable system values,
    and "Nth most recent" is ``First(Skip(...))``. See
    fix/20260929-cql-initial-expression-on-device.md.
    """
    return f"""\
// ── Repeat / current-encounter helpers ────────────────────────────────────────
// Extension URL: {TRICC_OBSERVATION_REPEAT_EXT}

// Concept codes are matched across any code system: a project's concepts are spread
// over several CodeSystems (tricc, sym, calculate, …) and extraction stamps whichever
// one owns the concept, so filtering the retrieve on one declared system matches
// nothing. See fix/20260914-cql-retrieve-codesystem.md.

define function ObservationHasCode(O Observation, conceptCode String):
  exists(O.code.coding C where C.code = conceptCode)

define function ConditionHasCode(C Condition, conceptCode String):
  exists(C.code.coding CC where CC.code = conceptCode)

// One retrieve per resource and scope: every function below reads these defines, which
// the engine evaluates once (a define is cached, a function call with arguments is not).
// See feature/20261125-requires-and-implied-retrievals.md §4.
define "HistoryObservations":
  [Observation] O where O.status in {{'final', 'amended', 'corrected'}}

define "EncounterObservations":
  if encounterid is null then {{}} as List<Observation>
  else
    ("HistoryObservations") O
      where O.encounter.reference = 'Encounter/' + encounterid

define "HistoryConditions":
  [Condition]

define "EncounterConditions":
  if encounterid is null then {{}} as List<Condition>
  else
    ("HistoryConditions") C
      where C.encounter.reference = 'Encounter/' + encounterid

define function GetObservations(code String):
  ("EncounterObservations") O where ObservationHasCode(O, code)

define function ObservationRepeatIndex(O Observation):
  singleton from (
    O.extension E
      where E.url = '{TRICC_OBSERVATION_REPEAT_EXT}'
      return FHIRHelpers.ToInteger(E.value as FHIR.integer)
  )

define function GetObservation(code String):
  First(
    (GetObservations(code)) O
      where ObservationRepeatIndex(O) is null or ObservationRepeatIndex(O) = 1
      sort by (effective as FHIR.dateTime).value desc
  )

define function GetRepeated(code String, repeatIndex Integer):
  First(
    (GetObservations(code)) O
      where ObservationRepeatIndex(O) = repeatIndex
      sort by (effective as FHIR.dateTime).value desc
  )

define function GetObservationValue(code String):
  GetObservation(code).value

define function GetRepeatedValue(code String, repeatIndex Integer):
  GetRepeated(code, repeatIndex).value

define function GetNumberOfRepeat(code String):
  Count(
    distinct(
      (GetObservations(code)) O
        return ObservationRepeatIndex(O)
    )
  )

define function GetHistoryObservation(
  code String,
  period String,
  reverseOrderPosition Integer,
  repeatIndex Integer
):
  First(
    Skip(
      (
        ("HistoryObservations") O
          where ObservationHasCode(O, code)
          and (
            repeatIndex is null
            or ObservationRepeatIndex(O) = repeatIndex
            or (repeatIndex = 1 and ObservationRepeatIndex(O) is null)
          )
          sort by (effective as FHIR.dateTime).value desc
      ),
      Coalesce(reverseOrderPosition, 1) - 1
    )
  )

define function GetHistoryObservationValue(
  code String,
  period String,
  reverseOrderPosition Integer,
  repeatIndex Integer
):
  GetHistoryObservation(code, period, reverseOrderPosition, repeatIndex).value

// Same lookback, restricted to Observations effective on or after `since` (null: no
// window). `period` above is kept for previously generated libraries and is ignored.
// See feature/20260929-cql-populate-wiring.md §4.
define function GetHistoryObservationSince(
  code String,
  since DateTime,
  reverseOrderPosition Integer,
  repeatIndex Integer
):
  First(
    Skip(
      (
        ("HistoryObservations") O
          where ObservationHasCode(O, code)
          and (since is null or (O.effective as FHIR.dateTime).value >= since)
          and (
            repeatIndex is null
            or ObservationRepeatIndex(O) = repeatIndex
            or (repeatIndex = 1 and ObservationRepeatIndex(O) is null)
          )
          sort by (effective as FHIR.dateTime).value desc
      ),
      Coalesce(reverseOrderPosition, 1) - 1
    )
  )

define function GetHistoryObservationValueSince(
  code String,
  since DateTime,
  reverseOrderPosition Integer,
  repeatIndex Integer
):
  GetHistoryObservationSince(code, since, reverseOrderPosition, repeatIndex).value

// Multi-select carry: a select_multiple answer is extracted as one Observation per ticked
// option (same code, same effective time). Returns all option codes of the most recent
// answer within the window, space-separated like an XLSForm select_multiple; null if none.
// See feature/20260929-cql-populate-wiring.md §10.
define function LatestObservationTime(code String, since DateTime):
  (GetHistoryObservationSince(code, since, 1, null).effective as FHIR.dateTime).value

// Time of the latest Observation of `code` in the current encounter (LatestDate
// retrieval, feature/20261125-populate-read-date.md).
define function GetEncounterObservationTime(code String):
  Max((GetObservations(code)) O return (O.effective as FHIR.dateTime).value)

define function GetHistoryObservationCodesSince(code String, since DateTime):
  Combine(
    distinct(
      (
        ("HistoryObservations") O
          where ObservationHasCode(O, code)
            and (O.effective as FHIR.dateTime).value = LatestObservationTime(code, since)
          return First((O.value as FHIR.CodeableConcept).coding.code).value
      )
    ),
    ' '
  )

// ── Condition family (same current-encounter / history split; no repeat index —
// Condition entries aren't repeated within one encounter the way vitals are) ──

define function GetConditions(code String):
  ("EncounterConditions") C where ConditionHasCode(C, code)

define function ConditionVerificationCode(C Condition):
  First(C.verificationStatus.coding.code)

define function GetActiveConditions(code String):
  (GetConditions(code)) C
    where ConditionVerificationCode(C) != 'refuted'
      and ConditionVerificationCode(C) != 'entered-in-error'

define function GetCondition(code String):
  First((GetActiveConditions(code)) C sort by recordedDate.value desc)

define function GetConditionValue(code String):
  exists(GetActiveConditions(code))

define function HasProvisionalCondition(code String):
  exists((GetConditions(code)) C where ConditionVerificationCode(C) = 'provisional')

define function HasConfirmedCondition(code String):
  exists((GetConditions(code)) C where ConditionVerificationCode(C) = 'confirmed')

define function HasRefutedCondition(code String):
  exists((GetConditions(code)) C where ConditionVerificationCode(C) = 'refuted')

define function GetHistoryCondition(code String):
  First(
    ("HistoryConditions") C
      where ConditionHasCode(C, code)
        and First(C.verificationStatus.coding.code) != 'refuted'
        and First(C.verificationStatus.coding.code) != 'entered-in-error'
      sort by recordedDate.value desc
  )

define function GetHistoryConditionValue(code String):
  GetHistoryCondition(code) is not null

// Date of a Condition: its onset, falling back to recordedDate (LatestDate retrieval,
// feature/20261125-populate-read-date.md). The latest date is the Max, nulls ignored.
define function ConditionDate(C Condition):
  Coalesce((C.onset as FHIR.dateTime).value, C.recordedDate.value)

define function GetEncounterConditionDate(code String):
  Max((GetActiveConditions(code)) C return ConditionDate(C))

define function GetHistoryConditionDate(code String, since DateTime):
  Max(
    (
      ("HistoryConditions") C
        where ConditionHasCode(C, code)
          and ConditionVerificationCode(C) != 'refuted'
          and ConditionVerificationCode(C) != 'entered-in-error'
        return ConditionDate(C)
    ) D
      where since is null or D >= since
  )

// ── Procedure family (#74; an activity done, feature/20261117-activity-procedure-dedup.md).
// A Procedure counts only when completed and its outcome is not Unsuccessful
// (SNOMED 385671000, matched by code across any system like every code here); a missing
// outcome counts. The repeat slot uses the Observation repeat extension. ──

define function ProcedureHasCode(P Procedure, conceptCode String):
  exists(P.code.coding C where C.code = conceptCode)

define function IsDoneProcedure(P Procedure):
  P.status = 'completed'
    and not exists(P.outcome.coding O where O.code = '385671000')

define function ProcedureRepeatIndex(P Procedure):
  singleton from (
    P.extension E
      where E.url = '{TRICC_OBSERVATION_REPEAT_EXT}'
      return FHIRHelpers.ToInteger(E.value as FHIR.integer)
  )

define "HistoryProcedures":
  [Procedure] P where IsDoneProcedure(P)

define "EncounterProcedures":
  if encounterid is null then {{}} as List<Procedure>
  else
    ("HistoryProcedures") P
      where P.encounter.reference = 'Encounter/' + encounterid

define function GetProcedures(code String):
  ("EncounterProcedures") P where ProcedureHasCode(P, code)

define function GetEncounterProcedureValue(code String, repeatIndex Integer):
  exists(
    (GetProcedures(code)) P
      where Coalesce(ProcedureRepeatIndex(P), 1) = Coalesce(repeatIndex, 1)
  )

define function GetHistoryProcedure(code String):
  First(
    ("HistoryProcedures") P
      where ProcedureHasCode(P, code)
      sort by (performed as FHIR.dateTime).value desc
  )

define function GetHistoryProcedureDate(code String):
  date from Coalesce(
    (GetHistoryProcedure(code).performed as FHIR.dateTime).value,
    (GetHistoryProcedure(code).performed as FHIR.Period).start.value
  )

// Time a Procedure was performed (dateTime, else the start of its Period), and the latest
// one in the encounter or since a date (null: ever). LatestDate / Latest / Exists of a
// Procedure retrieval, feature/20261125-populate-read-date.md.
define function ProcedureTime(P Procedure):
  Coalesce((P.performed as FHIR.dateTime).value, (P.performed as FHIR.Period).start.value)

define function GetEncounterProcedureDate(code String):
  Max((GetProcedures(code)) P return ProcedureTime(P))

define function GetHistoryProcedures(code String, since DateTime):
  ("HistoryProcedures") P
    where ProcedureHasCode(P, code)
      and (since is null or ProcedureTime(P) >= since)

define function GetHistoryProcedureDate(code String, since DateTime):
  Max((GetHistoryProcedures(code, since)) P return ProcedureTime(P))
"""
