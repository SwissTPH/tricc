"""
Item-typed results for CQL ``initialExpression`` defines.

fhircore evaluates a Questionnaire's CQL ``initialExpression``s and copies each result into
``item.initial`` as is. The Android SDK rejects an answer whose type differs from the item
type (``Mismatching question type STRING and answer type date``), and the whole form then
fails to load. Helper accessors return ``Observation.value[x]`` — a choice type whose runtime
type depends on what was stored — so every define attached to an item is converted to that
item's type here. See fix/20260929-cql-initial-expression-on-device.md.
"""

from __future__ import annotations

import re
from typing import Optional

# Observation.value[x] in FHIR R4 (the result type of every Observation-value accessor).
_OBSERVATION_VALUE_CHOICE = (
    "Choice<FHIR.Quantity, FHIR.CodeableConcept, FHIR.string, FHIR.boolean, FHIR.integer, "
    "FHIR.Range, FHIR.Ratio, FHIR.SampledData, FHIR.time, FHIR.dateTime, FHIR.Period>"
)

# Helper functions returning Observation.value[x].
OBSERVATION_VALUE_ACCESSORS = (
    "GetObservationValue",
    "GetRepeatedValue",
    "GetHistoryObservationValue",
    "GetHistoryObservationValueSince",
    "GetEncounterObservationValue",
    "GetEncounterValue",
)

# Questionnaire item type -> Helper conversion function for an Observation value.
VALUE_CONVERSION_BY_ITEM_TYPE = {
    "string": "ValueAsString",
    "text": "ValueAsString",
    "decimal": "ValueAsDecimal",
    "integer": "ValueAsInteger",
    "boolean": "ValueAsBoolean",
    "date": "ValueAsDate",
    "choice": "ValueAsCoding",
    "open-choice": "ValueAsCoding",
}

_ACCESSOR_CALL = re.compile(
    r"^(?:Helper\.)?(?:" + "|".join(OBSERVATION_VALUE_ACCESSORS) + r")\(.*\)$",
    re.DOTALL,
)


def _is_single_call(expr: str) -> bool:
    """True when ``expr`` is one call whose opening parenthesis closes at the very end."""
    start = expr.find("(")
    if start < 0 or not expr.endswith(")"):
        return False
    depth = 0
    in_string = False
    for index in range(start, len(expr)):
        char = expr[index]
        if char == "'" and (index == 0 or expr[index - 1] != "\\"):
            in_string = not in_string
        elif not in_string and char == "(":
            depth += 1
        elif not in_string and char == ")":
            depth -= 1
            if depth == 0:
                return index == len(expr) - 1
    return False


def is_observation_value_accessor(expr: str) -> bool:
    """True when ``expr`` is a single Helper call returning ``Observation.value[x]``.

    Args:
        expr: CQL expression text.

    Returns:
        Whether the expression's result is the Observation value choice type.
    """
    expr = (expr or "").strip()
    return bool(_ACCESSOR_CALL.match(expr)) and _is_single_call(expr)


# Known non-text result types of a non-accessor expression that ``ToString`` accepts.
_TO_STRING_SOURCE_TYPES = ("boolean", "integer", "decimal", "date")


def wrap_cql_for_item_type(
    expr: str,
    item_type: Optional[str],
    qualified: bool = True,
    source_type: Optional[str] = None,
) -> str:
    """Convert a define's CQL expression to the Questionnaire item's answer type.

    Observation-value accessors go through the Helper ``ValueAs*`` function for the item
    type (``null`` when the stored value cannot be that type). Any other expression is a
    system type: it is converted only when that type is known (``source_type``) and differs
    from the item's — ``ToString`` for a text item, ``ToDecimal`` for an integer read into a
    decimal item. CQL has no ``ToString(String)``, so an expression of unknown type is left
    as is.

    Args:
        expr: CQL expression text.
        item_type: Questionnaire ``item.type`` the result is copied into.
        qualified: Prefix Helper functions with ``Helper.`` (segment libraries).
        source_type: Known result type of a non-accessor expression (``boolean``,
            ``integer``, ``decimal``, ``date``), or None when unknown.

    Returns:
        CQL expression whose result type matches ``item_type``.
    """
    expr = (expr or "").strip()
    if not expr or expr == "null" or not item_type:
        return expr
    if is_observation_value_accessor(expr):
        func = VALUE_CONVERSION_BY_ITEM_TYPE.get(item_type)
        if func is None:
            return expr
        prefix = "Helper." if qualified else ""
        return f"{prefix}{func}({expr})"
    if item_type in ("string", "text") and source_type in _TO_STRING_SOURCE_TYPES:
        return f"ToString({expr})"
    if item_type == "decimal" and source_type == "integer":
        return f"ToDecimal({expr})"
    return expr


def cql_helper_value_block() -> str:
    """CQL ``ValueAs*`` functions converting ``Observation.value[x]`` (Helper library)."""
    choice = _OBSERVATION_VALUE_CHOICE
    return f"""\
// ── Value conversion ─────────────────────────────────────────────────────────
// Observation.value[x] -> the Questionnaire item's answer type; null when the stored
// value cannot be that type. fhircore copies an initialExpression result into
// item.initial unchanged, and a mismatched type makes the form fail to load.
// See fix/20260929-cql-initial-expression-on-device.md.

define function ValueAsString(v {choice}):
  case
    when v is FHIR.string then (v as FHIR.string).value
    when v is FHIR.Quantity then ToString((v as FHIR.Quantity).value.value)
    when v is FHIR.integer then ToString((v as FHIR.integer).value)
    when v is FHIR.boolean then ToString((v as FHIR.boolean).value)
    when v is FHIR.dateTime then ToString((v as FHIR.dateTime).value)
    when v is FHIR.CodeableConcept then First((v as FHIR.CodeableConcept).coding.code).value
    else null as String
  end

define function ValueAsDecimal(v {choice}):
  case
    when v is FHIR.Quantity then (v as FHIR.Quantity).value.value
    when v is FHIR.integer then ToDecimal((v as FHIR.integer).value)
    when v is FHIR.string then ToDecimal((v as FHIR.string).value)
    else null as Decimal
  end

define function ValueAsInteger(v {choice}):
  case
    when v is FHIR.integer then (v as FHIR.integer).value
    when v is FHIR.Quantity then Truncate((v as FHIR.Quantity).value.value)
    when v is FHIR.string then ToInteger((v as FHIR.string).value)
    else null as Integer
  end

define function ValueAsBoolean(v {choice}):
  case
    when v is FHIR.boolean then (v as FHIR.boolean).value
    else null as Boolean
  end

define function ValueAsDate(v {choice}):
  case
    when v is FHIR.dateTime then date from (v as FHIR.dateTime).value
    when v is FHIR.string then ToDate((v as FHIR.string).value)
    else null as Date
  end

define function ValueAsCoding(v {choice}):
  First((v as FHIR.CodeableConcept).coding)
"""
