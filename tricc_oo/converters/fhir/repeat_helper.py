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


def fml_repeat_extension_rule(link_id: str, repeat: int) -> str:
    """FML comment/rule fragment documenting repeat index for StructureMap authors."""
    return (
        f"  // {link_id}: set Observation.extension "
        f"({TRICC_OBSERVATION_REPEAT_EXT}) = {repeat}\n"
    )


def cql_helper_repeat_block(fhir_version: str = "4.0.1") -> str:
    """CQL definitions for repeat-aware Observation access (included in Helper library)."""
    return f"""\
// ── Repeat index helpers ─────────────────────────────────────────────────────
// Extension URL: {TRICC_OBSERVATION_REPEAT_EXT}

define function GetObservations(code String):
  [Observation: Code code from "http://snomed.info/sct"] O
    where O.status in {{'final', 'amended', 'corrected'}}

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

define function GetHistory(
  code String,
  period String,
  reverseOrderPosition Integer,
  repeatIndex Integer
):
  First(
    (
      GetObservations(code) O
        where (
          repeatIndex is null
          or ObservationRepeatIndex(O) = repeatIndex
          or (repeatIndex = 1 and ObservationRepeatIndex(O) is null)
        )
        sort by effective desc
    ) O
      skip reverseOrderPosition - 1
      take 1
  )

define function GetHistoryValue(
  code String,
  period String,
  reverseOrderPosition Integer,
  repeatIndex Integer
):
  GetHistory(code, period, reverseOrderPosition, repeatIndex).value
"""