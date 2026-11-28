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

from dataclasses import dataclass

from tricc_oo.converters.call_binding import (
    E_CALL_ARG_UNKNOWN,
    MISSING,
    NULL,
    CallParam,
    TriccParameterReference,
    bind_arguments,
    is_named_arguments,
    split_named,
    substitute_parameters,
)
from tricc_oo.converters.decision_table import (
    EXPRESSION_ATTRIBUTES,
    check_node_tables,
    check_project_tables,
    contains_table_call,
    expand_decision_tables,
    iter_activity_nodes,
)
from tricc_oo.models.base import TriccNodeBaseModel, TriccOperation, TriccOperator, TriccReference, TriccStatic

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

E_FUNCTION_UNKNOWN = "E_FUNCTION_UNKNOWN"
E_PARAM_FALLBACK_UNKNOWN = "E_PARAM_FALLBACK_UNKNOWN"
E_PARAM_RETRIEVAL_UNKNOWN = "E_PARAM_RETRIEVAL_UNKNOWN"
W_FUNCTION_NAME_SHARED = "W_FUNCTION_NAME_SHARED"
#: nested function calls deeper than this are taken for a recursion (out of scope, §Part I)
MAX_CALL_DEPTH = 16


@dataclass
class FunctionCall:
    """A call of a calculate function with its arguments bound to the parameters.

    Attributes:
        name: The function name as called.
        signature: The function (``cql_library.FunctionSignature``).
        values: One per parameter: the passed value, ``NULL`` or ``MISSING``.
    """

    name: str
    signature: Any
    values: List[Any]
    kind: str = "function"

    @property
    def key(self) -> str:
        """The carry-over key (§2.6): the same function."""
        return f"F:{self.signature.name}"

    @property
    def params(self) -> List[CallParam]:
        return self.signature.call_params

    @property
    def sources(self) -> List[str]:
        return list(self.signature.sources)


def function_name(op: Any) -> Optional[str]:
    """The name of the function a ``native`` operation calls, else None."""
    if isinstance(op, TriccOperation) and op.operator == TriccOperator.NATIVE and op.reference:
        head = op.reference[0]
        name = head.value if isinstance(head, TriccStatic) else head
        if isinstance(name, str):
            return name.strip("'`\"")
    return None


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
        signatures = getattr(project, "function_signatures", None) or {}
        #: the functions with a body, by lower-case name (a declaration is called as written)
        self.functions: Dict[str, Any] = {n.lower(): f for n, f in signatures.items() if f.body is not None}
        #: wrap each expanded function call in FUNCTION_CALL (FHIR writes a Helper function)
        self.function_calls = bool(getattr(project, "function_calls", False))
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
        self.check_node_functions(node)

    def function_of(self, op: Any) -> Any:
        """The function (with a body) ``op`` calls, else None."""
        name = function_name(op)
        return self.functions.get(name.lower()) if name else None

    def bind_function_call(self, op: TriccOperation, args: Optional[List[Any]] = None) -> FunctionCall:
        """Bind the arguments of a function call to its parameters (no fallback yet).

        Raises:
            FunctionError: ``E_CALL_*``.
        """
        from tricc_oo.converters.cql_library import FunctionError

        signature = self.function_of(op)
        name = function_name(op)
        positional, named = split_named(list(op.reference[1:] if args is None else args))
        values = bind_arguments(
            name,
            signature.param_names,
            positional,
            [(E_CALL_ARG_UNKNOWN, k, v) for k, v in named],
            error=FunctionError,
            owner=f"function {signature.name!r}",
        )
        return FunctionCall(name=name, signature=signature, values=values)

    def check_node_functions(self, node: Any) -> None:
        """Check the function calls of a node (§2.2, load).

        Raises:
            FunctionError: ``E_CALL_*``, ``E_FUNCTION_UNKNOWN`` (named arguments to a function the
                project does not define), with the node named.
        """
        from tricc_oo.converters.cql_library import FunctionError
        from tricc_oo.converters.decision_table import _call_name, _node_label
        from tricc_oo.models.decision_table import effective_aliases

        aliases = effective_aliases(self.aliases)
        for attribute in CALL_ATTRIBUTES:
            stack = [getattr(node, attribute, None)]
            while stack:
                item = stack.pop()
                if isinstance(item, list):
                    stack.extend(item)
                    continue
                if not isinstance(item, TriccOperation):
                    continue
                stack.extend(item.reference or [])
                name = function_name(item)
                if name is None or _call_name(item, aliases):
                    continue
                try:
                    if self.function_of(item) is not None:
                        self.bind_function_call(item)
                    elif any(is_named_arguments(r) for r in item.reference[1:]):
                        raise FunctionError(
                            E_FUNCTION_UNKNOWN, f"{name}(…, Tuple{{…}}): no function {name!r} in the project"
                        )
                except FunctionError as exc:
                    raise FunctionError(exc.code, f"{_node_label(node)} {attribute}: {exc.message}") from exc

    # ------------------------------------------------------------ queries

    def has_calls(self, node: Any) -> bool:
        """Whether one of the node's expressions holds a call."""
        return any(self._expr_has_calls(getattr(node, a, None)) for a in CALL_ATTRIBUTES)

    def _expr_has_calls(self, expr: Any) -> bool:
        return isinstance(expr, TriccOperation) and (
            contains_table_call(expr, self.aliases) or self._contains_function_call(expr)
        )

    def _contains_function_call(self, expr: Any) -> bool:
        if not self.functions:
            return False
        stack = [expr]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, TriccOperation):
                if self.function_of(item) is not None:
                    return True
                stack.extend(item.reference or [])
        return False

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

        stack = [expr]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, TriccOperation):
                if self.function_of(item) is not None:
                    keys.add(f"F:{self.function_of(item).name}")
                stack.extend(item.reference or [])
        try:
            expand_decision_tables(expr, dict(self.tables), self.aliases, binder=record)
        except ValueError:
            pass

    def drop_same_call_versions(self, node: Any, prev_versions: List[Any]) -> List[Any]:
        """The previous versions to inherit from: not those calling the same function (table and
        output) as ``node``, whose arguments the later call carries over (§3, version inheritance)."""
        keys = self.node_call_keys(node)
        if not keys:
            return prev_versions
        return [p for p in prev_versions if not (keys & self.node_call_keys(p))]

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
            expanded = self._expand_functions(expr, node, processed_nodes, binder, 0)

            def table_binder(call, params, values, binder=binder):
                values = binder(call, params, values)
                if len(call.table.rules) <= 1:
                    return values
                # a calculated argument is read once per row: its own calculate (§2.4)
                return [self.sub_calculate(node, call, p.name, v, processed_nodes) for p, v in zip(params, values)]

            expanded = expand_decision_tables(
                expanded, self.tables, self.aliases, keep_calls=self.keep_calls, binder=table_binder
            )
            setattr(node, attribute, expanded)
        if keys:
            self.call_keys[node.id] = keys

    def _expand_functions(self, expr: Any, node: Any, processed_nodes: Any, binder, depth: int) -> Any:
        """``expr`` with every function call bound and replaced by its body (§2.3, §3)."""
        if isinstance(expr, list):
            return [self._expand_functions(e, node, processed_nodes, binder, depth) for e in expr]
        if not isinstance(expr, TriccOperation):
            return expr
        signature = self.function_of(expr)
        if signature is None:
            reference = [self._expand_functions(r, node, processed_nodes, binder, depth) for r in expr.reference or []]
            if any(a is not b for a, b in zip(reference, expr.reference or [])):
                copy = TriccOperation(expr.operator, reference)
                copy.retrieves_stored_data = expr.retrieves_stored_data
                return copy
            return expr
        if depth >= MAX_CALL_DEPTH:
            raise ValueError(f"{signature.name}: functions that call themselves are not supported")
        # arguments are expanded first (a call in an argument), as written otherwise
        args = [self._expand_functions(r, node, processed_nodes, binder, depth) for r in expr.reference[1:]]
        call = self.bind_function_call(expr, args)
        values = binder(call, call.params, list(call.values))
        return self.expand_function(call, values, node, processed_nodes, binder, depth)

    def expand_function(self, call: FunctionCall, values: List[Any], node: Any, processed_nodes: Any,
                        binder=None, depth: int = 0) -> Any:
        """The body of ``call`` with its bound arguments (a calculated argument used more than
        once becomes a sub-calculate); a pure function of constants folds to a constant."""
        signature = call.signature
        uses = _parameter_uses(signature.body)
        arguments = {}
        for param, value in zip(call.params, values):
            if value is NULL or value is MISSING:
                value = None
            elif uses.get(param.name.lower(), 0) > 1:
                value = self.sub_calculate(node, call, param.name, value, processed_nodes)
            arguments[param.name.lower()] = value
        expansion = fold_nulls(substitute_parameters(signature.body, arguments))
        if expansion is None:
            expansion = TriccStatic(value="")  # no value, as a table call matching no row
        if binder is not None and self._contains_function_call(expansion):
            expansion = self._expand_functions(expansion, node, processed_nodes, binder, depth + 1)
        if not signature.retrieve and all(v is None or isinstance(v, TriccStatic) for v in arguments.values()):
            folded = _fold(expansion)
            if folded is not None:
                return folded
        if self.function_calls:
            args = [TriccStatic(value="") if v is None else v for v in arguments.values()]
            return TriccOperation(TriccOperator.FUNCTION_CALL, [expansion, TriccStatic(value=signature.name), *args])
        return expansion

    def sub_calculate(self, node: Any, call: Any, param: str, value: Any, processed_nodes: Any) -> Any:
        """A calculated argument as its own calculate, owned by the call (§2.4).

        It is not walked: it is instantiated here, with the call, and hung on the node's activity
        so every output writes it once. A reference, a node or a literal is returned as it is.
        """
        if not isinstance(value, TriccOperation):
            return value
        from tricc_oo.converters.utils import clean_name, generate_id
        from tricc_oo.models.calculate import TriccNodeCalculate
        from tricc_oo.visitors.tricc import process_reference

        target = _target(call) or "call"
        name = clean_name(f"{node.name}_{target}_{param}".replace(".", "_")).lower()
        sub = TriccNodeCalculate(
            id=generate_id(f"sub:{node.id}:{call.key}:{param}:{len(self.records)}"),
            name=name,
            label=f"{param} of {target} for {node.get_name()}",
            expression=value,
            activity=node.activity,
            group=node.group,
            path_len=node.path_len,
        )
        process_reference(sub, processed_nodes, {}, replace_reference=True)
        sub.is_sequence_defined = True
        node.activity.nodes[sub.id] = sub
        node.activity.calculates.append(sub)
        processed_nodes.add(sub)
        logger.debug(f"sub-calculate {name} for {param!r} of {target} in {node.get_name()}")
        return sub

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
            "kind": getattr(call, "kind", "decision_table"),
            "target": _target(call),
            "sources": getattr(call, "sources", None) or ["decision_table"],
            "calculate": getattr(node, "name", None),
            "node": node.id,
            "activity": getattr(activity, "name", None) or getattr(activity, "id", None),
            "parameters": parameters,
        }


def _target(call: Any) -> Optional[str]:
    table = getattr(call, "table", None)
    if table is not None:
        return f"{table.id}.{table.outputs[call.out_at].name}"
    signature = getattr(call, "signature", None)
    return signature.name if signature is not None else getattr(call, "name", None)


def _parameter_uses(body: Any) -> Dict[str, int]:
    """How many times each parameter (lower case) appears in a body."""
    uses: Dict[str, int] = {}
    stack = [body]
    while stack:
        item = stack.pop()
        if isinstance(item, TriccParameterReference):
            uses[item.value.lower()] = uses.get(item.value.lower(), 0) + 1
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, TriccOperation):
            stack.extend(item.reference or [])
    return uses


_NULL_SAFE = {
    TriccOperator.ISNULL: True,
    TriccOperator.ISNOTNULL: False,
}


def fold_nulls(expr: Any) -> Any:
    """Fold the ``null`` arguments of an expanded body away (CQL null semantics), so no output
    has to write a null operand: ``Coalesce`` skips them, ``is null`` is decided, an ``if`` on
    null takes its ``else``, ``and`` / ``or`` drop them, any other operator on null is null.

    Returns:
        The folded expression; None when it is null.
    """
    if isinstance(expr, list):
        return [fold_nulls(e) for e in expr]
    if not isinstance(expr, TriccOperation):
        return expr
    refs = [fold_nulls(r) for r in expr.reference or []]
    operator = expr.operator
    if None not in refs:
        if any(a is not b for a, b in zip(refs, expr.reference or [])):
            copy = TriccOperation(operator, refs)
            copy.retrieves_stored_data = expr.retrieves_stored_data
            return copy
        return expr
    if operator in _NULL_SAFE and len(refs) == 1:
        return TriccStatic(_NULL_SAFE[operator])
    if operator in (TriccOperator.COALESCE, TriccOperator.AND, TriccOperator.OR):
        kept = [r for r in refs if r is not None]
        if not kept:
            return None
        return kept[0] if len(kept) == 1 else TriccOperation(operator, kept)
    if operator == TriccOperator.IF and len(refs) == 3:
        return refs[2] if refs[0] is None else TriccOperation(operator, refs)
    if operator in (TriccOperator.IFS, TriccOperator.CASE, TriccOperator.IF, TriccOperator.NATIVE):
        return TriccOperation(operator, [TriccStatic(value="") if r is None else r for r in refs])
    return None


def _fold(expansion: Any) -> Optional[TriccStatic]:
    """The value of a constant expansion (a pure function of constants), else None."""
    from tricc_oo.visitors.constant_eval import evaluate_constant

    if isinstance(expansion, TriccStatic):
        return expansion
    try:
        value = evaluate_constant(expansion)
    except Exception:
        return None
    return value if value is not None else None


def check_project_calls(project: Any) -> None:
    """Check the calls and the parameter metadata of a loaded project (§2.2, §5).

    Raises:
        DecisionTableError: An invalid table call.
        FunctionError: An invalid function call, ``E_PARAM_FALLBACK_UNKNOWN``,
            ``E_PARAM_RETRIEVAL_UNKNOWN``.
    """
    from tricc_oo.converters.cql_library import FunctionError
    from tricc_oo.converters.datadictionnary import lookup_codesystems_code

    check_project_tables(project)
    state = getattr(project, "call_state", None) or CallState(project)
    nodes = list(iter_activity_nodes(list(project.pages.values()) + list(project.library_calculates or [])))
    names = {getattr(n, "name", None) for n in nodes} - {None}
    for node in nodes:
        state.check_node_functions(node)
    retrievals = None
    for function in (getattr(project, "function_signatures", None) or {}).values():
        if function.name in names or function.name.lower() in {str(n).lower() for n in names}:
            logger.warning(
                f"{W_FUNCTION_NAME_SHARED}: function {function.name!r} has the name of a calculate or define; "
                "a call is always written with ()"
            )
        for param in function.params:
            if param.fallback and param.fallback not in names and not lookup_codesystems_code(
                getattr(project, "code_systems", None) or {}, param.fallback
            ):
                raise FunctionError(
                    E_PARAM_FALLBACK_UNKNOWN,
                    f"function {function.name!r}: parameter {param.name!r} falls back to {param.fallback!r}, "
                    "neither a concept nor a node of the project",
                )
            if param.retrievals:
                if retrievals is None:
                    from tricc_oo.converters.retrieval import read_project_retrievals

                    retrievals = read_project_retrievals(project)
                unknown = [r for r in param.retrievals if r not in retrievals]
                if unknown:
                    raise FunctionError(
                        E_PARAM_RETRIEVAL_UNKNOWN,
                        f"function {function.name!r}: parameter {param.name!r} lists retrieval "
                        f"{', '.join(unknown)}, not in the retrieval dictionary",
                    )


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


E_FUNCTION_NOT_EXPORTABLE = "E_FUNCTION_NOT_EXPORTABLE"


def inline_function_call(operation: TriccOperation, serialise: Callable[[Any], str], strategy: str) -> str:
    """Write a kept function call (``FUNCTION_CALL``) as its expanded body.

    Raises:
        FunctionError: ``E_FUNCTION_NOT_EXPORTABLE`` when the strategy cannot write the body.
    """
    from tricc_oo.converters.cql_library import FunctionError

    name = function_call_name(operation)
    try:
        return serialise(operation.reference[0])
    except (NotImplementedError, KeyError, AttributeError) as exc:
        raise FunctionError(
            E_FUNCTION_NOT_EXPORTABLE, f"function {name!r}: {strategy} cannot write its body ({exc})"
        ) from exc


def function_call_name(operation: TriccOperation) -> str:
    """The function name of a kept function call (``FUNCTION_CALL``)."""
    head = operation.reference[1] if len(operation.reference or []) > 1 else None
    return str(getattr(head, "value", head))


def function_call_arguments(operation: TriccOperation) -> List[Any]:
    """The bound arguments of a kept function call, ``None`` for no value."""
    return [None if a == TriccStatic(value="") else a for a in (operation.reference or [])[2:]]
