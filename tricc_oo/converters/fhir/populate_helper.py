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


def resolve_populate_reference(node: "TriccNodePopulate", qualified: bool = False) -> str:
    """Return author-facing CQL accessor for a populate node (*Value helpers only)."""
    prefix = "Helper." if qualified else ""
    code = (node.name or "").replace("'", "\\'")
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
    if ctx == ENCOUNTER_CONTEXT:
        return (
            f"{prefix}GetEncounterValue('{code}', {repeat_arg}, "
            f"{_cql_string_literal(node.period)})"
        )
    if ctx == HISTORY_CONTEXT:
        period = node.period or DEFAULT_HISTORY_PERIOD
        return (
            f"{prefix}GetHistoryObservationValue("
            f"'{code}', {_cql_string_literal(period)}, 1, {repeat_arg})"
        )
    return f"{prefix}GetPatientValue('{code}')"


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

define function GetEncounterValue(code String, repeatIndex Integer, period String):
  if repeatIndex is null or repeatIndex = 1 then GetObservationValue(code)
  else GetRepeatedValue(code, repeatIndex)
"""

