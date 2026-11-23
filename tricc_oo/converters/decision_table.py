"""Expand ``DMN(table, …)`` calls into plain operations (feature/20261123-decision-tables.md).

A call becomes, by hit policy, an ``IFS`` (``first`` / ``unique``: the output of the first row
whose tests hold, empty when none) or a ``LIST_IF`` (``rule_order``: the outputs of every such
row, in row order), with one ``[and of the row's cell tests, output literal]`` pair per row.
Every output strategy serialises those two operators, so the dose is computed in the form when
its inputs are there, from the record otherwise, like any other calculation.

Arguments bind table inputs (feature/20261123-dmn-named-overrides.md):

- positionally, in input order (for an alias, by the alias' argument names);
- by name, through a trailing ``Tuple{ input: expr }``;
- an input left unbound reads its column ``concept``.

``null`` (and any literal) is evaluated at expansion: a row whose test fails on it is dropped,
a test that holds is removed, so no reference is created for it.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

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

_NULL = object()  # an argument bound to null


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
            if item.operator == TriccOperator.DMN or _call_name(item, known):
                return True
            stack.extend(item.reference or [])
    return False


def expand_decision_tables(
    expr: Any,
    tables: Dict[str, DecisionTable],
    aliases: Optional[Dict[str, FunctionAlias]] = None,
    used: Optional[Set[str]] = None,
) -> Any:
    """``expr`` with every table call replaced by its expansion (calls in arguments too).

    Args:
        expr: An operation, reference, literal or list of them.
        tables: The project's tables by id.
        aliases: The project's aliases (``DrugDosage`` is built in).
        used: Collects the ids of the tables called.

    Raises:
        DecisionTableError: A call cannot be expanded (unknown table, arguments, …).
    """
    known = effective_aliases(aliases)
    if not contains_table_call(expr, aliases):
        return expr
    return _expand(expr, tables, known, used if used is not None else set())


def _expand(expr: Any, tables, aliases, used) -> Any:
    if isinstance(expr, list):
        return [_expand(e, tables, aliases, used) for e in expr]
    if not isinstance(expr, TriccOperation):
        return expr
    reference = [_expand(r, tables, aliases, used) for r in expr.reference or []]
    name = _call_name(expr, aliases)
    if name is None:
        if expr.operator != TriccOperator.TUPLE and any(
            isinstance(r, TriccOperation) and r.operator == TriccOperator.TUPLE for r in reference
        ):
            raise DecisionTableError("E_DMN_ARG_UNKNOWN", "A Tuple{…} is only read as the last argument of DMN.")
        if any(a is not b for a, b in zip(reference, expr.reference or [])):
            copy = expr.copy()
            copy.reference = reference
            copy._invalidate_identity_cache()
            return copy
        return expr
    return expand_call(name, reference[1:], tables, aliases, used)


def _split_named(args: List[Any]) -> Tuple[List[Any], List[Tuple[str, Any]]]:
    if args and isinstance(args[-1], TriccOperation) and args[-1].operator == TriccOperator.TUPLE:
        flat = list(args[-1].reference or [])
        named = [(str(getattr(flat[i], "value", flat[i])), flat[i + 1]) for i in range(0, len(flat) - 1, 2)]
        return args[:-1], named
    return args, []


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
                "E_DMN_ARITY", f"{name} takes {len(alias.args)} arguments ({', '.join(alias.args)}); got {len(args)}."
            )
        bound.append((alias.args[i], arg))
    return alias.function, (args[table_at] if table_at < len(args) else None), bound


def expand_call(
    name: str, args: List[Any], tables: Dict[str, DecisionTable], aliases: Dict[str, FunctionAlias], used: Set[str]
) -> Any:
    """The expansion of one call ``name(args…)`` (arguments already expanded)."""
    args, named = _split_named(list(args))
    function, table_arg, bound = _bind(name, args, aliases)
    if not (isinstance(table_arg, TriccStatic) and isinstance(table_arg.value, str)):
        raise DecisionTableError(
            "E_DMN_TABLE_NOT_STATIC", f"{name}: the table must be a text literal such as 'diazepam', not {table_arg}."
        )
    table_id, _, output = table_arg.value.partition(".")
    table = tables.get(table_id)
    if table is None:
        known = ", ".join(sorted(tables)) or "none"
        raise DecisionTableError(
            "E_DMN_TABLE_UNKNOWN",
            f"{name}: no decision table {table_id!r} (tables: {known}). List tables/<id>.yaml files under "
            "decision_tables in tricc.yaml; python -m tricc_oo.tools.drugs_js_to_tables converts a CHT drugs.js.",
        )
    used.add(table_id)
    out_at = table.output_index(output or None)
    if out_at is None:
        raise DecisionTableError("E_DMN_TABLE_UNKNOWN", f"{name}: table {table_id!r} has no output {output!r}.")

    values: List[Any] = [None] * len(table.inputs)
    is_bound = [False] * len(table.inputs)
    positional = [v for k, v in bound if k is None]
    if len(positional) > len(table.inputs):
        raise DecisionTableError(
            "E_DMN_ARITY",
            f"{name}: table {table_id!r} has {len(table.inputs)} inputs "
            f"({', '.join(c.name for c in table.inputs)}); got {len(positional)} arguments.",
        )
    for i, value in enumerate(positional):
        values[i], is_bound[i] = value, True
    by_name = [("E_ALIAS_UNKNOWN_INPUT", k, v) for k, v in bound if k is not None]
    by_name += [("E_DMN_ARG_UNKNOWN", k, v) for k, v in named]
    for code, key, value in by_name:
        at = table.input_index(key)
        if at is None:
            raise DecisionTableError(code, f"{name}: table {table_id!r} has no input {key!r}.")
        if is_bound[at]:
            raise DecisionTableError("E_DMN_ARG_TWICE", f"{name}: input {key!r} of {table_id!r} is given twice.")
        values[at], is_bound[at] = value, True
    for i, column in enumerate(table.inputs):
        if is_bound[i]:
            if values[i] is None:
                values[i] = _NULL
            continue
        if not column.concept:
            raise DecisionTableError(
                "E_DMN_ARITY", f"{name}: input {column.name!r} of {table_id!r} has no argument and no concept."
            )
        values[i] = TriccReference(column.concept)

    policy = table.hit_policy
    if function == "DMNFirst":
        policy = "first"
    elif function == "DMNList":
        policy = "rule_order"
    return _expansion(table, values, out_at, policy)


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


def expand_node_tables(
    node: Any,
    tables: Dict[str, DecisionTable],
    aliases: Optional[Dict[str, FunctionAlias]] = None,
    used: Optional[Set[str]] = None,
) -> bool:
    """Expand the table calls of a node's expressions in place; ``True`` when one changed.

    ``node.reference`` is rebuilt from ``expression_reference`` so the walk waits for the inputs
    a call reads (including the column concepts of left-out inputs), and for no input bound to
    ``null``.

    Raises:
        DecisionTableError: With the node named in the message.
    """
    changed = False
    for attribute in EXPRESSION_ATTRIBUTES:
        expr = getattr(node, attribute, None)
        if not isinstance(expr, TriccOperation):
            continue
        try:
            expanded = expand_decision_tables(expr, tables, aliases, used)
        except DecisionTableError as exc:
            raise DecisionTableError(exc.code, f"{_node_label(node)} {attribute}: {exc.message}") from exc
        if expanded is not expr:
            setattr(node, attribute, expanded)
            changed = True
            if attribute == "expression_reference" and hasattr(expanded, "get_references"):
                node.reference = list(expanded.get_references())
    reference = getattr(node, "reference", None)
    if isinstance(reference, TriccOperation):
        expanded = expand_decision_tables(reference, tables, aliases, used)
        if expanded is not reference:
            node.reference = expanded
            changed = True
    return changed


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


def expand_project_tables(project: Any) -> Set[str]:
    """Expand every table call of a loaded project (pages and library calculates).

    Returns:
        The ids of the tables called. A table nobody calls is logged as a warning.
    """
    tables = getattr(project, "decision_tables", None) or {}
    aliases = getattr(project, "aliases", None) or {}
    used: Set[str] = set()
    nodes = list(iter_activity_nodes(list(project.pages.values()) + list(project.library_calculates or [])))
    for node in nodes:
        expand_node_tables(node, tables, aliases, used)
    for table_id in tables:
        if table_id not in used:
            logger.warning(f"decision table {table_id!r} is not called by any expression")
    return used
