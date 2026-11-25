"""A decision table as an ODK secondary instance, read by an XPath predicate.

feature/20261123-dmn-instance-lookup.md. A table too large to write inline becomes the choice
list ``dmn_<table>``: one item per row (per value of a list cell), with flag and bound columns
per input and one column per output. The predicate is the same for every item, so each
argument appears once per test kind instead of once per row:

``instance('dmn_t')/root/item[pred][1]/o0`` (``first``, ``unique``) or
``join(' ', instance('dmn_t')/root/item[pred]/o0)`` (``rule_order``).

pyxform leaves empty cells out of an item, so a bound is only read when its flag says it is set.
"""

from __future__ import annotations

import itertools
import re
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from tricc_oo.models.decision_table import (
    CellTest,
    CellValue,
    DecisionTable,
    DecisionTableError,
    compile_table,
    tests_overlap,
)

LIST_PREFIX = "dmn_"

#: input test kinds (column ``i<k>_k``)
ANY, NULL, NOT_NULL, EQUAL, TRUE, FALSE, RANGE = "a", "n", "v", "e", "t", "f", "r"
#: bound kinds (columns ``i<k>_lo_k`` / ``i<k>_hi_k``)
NO_BOUND, INCLUSIVE, EXCLUSIVE = "n", "i", "x"


def list_name(table_id: str) -> str:
    """The choice list and instance id of a table: ``dmn_<table>``."""
    return LIST_PREFIX + re.sub(r"[^A-Za-z0-9_]", "_", table_id)


def valid_row_count(table: DecisionTable) -> int:
    """The rows a call can match (the size compared with the inline threshold)."""
    return sum(1 for row in compile_table(table).rows if row.valid)


def _number(value: CellValue) -> str:
    if isinstance(value, float):
        text = format(value, "f").rstrip("0").rstrip(".")
        return text if text not in ("", "-0") else "0"
    return str(value)


def _value(value: Optional[CellValue]) -> str:
    """An output cell as the instance holds it (booleans as 1 / 0, like the XLSForm literals)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return _number(value)
    return str(value)


def _encode_test(test: Optional[CellTest], k: int) -> Dict[str, str]:
    p = f"i{k}_"
    if test is None or test.kind == "any":
        return {p + "k": ANY}
    if test.kind == "null":
        return {p + "k": NOT_NULL if test.negated else NULL}
    if test.kind == "range":
        return {
            p + "k": RANGE,
            p + "lo_k": INCLUSIVE if test.low_in else EXCLUSIVE,
            p + "lo": _number(test.low),
            p + "hi_k": INCLUSIVE if test.high_in else EXCLUSIVE,
            p + "hi": _number(test.high),
        }
    value = test.value
    if isinstance(value, bool):
        return {p + "k": TRUE if value else FALSE}
    if isinstance(value, str):
        return {p + "k": EQUAL, p + "eq": value}
    low = high = (NO_BOUND, "")
    if test.op in ("=", ">", ">="):
        low = (INCLUSIVE if test.op != ">" else EXCLUSIVE, _number(value))
    if test.op in ("=", "<", "<="):
        high = (INCLUSIVE if test.op != "<" else EXCLUSIVE, _number(value))
    cells = {p + "k": RANGE, p + "lo_k": low[0], p + "hi_k": high[0]}
    if low[1]:
        cells[p + "lo"] = low[1]
    if high[1]:
        cells[p + "hi"] = high[1]
    return cells


def _alternatives(test: Optional[CellTest]) -> List[Optional[CellTest]]:
    return list(test.items) if test is not None and test.kind == "list" else [test]


def instance_items(table: DecisionTable, policy: str = "first") -> List[Dict[str, str]]:
    """The items of the table's list, in row order: ``name`` then the ``i<k>_*`` and ``o<j>`` columns.

    Raises:
        DecisionTableError: ``E_DMN_LIST_OVERLAP`` when, under ``rule_order``, two values of one
            list cell can both match (the row's output would be listed twice).
    """
    items: List[Dict[str, str]] = []
    for r, row in enumerate(compile_table(table).rows):
        if not row.valid:
            continue
        options = [_alternatives(t) for t in row.tests]
        if policy == "rule_order":
            for k, alternatives in enumerate(options):
                for a, b in itertools.combinations(alternatives, 2):
                    if a is not None and b is not None and tests_overlap(a, b):
                        raise DecisionTableError(
                            "E_DMN_LIST_OVERLAP",
                            f"table {table.id!r} row {r + 1}, input {table.inputs[k].name!r}: two values of the "
                            "list can both match, so a list result would hold the row twice. Split the row.",
                        )
        combos = list(itertools.product(*options))
        for n, combo in enumerate(combos):
            item = {"name": f"r{r}" if len(combos) == 1 else f"r{r}_{n}"}
            for k, test in enumerate(combo):
                item.update(_encode_test(test, k))
            for j, value in enumerate(row.outputs):
                item[f"o{j}"] = _value(value)
            items.append(item)
    return items


def item_columns(table: DecisionTable) -> List[str]:
    """Every column the items can have, in a stable order."""
    columns = []
    for k in range(len(table.inputs)):
        columns += [f"i{k}_{c}" for c in ("k", "lo_k", "lo", "hi_k", "hi", "eq")]
    return columns + [f"o{j}" for j in range(len(table.outputs))]


def _bound(items: Sequence[Dict[str, str]], column: str, number: str, ops: Tuple[str, str]) -> Optional[str]:
    """The test on one bound, from the bound kinds the items use (``None``: always holds)."""
    kinds: Set[str] = {i[column + "_k"] for i in items if column + "_k" in i}
    parts = []
    for kind, op in ((INCLUSIVE, ops[0]), (EXCLUSIVE, ops[1])):
        if kind in kinds:
            test = f"{number}{op}{column}"
            parts.append(test if len(kinds) == 1 else f"({column}_k='{kind}' and {test})")
    if not parts:
        return None
    if NO_BOUND in kinds:
        parts.insert(0, f"{column}_k='{NO_BOUND}'")
    return parts[0] if len(parts) == 1 else f"({' or '.join(parts)})"


def input_predicate(
    items: Sequence[Dict[str, str]],
    k: int,
    raw: str,
    number: str,
    boolean_test: Callable[[bool], str],
) -> Optional[str]:
    """The test of input ``k`` on an item; ``None`` when every item accepts any value.

    Args:
        items: The table's items (``instance_items``).
        raw: The argument as an XPath expression (empty when not entered).
        number: The argument as a number (``int(raw)`` for an integer column).
        boolean_test: The XLSForm test "argument equals true / false".
    """
    p = f"i{k}_"
    kinds = {i[p + "k"] for i in items}
    if kinds <= {ANY}:
        return None
    branches: List[Tuple[str, Optional[str]]] = []  # (kind, test; None: the kind alone)
    if ANY in kinds:
        branches.append((ANY, None))
    if NULL in kinds:
        branches.append((NULL, f"{raw}=''"))
    if NOT_NULL in kinds:
        branches.append((NOT_NULL, f"{raw}!=''"))
    if EQUAL in kinds:
        branches.append((EQUAL, f"{raw}={p}eq"))
    if TRUE in kinds:
        branches.append((TRUE, boolean_test(True)))
    if FALSE in kinds:
        branches.append((FALSE, boolean_test(False)))
    if RANGE in kinds:
        rows = [i for i in items if i[p + "k"] == RANGE]
        tests = [f"{raw}!=''"]
        for column, ops in ((p + "lo", (">=", ">")), (p + "hi", ("<=", "<"))):
            bound = _bound(rows, column, number, ops)
            if bound:
                tests.append(bound)
        branches.append((RANGE, " and ".join(tests)))
    if len(branches) == 1:
        return f"({branches[0][1]})"
    parts = [f"{p}k='{kind}'" if test is None else f"({p}k='{kind}' and {test})" for kind, test in branches]
    return f"({' or '.join(parts)})"


def lookup_expression(
    table: DecisionTable,
    policy: str,
    output: str,
    arguments: Sequence[Tuple[str, str, Callable[[bool], str]]],
) -> str:
    """The XPath reading the table's instance.

    Args:
        arguments: Per input ``(raw, number, boolean_test)`` (see ``input_predicate``).
    """
    items = instance_items(table, policy)
    tests = [
        t
        for t in (input_predicate(items, k, raw, number, bt) for k, (raw, number, bt) in enumerate(arguments))
        if t
    ]
    out = f"o{table.output_index(output) or 0}"
    path = f"instance('{list_name(table.id)}')/root/item"
    predicate = f"[{' and '.join(tests)}]" if tests else ""
    if policy == "rule_order":
        return f"join(' ', {path}{predicate}/{out})"
    return f"{path}{predicate}[1]/{out}"
