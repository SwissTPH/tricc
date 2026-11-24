"""Turn a CHT ``drugs.js`` (``DrugDosage`` lookups) into one decision table per drug.

feature/20261123-decision-tables.md, phase 3. ``drugs.js`` holds two tables of steps per drug,
``{lower bound: dose}`` by weight (kg) and by age (months); a step applies from its key up to
the next key, and the weight wins when it is entered and gives a dose. Each drug becomes
``tables/<drug>.yaml`` with hit policy ``first``: the weight rows (age ``-``), then the age rows
(weight ``-``), so the age rows also catch a weight below the first step, as ``drugs.js`` does.
Doses are kept as text (``"-"``, ``"1/2"``, ``"5ml (2.5ml in each thigh)"``).

Usage::

    python -m tricc_oo.tools.drugs_js_to_tables drugs.js tables/ \\
        [--weight-concept CHE.B6.DE07] [--age-concept age_in_months]

then list the folder in ``tricc.yaml``::

    decision_tables:
      - tables/*.yaml

``DrugDosage('<drug>', age, weight)`` calls keep working: it is a built-in alias of ``DMN``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence

from tricc_oo.models.decision_table import DecisionTable, TableColumn, encode_table, table_problems

logger = logging.getLogger("default")

DEFAULT_WEIGHT_CONCEPT = "CHE.B6.DE07"
DEFAULT_AGE_CONCEPT = "age_in_months"
#: the four ``const`` arrays drugs.js declares (``drugesAge`` is spelled so in the source)
ARRAYS = ("dosesWeightClasses", "dosesAgeClasses", "drugsWeight", "drugesAge")


def _strip_comments(source: str) -> str:
    out = []
    i, quote = 0, None
    while i < len(source):
        ch = source[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < len(source):
                out.append(source[i + 1])
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
            out.append(ch)
        elif source.startswith("//", i):
            while i < len(source) and source[i] != "\n":
                i += 1
            continue
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = len(source) if end < 0 else end + 2
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _array_literal(source: str, name: str) -> str:
    match = re.search(rf"\bconst\s+{name}\s*=\s*\[", source)
    if not match:
        raise ValueError(f"drugs.js has no `const {name} = [...]`")
    start = match.end() - 1
    depth, quote = 0, None
    for i in range(start, len(source)):
        ch = source[i]
        if quote:
            if ch == "\\":
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise ValueError(f"`const {name}` in drugs.js is not closed")


def _js_to_json(literal: str) -> Any:
    """A JS array / object literal of numbers and strings (unquoted keys allowed) as Python."""
    text = re.sub(r"'((?:[^'\\]|\\.)*)'", lambda m: json.dumps(m.group(1)), literal)
    text = re.sub(r'([{,]\s*)([A-Za-z_$][\w$]*|-?\d+(?:\.\d+)?)\s*:', r'\1"\2":', text)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return json.loads(text)


def read_drugs_js(source: str) -> Dict[str, Any]:
    """The four arrays of a drugs.js source."""
    clean = _strip_comments(source)
    return {name: _js_to_json(_array_literal(clean, name)) for name in ARRAYS}


def _dose_text(value: Any) -> str:
    """``String(value)`` as JavaScript prints it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def step_rows(steps: Dict[str, Any]) -> List[List[str]]:
    """``{3: a, 6: b}`` → ``[3..6)`` a, ``>= 6`` b. Keys are lower bounds, as drugs.js reads them."""
    keys = sorted(steps, key=float)
    rows = []
    for i, key in enumerate(keys):
        cell = f">= {key}" if i + 1 == len(keys) else f"[{key}..{keys[i + 1]})"
        rows.append([cell, _dose_text(steps[key])])
    return rows


def drug_tables(
    data: Dict[str, Any], weight_concept: str = DEFAULT_WEIGHT_CONCEPT, age_concept: str = DEFAULT_AGE_CONCEPT
) -> List[DecisionTable]:
    """One table per drug, sorted by drug name: weight rows, then age rows."""
    by_weight, by_age = data["drugsWeight"], data["drugesAge"]
    tables = []
    for drug in sorted(set(by_weight) | set(by_age)):
        rules: List[List[str]] = []
        if drug in by_weight:
            for cell, dose in step_rows(data["dosesWeightClasses"][by_weight.index(drug)][drug]):
                rules.append([cell, "-", dose])
        if drug in by_age:
            for cell, dose in step_rows(data["dosesAgeClasses"][by_age.index(drug)][drug]):
                rules.append(["-", cell, dose])
        tables.append(
            DecisionTable(
                id=drug,
                hit_policy="first",
                inputs=[
                    TableColumn(name="weight", concept=weight_concept, type="decimal"),
                    TableColumn(name="age", concept=age_concept, type="integer"),
                ],
                outputs=[TableColumn(name="dose", type="string")],
                rules=rules,
            )
        )
    return tables


def write_tables(tables: Sequence[DecisionTable], out_dir: str) -> List[str]:
    """Write ``<out_dir>/<id>.yaml`` for each table; returns the paths.

    Raises:
        ValueError: A table would not load (a cell the drugs.js data cannot express).
    """
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for table in tables:
        problems = table_problems(table)
        if problems:
            raise ValueError(f"{table.id}: {problems[0].located()}")
        path = os.path.join(out_dir, f"{table.id}.yaml")
        with open(path, "w", encoding="utf-8") as file:
            file.write(encode_table(table))
        paths.append(path)
    return paths


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("drugs_js", help="path to drugs.js")
    parser.add_argument("out_dir", help="folder for the <drug>.yaml tables")
    parser.add_argument("--weight-concept", default=DEFAULT_WEIGHT_CONCEPT)
    parser.add_argument("--age-concept", default=DEFAULT_AGE_CONCEPT)
    args = parser.parse_args(argv)
    with open(args.drugs_js, encoding="utf-8") as file:
        data = read_drugs_js(file.read())
    paths = write_tables(drug_tables(data, args.weight_concept, args.age_concept), args.out_dir)
    logging.basicConfig(level=logging.INFO)
    logger.info(f"wrote {len(paths)} decision tables to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
