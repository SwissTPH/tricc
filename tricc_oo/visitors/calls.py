"""Instantiate the calls of a node: bind left-out parameters, expand, record the data needs.

feature/20261125-calculate-functions.md §2. A call (a decision table call, a calculate function)
stays a call while the graph is walked: only its passed arguments are references, so only they
make the walk wait. When the node holding it is instantiated (the end of ``load_calculate``),
every left-out parameter takes the first of (§2.3):

1. ``form``: the latest version of its fallback concept;
2. ``earlier_call``: the argument the latest earlier call of the same function (same table and
   output) passed or carried for it, as written, resolved again here;
3. ``retrieval``: the first ``#code`` listed on the parameter (its node is built on demand);
4. ``none``: no value (``W_PARAM_NO_VALUE``).

An explicit ``null`` is no value; nothing is tried. Then the call is expanded and the node's
references are replaced as before.

A free-standing calculate (no arrow into it) holding a call is instantiated where it is first
read, or at the end of the walk when it is saved to the record; otherwise it is dropped (§2.5).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from tricc_oo.converters.call_binding import MISSING, NULL, CallParam
from tricc_oo.converters.decision_table import (
    EXPRESSION_ATTRIBUTES,
    check_node_tables,
    contains_table_call,
    expand_decision_tables,
)
from tricc_oo.models.base import TriccNodeBaseModel, TriccOperation, TriccReference, TriccStatic

logger = logging.getLogger("default")

#: how a parameter was bound (the data needs report, §4)
STEP_PASSED = "passed"
STEP_NULL = "null"
STEP_FORM = "form"
STEP_EARLIER_CALL = "earlier_call"
STEP_RETRIEVAL = "retrieval"
STEP_NONE = "none"

W_PARAM_NO_VALUE = "W_PARAM_NO_VALUE"

#: the node fields that may hold a call
CALL_ATTRIBUTES = (*EXPRESSION_ATTRIBUTES, "reference", "constraint")

#: pending free-standing calculates by node id -> their CallState (§2.5), so the reference
#: resolution (``process_operation_reference``) can instantiate one where it is first read
_PENDING: Dict[str, "CallState"] = {}


def instantiate_if_pending(node: Any) -> None:
    """Instantiate ``node`` now if it is a free-standing calculate waiting for its first reader."""
    state = _PENDING.get(getattr(node, "id", None)) if isinstance(node, TriccNodeBaseModel) else None
    if state is not None:
        state.instantiate_pending(node)


def as_written(value: Any) -> Any:
    """A copy of an argument with nodes back to references by name (what the author wrote)."""
    if isinstance(value, TriccOperation):
        return value.copy()
    if isinstance(value, (TriccReference, TriccStatic)):
        return value.copy()
    if isinstance(value, TriccNodeBaseModel) and getattr(value, "name", None):
        return TriccReference(value.name)
    return value


def describe(value: Any) -> Optional[str]:
    """An argument as text for the data needs report."""
    if value is None or value is NULL or value is MISSING:
        return None
    if isinstance(value, TriccNodeBaseModel):
        return getattr(value, "name", None) or value.id
    if isinstance(value, (TriccReference, TriccStatic)):
        return str(value.value)
    return str(value)


class CallState:
    """What the calls of one project share across its walks (``CallArguments`` and more, §2.6).

    Attributes:
        project: The project (tables, aliases, functions, retrieval dictionary).
        arguments: ``{call key: {parameter: original expression}}``: what the latest call of
            each function (table and output) passed or carried, for the next one.
        records: The data needs report, one entry per instantiated call (§4).
        pending: The free-standing calculates waiting for a reader, by node id.
        call_keys: The call keys each instantiated node held, by node id (version inheritance).
        start_page: The start page of the current walk (built retrievals hang there).
    """

    def __init__(
        self,
        project: Any = None,
        tables: Optional[Dict[str, Any]] = None,
        aliases: Optional[Dict[str, Any]] = None,
        keep_calls: Optional[bool] = None,
    ):
        self.project = project
        if tables is None:
            if project is not None and getattr(project, "decision_tables", None) is None:
                project.decision_tables = {}
            tables = getattr(project, "decision_tables", None) if project is not None else {}
        self.tables: Dict[str, Any] = tables if tables is not None else {}
        self.aliases: Dict[str, Any] = aliases if aliases is not None else (getattr(project, "aliases", None) or {})
        self.keep_calls = (
            bool(getattr(project, "decision_table_calls", False)) if keep_calls is None else bool(keep_calls)
        )
        self.arguments: Dict[str, Dict[str, Any]] = {}
        self.records: List[Dict[str, Any]] = []
        self.pending: Dict[str, Tuple[Any, Callable[[], None]]] = {}
        self.call_keys: Dict[str, Set[str]] = {}
        self.start_page: Any = None
        self._checked: Set[str] = set()

    # ------------------------------------------------------------ load (checks only)

    def check_node(self, node: Any) -> None:
        """Check the calls of a node the project check did not reach (once per node).

        Raises:
            DecisionTableError: An invalid table call.
        """
        if node.id in self._checked:
            return
        self._checked.add(node.id)
        check_node_tables(node, self.tables, self.aliases)

    # ------------------------------------------------------------ queries

    def has_calls(self, node: Any) -> bool:
        """Whether one of the node's expressions holds a call."""
        return any(self._expr_has_calls(getattr(node, a, None)) for a in CALL_ATTRIBUTES)

    def _expr_has_calls(self, expr: Any) -> bool:
        return isinstance(expr, TriccOperation) and contains_table_call(expr, self.aliases)

    def node_call_keys(self, node: Any) -> Set[str]:
        """The call keys (function, table and output) of the calls a node holds or held."""
        if node.id in self.call_keys:
            return self.call_keys[node.id]
        keys: Set[str] = set()
        for attribute in CALL_ATTRIBUTES:
            expr = getattr(node, attribute, None)
            if self._expr_has_calls(expr):
                self._collect_keys(expr, keys)
        return keys

    def _collect_keys(self, expr: Any, keys: Set[str]) -> None:
        def record(call, params, values):
            keys.add(call.key)
            return [NULL if v is MISSING else v for v in values]

        try:
            expand_decision_tables(expr, dict(self.tables), self.aliases, binder=record)
        except ValueError:
            pass

    # ------------------------------------------------------------ free-standing calculates (§2.5)

    def is_free_standing(self, node: Any) -> bool:
        """A calculate drawn without an arrow into it (or a library calculate) holding a call."""
        from tricc_oo.models.calculate import TriccNodeCalculate

        return isinstance(node, TriccNodeCalculate) and not getattr(node, "prev_nodes", None) and self.has_calls(node)

    def defer(self, node: Any, instantiate: Callable[[], None]) -> None:
        """Keep a free-standing calculate for its first reader."""
        self.pending[node.id] = (node, instantiate)
        _PENDING[node.id] = self

    def instantiate_pending(self, target: Any) -> None:
        """Instantiate ``target`` if it is a pending free-standing calculate (its first reader)."""
        entry = self.pending.pop(getattr(target, "id", None), None)
        if entry is not None:
            _PENDING.pop(target.id, None)
            logger.debug(f"free-standing calculate {target.get_name()} instantiated where it is first read")
            entry[1]()

    def finish_walk(self, processed_nodes: Any) -> None:
        """End of a start page's walk: an unread free-standing calculate is instantiated when it
        is saved to the record, dropped otherwise."""
        from tricc_oo.converters.fhir.concept_mapper import classify_extraction

        codesystems = getattr(self.project, "code_systems", None)
        for node_id in list(self.pending):
            entry = self.pending.pop(node_id, None)
            _PENDING.pop(node_id, None)
            if entry is None:
                continue
            node, instantiate = entry
            saved = getattr(node, "next_nodes", None) or classify_extraction(node, codesystems) is not None
            if saved:
                instantiate()
                continue
            logger.debug(f"free-standing calculate {node.get_name()} is never read nor saved: dropped")
            activity = getattr(node, "activity", None)
            if activity is not None:
                activity.nodes.pop(node.id, None)
                if node in activity.calculates:
                    activity.calculates.remove(node)
            if node in processed_nodes:
                processed_nodes.remove(node)

    # ------------------------------------------------------------ instantiation (§2.2, §2.3)

    def instantiate_calls(self, node: Any, processed_nodes: Any) -> None:
        """Bind and expand every call of ``node`` (its references are replaced afterwards)."""
        keys: Set[str] = set()
        for attribute in CALL_ATTRIBUTES:
            expr = getattr(node, attribute, None)
            if not self._expr_has_calls(expr):
                continue
            binder = self._binder(node, processed_nodes, keys)
            expanded = expand_decision_tables(expr, self.tables, self.aliases, keep_calls=self.keep_calls,
                                              binder=binder)
            setattr(node, attribute, expanded)
        if keys:
            self.call_keys[node.id] = keys

    def _binder(self, node: Any, processed_nodes: Any, keys: Set[str]):
        def bind(call: Any, params: List[CallParam], values: List[Any]) -> List[Any]:
            keys.add(call.key)
            carried = self.arguments.get(call.key, {})
            new_carried: Dict[str, Any] = {}
            bound: List[Any] = []
            report = []
            for param, value in zip(params, values):
                if value is NULL:
                    step, source = STEP_NULL, None
                elif value is not MISSING:
                    step, source = STEP_PASSED, describe(value)
                    new_carried[param.name] = as_written(value)
                else:
                    value, step, source, original = self.resolve_left_out(
                        call, param, carried.get(param.name), node, processed_nodes
                    )
                    if step == STEP_EARLIER_CALL:
                        new_carried[param.name] = original
                bound.append(value)
                report.append({"name": param.name, "step": step, "source": source})
            self.arguments[call.key] = {**carried, **new_carried}
            self.records.append(self._record(call, node, report))
            return bound

        return bind

    def resolve_left_out(
        self, call: Any, param: CallParam, carried: Any, node: Any, processed_nodes: Any
    ) -> Tuple[Any, str, Optional[str], Any]:
        """Bind a left-out parameter (§2.3).

        Returns:
            ``(value, step, source, original expression for the carry-over)``.
        """
        if param.fallback:
            value = self._resolve(TriccReference(param.fallback), node, processed_nodes)
            if value is None:
                from tricc_oo.visitors.tricc import get_last_version

                value = get_last_version(param.fallback, processed_nodes)
            if value is not None:
                return value, STEP_FORM, param.fallback, None
        if carried is not None:
            value = self._resolve(as_written(carried), node, processed_nodes)
            if value is not None:
                return value, STEP_EARLIER_CALL, describe(carried), carried
        for code in param.retrievals[:1]:
            retrieval = self.add_retrieval(code, processed_nodes)
            if retrieval is not None:
                return TriccReference(code), STEP_RETRIEVAL, code, None
        logger.warning(f"{W_PARAM_NO_VALUE}: {_label(call)} in {node.get_name()}: {param.name!r} has no value")
        return NULL, STEP_NONE, None, None

    @staticmethod
    def _resolve(expr: Any, node: Any, processed_nodes: Any) -> Any:
        """``expr`` when every reference in it resolves here, else None."""
        from tricc_oo.visitors.tricc import process_operation_reference

        if not hasattr(expr, "get_references"):
            return expr
        if process_operation_reference(expr, node, processed_nodes, replace_reference=False) is False:
            return None
        return expr

    def add_retrieval(self, code: str, processed_nodes: Any) -> Any:
        """The retrieval node of ``code``, built and hung on the start page when new (§2.3 step 3)."""
        from tricc_oo.converters.retrieval import add_retrieval

        if self.project is None:
            return None
        node = add_retrieval(self.project, code)
        page = self.start_page
        if page is not None and node.id not in page.nodes:
            node.activity = page
            node.group = page
            page.nodes[node.id] = node
            page.calculates.append(node)
        if node not in processed_nodes:
            processed_nodes.add(node)
        return node

    def _record(self, call: Any, node: Any, parameters: List[Dict[str, Any]]) -> Dict[str, Any]:
        activity = getattr(node, "activity", None)
        return {
            "call": getattr(call, "name", None),
            "kind": "decision_table",
            "target": _target(call),
            "sources": ["decision_table"],
            "calculate": getattr(node, "name", None),
            "node": node.id,
            "activity": getattr(activity, "name", None) or getattr(activity, "id", None),
            "parameters": parameters,
        }


def _target(call: Any) -> Optional[str]:
    table = getattr(call, "table", None)
    if table is not None:
        return f"{table.id}.{table.outputs[call.out_at].name}"
    return getattr(call, "name", None)


def _label(call: Any) -> str:
    target = _target(call)
    name = getattr(call, "name", None)
    return f"{name}({target})" if target and target != name else str(name)


def write_data_needs(project: Any, out_dir: str, form: Optional[str] = None) -> Optional[str]:
    """Write ``<form>.data-needs.json`` next to the output (§4); nothing when no call was bound.

    Returns:
        The path written, or None.
    """
    records = list(getattr(project, "data_needs", None) or [])
    if not records:
        return None
    if not form:
        try:
            form = project.intervention_name()
        except Exception:
            form = None
    path = os.path.join(out_dir, f"{form or 'form'}.data-needs.json")
    os.makedirs(out_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump({"form": form, "calls": records}, file, indent=2, ensure_ascii=False)
    logger.info(f"data needs: {path} ({len(records)} calls)")
    return path
