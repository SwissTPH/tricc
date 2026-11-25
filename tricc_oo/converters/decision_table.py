"""Expand ``DMN(table, …)`` calls into plain operations (feature/20261123-decision-tables.md).

A call becomes, by hit policy, an ``IFS`` (``first`` / ``unique``: the output of the first row
whose tests hold, empty when none) or a ``LIST_IF`` (``rule_order``: the outputs of every such
row, in row order), with one ``[and of the row's cell tests, output literal]`` pair per row.
Every output strategy serialises those two operators, so the dose is computed in the form when
its inputs are there, from the record otherwise, like any other calculation.

Arguments bind table inputs (feature/20261123-dmn-named-overrides.md):

- positionally, in input order (for an alias, by the alias' argument names);
- by name, through a trailing ``Tuple{ input: expr }``;
- an input left out is bound when the node holding the call is instantiated, from its fallbacks
  (column ``concept``, an earlier call, a listed retrieval; feature/20261125-calculate-functions.md
  §2.3). Outside a walk (:func:`expand_decision_tables` with no binder) it reads its ``concept``.

The calls stay in the expressions while the graph is walked (:func:`check_project_tables` only
checks them): only the passed arguments make the walk wait.

``null`` (and any literal) is evaluated at expansion: a row whose test fails on it is dropped,
a test that holds is removed, so no reference is created for it.

``Zscore(table, sex, x, y)`` / ``Izscore(table, sex, x, z)`` are expanded here too: three
lookups of the LMS table (``'t.l'``, ``'t.m'``, ``'t.s'``) in the WHO formula, written with the
arithmetic operators (``POWER`` for the exponent). A table id the project does not define is
looked up among the WHO tables that ship with TRICC (feature/20261123-dmn-instance-lookup.md).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from tricc_oo.converters.call_binding import (
    E_CALL_ARG_UNKNOWN,
    E_CALL_ARITY,
    MISSING,
    NULL,
    CallParam,
    bind_arguments,
    is_named_arguments,
    split_named,
)
from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference, TriccStatic
from tricc_oo.models.decision_table import (
    TABLE_FUNCTIONS,
    CellTest,
    DecisionTable,
    DecisionTableError,
    FunctionAlias,
    cell_matches,
    compile_table,
    effective_aliases,
    normalize_input,
)

logger = logging.getLogger("default")

#: node attributes that may hold an expression
EXPRESSION_ATTRIBUTES = (
    "expression_reference",
    "expression",
    "relevance",
    "trigger",
    "default",
    "applicability",
    "remote_reference",
)

_NULL = NULL  # an argument bound to null

#: a table this large written inline (strategies that do not keep the calls, e.g. FHIR) is logged
INLINE_WARNING_ROWS = 50

_ZSCORE_OPERATORS = (TriccOperator.ZSCORE, TriccOperator.IZSCORE)


def resolve_table(table_id: str, tables: Dict[str, DecisionTable]) -> Optional[DecisionTable]:
    """The project's table ``table_id``, else the built-in LMS table of that id (added to ``tables``)."""
    table = tables.get(table_id)
    if table is None:
        from tricc_oo.data.anthro import builtin_decision_table

        table = builtin_decision_table(table_id)
        if table is not None:
            tables[table_id] = table
    return table


def _call_name(op: TriccOperation, aliases: Dict[str, FunctionAlias]) -> Optional[str]:
    """The table function or alias name of a call, ``None`` when ``op`` is not one."""
    if not op.reference:
        return None
    head = op.reference[0]
    if op.operator == TriccOperator.DMN:
        return head.value if isinstance(head, TriccStatic) else str(head)
    if op.operator == TriccOperator.NATIVE:
        name = head.value if isinstance(head, TriccStatic) else head
        if isinstance(name, str):
            name = name.strip("'`")
            if name in aliases:
                return name
    return None


def contains_table_call(expr: Any, aliases: Optional[Dict[str, FunctionAlias]] = None) -> bool:
    """Whether an expression holds a ``DMN`` call (or an alias of one)."""
    known = effective_aliases(aliases)
    stack = [expr]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, TriccOperation):
            if item.operator in (TriccOperator.DMN, *_ZSCORE_OPERATORS) or _call_name(item, known):
                return True
            stack.extend(item.reference or [])
    return False


@dataclass
class TableCall:
    """A table call with its arguments bound to the table inputs (not yet expanded).

    Attributes:
        name: The function or alias called (``DMN``, ``DrugDosage``…).
        table: The table read.
        out_at: The index of the output read.
        policy: The hit policy in effect.
        values: One per input: the passed value, ``NULL`` or ``MISSING`` (left out).
    """

    name: str
    table: DecisionTable
    out_at: int
    policy: str
    values: List[Any]

    @property
    def key(self) -> str:
        """The carry-over key (§2.6): same table and output."""
        return f"DMN:{self.table.id}.{self.table.outputs[self.out_at].name}"

    @property
    def params(self) -> List[CallParam]:
        """The table inputs as call parameters (the column concept is the fallback)."""
        return [
            CallParam(name=c.name, type=c.type, fallback=c.concept, retrievals=tuple(c.retrievals or ()))
            for c in self.table.inputs
        ]


#: ``binder(call, params, values) -> values``: binds the left-out (``MISSING``) parameters of a
#: call (feature/20261125-calculate-functions.md §2.3) and may record how each was bound
Binder = Callable[[Any, List[CallParam], List[Any]], List[Any]]


def bind_left_out_to_fallback(call: Any, params: List[CallParam], values: List[Any]) -> List[Any]:
    """The binder used outside a walk: a left-out parameter reads its fallback concept.

    With no fallback concept it has no value (``W_PARAM_NO_VALUE``).
    """
    bound = []
    for param, value in zip(params, values):
        if value is MISSING:
            if param.fallback:
                value = TriccReference(param.fallback)
            else:
                logger.warning(f"W_PARAM_NO_VALUE: {getattr(call, 'name', call)}: {param.name!r} has no value")
                value = _NULL
        bound.append(value)
    return bound


def expand_decision_tables(
    expr: Any,
    tables: Dict[str, DecisionTable],
    aliases: Optional[Dict[str, FunctionAlias]] = None,
    used: Optional[Set[str]] = None,
    keep_calls: bool = False,
    binder: Optional[Binder] = None,
) -> Any:
    """``expr`` with every table call replaced by its expansion (calls in arguments too).

    Args:
        expr: An operation, reference, literal or list of them.
        tables: The project's tables by id.
        aliases: The project's aliases (``DrugDosage`` is built in).
        used: Collects the ids of the tables called.
        keep_calls: Wrap each expansion that is not a constant in ``DMN_CALL`` (inline
            expansion, table, policy, output, one argument per input), for a strategy that
            evaluates the tables itself.
        binder: Binds the left-out inputs; default :func:`bind_left_out_to_fallback`.

    Raises:
        DecisionTableError: A call cannot be expanded (unknown table, arguments, …).
    """
    known = effective_aliases(aliases)
    if not contains_table_call(expr, aliases):
        return expr
    return _expand(expr, tables, known, used if used is not None else set(), keep_calls, binder)


def _expand(expr: Any, tables, aliases, used, keep_calls=False, binder=None) -> Any:
    if isinstance(expr, list):
        return [_expand(e, tables, aliases, used, keep_calls, binder) for e in expr]
    if not isinstance(expr, TriccOperation):
        return expr
    reference = [_expand(r, tables, aliases, used, keep_calls, binder) for r in expr.reference or []]
    if expr.operator in _ZSCORE_OPERATORS:
        return _expand_zscore(expr.operator, reference, tables, aliases, used, keep_calls, binder)
    name = _call_name(expr, aliases)
    if name is None:
        _check_tuple_position(expr, reference)
        if any(a is not b for a, b in zip(reference, expr.reference or [])):
            copy = expr.copy()
            copy.reference = reference
            copy._invalidate_identity_cache()
            return copy
        return expr
    return expand_call(name, reference[1:], tables, aliases, used, keep_calls, binder)


def _check_tuple_position(expr: TriccOperation, reference: List[Any]) -> None:
    if expr.operator != TriccOperator.TUPLE and any(is_named_arguments(r) for r in reference):
        if expr.operator == TriccOperator.NATIVE and reference and isinstance(reference[0], str):
            return  # a function call: its own binding reads the Tuple
        raise DecisionTableError(E_CALL_ARG_UNKNOWN, "A Tuple{…} is only read as the last argument of a call.")


def _zscore_arguments(operator, args) -> Tuple[str, str, List[Any]]:
    name = "Zscore" if operator == TriccOperator.ZSCORE else "Izscore"
    if len(args) != 4:
        raise DecisionTableError(E_CALL_ARITY, f"{name}(table, sex, x, value) takes 4 arguments; got {len(args)}.")
    table_arg = args[0]
    if not (isinstance(table_arg, TriccStatic) and isinstance(table_arg.value, str)):
        raise DecisionTableError(
            "E_DMN_TABLE_NOT_STATIC", f"{name}: the table must be a text literal such as 'wfa', not {table_arg}."
        )
    return name, table_arg.value.strip().strip("'\""), list(args[1:])


def _expand_zscore(operator, args, tables, aliases, used, keep_calls, binder=None) -> TriccOperation:
    """The WHO LMS formula, each of l, m, s a table lookup.

    ``Zscore``: ``((y / m)^l - 1) / (s * l)``; ``Izscore``: ``m * (z * s * l + 1)^(1 / l)``.
    """
    _, table_id, (sex, x, value) = _zscore_arguments(operator, args)
    lms = [
        expand_call(
            "DMNFirst", [TriccStatic(value=f"{table_id}.{out}"), sex, x], tables, aliases, used, keep_calls, binder
        )
        for out in ("l", "m", "s")
    ]
    ll, m, s = lms
    one = TriccStatic(value=1)
    if operator == TriccOperator.ZSCORE:
        ratio = TriccOperation(TriccOperator.DIVIDED, [value, m])
        top = TriccOperation(TriccOperator.MINUS, [TriccOperation(TriccOperator.POWER, [ratio, ll]), one])
        return TriccOperation(TriccOperator.DIVIDED, [top, TriccOperation(TriccOperator.MULTIPLIED, [s, ll])])
    base = TriccOperation(TriccOperator.PLUS, [TriccOperation(TriccOperator.MULTIPLIED, [value, s, ll]), one])
    exponent = TriccOperation(TriccOperator.DIVIDED, [one, ll])
    return TriccOperation(TriccOperator.MULTIPLIED, [m, TriccOperation(TriccOperator.POWER, [base, exponent])])


def _bind(
    name: str, args: List[Any], aliases: Dict[str, FunctionAlias]
) -> Tuple[str, Any, List[Tuple[Optional[str], Any]]]:
    """``(function, table argument, [(input name or None for positional, value)])``."""
    if name in TABLE_FUNCTIONS:
        return name, (args[0] if args else None), [(None, a) for a in args[1:]]
    alias = aliases[name]
    table_at = alias.args.index("table") if "table" in alias.args else 0
    bound: List[Tuple[Optional[str], Any]] = []
    for i, arg in enumerate(args):
        if i == table_at:
            continue
        if i >= len(alias.args):
            raise DecisionTableError(
                E_CALL_ARITY, f"{name} takes {len(alias.args)} arguments ({', '.join(alias.args)}); got {len(args)}."
            )
        bound.append((alias.args[i], arg))
    return alias.function, (args[table_at] if table_at < len(args) else None), bound


def bind_table_call(
    name: str,
    args: List[Any],
    tables: Dict[str, DecisionTable],
    aliases: Dict[str, FunctionAlias],
    used: Optional[Set[str]] = None,
) -> TableCall:
    """Bind the arguments of one call ``name(args…)`` to the table inputs (no expansion).

    Args:
        name: ``DMN``, ``DMNFirst``, ``DMNList`` or an alias (in ``aliases``).
        args: The arguments after the function name.
        tables: The project's tables by id (a built-in table is added when called).
        aliases: The aliases in effect.
        used: Collects the id of the table called.

    Raises:
        DecisionTableError: Unknown table or output, table not a literal, ``E_CALL_*``.
    """
    args, named = split_named(list(args))
    function, table_arg, bound = _bind(name, args, aliases)
    if not (isinstance(table_arg, TriccStatic) and isinstance(table_arg.value, str)):
        raise DecisionTableError(
            "E_DMN_TABLE_NOT_STATIC", f"{name}: the table must be a text literal such as 'diazepam', not {table_arg}."
        )
    table_id, _, output = table_arg.value.partition(".")
    table = resolve_table(table_id, tables)
    if table is None:
        known = ", ".join(sorted(tables)) or "none"
        raise DecisionTableError(
            "E_DMN_TABLE_UNKNOWN",
            f"{name}: no decision table {table_id!r} (tables: {known}). List tables/<id>.yaml files under "
            "decision_tables in tricc.yaml; python -m tricc_oo.tools.drugs_js_to_tables converts a CHT drugs.js.",
        )
    if used is not None:
        used.add(table_id)
    out_at = table.output_index(output or None)
    if out_at is None:
        raise DecisionTableError("E_DMN_TABLE_UNKNOWN", f"{name}: table {table_id!r} has no output {output!r}.")
    by_name = [("E_ALIAS_UNKNOWN_INPUT", k, v) for k, v in bound if k is not None]
    by_name += [(E_CALL_ARG_UNKNOWN, k, v) for k, v in named]
    values = bind_arguments(
        name,
        [c.name for c in table.inputs],
        [v for k, v in bound if k is None],
        by_name,
        error=DecisionTableError,
        owner=f"table {table_id!r}",
    )
    policy = table.hit_policy
    if function == "DMNFirst":
        policy = "first"
    elif function == "DMNList":
        policy = "rule_order"
    return TableCall(name=name, table=table, out_at=out_at, policy=policy, values=values)


def expand_bound_call(call: TableCall, keep_calls: bool = False) -> Any:
    """The expansion of a call whose every input is bound (a value or ``NULL``)."""
    table = call.table
    values = [_NULL if v is NULL or v is MISSING else v for v in call.values]
    expansion = _expansion(table, values, call.out_at, call.policy)
    if not keep_calls and len(table.rules) > INLINE_WARNING_ROWS:
        logger.warning(
            f"decision table {table.id!r} ({len(table.rules)} rows) is written inline: the expression is "
            "long (feature/20261123-dmn-instance-lookup.md)"
        )
    if not keep_calls or isinstance(expansion, TriccStatic):
        return expansion
    call_args = [TriccStatic(value="") if v is _NULL else v for v in values]
    head = [
        TriccStatic(value=table.id),
        TriccStatic(value=call.policy),
        TriccStatic(value=table.outputs[call.out_at].name),
    ]
    return TriccOperation(TriccOperator.DMN_CALL, [expansion, *head, *call_args])


def expand_call(
    name: str,
    args: List[Any],
    tables: Dict[str, DecisionTable],
    aliases: Dict[str, FunctionAlias],
    used: Set[str],
    keep_calls: bool = False,
    binder: Optional[Binder] = None,
) -> Any:
    """The expansion of one call ``name(args…)`` (arguments already expanded).

    The left-out inputs are bound by ``binder`` (default: their fallback concept).
    """
    call = bind_table_call(name, args, tables, aliases, used)
    call.values = (binder or bind_left_out_to_fallback)(call, call.params, list(call.values))
    return expand_bound_call(call, keep_calls)


def _static(value: Any) -> Tuple[bool, Any]:
    """``(True, python value)`` when the argument is a literal or null."""
    if value is _NULL:
        return True, None
    if isinstance(value, TriccStatic) and isinstance(value.value, (str, int, float, bool)):
        return True, value.value
    return False, None


def _and(items: List[Any]) -> Any:
    return items[0] if len(items) == 1 else TriccOperation(TriccOperator.AND, items)


def _test_operation(test: CellTest, value: Any) -> Any:
    if test.kind == "null":
        return TriccOperation(TriccOperator.ISNOTNULL if test.negated else TriccOperator.ISNULL, [value])
    if test.kind == "list":
        return TriccOperation(TriccOperator.OR, [_test_operation(t, value) for t in test.items])
    if test.kind == "range":
        low = TriccOperator.MORE_OR_EQUAL if test.low_in else TriccOperator.MORE
        high = TriccOperator.LESS_OR_EQUAL if test.high_in else TriccOperator.LESS
        return _and(
            [
                TriccOperation(low, [value, TriccStatic(value=test.low)]),
                TriccOperation(high, [value, TriccStatic(value=test.high)]),
            ]
        )
    operator = {
        "=": TriccOperator.EQUAL,
        "<": TriccOperator.LESS,
        "<=": TriccOperator.LESS_OR_EQUAL,
        ">": TriccOperator.MORE,
        ">=": TriccOperator.MORE_OR_EQUAL,
    }[test.op]
    return TriccOperation(operator, [value, TriccStatic(value=test.value)])


def _expansion(table: DecisionTable, values: List[Any], out_at: int, policy: str) -> Any:
    compiled = compile_table(table)
    operands = []
    for i, column in enumerate(table.inputs):
        static, literal = _static(values[i])
        if static:
            operands.append((True, normalize_input(literal, column)))
        elif column.type == "integer":
            operands.append((False, TriccOperation(TriccOperator.FLOOR, [values[i]])))
        else:
            operands.append((False, values[i]))

    rows: List[Tuple[Optional[Any], Any]] = []  # (condition or None when it always holds, output)
    for row in compiled.rows:
        if not row.valid:
            continue
        conditions = []
        possible = True
        for i, test in enumerate(row.tests):
            static, operand = operands[i]
            if test.kind == "any":
                continue
            if static:
                if not cell_matches(test, operand):
                    possible = False
                    break
                continue
            conditions.append(_test_operation(test, operand))
        if possible:
            rows.append((_and(conditions) if conditions else None, TriccStatic(value=row.outputs[out_at])))

    if policy == "rule_order":
        if not rows:
            logger.warning(f"decision table {table.id!r}: no row can match these arguments")
        items = [[cond, value] if cond is not None else value for cond, value in rows]
        return TriccOperation(TriccOperator.LIST_IF, items)
    pairs = []
    for cond, value in rows:
        if cond is None:
            return TriccOperation(TriccOperator.IFS, [*pairs, value]) if pairs else value
        pairs.append([cond, value])
    if not pairs:
        logger.warning(f"decision table {table.id!r}: no row can match these arguments")
        return TriccStatic(value="")
    return TriccOperation(TriccOperator.IFS, pairs)


# ---------------------------------------------------------------- nodes


def check_table_calls(
    expr: Any,
    tables: Dict[str, DecisionTable],
    aliases: Optional[Dict[str, FunctionAlias]] = None,
    used: Optional[Set[str]] = None,
) -> None:
    """Check every table call of an expression; the calls are left as they are (§2.2, load).

    Raises:
        DecisionTableError: Unknown table or output, table not a literal, ``E_CALL_*``.
    """
    known = effective_aliases(aliases)
    stack = [expr]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
            continue
        if not isinstance(item, TriccOperation):
            continue
        reference = list(item.reference or [])
        stack.extend(reference)
        if item.operator in _ZSCORE_OPERATORS:
            _, table_id, (sex, x, _value) = _zscore_arguments(item.operator, reference)
            for out in ("l", "m", "s"):
                bind_table_call("DMNFirst", [TriccStatic(value=f"{table_id}.{out}"), sex, x], tables, known, used)
            continue
        name = _call_name(item, known)
        if name is None:
            _check_tuple_position(item, reference)
            continue
        bind_table_call(name, reference[1:], tables, known, used)


def check_node_tables(
    node: Any,
    tables: Dict[str, DecisionTable],
    aliases: Optional[Dict[str, FunctionAlias]] = None,
    used: Optional[Set[str]] = None,
) -> None:
    """Check the table calls of a node's expressions (they stay calls until instantiation).

    Raises:
        DecisionTableError: With the node named in the message.
    """
    for attribute in (*EXPRESSION_ATTRIBUTES, "reference"):
        expr = getattr(node, attribute, None)
        if not isinstance(expr, TriccOperation):
            continue
        try:
            check_table_calls(expr, tables, aliases, used)
        except DecisionTableError as exc:
            raise DecisionTableError(exc.code, f"{_node_label(node)} {attribute}: {exc.message}") from exc


def _node_label(node: Any) -> str:
    name = getattr(node, "name", None) or getattr(node, "id", "?")
    activity = getattr(getattr(node, "activity", None), "name", None)
    return f"node {name!r}" + (f" ({activity})" if activity else "")


def iter_activity_nodes(pages: Iterable[Any]) -> Iterable[Any]:
    """Every node of these activities, nested activities included, each once."""
    seen: Set[int] = set()
    stack = list(pages)
    while stack:
        item = stack.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        yield item
        nodes = getattr(item, "nodes", None)
        if isinstance(nodes, dict):
            stack.extend(nodes.values())


def check_project_tables(project: Any) -> Set[str]:
    """Check every table call of a loaded project (pages and library calculates).

    The calls stay in the expressions: they are bound and expanded when the node holding them
    is instantiated (feature/20261125-calculate-functions.md §2.2).

    Returns:
        The ids of the tables called. A table nobody calls is logged as a warning.
    """
    if not getattr(project, "decision_tables", None):
        project.decision_tables = {}  # a dict of its own: built-in tables are added when called
    tables = project.decision_tables
    declared = list(tables)
    aliases = getattr(project, "aliases", None) or {}
    used: Set[str] = set()
    nodes = list(iter_activity_nodes(list(project.pages.values()) + list(project.library_calculates or [])))
    for node in nodes:
        check_node_tables(node, tables, aliases, used)
    for table_id in declared:
        if table_id not in used:
            logger.warning(f"decision table {table_id!r} is not called by any expression")
    listed = {r: t for t in used for c in tables[t].inputs for r in c.retrievals}
    if listed:
        from tricc_oo.converters.retrieval import read_project_retrievals

        available = read_project_retrievals(project)
        unknown = sorted(code for code in listed if code not in available)
        if unknown:
            raise DecisionTableError(
                "E_PARAM_RETRIEVAL_UNKNOWN",
                f"table {listed[unknown[0]]!r} lists retrieval {', '.join(unknown)}, not in the retrieval dictionary.",
            )
    return used
