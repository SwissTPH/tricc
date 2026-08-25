"""
Emit a machine-readable *form model* for a completed build.

Runs as a test strategy, after whichever output strategy the user selected::

    python tests/build.py -i flow.drawio -o out/ \
        -O XLSFormCHTStrategy -T TestSpecStrategy

The deployable ``.xlsx`` is produced by ``XLSFormCHTStrategy`` exactly as it
would be without ``-T``; this strategy only adds ``<form_id>.form-model.json``.
That is the point: the harness tests the artifact you actually deploy.

The model is keyed by post-mangling **export name**, so it aligns with the names
present in the deployed form. See ``feature/test-spec-strategy.md`` for the
schema contract.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from tricc_oo.converters.fhir.populate_helper import populate_uses_inputs_group
from tricc_oo.converters.tricc_to_xls_form import get_export_name
from tricc_oo.converters.utils import clean_name
from tricc_oo.models.base import TriccOperation, get_repeat
from tricc_oo.models.calculate import (
    TriccNodeActivityEnd,
    TriccNodeDiagnosis,
    TriccNodeEnd,
    TriccNodePopulate,
    TriccNodeProposedDiagnosis,
)
from tricc_oo.models.tricc import (
    TriccNodeCalculateBase,
    TriccNodeNumber,
    TriccNodeSelect,
    TriccNodeSelectOption,
)
from tricc_oo.strategies.registry import register_test_strategy
from tricc_oo.strategies.test.base_test_strategy import BaseTestStrategy

logger = logging.getLogger("default")

#: Bumped whenever the emitted JSON schema changes in a breaking way.
FORM_MODEL_VERSION = 1

#: By export time every cross-reference has been serialised as ``${export_name}``
#: by the XLSForm serializer, so this match is exact rather than heuristic.
REF_PATTERN = re.compile(r"\$\{([^}]+)\}")

#: XLSForm ``type`` values that are structural rather than answerable. Both the
#: spaced and underscored spellings occur: the base serializer emits
#: ``begin group`` while the CHT input wrapper emits ``begin_group``.
STRUCTURAL_TYPES = frozenset({
    "begin group", "end group", "begin_group", "end_group",
    "begin repeat", "end repeat", "begin_repeat", "end_repeat",
})

#: Output strategies whose artifacts a CHT-flavoured harness should drive.
CHT_STRATEGIES = ("XLSFormCHTStrategy", "XLSFormCHTHFStrategy")

#: Rows the output strategies inject that correspond to no TRICC node.
#: ``version`` comes from ``XLSFormStrategy.inject_version``; the rest are the
#: CHT ``inputs`` wrapper.
INJECTED_ROWS = frozenset({
    "version", "inputs", "source", "source_id", "user", "contact",
    "contact_id", "facility_id", "name", "external_id", "_id",
})


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def expression_text(value: Any) -> Optional[str]:
    """Render an expression-ish value as the string the XLSForm would carry.

    An unserialised ``TriccOperation`` is deliberately dropped rather than
    stringified: its ``__str__`` produces ``TriccOperator.ISTRUE(Select|x|0|1)``,
    which is not an XLSForm expression. Emitting it would give the harness a
    value it cannot parse *and* an empty reference list, silently claiming the
    expression depends on nothing.

    Args:
        value: An ``Expression``, ``TriccStatic``, plain str, number, bool,
            ``TriccOperation`` or ``None``.

    Returns:
        The string form, or ``None`` when the value is absent, empty or not yet
        serialised.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, TriccOperation):
        return None
    text = str(value).strip()
    if text.startswith("TriccOperator."):
        return None
    return text or None


def label_text(label: Any, lang_code: str = "en") -> Optional[str]:
    """Flatten a ``DisplayText`` (str, multi-language dict or operation) to one string.

    Args:
        label: The node label.
        lang_code: Preferred language key when the label is a dict.

    Returns:
        A single display string, or ``None``.
    """
    if label is None:
        return None
    if isinstance(label, dict):
        if not label:
            return None
        chosen = label.get(lang_code)
        if chosen is None:
            # Fall back to any language rather than losing the label entirely.
            chosen = next(iter(label.values()))
        return label_text(chosen, lang_code)
    return str(label).strip() or None


def expression_refs(text: Optional[str]) -> List[str]:
    """Extract the ``${...}`` export names referenced by an expression.

    Args:
        text: The serialised expression, or ``None``.

    Returns:
        Sorted, de-duplicated reference names.
    """
    if not text:
        return []
    return sorted({match.strip() for match in REF_PATTERN.findall(text)})


def group_path(node: Any) -> List[str]:
    """Walk the ``group`` chain upwards and return export names, outermost first.

    Args:
        node: Any TRICC node.

    Returns:
        The list of enclosing group export names.
    """
    path: List[str] = []
    seen = set()
    current = getattr(node, "group", None)
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        try:
            name = get_export_name(current)
        except Exception:  # pragma: no cover - group naming is best effort
            name = getattr(current, "name", None)
        if name:
            path.append(str(name))
        current = getattr(current, "group", None)
    path.reverse()
    return path


def safe_export_name(node: Any) -> Optional[str]:
    """Return ``get_export_name(node)`` as a usable string, or ``None``."""
    if node is None:
        return None
    try:
        name = get_export_name(node)
    except Exception:  # pragma: no cover - defensive
        return None
    if name is None or isinstance(name, (int, float, bool)):
        return None
    name = str(name).strip()
    return name or None


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

@register_test_strategy("TestSpecStrategy")
class TestSpecStrategy(BaseTestStrategy):
    """Write ``<form_id>.form-model.json`` describing the build that just ran."""

    #: The name starts with "Test", so pytest would otherwise try to collect
    #: this class as a test suite and warn about its __init__.
    __test__ = False

    def __init__(self, project, output_path, output_strategy=None):
        super().__init__(project, output_path, output_strategy)
        #: Export names seen more than once; populated by :meth:`collect_nodes`.
        self._duplicate_names: List[str] = []
        #: Selects whose authored options differ from the shipped choice list.
        self._option_mismatches: List[dict] = []

    def execute(self):
        """Build and write the form model.

        Returns:
            The path written, or ``None`` if nothing could be produced.
        """
        model = self.build_form_model()
        return self.write_form_model(model)

    # -- runtime flavour ---------------------------------------------------

    @property
    def runtime(self) -> str:
        """``"cht"`` or ``"odk"``, inferred from the output strategy that ran.

        The harness uses this to pick a driver, so it must reflect the artifact
        that was actually produced rather than a strategy-level constant.
        """
        name = self.output_strategy_name or ""
        if name in CHT_STRATEGIES:
            return "cht"
        # Subclasses of the CHT strategies count too.
        for base in type(self.output_strategy).__mro__ if self.output_strategy else []:
            if base.__name__ in CHT_STRATEGIES:
                return "cht"
        return "odk"

    def lang_code(self) -> str:
        return getattr(self.project, "lang_code", "en") or "en"

    # -- node collection ---------------------------------------------------

    def index_nodes(self) -> Dict[str, Any]:
        """Map every name a node might be addressable by -> the node.

        A node can reach the survey sheet under more than one spelling: the
        export name usually, but an encounter-context populate (the CHT
        ``inputs`` group) exports as ``load_<name>`` while the CHT strategy
        writes its row as ``<name>``. Both are indexed so the sheet can be
        joined either way, with the export name taking precedence.

        Returns:
            ``{name: node}``, first occurrence winning.
        """
        index: Dict[str, Any] = {}
        for node in self.all_nodes():
            if isinstance(node, TriccNodeSelectOption):
                # Options are captured through their parent select.
                continue
            for name in (safe_export_name(node), self._raw_name(node)):
                if name and name not in index:
                    index[name] = node
        return index

    @staticmethod
    def _raw_name(node) -> Optional[str]:
        raw = getattr(node, "name", None)
        return clean_name(str(raw)) if raw else None

    def collect_nodes(self, survey_rows: Dict[str, dict]) -> Dict[str, Any]:
        """Map deployed name -> node, driven by what actually shipped.

        The survey sheet is authoritative for the form's contents; the node graph
        supplies semantics. Building the model the other way round -- walking the
        graph and hoping it covers the sheet -- silently drops whatever the walk
        cannot reach, and on a real form that is most of it.

        Args:
            survey_rows: ``{name: row}`` from the shipped survey sheet.

        Returns:
            An insertion-ordered ``{name: node_or_None}`` covering every
            answerable row, followed by any graph-only nodes worth keeping.
        """
        self._duplicate_names = []
        index = self.index_nodes()

        observed: Dict[str, Any] = {}
        for name, row in survey_rows.items():
            if str(row.get("type", "")).strip() in STRUCTURAL_TYPES:
                continue
            if name in INJECTED_ROWS:
                continue
            observed[name] = index.get(name)

        # End and diagnosis nodes carry the clinical outcomes a scenario asserts
        # on. Keep any that produced no row, so they remain assertable.
        for name, node in index.items():
            if name in observed:
                continue
            if isinstance(node, (TriccNodeEnd, TriccNodeActivityEnd,
                                 TriccNodeDiagnosis, TriccNodeProposedDiagnosis)):
                observed[name] = node

        self._duplicate_names = sorted(self._duplicated_survey_names())
        return observed

    def _duplicated_survey_names(self) -> List[str]:
        """Names appearing on more than one answerable survey row.

        A duplicate makes every name-based selector ambiguous, so it is worth
        surfacing even though the output strategy only logs it.
        """
        frame = self.survey_frame
        if frame is None or not len(frame):
            return []
        counts: Dict[str, int] = {}
        for record in frame.fillna("").to_dict(orient="records"):
            name = str(record.get("name", "")).strip()
            if not name or str(record.get("type", "")).strip() in STRUCTURAL_TYPES:
                continue
            counts[name] = counts.get(name, 0) + 1
        return [name for name, count in counts.items() if count > 1]

    # -- entry building ----------------------------------------------------

    @staticmethod
    def list_name_of(survey_row: Optional[dict]) -> Optional[str]:
        """The choice list named in a ``select_one x`` / ``select_multiple x`` type."""
        odk_type = str((survey_row or {}).get("type", "")).strip()
        parts = odk_type.split(None, 1)
        if len(parts) == 2 and parts[0] in ("select_one", "select_multiple"):
            return parts[1].strip()
        return None

    def node_entry(self, export_name: str, node, survey_row: Optional[dict],
                   choices: Optional[Dict[str, List[dict]]] = None) -> dict:
        """Build one ``nodes[]`` entry.

        Either source may be missing: a row can ship without a locatable node
        (the graph is not fully reachable after export), and an end node can
        exist without a row. The entry is assembled from whatever is available,
        with the sheet winning on anything both describe, because the sheet is
        what the runtime executes.

        Args:
            export_name: The post-mangling name used by the deployed form.
            node: The TRICC node, or ``None``.
            survey_row: The matching ``survey`` sheet row, or ``None``.

        Returns:
            A JSON-serialisable dict.
        """
        relevance = expression_text(getattr(node, "relevance", None))
        constraint = expression_text(getattr(node, "constraint", None))
        calculation = expression_text(getattr(node, "expression", None))

        # The survey sheet is authoritative for what actually shipped; the node
        # is authoritative for semantics. Prefer the sheet where they overlap.
        if survey_row:
            relevance = expression_text(survey_row.get("relevance")) or relevance
            constraint = expression_text(survey_row.get("constraint")) or constraint
            calculation = expression_text(survey_row.get("calculation")) or calculation

        # Former ``TriccNodeInput`` is now ``TriccNodePopulate``. The harness
        # still needs the CHT *data source*: encounter-context populates land in
        # the form ``inputs`` group; every other context is contact-summary backed.
        is_populate_node = isinstance(node, TriccNodePopulate)
        uses_inputs_group = is_populate_node and populate_uses_inputs_group(node)

        entry: Dict[str, Any] = {
            "exportName": export_name,
            "conceptCode": getattr(node, "name", None),
            "triccType": str(getattr(node, "tricc_type", "") or "") or None,
            "odkType": (survey_row or {}).get("type"),
            "conceptType": getattr(node, "concept_type", None),
            "datatype": getattr(node, "datatype", None),
            "label": label_text(getattr(node, "label", None), self.lang_code()),
            "group": group_path(node),
            "activity": safe_export_name(getattr(node, "activity", None)),
            "required": self.required_flag(node, survey_row),
            "readOnly": bool((survey_row or {}).get("read only")),
            "default": expression_text(getattr(node, "default", None)),
            "relevance": relevance,
            "relevanceRefs": expression_refs(relevance),
            "constraint": constraint,
            "constraintRefs": expression_refs(constraint),
            "calculation": calculation,
            "calculationRefs": expression_refs(calculation),
            "listName": getattr(node, "list_name", None) or self.list_name_of(survey_row),
            "options": self.options(node),
            "min": getattr(node, "min", None) if isinstance(node, TriccNodeNumber) else None,
            "max": getattr(node, "max", None) if isinstance(node, TriccNodeNumber) else None,
            "repeat": get_repeat(node),
            "instance": getattr(node, "instance", 1),
            "version": getattr(node, "version", 1),
            "isLastVersion": getattr(node, "last", True) is not False,
            "isInput": uses_inputs_group,
            "isPopulate": is_populate_node and not uses_inputs_group,
            # Fall back to the shipped type when no node was located, so a
            # calculate is still recognised as derived rather than answerable.
            "isCalculate": isinstance(node, TriccNodeCalculateBase)
            or (node is None and (survey_row or {}).get("type") == "calculate"),
            "hasNode": node is not None,
            "binding": None,
        }

        # For inputs and populates the calculation *is* the binding expression,
        # and that is what the harness must seed rather than type into.
        if entry["isInput"] or entry["isPopulate"]:
            entry["binding"] = calculation

        reconciled = self.reconcile_options(entry, choices)
        self._record_option_mismatch(entry, reconciled)
        entry["options"] = reconciled
        return entry

    #: TRICC stores yes/no options as true/false but writes 1/0 to the sheet via
    #: BOOLEAN_MAP. That difference is by design and not worth reporting.
    _BOOLEAN_SPELLINGS = ({"true", "false"}, {"1", "0"})

    def _record_option_mismatch(self, entry: dict, reconciled: List[dict]) -> None:
        """Note a select whose authored options differ from the shipped ones.

        A disagreement means expressions written against the authored values can
        never match what the form renders. It is not fatal -- the shipped values
        are what the harness must use -- but it is a content defect worth
        surfacing, because it fails silently.
        """
        authored = {str(option["value"]) for option in entry["options"]}
        shipped = {str(option["value"]) for option in reconciled}
        if not authored or not shipped or authored == shipped:
            return
        if (authored, shipped) == self._BOOLEAN_SPELLINGS:
            return
        self._option_mismatches.append({
            "exportName": entry["exportName"],
            "listName": entry["listName"],
            "authored": sorted(authored),
            "shipped": sorted(shipped),
        })

    @staticmethod
    def reconcile_options(entry: dict, choices: Optional[Dict[str, List[dict]]]) -> List[dict]:
        """Return the option values the *deployed* form actually offers.

        The node model and the shipped form can disagree. A yes/no select carries
        ``true``/``false`` on the node but is written to the choices sheet as
        ``1``/``0`` via ``BOOLEAN_MAP``, and the rendered form uses the latter.
        Emitting the node's values would hand the harness options that match no
        control, so the sheet wins on values and the node only enriches labels
        and the ``isNone`` flag.

        Args:
            entry: The partially built node entry.
            choices: ``{list_name: [{value, label}]}`` from the shipped sheet.

        Returns:
            The option list, sheet-authoritative where a sheet exists.
        """
        node_options = entry["options"]
        list_name = entry["listName"]
        shipped = (choices or {}).get(list_name or "", [])

        if not shipped:
            return node_options

        by_value = {str(option["value"]): option for option in node_options}
        reconciled = []
        for choice in shipped:
            value = str(choice["value"])
            known = by_value.get(value, {})
            reconciled.append({
                "value": value,
                "label": known.get("label") or choice.get("label"),
                # `is_none` is only set when the diagram says so, but the
                # generated forms rely on an `opt_none` naming convention that
                # the node model never records.
                "isNone": bool(known.get("isNone")) or value.lower() in ("opt_none", "none"),
                "listName": list_name,
            })
        return reconciled

    @staticmethod
    def required_flag(node, survey_row: Optional[dict]) -> Optional[bool]:
        """Normalise the inconsistent ``required`` values (``1``/``true``/blank)."""
        raw = (survey_row or {}).get("required")
        if raw is None or raw == "":
            raw = getattr(node, "required", None)
        if raw is None or raw == "":
            return None
        text = str(raw).strip().lower()
        if text in ("1", "true", "yes"):
            return True
        if text in ("0", "false", "no"):
            return False
        # An expression-valued `required` is neither true nor false statically.
        return None

    @staticmethod
    def options(node) -> List[dict]:
        """Return the answer options of a select node, in declaration order.

        Uses ``option.name`` rather than ``get_export_name(option)``: for a
        ``TriccNodeSelectOption`` the latter returns the value *quoted* for
        embedding in an expression (``'yes'``), whereas the ``choices`` sheet
        and the rendered form both carry it bare (``yes``).
        """
        if not isinstance(node, TriccNodeSelect):
            return []
        result = []
        for _, option in sorted((node.options or {}).items(), key=lambda kv: kv[0]):
            result.append(
                {
                    "value": option.name,
                    "label": label_text(getattr(option, "label", None)),
                    "isNone": bool(getattr(option, "is_none", False)),
                    "listName": getattr(option, "list_name", None),
                }
            )
        return result

    # -- graph -------------------------------------------------------------

    @staticmethod
    def edges(observed: Dict[str, Any]) -> List[dict]:
        """Derive edges between exported nodes from ``next_nodes``."""
        result: List[dict] = []
        seen = set()
        by_id = {id(node): name for name, node in observed.items()}
        for source_name, node in observed.items():
            for target in getattr(node, "next_nodes", None) or []:
                target_name = by_id.get(id(target)) or safe_export_name(target)
                if not target_name:
                    continue
                key = (source_name, target_name)
                if key in seen:
                    continue
                seen.add(key)
                result.append({"from": source_name, "to": target_name})
        return result

    def terminals(self, observed: Dict[str, Any]) -> Dict[str, List[dict]]:
        """Collect end nodes and diagnoses -- the assertable clinical outcomes."""
        ends: List[dict] = []
        diagnoses: List[dict] = []
        for name, node in observed.items():
            if isinstance(node, (TriccNodeEnd, TriccNodeActivityEnd)):
                ends.append(
                    {
                        "exportName": name,
                        "process": getattr(node, "process", None),
                        "label": label_text(getattr(node, "label", None), self.lang_code()),
                        "isActivityEnd": isinstance(node, TriccNodeActivityEnd),
                    }
                )
            if isinstance(node, (TriccNodeDiagnosis, TriccNodeProposedDiagnosis)):
                diagnoses.append(
                    {
                        "exportName": name,
                        "label": label_text(getattr(node, "label", None), self.lang_code()),
                        "severity": getattr(node, "severity", None),
                        "priority": getattr(node, "priority", None),
                        "isProposed": isinstance(node, TriccNodeProposedDiagnosis),
                    }
                )
        return {"ends": ends, "diagnoses": diagnoses}

    # -- assembly ----------------------------------------------------------

    def build_form_model(self) -> dict:
        """Assemble the complete form model.

        Returns:
            A JSON-serialisable dict following ``formModelVersion`` 1.
        """
        survey_rows = self.survey_rows_by_name()
        choices = self.choices_by_list()
        observed = self.collect_nodes(survey_rows)
        self._option_mismatches = []

        nodes = [
            self.node_entry(name, node, survey_rows.get(name), choices)
            for name, node in observed.items()
        ]

        known = {entry["exportName"] for entry in nodes}

        # The model is now driven by the survey sheet, so a row can only be
        # missing if it was deliberately excluded. Keep the check as a guard
        # against that logic drifting.
        answerable_rows = {
            name
            for name, row in survey_rows.items()
            if str(row.get("type", "")).strip() not in STRUCTURAL_TYPES
            and name not in INJECTED_ROWS
        }

        # Entries carrying no TRICC node are usable but thin: no options, no
        # concept type, and expressions only as the sheet spelled them. This is
        # the number to watch when judging how much the model actually knows.
        without_semantics = sorted(
            entry["exportName"] for entry in nodes if not entry["hasNode"]
        )

        unresolved = sorted(
            {
                ref
                for entry in nodes
                for key in ("relevanceRefs", "constraintRefs", "calculationRefs")
                for ref in entry[key]
                if ref not in known and ref not in survey_rows
            }
        )

        terminals = self.terminals(observed)
        page = (getattr(self.project, "start_pages", {}) or {}).get(self.processes[0])
        if isinstance(page, (list, tuple)):
            page = page[0] if page else None
        root = getattr(page, "root", None)

        return {
            "formModelVersion": FORM_MODEL_VERSION,
            "formId": self.form_id() or "",
            "title": label_text(getattr(root, "label", None), self.lang_code()),
            "version": datetime.datetime.now().strftime("%Y%m%d%H%M"),
            "strategy": type(self).__name__,
            "outputStrategy": self.output_strategy_name,
            "runtime": self.runtime,
            "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "nodes": nodes,
            "edges": self.edges(observed),
            "ends": terminals["ends"],
            "diagnoses": terminals["diagnoses"],
            "inputs": [
                {"exportName": e["exportName"], "binding": e["binding"]}
                for e in nodes
                if e["isInput"]
            ],
            "populates": [
                {"exportName": e["exportName"], "binding": e["binding"]}
                for e in nodes
                if e["isPopulate"]
            ],
            "choices": choices,
            "diagnostics": {
                "duplicateNames": sorted(self._duplicate_names),
                "unresolvedRefs": unresolved,
                "missingFromModel": sorted(answerable_rows - known),
                "withoutSemantics": without_semantics,
                "optionMismatches": self._option_mismatches,
            },
        }

    def write_form_model(self, model: dict) -> str:
        """Serialise the model to ``<output_path>/<form_id>.form-model.json``.

        Args:
            model: The dict returned by :meth:`build_form_model`.

        Returns:
            The path written.
        """
        if not os.path.exists(self.output_path):
            os.makedirs(self.output_path)
        form_id = model.get("formId") or "form"
        path = os.path.join(self.output_path, f"{form_id}.form-model.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(model, handle, indent=2, ensure_ascii=False, default=str)

        noisy = {key: value for key, value in model.get("diagnostics", {}).items() if value}
        if noisy:
            logger.warning(f"TestSpec: model written with diagnostics: {noisy}")
        logger.info(
            f"TestSpec: form model written to {path} "
            f"({len(model['nodes'])} nodes, runtime={model['runtime']})"
        )
        return path
