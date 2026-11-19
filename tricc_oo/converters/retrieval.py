"""Project retrieval dictionary: data read before the consultation, referenced as ``"#name"``.

A project CodeSystem (tagged ``codesystem-role|retrieve``, else the tricc.yaml
``retrieve_code_system``, else ``<default>-retrieve``) holds one concept per retrieval:
code ``#name``, properties ``context``, ``function``, ``reads`` and ``period``, and for
``custom`` one ``retrieve-expression`` extension per export language.

Only the retrievals an intervention's expressions use are loaded: each becomes a
``TriccNodeRetrieval`` hung on the main page (like a library calculate), so ``"#name"``
references resolve to it, and every output strategy turns it into its own input.
See feature/20261109-project-retrievals.md.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Set

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger("default")

RETRIEVE_ROLE = "retrieve"
RETRIEVE_EXPRESSION_URL = "http://tricc.org/fhir/StructureDefinition/retrieve-expression"
CQL_LANGUAGE = "text/cql"
XLSFORM_LANGUAGE = "text/x-xlsform"
CUSTOM_CONTEXT = "custom"
RETRIEVAL_CONTEXTS = ("patient", "facility", "practitioner", "location", "encounter", "history", CUSTOM_CONTEXT)
# contexts a period applies to; elsewhere it is ignored
PERIOD_CONTEXTS = ("encounter", "history", CUSTOM_CONTEXT)
#: prefix of a retrieval's XLSForm field name
XLSFORM_PREFIX = "r_"

_PATIENT = ("patient",)
_TIMED = ("encounter", "history")

#: the function catalogue (mirror of tricc-frontend ``terminology/retrieval.ts``):
#: code -> (contexts, needs ``reads``, value type; ``source`` = the type of the concept read)
RETRIEVAL_FUNCTIONS: Dict[str, tuple] = {
    "PatientValue": (_PATIENT, True, "source"),
    "AgeInDays": (_PATIENT, False, "integer"),
    "AgeInWeeks": (_PATIENT, False, "integer"),
    "AgeInMonths": (_PATIENT, False, "integer"),
    "AgeInYears": (_PATIENT, False, "integer"),
    "DateOfBirth": (_PATIENT, False, "date"),
    "Sex": (_PATIENT, False, "coded"),
    "DeceasedDateTime": (_PATIENT, False, "dateTime"),
    "FullName": (_PATIENT, False, "string"),
    "FirstName": (_PATIENT, False, "string"),
    "MiddleName": (_PATIENT, False, "string"),
    "LastName": (_PATIENT, False, "string"),
    "Telecom": (_PATIENT, False, "string"),
    "Photo": (_PATIENT, False, "string"),
    "FacilityValue": (("facility",), True, "source"),
    "PractitionerValue": (("practitioner",), True, "source"),
    "LocationValue": (("location",), True, "source"),
    "Latest": (_TIMED, True, "source"),
    "Exists": (_TIMED, True, "boolean"),
    "Count": (_TIMED, True, "integer"),
}

DEFAULT_FUNCTION = {
    "patient": "PatientValue",
    "facility": "FacilityValue",
    "practitioner": "PractitionerValue",
    "location": "LocationValue",
    "encounter": "Latest",
    "history": "Latest",
}

_CODE_RE = re.compile(r"^#[A-Za-z][A-Za-z0-9_]*$")
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(code|period)\s*\}\}")
_DURATION_RE = re.compile(
    r"^P(?!$)(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?(?:T(?=\d)(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$"
)
# ISO duration component -> (CQL singular, CQL plural, days)
_DURATION_UNITS = (
    ("year", "years", 365),
    ("month", "months", 30),
    ("week", "weeks", 7),
    ("day", "days", 1),
    ("hour", "hours", 1 / 24),
    ("minute", "minutes", 1 / 1440),
    ("second", "seconds", 1 / 86400),
)
# node fields holding expressions that may use a retrieval
_EXPRESSION_FIELDS = (
    "relevance", "expression", "expression_reference", "reference", "trigger", "applicability",
    "constraint", "default",
)


class TriccRetrievalError(ValueError):
    """A retrieval that is unknown, malformed, or that a strategy cannot export."""


class Retrieval(BaseModel):
    """One entry of the retrieval dictionary."""

    model_config = ConfigDict(extra="ignore")

    code: str
    label: Optional[str] = None
    context: str = CUSTOM_CONTEXT
    function: Optional[str] = None
    reads_code: Optional[str] = None
    reads_system: Optional[str] = None
    period: Optional[str] = None
    # language -> expression (``custom`` only)
    expressions: Dict[str, str] = {}
    # TRICC data type of the concept read (its ``dataType`` property), when known
    reads_data_type: Optional[str] = None
    # ``conceptType`` of the concept read, when known (picks the FHIR resource)
    reads_concept_type: Optional[str] = None

    @property
    def name(self) -> str:
        """The code without ``#`` (``age_months``)."""
        return self.code.lstrip("#")

    @property
    def export_name(self) -> str:
        """Name of the XLSForm field and Questionnaire item (``r_age_months``)."""
        return XLSFORM_PREFIX + self.name

    @property
    def effective_function(self) -> Optional[str]:
        """The function run: its own, else the context's default; None for ``custom``."""
        if self.context == CUSTOM_CONTEXT:
            return None
        return self.function or DEFAULT_FUNCTION.get(self.context)

    @property
    def value_type(self) -> Optional[str]:
        """TRICC data type of the value read (``integer``, ``date``, ``coded``…), or None."""
        function = self.effective_function
        entry = RETRIEVAL_FUNCTIONS.get(function) if function else None
        value_type = entry[2] if entry else "source"
        return self.reads_data_type if value_type == "source" else value_type


def _property(concept, code: str):
    return next((p for p in (concept.property or []) if getattr(p, "code", None) == code), None)


def _property_text(concept, code: str) -> Optional[str]:
    prop = _property(concept, code)
    if prop is None:
        return None
    for attr in ("valueCode", "valueString"):
        value = getattr(prop, attr, None)
        if value not in (None, ""):
            return str(value).strip()
    return None


def read_retrieval(concept) -> Retrieval:
    """The retrieval a CodeSystem concept defines.

    Args:
        concept: A ``CodeSystemConcept`` of the retrieval dictionary.

    Returns:
        The retrieval.

    Raises:
        TriccRetrievalError: When the code, context or function is not valid.
    """
    code = concept.code
    if not _CODE_RE.match(code or ""):
        raise TriccRetrievalError(f"retrieval code {code!r} must be '#' and a name (e.g. '#age_months')")
    context = (_property_text(concept, "context") or CUSTOM_CONTEXT).lower()
    if context not in RETRIEVAL_CONTEXTS:
        raise TriccRetrievalError(f"retrieval {code}: unknown context {context!r}")
    function = _property_text(concept, "function")
    if function is not None:
        entry = RETRIEVAL_FUNCTIONS.get(function)
        if entry is None:
            raise TriccRetrievalError(f"retrieval {code}: unknown function {function!r}")
        if context not in entry[0]:
            raise TriccRetrievalError(f"retrieval {code}: function {function} is not allowed in context {context}")
    reads = _property(concept, "reads")
    coding = getattr(reads, "valueCoding", None) if reads is not None else None
    expressions = {}
    for extension in concept.extension or []:
        if getattr(extension, "url", None) != RETRIEVE_EXPRESSION_URL:
            continue
        value = getattr(extension, "valueExpression", None)
        language = getattr(value, "language", None)
        if language and getattr(value, "expression", None):
            expressions[str(language)] = value.expression
    period = _property_text(concept, "period")
    if period and context not in PERIOD_CONTEXTS:
        logger.warning(f"retrieval {code}: period ignored in context {context}")
        period = None
    retrieval = Retrieval(
        code=code,
        label=concept.display,
        context=context,
        function=function,
        reads_code=getattr(coding, "code", None),
        reads_system=getattr(coding, "system", None) or None,
        period=period,
        expressions=expressions,
    )
    needs_reads = RETRIEVAL_FUNCTIONS.get(retrieval.effective_function, ((), False, None))[1]
    if needs_reads and not retrieval.reads_code:
        raise TriccRetrievalError(f"retrieval {code}: function {retrieval.effective_function} needs 'reads'")
    return retrieval


def retrieve_code_system_key(project) -> Optional[str]:
    """Key of the retrieval dictionary in ``project.code_systems``, or None."""
    from tricc_oo.strategies.input.param_build import role_code_system_key

    return role_code_system_key(
        getattr(project, "code_systems", None) or {}, RETRIEVE_ROLE, getattr(project, "retrieve_code_system", None)
    )


def read_project_retrievals(project) -> Dict[str, Retrieval]:
    """Every retrieval of the project dictionary, by code, with the concept read resolved."""
    from tricc_oo.converters.datadictionnary import find_concept

    key = retrieve_code_system_key(project)
    if key is None:
        return {}
    retrievals = {}
    for concept in project.code_systems[key].concept or []:
        retrieval = read_retrieval(concept)
        if retrieval.reads_code:
            read = find_concept(project.code_systems, retrieval.reads_code, retrieval.reads_system)
            if read is None:
                logger.warning(f"retrieval {retrieval.code}: reads {retrieval.reads_code!r}, not a project concept")
            else:
                retrieval.reads_data_type = _property_text(read, "dataType")
                retrieval.reads_concept_type = _property_text(read, "conceptType")
        retrievals[retrieval.code] = retrieval
    return retrievals


def retrieval_refs(value: Any, found: Optional[Set[str]] = None, _seen: Optional[Set[int]] = None) -> Set[str]:
    """The ``#name`` references (unresolved ``TriccReference``) in an expression."""
    from tricc_oo.models.base import TriccOperation, TriccReference

    found = set() if found is None else found
    if isinstance(value, TriccReference):
        if isinstance(value.value, str) and value.value.startswith("#"):
            found.add(value.value)
    elif isinstance(value, TriccOperation):
        seen = set() if _seen is None else _seen
        if id(value) in seen:
            return found
        seen.add(id(value))
        for ref in value.reference:
            retrieval_refs(ref, found, seen)
    elif isinstance(value, (list, tuple, set)) or type(value).__name__ == "OrderedSet":
        for ref in value:
            retrieval_refs(ref, found, _seen)
    return found


def used_retrieval_codes(project) -> List[str]:
    """Codes of the retrievals the loaded pages (activities and block instances) and the
    library calculates use, sorted."""
    found: Set[str] = set()
    nodes: List[Any] = list(getattr(project, "library_calculates", None) or [])
    for page in (getattr(project, "pages", None) or {}).values():
        retrieval_refs(getattr(page, "applicability", None), found)
        nodes.extend((getattr(page, "nodes", None) or {}).values())
    for node in nodes:
        for field in _EXPRESSION_FIELDS:
            retrieval_refs(getattr(node, field, None), found)
    return sorted(found)


def _data_type_to_item(value_type: Optional[str]) -> Optional[str]:
    """Populate ``data_type`` (Questionnaire item type) for a TRICC data type."""
    return {
        "integer": "integer",
        "decimal": "decimal",
        "quantity": "decimal",
        "boolean": "boolean",
        "date": "date",
        "dateTime": "datetime",
        "datetime": "datetime",
        "coded": "string",
        "string": "string",
        "text": "string",
    }.get(value_type or "")


def build_retrieval_node(retrieval: Retrieval):
    """The ``TriccNodeRetrieval`` standing for ``retrieval`` in the graph."""
    from tricc_oo.converters.utils import generate_id
    from tricc_oo.models.calculate import TriccNodeRetrieval

    return TriccNodeRetrieval(
        id=generate_id(f"retrieval:{retrieval.code}"),
        name=retrieval.code,
        label=retrieval.label or retrieval.name,
        export_name=retrieval.export_name,
        context=retrieval.context,
        period=retrieval.period,
        source=retrieval.reads_code,
        concept_type=retrieval.reads_concept_type,
        data_type=_data_type_to_item(retrieval.value_type),
        retrieval=retrieval,
    )


def build_used_retrievals(project) -> List[Any]:
    """Read the dictionary and build one node per used retrieval (once per project).

    Fills ``project.retrievals`` (used ones, by code) and ``project.retrieval_nodes``.

    Raises:
        TriccRetrievalError: An expression uses a ``#code`` the dictionary does not have.
    """
    if getattr(project, "retrieval_nodes", None):
        return project.retrieval_nodes
    used = used_retrieval_codes(project)
    if not used:
        return []
    available = read_project_retrievals(project)
    unknown = [code for code in used if code not in available]
    if unknown:
        raise TriccRetrievalError(
            f"unknown retrieval {', '.join(unknown)}: no concept with this code in the retrieval dictionary"
            f" ({retrieve_code_system_key(project) or 'none found'})"
        )
    project.retrievals = {code: available[code] for code in used}
    project.retrieval_nodes = [build_retrieval_node(r) for r in project.retrievals.values()]
    logger.info(f"retrievals used: {', '.join(used)}")
    return project.retrieval_nodes


# --- expressions ------------------------------------------------------------------


def _duration_parts(period: str, code: str) -> List[tuple]:
    match = _DURATION_RE.match(str(period or "").strip())
    if not match:
        raise TriccRetrievalError(f"retrieval {code}: period {period!r} is not an ISO-8601 duration (e.g. P30D)")
    return [(int(amount), unit) for amount, unit in zip(match.groups(), _DURATION_UNITS) if amount and int(amount)]


def cql_quantity(period: str, code: str = "") -> str:
    """A period as a CQL quantity: ``P30D`` -> ``30 days``, ``PT6H`` -> ``6 hours``.

    Raises:
        TriccRetrievalError: Not a duration, or one with several units (``P1Y6M``).
    """
    parts = _duration_parts(period, code)
    if len(parts) != 1:
        raise TriccRetrievalError(f"retrieval {code}: period {period!r} must have a single unit to be a CQL quantity")
    amount, (singular, plural, _) = parts[0]
    return f"{amount} {singular if amount == 1 else plural}"


def period_days(period: str, code: str = "") -> str:
    """A period as a number of days (months of 30 days, years of 365): ``P2W`` -> ``14``."""
    days = sum(amount * unit[2] for amount, unit in _duration_parts(period, code))
    days = round(days, 6)
    return str(int(days)) if float(days).is_integer() else str(days)


def fill_placeholders(retrieval: Retrieval, expression: str, code_text: Optional[str],
                      period_text: Optional[str]) -> str:
    """Replace ``{{code}}`` / ``{{period}}`` in a custom expression.

    Raises:
        TriccRetrievalError: A placeholder the retrieval has no value for.
    """
    def replace(match):
        value = code_text if match.group(1) == "code" else period_text
        if value is None:
            what = "reads" if match.group(1) == "code" else "period"
            raise TriccRetrievalError(
                f"retrieval {retrieval.code}: the expression uses {{{{{match.group(1)}}}}} but has no {what}"
            )
        return value

    return _PLACEHOLDER_RE.sub(replace, expression)


def custom_expression(retrieval: Retrieval, language: str, strategy: str) -> str:
    """The ``language`` expression of a custom retrieval, placeholders filled.

    Raises:
        TriccRetrievalError: No expression for ``language``.
    """
    expression = retrieval.expressions.get(language)
    if not expression:
        raise TriccRetrievalError(
            f"retrieval {retrieval.code}: custom retrieval has no {language} expression ({strategy})"
        )
    if language == CQL_LANGUAGE:
        code = f'"{retrieval.reads_code}"' if retrieval.reads_code else None
        period = cql_quantity(retrieval.period, retrieval.code) if retrieval.period else None
    else:
        from tricc_oo.converters.utils import clean_name

        code = clean_name(retrieval.reads_code, replace_dots=True) if retrieval.reads_code else None
        period = period_days(retrieval.period, retrieval.code) if retrieval.period else None
    return fill_placeholders(retrieval, expression, code, period).strip()


def unsupported(retrieval: Retrieval, strategy: str) -> TriccRetrievalError:
    """The error for a retrieval function ``strategy`` cannot export."""
    return TriccRetrievalError(
        f"retrieval {retrieval.code}: {strategy} has no mapping for function "
        f"{retrieval.effective_function} (context {retrieval.context})"
    )


def is_retrieval_node(node) -> bool:
    """True for a ``TriccNodeRetrieval``."""
    from tricc_oo.models.calculate import TriccNodeRetrieval

    return isinstance(node, TriccNodeRetrieval)


def iter_retrievals(project) -> Iterable[Retrieval]:
    """The used retrievals of ``project``."""
    return (getattr(project, "retrievals", None) or {}).values()
