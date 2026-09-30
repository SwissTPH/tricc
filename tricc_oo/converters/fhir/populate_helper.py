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


def resolve_populate_reference(node: "TriccNodePopulate", qualified: bool = False) -> str:
    """Return author-facing CQL accessor for a populate node (*Value helpers only)."""
    prefix = "Helper." if qualified else ""
    code = populate_source_concept(node).replace("'", "\\'")
    ctx = node.context
    repeat_arg = _repeat_cql_arg(node)

    if ctx == "patient":
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
        return (
            f"{prefix}GetEncounterObservationValue('{code}', {repeat_arg}, "
            f"{_cql_string_literal(node.period)})"
        )
    if ctx == HISTORY_CONTEXT:
        period = node.period or DEFAULT_HISTORY_PERIOD
        if target == "Condition":
            return f"{prefix}GetHistoryConditionValue('{code}')"
        since = cql_lookback_start(period)
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
"""

