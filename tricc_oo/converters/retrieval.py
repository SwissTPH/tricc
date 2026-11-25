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
    # date of the latest record (feature/20261125-populate-read-date.md)
    "LatestDate": (_TIMED, True, "dateTime"),
    # medication reads (feature/20261125-populate-medication.md): the drug codes of the open
    # prescriptions (multi-select) and the dosage of the open prescription of a drug
    "ActiveDrugs": (_TIMED, True, "coded"),
    "OpenDosage": (_TIMED, True, "string"),
}

#: catalogue functions that read medication records only
MEDICATION_FUNCTIONS = ("ActiveDrugs", "OpenDosage")
#: FHIR resources holding medication records
MEDICATION_RESOURCES = ("MedicationRequest", "MedicationDispense")

DEFAULT_FUNCTION = {
    "patient": "PatientValue",
    "facility": "FacilityValue",
    "practitioner": "PractitionerValue",
    "location": "LocationValue",
    "encounter": "Latest",
    "history": "Latest",
}

#: resources whose ``Latest`` reads whether a record exists (done / on treatment), not a value
_DONE_RESOURCES = ("Procedure",) + MEDICATION_RESOURCES

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
    """A retrieval that is unknown, malformed, or that a strategy cannot export.

    Attributes:
        code: The error code (``E_RETRIEVAL_UNKNOWN``, ``E_RETRIEVAL_STATIC``…), or None.
    """

    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(f"{code}: {message}" if code else message)
        self.code = code


# --- implied retrievals: ``Retrieve(...)`` (feature/20261125-requires-and-implied-retrievals.md §3)

E_RETRIEVAL_UNKNOWN = "E_RETRIEVAL_UNKNOWN"
E_RETRIEVAL_STATIC = "E_RETRIEVAL_STATIC"
E_RETRIEVAL_IMPLIED_CONCEPT = "E_RETRIEVAL_IMPLIED_CONCEPT"
E_RETRIEVAL_IMPLIED_PERIOD = "E_RETRIEVAL_IMPLIED_PERIOD"
E_RETRIEVAL_READ_UNSUPPORTED = "E_RETRIEVAL_READ_UNSUPPORTED"
#: the build-time function saving a retrieval (``Retrieve('code')``, ``Retrieve('concept', 'P3M', 'date')``)
RETRIEVE_FUNCTION = "Retrieve"
#: the window of an implied read of the current encounter (else an ISO-8601 duration, or null)
ENCOUNTER_WINDOW = "encounter"
#: field of an implied read -> catalogue function; ``value`` is the default
RETRIEVE_FIELDS = {
    "value": "Latest",
    "date": "LatestDate",
    "exists": "Exists",
    "count": "Count",
    "drugs": "ActiveDrugs",
    "dosage": "OpenDosage",
}
DEFAULT_FIELD = "value"
#: field -> the FHIR resources it is offered for (a field missing here applies to all)
FIELD_RESOURCES = {
    "date": ("Observation", "Condition", "Procedure", "MedicationRequest", "MedicationDispense"),
    "drugs": ("MedicationRequest",),
    "dosage": ("MedicationRequest",),
}
#: catalogue function -> how an implied read is named (the editor builds its chip the same way)
_FUNCTION_LABELS = {
    "Latest": "{concept}",
    "LatestDate": "Date of the latest {concept}",
    "Exists": "{concept} recorded",
    "Count": "Number of {concept} records",
    "ActiveDrugs": "Active drugs ({concept})",
    "OpenDosage": "Open dosage of {concept}",
}


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
    def implied(self) -> bool:
        """True for a read written ``Retrieve('concept', window[, field])`` (code ``#concept@window``)."""
        return "@" in self.code

    @property
    def name(self) -> str:
        """The code without ``#`` (``age_months``); for an implied read a field-safe name:
        ``#weight@P3M.date`` -> ``weight_P3M_date``, ``#weight@`` -> ``weight_any``."""
        if not self.implied:
            return self.code.lstrip("#")
        concept, window, field = split_implied_code(self.code)
        parts = [concept, window or "any"] + ([field] if field != DEFAULT_FIELD else [])
        return re.sub(r"[^A-Za-z0-9_]", "_", "_".join(parts))

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
        if value_type == "source" and function == "Latest" and self.resource in _DONE_RESOURCES:
            # a procedure done / a medication taken: yes or no (#76, #75)
            return "boolean"
        return self.reads_data_type if value_type == "source" else value_type

    @property
    def resource(self) -> str:
        """FHIR resource the concept read is recorded as (``Observation`` by default)."""
        from tricc_oo.converters.fhir.concept_mapper import get_fhir_resource

        return get_fhir_resource(self.reads_concept_type, None)[0]


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


def check_reads_resource(retrieval: Retrieval) -> None:
    """Reject a medication function reading a concept that is not a medication.

    Args:
        retrieval: A retrieval whose concept read (``reads_concept_type``) is resolved.

    Raises:
        TriccRetrievalError: ``ActiveDrugs`` / ``OpenDosage`` on a concept recorded as another
            resource than MedicationRequest / MedicationDispense.
    """
    function = retrieval.effective_function
    if function in MEDICATION_FUNCTIONS and retrieval.resource not in MEDICATION_RESOURCES:
        raise TriccRetrievalError(
            f"retrieval {retrieval.code}: {function} reads medication records, but "
            f"{retrieval.reads_code!r} is recorded as {retrieval.resource} (conceptType "
            f"{retrieval.reads_concept_type!r})"
        )


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
        check_reads_resource(retrieval)
        retrievals[retrieval.code] = retrieval
    return retrievals


def implied_code(concept: str, window: Optional[str], field: str = DEFAULT_FIELD) -> str:
    """The internal code of an implied read: ``#weight@P3M``, ``#weight@`` (no window),
    ``#weight@P3M.date``; the default field ``value`` is left out."""
    return f"#{concept}@{window or ''}" + ("" if field == DEFAULT_FIELD else f".{field}")


def split_implied_code(code: str) -> tuple:
    """``(concept, window or None, field)`` of an implied code (``implied_code`` reversed)."""
    concept, _, rest = code.lstrip("#").rpartition("@")
    window, _, field = rest.partition(".")
    return concept, window or None, field or DEFAULT_FIELD


def retrieve_reference(args: List[Any]):
    """The reference a ``Retrieve(...)`` call stands for (parsed arguments, in order).

    ``Retrieve('code')`` is the dictionary retrieval ``#code``; ``Retrieve('concept', window[,
    field])`` an implied read, ``window`` an ISO-8601 duration, ``null`` (no window) or
    ``'encounter'``. Every argument is a literal. The concept and field are checked against
    the project when the retrievals are built (``implied_retrieval``).

    Args:
        args: The parsed arguments (``TriccStatic``; ``None`` for ``null``).

    Returns:
        A ``TriccReference`` to ``#code`` / ``#concept@window[.field]``.

    Raises:
        TriccRetrievalError: ``E_RETRIEVAL_STATIC`` (an argument is not a literal),
            ``E_RETRIEVAL_IMPLIED_PERIOD`` (a window that is not a duration),
            ``E_RETRIEVAL_READ_UNSUPPORTED`` (an unknown field).
    """
    from tricc_oo.models.base import TriccReference, TriccStatic

    if not 1 <= len(args) <= 3:
        raise TriccRetrievalError(f"{RETRIEVE_FUNCTION} takes 1 to 3 arguments, got {len(args)}", E_RETRIEVAL_STATIC)
    values = []
    for position, arg in enumerate(args):
        if arg is None and position == 1:
            values.append(None)
        elif isinstance(arg, TriccStatic) and isinstance(arg.value, str) and arg.value.strip():
            values.append(arg.value.strip())
        else:
            raise TriccRetrievalError(
                f"{RETRIEVE_FUNCTION} argument {position + 1} must be a text literal such as 'weight', not {arg}",
                E_RETRIEVAL_STATIC,
            )
    if len(values) == 1:
        return TriccReference("#" + values[0].lstrip("#"))
    concept, window = values[0], values[1]
    field = values[2] if len(values) == 3 else DEFAULT_FIELD
    if window is not None and window != ENCOUNTER_WINDOW and not _DURATION_RE.match(window):
        raise TriccRetrievalError(
            f"{RETRIEVE_FUNCTION}({concept!r}, {window!r}): the window must be an ISO-8601 duration (e.g. 'P3M'), "
            f"null or '{ENCOUNTER_WINDOW}'",
            E_RETRIEVAL_IMPLIED_PERIOD,
        )
    if field not in RETRIEVE_FIELDS:
        raise TriccRetrievalError(
            f"{RETRIEVE_FUNCTION}({concept!r}, …, {field!r}): unknown field, use one of {', '.join(RETRIEVE_FIELDS)}",
            E_RETRIEVAL_READ_UNSUPPORTED,
        )
    return TriccReference(implied_code(concept, window, field))


def implied_retrieval(code: str, project) -> Retrieval:
    """The retrieval an implied code stands for, with the concept read resolved.

    ``#weight@P3M.date`` -> ``Retrieval(context="history", function="LatestDate",
    reads_code="weight", period="P3M")``; ``#weight@`` has no period, ``#weight@encounter``
    the ``encounter`` context.

    Raises:
        TriccRetrievalError: ``E_RETRIEVAL_IMPLIED_CONCEPT`` (not a project concept),
            ``E_RETRIEVAL_IMPLIED_PERIOD``, ``E_RETRIEVAL_READ_UNSUPPORTED`` (a field not valid
            for the concept's resource).
    """
    from tricc_oo.converters.datadictionnary import find_concept

    concept, window, field = split_implied_code(code)
    function = RETRIEVE_FIELDS.get(field)
    if function is None:
        raise TriccRetrievalError(f"retrieval {code}: unknown field {field!r}", E_RETRIEVAL_READ_UNSUPPORTED)
    encounter = window == ENCOUNTER_WINDOW
    if window and not encounter and not _DURATION_RE.match(window):
        raise TriccRetrievalError(
            f"retrieval {code}: {window!r} is not an ISO-8601 duration", E_RETRIEVAL_IMPLIED_PERIOD
        )
    code_systems = getattr(project, "code_systems", None) or {}
    read = find_concept(code_systems, concept, None) if code_systems else None
    if read is None:
        raise TriccRetrievalError(
            f"retrieval {code}: {concept!r} is not a project concept", E_RETRIEVAL_IMPLIED_CONCEPT
        )
    retrieval = Retrieval(
        code=code,
        context="encounter" if encounter else "history",
        function=function,
        reads_code=concept,
        period=None if encounter else window,
        reads_data_type=_property_text(read, "dataType"),
        reads_concept_type=_property_text(read, "conceptType"),
    )
    allowed = FIELD_RESOURCES.get(field)
    if allowed is not None and retrieval.resource not in allowed:
        raise TriccRetrievalError(
            f"retrieval {code}: the field {field!r} is not offered for {concept!r} ({retrieval.resource})",
            E_RETRIEVAL_READ_UNSUPPORTED,
        )
    window_text = "this encounter" if encounter else (window or "any time")
    retrieval.label = _FUNCTION_LABELS[function].format(concept=read.display or concept) + f", {window_text}"
    return retrieval


def reference_values(value: Any, found: Optional[Set[str]] = None, _seen: Optional[Set[int]] = None) -> Set[str]:
    """The names of the unresolved ``TriccReference``s in an expression."""
    from tricc_oo.models.base import TriccOperation, TriccReference

    found = set() if found is None else found
    if isinstance(value, TriccReference):
        if isinstance(value.value, str):
            found.add(value.value)
    elif isinstance(value, TriccOperation):
        seen = set() if _seen is None else _seen
        if id(value) in seen:
            return found
        seen.add(id(value))
        for ref in value.reference:
            reference_values(ref, found, seen)
    elif isinstance(value, (list, tuple, set)) or type(value).__name__ == "OrderedSet":
        for ref in value:
            reference_values(ref, found, _seen)
    return found


def retrieval_refs(value: Any, found: Optional[Set[str]] = None, _seen: Optional[Set[int]] = None) -> Set[str]:
    """The ``#name`` references (unresolved ``TriccReference``) in an expression."""
    found = set() if found is None else found
    found.update(name for name in reference_values(value) if name.startswith("#"))
    return found


def expression_nodes(project) -> List[Any]:
    """The expressions of the loaded pages (activities and block instances) and the library
    calculates: each page's applicability and each node's expression fields."""
    values: List[Any] = []
    nodes: List[Any] = list(getattr(project, "library_calculates", None) or [])
    for page in (getattr(project, "pages", None) or {}).values():
        values.append(getattr(page, "applicability", None))
        nodes.extend((getattr(page, "nodes", None) or {}).values())
    for node in nodes:
        values.extend(getattr(node, field, None) for field in _EXPRESSION_FIELDS)
    return values


def used_retrieval_codes(project) -> List[str]:
    """Codes of the retrievals the loaded pages (activities and block instances) and the
    library calculates use, sorted."""
    found: Set[str] = set()
    for value in expression_nodes(project):
        retrieval_refs(value, found)
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


def _select_multiple_concepts(project) -> Set[str]:
    """Names of the select_multiple questions of the loaded pages."""
    names = set()
    for page in (getattr(project, "pages", None) or {}).values():
        for node in (getattr(page, "nodes", None) or {}).values():
            if str(getattr(node, "tricc_type", "")) == "select_multiple" and getattr(node, "name", None):
                names.add(node.name)
    return names


def _warn_dosage_of_multiple(project, retrievals: Iterable[Retrieval]) -> None:
    """Warn when ``OpenDosage`` reads a select_multiple concept (one dosage per drug)."""
    dosages = [r for r in retrievals if r.effective_function == "OpenDosage"]
    if not dosages:
        return
    multiple = _select_multiple_concepts(project)
    for retrieval in dosages:
        if retrieval.reads_code in multiple or (retrieval.reads_data_type or "").lower() == "select_multiple":
            logger.warning(
                f"retrieval {retrieval.code}: OpenDosage reads {retrieval.reads_code!r}, a select_multiple "
                "concept; the dosage is the one of a single drug, read the drug concept instead"
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
    implied = [code for code in used if "@" in code]
    available = read_project_retrievals(project) if len(implied) < len(used) else {}
    available.update((code, implied_retrieval(code, project)) for code in implied)
    unknown = [code for code in used if code not in available]
    if unknown:
        raise TriccRetrievalError(
            f"unknown retrieval {', '.join(unknown)}: no concept with this code in the retrieval dictionary"
            f" ({retrieve_code_system_key(project) or 'none found'})",
            E_RETRIEVAL_UNKNOWN,
        )
    project.retrievals = {code: available[code] for code in used}
    _warn_dosage_of_multiple(project, project.retrievals.values())
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
