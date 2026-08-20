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
    """
    return f"""\
// ── Repeat / current-encounter helpers ────────────────────────────────────────
// Extension URL: {TRICC_OBSERVATION_REPEAT_EXT}

define function GetObservations(code String):
  if encounterid is null then {{}} as List<Observation>
  else
    [Observation: Code code from "http://snomed.info/sct"] O
      where O.status in {{'final', 'amended', 'corrected'}}
        and O.encounter.reference = 'Encounter/' + encounterid

define function ObservationRepeatIndex(O Observation):
  singleton from (
    O.extension.where(url = '{TRICC_OBSERVATION_REPEAT_EXT}').value as Integer
  )

define function GetObservation(code String):
  First(
    GetObservations(code) O
      where ObservationRepeatIndex(O) is null or ObservationRepeatIndex(O) = 1
      sort by effective desc
  )

define function GetRepeated(code String, repeatIndex Integer):
  First(
    GetObservations(code) O
      where ObservationRepeatIndex(O) = repeatIndex
      sort by effective desc
  )

define function GetObservationValue(code String):
  GetObservation(code).value

define function GetRepeatedValue(code String, repeatIndex Integer):
  GetRepeated(code, repeatIndex).value

define function GetNumberOfRepeat(code String):
  Count(
    distinct(
      GetObservations(code) O
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
    (
      [Observation: Code code from "http://snomed.info/sct"] O
        where O.status in {{'final', 'amended', 'corrected'}}
        and (
          repeatIndex is null
          or ObservationRepeatIndex(O) = repeatIndex
          or (repeatIndex = 1 and ObservationRepeatIndex(O) is null)
        )
        sort by effective desc
    ) O
      skip reverseOrderPosition - 1
      take 1
  )

define function GetHistoryObservationValue(
  code String,
  period String,
  reverseOrderPosition Integer,
  repeatIndex Integer
):
  GetHistoryObservation(code, period, reverseOrderPosition, repeatIndex).value

// ── Condition family (same current-encounter / history split; no repeat index —
// Condition entries aren't repeated within one encounter the way vitals are) ──

define function GetConditions(code String):
  if encounterid is null then {{}} as List<Condition>
  else
    [Condition: Code code from "http://snomed.info/sct"] C
      where C.encounter.reference = 'Encounter/' + encounterid

define function ConditionVerificationCode(C Condition):
  First(C.verificationStatus.coding.code)

define function GetActiveConditions(code String):
  GetConditions(code) C
    where ConditionVerificationCode(C) != 'refuted'
      and ConditionVerificationCode(C) != 'entered-in-error'

define function GetCondition(code String):
  First(GetActiveConditions(code) C sort by recordedDate desc)

define function GetConditionValue(code String):
  exists(GetActiveConditions(code))

define function HasProvisionalCondition(code String):
  exists(GetConditions(code) C where ConditionVerificationCode(C) = 'provisional')

define function HasConfirmedCondition(code String):
  exists(GetConditions(code) C where ConditionVerificationCode(C) = 'confirmed')

define function HasRefutedCondition(code String):
  exists(GetConditions(code) C where ConditionVerificationCode(C) = 'refuted')

define function GetHistoryCondition(code String):
  First(
    [Condition: Code code from "http://snomed.info/sct"] C
      where First(C.verificationStatus.coding.code) != 'refuted'
        and First(C.verificationStatus.coding.code) != 'entered-in-error'
      sort by recordedDate desc
  )

define function GetHistoryConditionValue(code String):
  exists(GetHistoryCondition(code))
"""
