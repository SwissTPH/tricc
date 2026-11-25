"""Decision tables: ``tables/<id>.yaml`` read by ``DMN(table, …)`` calls.

feature/20261123-decision-tables.md. The cell grammar, the hit policies, the error codes and the
shared test vectors (``tests/data/decision_tables/``) are identical to the DrawTRICC editor
(``tricc-frontend`` ``packages/core/src/decision-table/``): change both sides together.

Cells are a subset of FEEL unary tests:

=========================================  ======================================
Cell                                       Test
=========================================  ======================================
``-``                                      any value (no test)
``null`` / ``not(null)``                   empty / not empty
``< v``, ``<= v``, ``> v``, ``>= v``,      comparison / equality (``v`` a number,
``= v``, ``v``                             ``'text'``, ``true`` / ``false``)
``[a..b)``, ``(a..b]``, ``[a..b]``,        range, square bracket = inclusive
``(a..b)``
``a, b, c``                                any of
=========================================  ======================================
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Tuple, Union

import yaml

logger = logging.getLogger("default")

HIT_POLICIES = ("first", "unique", "rule_order")
TABLE_COLUMN_TYPES = ("string", "integer", "decimal", "boolean")
#: the table functions; ``DMN`` uses the table's hit policy, the others force one
TABLE_FUNCTIONS = ("DMN", "DMNFirst", "DMNList")

HitPolicy = Literal["first", "unique", "rule_order"]
ColumnType = Literal["string", "integer", "decimal", "boolean"]
CellValue = Union[float, int, str, bool]
#: an input value; ``None`` is "not entered"
InputValue = Optional[CellValue]


class DecisionTableError(ValueError):
    """A decision table or a call to one that cannot be exported.

    Attributes:
        code: The shared error code (``E_DMN_CELL``, ``E_DMN_ARITY``, …).
    """

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# ---------------------------------------------------------------- model


@dataclass
class TableColumn:
    """An input or output column.

    A call that leaves an input out binds it from its fallbacks
    (feature/20261125-calculate-functions.md §2.3): the latest value of ``concept``, an earlier
    call's argument, then the first of ``retrievals`` (``#code``).
    """

    name: str
    type: ColumnType = "string"
    concept: Optional[str] = None
    retrievals: List[str] = field(default_factory=list)


@dataclass
class DecisionTable:
    """One decision table: input columns, output columns and rules read top to bottom."""

    id: str
    inputs: List[TableColumn] = field(default_factory=list)
    outputs: List[TableColumn] = field(default_factory=list)
    rules: List[List[str]] = field(default_factory=list)
    hit_policy: HitPolicy = "first"
    title: Optional[str] = None

    def input_index(self, name: str) -> Optional[int]:
        for i, column in enumerate(self.inputs):
            if column.name == name:
                return i
        return None

    def output_index(self, name: Optional[str]) -> Optional[int]:
        if not name:
            return 0 if self.outputs else None
        for i, column in enumerate(self.outputs):
            if column.name == name:
                return i
        return None


@dataclass
class FunctionAlias:
    """``aliases.<Name>`` in ``tricc.yaml``: a call's arguments mapped to table inputs by name.

    ``table`` in ``args`` is the position of the table name.
    """

    function: str = "DMN"
    args: List[str] = field(default_factory=list)


#: ``DrugDosage`` keeps working when a project declares no alias of that name
BUILTIN_ALIASES: Dict[str, FunctionAlias] = {
    "DrugDosage": FunctionAlias(function="DMN", args=["table", "age", "weight"]),
}


def effective_aliases(aliases: Optional[Dict[str, FunctionAlias]]) -> Dict[str, FunctionAlias]:
    """The aliases in effect: the project's, over the built-in ones."""
    return {**BUILTIN_ALIASES, **(aliases or {})}


def decode_aliases(value: Any) -> Dict[str, FunctionAlias]:
    """Read ``tricc.yaml`` ``aliases``; entries with another function than a table one are skipped."""
    if not isinstance(value, dict):
        return {}
    out: Dict[str, FunctionAlias] = {}
    for name, raw in value.items():
        rec = raw if isinstance(raw, dict) else {}
        function = rec.get("function") or "DMN"
        if function not in TABLE_FUNCTIONS:
            logger.warning(f"tricc.yaml alias {name!r}: function {function!r} is not a table function, skipped")
            continue
        args = [a for a in rec.get("args") or [] if isinstance(a, str)]
        out[str(name)] = FunctionAlias(function=function, args=args)
    return out


# ---------------------------------------------------------------- file


def _cell_text(cell: Any) -> str:
    """An unquoted YAML cell reads as a number or a boolean; keep what was written."""
    if cell is None:
        return "null"
    if isinstance(cell, bool):
        return "true" if cell else "false"
    if isinstance(cell, float) and cell.is_integer():
        return str(int(cell))
    return str(cell)


def _decode_columns(value: Any, path: str, key: str) -> List[TableColumn]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise DecisionTableError("E_DMN_SHAPE", f"{path}: {key} must be a list of columns.")
    columns = []
    for i, entry in enumerate(value):
        rec = entry if isinstance(entry, dict) else {}
        name = rec.get("name")
        if not isinstance(name, str) or not name:
            raise DecisionTableError("E_DMN_SHAPE", f"{path}: {key} column {i + 1} has no name.")
        column_type = rec.get("type") or "string"
        if column_type not in TABLE_COLUMN_TYPES:
            raise DecisionTableError(
                "E_DMN_TYPE",
                f"{path}: column {name!r} has type {column_type!r}; use one of {', '.join(TABLE_COLUMN_TYPES)}.",
            )
        concept = rec.get("concept") if isinstance(rec.get("concept"), str) and rec.get("concept") else None
        retrievals = rec.get("retrievals") or []
        if isinstance(retrievals, str):
            retrievals = retrievals.split()
        if not isinstance(retrievals, list) or not all(isinstance(r, str) and r.startswith("#") for r in retrievals):
            raise DecisionTableError(
                "E_DMN_SHAPE", f"{path}: column {name!r} retrievals must be a list of '#code'."
            )
        columns.append(TableColumn(name=name, type=column_type, concept=concept, retrievals=list(retrievals)))
    return columns


def decode_table(doc: Any, path: str = "<table>") -> DecisionTable:
    """A table from its parsed YAML (or JSON) mapping.

    Raises:
        DecisionTableError: The mapping is not a table.
    """
    if not isinstance(doc, dict):
        raise DecisionTableError("E_DMN_SHAPE", f"{path} must be a mapping with id, inputs, outputs and rules.")
    table_id = doc.get("id").strip() if isinstance(doc.get("id"), str) else ""
    if not table_id:
        raise DecisionTableError("E_DMN_SHAPE", f"{path} has no id. Add \"id: <name>\" — the name DMN uses.")
    policy = doc.get("hit_policy") or "first"
    if policy not in HIT_POLICIES:
        raise DecisionTableError(
            "E_DMN_SHAPE", f"{path}: hit_policy {policy!r} is not one of {', '.join(HIT_POLICIES)}."
        )
    rules_raw = doc.get("rules") or []
    if not isinstance(rules_raw, list):
        raise DecisionTableError("E_DMN_SHAPE", f"{path}: rules must be a list of rows.")
    rules = []
    for i, row in enumerate(rules_raw):
        if not isinstance(row, list):
            raise DecisionTableError("E_DMN_SHAPE", f"{path}: rule {i + 1} must be a list of cells.")
        rules.append([_cell_text(c) for c in row])
    title = doc.get("title") if isinstance(doc.get("title"), str) and doc.get("title") else None
    return DecisionTable(
        id=table_id,
        title=title,
        hit_policy=policy,
        inputs=_decode_columns(doc.get("inputs"), path, "inputs"),
        outputs=_decode_columns(doc.get("outputs"), path, "outputs"),
        rules=rules,
    )


def read_table(text: str, path: str) -> DecisionTable:
    """Read a ``tables/<id>.yaml`` file and check it (cells, types, ``unique`` overlaps).

    Raises:
        DecisionTableError: The file is not a valid table.
    """
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DecisionTableError("E_DMN_SHAPE", f"{path} is not valid YAML ({exc}).") from exc
    table = decode_table(doc, path)
    problems = table_problems(table)
    if problems:
        first = problems[0]
        raise DecisionTableError(first.code, f"{path}: {first.located()}")
    return table


class _IndentDumper(yaml.SafeDumper):
    """Lists indented under their key, as the editor writes them."""

    def increase_indent(self, flow: bool = False, indentless: bool = False):
        return super().increase_indent(flow, False)


def encode_table(table: DecisionTable) -> str:
    """A table as the editor writes it: same key order, one rule per line, columns aligned."""
    import json

    def column(c: TableColumn) -> Dict[str, Any]:
        out: Dict[str, Any] = {"name": c.name}
        if c.concept:
            out["concept"] = c.concept
        out["type"] = c.type
        if c.retrievals:
            out["retrievals"] = list(c.retrievals)
        return out

    head: Dict[str, Any] = {"id": table.id}
    if table.title:
        head["title"] = table.title
    head["hit_policy"] = table.hit_policy
    head["inputs"] = [column(c) for c in table.inputs]
    head["outputs"] = [column(c) for c in table.outputs]
    text = yaml.dump(
        head, Dumper=_IndentDumper, sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000
    )
    if not table.rules:
        return text + "rules: []\n"
    text += "rules:\n"
    quoted = [[json.dumps(cell, ensure_ascii=False) for cell in rule] for rule in table.rules]
    widths: List[int] = []
    for row in quoted:
        for i, q in enumerate(row):
            if i >= len(widths):
                widths.append(0)
            widths[i] = max(widths[i], len(q))
    for row in quoted:
        last = len(row) - 1
        cells = [f"{q},".ljust(widths[i] + 2) if i < last else q for i, q in enumerate(row)]
        text += f"  - [{''.join(cells)}]\n"
    return text


# ---------------------------------------------------------------- cells


@dataclass(frozen=True)
class CellTest:
    """A parsed input cell.

    ``kind`` is ``any``, ``null`` (``negated`` for ``not(null)``), ``compare`` (``op``, ``value``),
    ``range`` (``low``, ``high``, ``low_in``, ``high_in``) or ``list`` (``items``).
    """

    kind: str
    negated: bool = False
    op: str = "="
    value: Any = None
    low: float = 0
    high: float = 0
    low_in: bool = True
    high_in: bool = False
    items: Tuple["CellTest", ...] = ()


_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
_COMPARE = re.compile(r"^(<=|>=|<|>|=)\s*(.+)$")
_RANGE = re.compile(r"^([\[(])\s*(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)\s*([\])])$")
_NOT_NULL = re.compile(r"^not\s*\(\s*null\s*\)$")


def _number(text: str) -> Union[int, float]:
    value = float(text)
    return int(value) if value.is_integer() and "." not in text else value


def parse_literal(text: str) -> Optional[CellValue]:
    """A number, ``'text'`` or a boolean; ``None`` when it is none of them."""
    if _NUMBER.match(text):
        return _number(text)
    if text == "true":
        return True
    if text == "false":
        return False
    quoted = re.match(r"^'((?:[^'\\]|\\.)*)'$", text) or re.match(r'^"((?:[^"\\]|\\.)*)"$', text)
    if quoted:
        return re.sub(r"\\(.)", r"\1", quoted.group(1))
    return None


def split_list(text: str) -> Optional[List[str]]:
    """Split ``a, b, c`` at top-level commas, outside quotes and brackets. ``None`` when unbalanced."""
    parts: List[str] = []
    depth = 0
    quote: Optional[str] = None
    start = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i].strip())
            start = i + 1
        i += 1
    if quote or depth != 0:
        return None
    parts.append(text[start:].strip())
    return parts


def _is_numeric(column_type: str) -> bool:
    return column_type in ("integer", "decimal")


def _show(value: CellValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return f"'{value}'" if isinstance(value, str) else str(value)


def _type_mismatch(value: CellValue, column_type: str) -> Optional[str]:
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if _is_numeric(column_type):
        return None if is_number else f"This column is {column_type}; {_show(value)} is not a number."
    if column_type == "boolean" and not isinstance(value, bool):
        return f"This column is yes/no; write true or false, not {_show(value)}."
    if column_type == "string" and not isinstance(value, str):
        return f"This column is text; write '{_show(value)}' with quotes."
    return None


def parse_cell(text: str, column_type: str) -> CellTest:
    """Parse an input cell against its column type.

    Raises:
        DecisionTableError: ``E_DMN_CELL`` (syntax) or ``E_DMN_TYPE`` (value vs column type).
    """
    cell = text.strip()
    if cell == "-":
        return CellTest("any")
    if cell == "":
        raise DecisionTableError("E_DMN_CELL", 'The cell is empty. Write - for "any value", or null for "not entered".')
    parts = split_list(cell)
    if parts is None:
        raise DecisionTableError("E_DMN_CELL", f'"{cell}" has an unclosed quote or bracket.')
    if len(parts) > 1:
        items = []
        for part in parts:
            if part == "-":
                raise DecisionTableError("E_DMN_CELL", '- cannot be one value of a list: it already means "any".')
            items.append(_parse_single(part, column_type))
        return CellTest("list", items=tuple(items))
    return _parse_single(cell, column_type)


def _parse_single(cell: str, column_type: str) -> CellTest:
    if cell == "":
        raise DecisionTableError("E_DMN_CELL", "A list has an empty value between two commas.")
    if cell == "null":
        return CellTest("null")
    if _NOT_NULL.match(cell):
        return CellTest("null", negated=True)
    rng = _RANGE.match(cell)
    if rng:
        if not _is_numeric(column_type):
            raise DecisionTableError("E_DMN_TYPE", f"A range needs a number column; this column is {column_type}.")
        low, high = _number(rng.group(2)), _number(rng.group(3))
        if low > high:
            raise DecisionTableError("E_DMN_CELL", f"The range {cell} is empty: {low} is above {high}.")
        return CellTest("range", low=low, high=high, low_in=rng.group(1) == "[", high_in=rng.group(4) == "]")
    if cell[0] in "[(":
        raise DecisionTableError(
            "E_DMN_CELL", f'"{cell}" is not a range. Write it as [3..6) — a square bracket includes the bound.'
        )
    cmp = _COMPARE.match(cell)
    op = cmp.group(1) if cmp else "="
    literal = parse_literal(cmp.group(2).strip() if cmp else cell)
    if literal is None:
        raise DecisionTableError(
            "E_DMN_CELL",
            f'"{cell}" is not a test. Use -, null, a comparison (>= 20), a range ([3..6)), a value '
            "(a number, 'text', true or false) or a list of them.",
        )
    mismatch = _type_mismatch(literal, column_type)
    if mismatch:
        raise DecisionTableError("E_DMN_TYPE", mismatch)
    if op != "=" and not _is_numeric(column_type):
        raise DecisionTableError("E_DMN_TYPE", f"{op} compares numbers; this column is {column_type}.")
    return CellTest("compare", op=op, value=literal)


def parse_output(text: str, column_type: str) -> CellValue:
    """An output cell as a value of the column type. Text is kept as written.

    Raises:
        DecisionTableError: ``E_DMN_TYPE``.
    """
    if column_type == "string":
        return text
    cell = text.strip()
    if _is_numeric(column_type):
        if not _NUMBER.match(cell):
            raise DecisionTableError("E_DMN_TYPE", f'This output is {column_type}; "{text}" is not a number.')
        value = _number(cell)
        if column_type == "integer" and not float(value).is_integer():
            raise DecisionTableError("E_DMN_TYPE", f"This output is a whole number; {cell} is not.")
        return int(value) if column_type == "integer" else value
    if cell in ("true", "false"):
        return cell == "true"
    raise DecisionTableError("E_DMN_TYPE", f'This output is yes/no; write true or false, not "{text}".')


def _equal(a: CellValue, b: CellValue) -> bool:
    """JavaScript ``===`` on cell values: a number never equals a text or a boolean."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, str) or isinstance(b, str):
        return isinstance(a, str) and isinstance(b, str) and a == b
    return a == b


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def cell_matches(test: CellTest, value: InputValue) -> bool:
    """Whether a value passes a test. ``None`` passes only ``-``, ``null`` and lists holding ``null``."""
    if test.kind == "any":
        return True
    if test.kind == "null":
        return value is not None if test.negated else value is None
    if test.kind == "list":
        return any(cell_matches(t, value) for t in test.items)
    if test.kind == "range":
        if not _is_number(value):
            return False
        above = value >= test.low if test.low_in else value > test.low
        below = value <= test.high if test.high_in else value < test.high
        return above and below
    if value is None:
        return False
    if test.op == "=":
        return _equal(value, test.value)
    if not _is_number(value) or not _is_number(test.value):
        return False
    return {"<": value < test.value, "<=": value <= test.value, ">": value > test.value, ">=": value >= test.value}[
        test.op
    ]


# ---------------------------------------------------------------- compile and check


@dataclass
class TableProblem:
    """One problem in a table, located on a row (0-based) and a column (inputs, then outputs)."""

    code: str
    message: str
    row: Optional[int] = None
    column: Optional[int] = None

    def located(self) -> str:
        where = []
        if self.row is not None:
            where.append(f"row {self.row + 1}")
        if self.column is not None:
            where.append(f"column {self.column + 1}")
        return f"{', '.join(where)}: {self.message}" if where else self.message


@dataclass
class CompiledRow:
    """A row's parsed tests (one per input) and output values; ``None`` where a cell is invalid."""

    tests: List[Optional[CellTest]]
    outputs: List[Optional[CellValue]]
    valid: bool = True


@dataclass
class CompiledTable:
    table: DecisionTable
    rows: List[CompiledRow]
    problems: List[TableProblem]


def compile_table(table: DecisionTable) -> CompiledTable:
    """Parse every cell once. Problems are returned, never raised."""
    problems: List[TableProblem] = []
    width = len(table.inputs) + len(table.outputs)
    rows = []
    for r, rule in enumerate(table.rules):
        valid = True
        if len(rule) != width:
            valid = False
            problems.append(
                TableProblem(
                    "E_DMN_SHAPE",
                    f"Row {r + 1} has {len(rule)} cells; the table has {len(table.inputs)} inputs and "
                    f"{len(table.outputs)} outputs ({width} cells).",
                    row=r,
                )
            )
        tests: List[Optional[CellTest]] = []
        for i, column in enumerate(table.inputs):
            try:
                tests.append(parse_cell(rule[i] if i < len(rule) else "", column.type))
            except DecisionTableError as exc:
                valid = False
                tests.append(None)
                problems.append(TableProblem(exc.code, exc.message, row=r, column=i))
        outputs: List[Optional[CellValue]] = []
        for j, column in enumerate(table.outputs):
            at = len(table.inputs) + j
            try:
                outputs.append(parse_output(rule[at] if at < len(rule) else "", column.type))
            except DecisionTableError as exc:
                valid = False
                outputs.append(None)
                problems.append(TableProblem(exc.code, exc.message, row=r, column=at))
        rows.append(CompiledRow(tests=tests, outputs=outputs, valid=valid))
    return CompiledTable(table=table, rows=rows, problems=problems)


def table_problems(table: DecisionTable, list_values: Optional[bool] = None) -> List[TableProblem]:
    """Problems of the table alone: cell syntax and types, and for ``unique``, rows that can both match.

    Args:
        table: The table.
        list_values: Check list results read by XPath (a value with a space reads as two);
            defaults to the table being ``rule_order``.
    """
    compiled = compile_table(table)
    problems = list(compiled.problems)
    if table.hit_policy == "unique":
        problems.extend(_overlaps(compiled))
    if table.hit_policy == "rule_order" if list_values is None else list_values:
        for r, row in enumerate(compiled.rows):
            for j, value in enumerate(row.outputs):
                if isinstance(value, str) and re.search(r"\s", value.strip()):
                    column = len(table.inputs) + j
                    problems.append(TableProblem("E_DMN_LIST_VALUE", list_value_message(value), r, column))
    return problems


def list_value_message(value: str) -> str:
    return (
        f'"{value}" has a space. A list result is a space-separated list in CHT and ODK, so it would read '
        "as several values. Use a code without spaces."
    )


# overlap (hit policy unique) ------------------------------------------------------------


@dataclass
class _Interval:
    low: float
    high: float
    low_in: bool
    high_in: bool


@dataclass
class _ValueSet:
    null: bool = False
    all: bool = False
    intervals: List[_Interval] = field(default_factory=list)
    points: set = field(default_factory=set)


def _value_set(test: CellTest) -> _ValueSet:
    out = _ValueSet()

    def add(t: CellTest) -> None:
        if t.kind == "any":
            out.null = out.all = True
        elif t.kind == "null":
            if t.negated:
                out.all = True
            else:
                out.null = True
        elif t.kind == "list":
            for item in t.items:
                add(item)
        elif t.kind == "range":
            out.intervals.append(_Interval(t.low, t.high, t.low_in, t.high_in))
        elif not _is_number(t.value):
            out.points.add(f"{type(t.value).__name__}:{t.value}")
        else:
            v, inf = t.value, math.inf
            out.intervals.append(
                {
                    "=": _Interval(v, v, True, True),
                    "<": _Interval(-inf, v, False, False),
                    "<=": _Interval(-inf, v, False, True),
                    ">": _Interval(v, inf, False, False),
                    ">=": _Interval(v, inf, True, False),
                }[t.op]
            )

    add(test)
    return out


def _intervals_meet(a: _Interval, b: _Interval) -> bool:
    if a.high < b.low or b.high < a.low:
        return False
    if a.high == b.low:
        return a.high_in and b.low_in
    if b.high == a.low:
        return b.high_in and a.low_in
    return True


def _non_empty(s: _ValueSet) -> bool:
    return s.all or bool(s.intervals) or bool(s.points)


def tests_overlap(a: CellTest, b: CellTest) -> bool:
    """Whether some value passes both tests."""
    x, y = _value_set(a), _value_set(b)
    if x.null and y.null:
        return True
    if (x.all and _non_empty(y)) or (y.all and _non_empty(x)):
        return True
    if any(_intervals_meet(i, j) for i in x.intervals for j in y.intervals):
        return True
    return bool(x.points & y.points)


def _overlaps(compiled: CompiledTable) -> List[TableProblem]:
    problems = []
    rows = compiled.rows
    for a in range(len(rows)):
        for b in range(a + 1, len(rows)):
            x, y = rows[a].tests, rows[b].tests
            if any(t is None for t in x) or any(t is None for t in y):
                continue
            if all(tests_overlap(t, y[i]) for i, t in enumerate(x)):
                problems.append(
                    TableProblem(
                        "E_DMN_OVERLAP",
                        f"Rows {a + 1} and {b + 1} can both match, so the table is not unique. Narrow one of "
                        'them, or make the hit policy "first".',
                        row=b,
                    )
                )
    return problems


# ---------------------------------------------------------------- evaluate (tests, parity)


def normalize_input(value: InputValue, column: TableColumn) -> InputValue:
    """An input as the table tests it: a whole-number column rounds down first."""
    if column.type == "integer" and _is_number(value):
        return math.floor(value)
    return value


def matching_rows(table: Union[DecisionTable, CompiledTable], inputs: Sequence[InputValue]) -> List[int]:
    """The rows whose every input test passes, in row order. Invalid rows never match."""
    compiled = table if isinstance(table, CompiledTable) else compile_table(table)
    columns = compiled.table.inputs
    values = [normalize_input(inputs[i] if i < len(inputs) else None, c) for i, c in enumerate(columns)]
    return [
        r
        for r, row in enumerate(compiled.rows)
        if row.valid and all(t is not None and cell_matches(t, values[i]) for i, t in enumerate(row.tests))
    ]


def evaluate_table(
    table: DecisionTable, inputs: Sequence[InputValue], policy: Optional[str] = None
) -> Tuple[List[int], Union[List[Optional[CellValue]], List[List[Optional[CellValue]]]]]:
    """The table's result for these inputs (in input order): ``(matching rows, value)``.

    ``value`` is the output values of the first match (empty when none) for ``first`` / ``unique``,
    the values of every match for ``rule_order``. The same semantics as the expansion.
    """
    compiled = compile_table(table)
    matches = matching_rows(compiled, inputs)
    if (policy or table.hit_policy) == "rule_order":
        return matches, [compiled.rows[r].outputs for r in matches]
    return matches, (compiled.rows[matches[0]].outputs if matches else [])


def unused_tables(tables: Dict[str, DecisionTable], used: Iterable[str]) -> List[str]:
    """Ids of the tables no call uses."""
    used_set = set(used)
    return [t for t in tables if t not in used_set]
