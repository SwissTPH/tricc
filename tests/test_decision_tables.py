"""Decision tables: ``DMN(table, …)``, ``DMNFirst``, ``DMNList``, aliases and named overrides.

feature/20261123-decision-tables.md (RFC #85) and feature/20261123-dmn-named-overrides.md
(RFC #96). The vectors in ``tests/data/decision_tables/`` are copies of the DrawTRICC ones
(``tricc-frontend`` ``packages/core/src/decision-table/__vectors__/``): keep them identical.

Run with:
    python -m pytest tests/test_decision_tables.py -v
"""

from __future__ import annotations

import glob
import json
import logging
import math
import os
import shutil
import subprocess

import pandas as pd
import pytest

from tests.helpers import load_yaml_project
from tricc_oo.converters.cql_to_operation import transform_cql_to_operation
from tricc_oo.converters.decision_table import expand_decision_tables
from tricc_oo.models.base import TriccOperator, TriccReference, TriccStatic
from tricc_oo.models.decision_table import (
    DecisionTable,
    DecisionTableError,
    FunctionAlias,
    cell_matches,
    decode_aliases,
    decode_table,
    encode_table,
    evaluate_table,
    parse_cell,
    read_table,
    table_problems,
)
from tricc_oo.models.project_config import TriccProjectConfig
from tricc_oo.runner import run_project_build
from tricc_oo.serializers.dmn_js import build_dmn_js, library_name
from tricc_oo.tools.drugs_js_to_tables import drug_tables, read_drugs_js, write_tables

HERE = os.path.dirname(__file__)
VECTORS = os.path.join(HERE, "data", "decision_tables")
PROJECT = os.path.join(HERE, "data", "projects", "decision_tables")
DRUGS_JS = os.path.join(VECTORS, "drugs.cjs")
TABLE_FILE = os.path.join(PROJECT, "tables", "diazepam.yaml")
YAML_FIXTURE = os.path.join(HERE, "data", "yaml", "content_version.yaml")


def _load(name):
    with open(os.path.join(VECTORS, name), encoding="utf-8") as file:
        return json.load(file)


CELLS = _load("cells.json")["cases"]
TABLES = _load("tables.json")
DIAZEPAM = decode_table(TABLES["tables"]["diazepam"], "diazepam")
TABLE_MAP = {"diazepam": DIAZEPAM}


# ---------------------------------------------------------------- a tiny evaluator


def run(expr, env):
    """Evaluate an expanded expression; ``None`` is "not entered", as the forms read it."""
    if isinstance(expr, TriccStatic):
        return expr.value
    if isinstance(expr, TriccReference):
        return env.get(expr.value)
    op = expr.operator
    refs = expr.reference
    if op == TriccOperator.AND:
        return all(run(r, env) for r in refs)
    if op == TriccOperator.OR:
        return any(run(r, env) for r in refs)
    if op == TriccOperator.ISNULL:
        return run(refs[0], env) is None
    if op == TriccOperator.ISNOTNULL:
        return run(refs[0], env) is not None
    if op == TriccOperator.FLOOR:
        value = run(refs[0], env)
        return None if value is None else math.floor(value)
    if op in (
        TriccOperator.EQUAL,
        TriccOperator.LESS,
        TriccOperator.LESS_OR_EQUAL,
        TriccOperator.MORE,
        TriccOperator.MORE_OR_EQUAL,
    ):
        left, right = run(refs[0], env), run(refs[1], env)
        if left is None or right is None:
            return False
        return {
            TriccOperator.EQUAL: left == right,
            TriccOperator.LESS: left < right,
            TriccOperator.LESS_OR_EQUAL: left <= right,
            TriccOperator.MORE: left > right,
            TriccOperator.MORE_OR_EQUAL: left >= right,
        }[op]
    if op == TriccOperator.IFS:
        for item in refs:
            if not isinstance(item, list):
                return run(item, env)
            if run(item[0], env):
                return run(item[1], env)
        return None
    if op == TriccOperator.LIST_IF:
        kept = [i for i in refs if not isinstance(i, list) or run(i[0], env)]
        return [run(i[1], env) if isinstance(i, list) else run(i, env) for i in kept]
    raise AssertionError(f"unexpected operator {op}")


def expand(cql, tables=None, aliases=None, used=None):
    return expand_decision_tables(transform_cql_to_operation(cql), tables or TABLE_MAP, aliases, used)


# ---------------------------------------------------------------- shared vectors


@pytest.mark.parametrize("case", CELLS, ids=lambda c: f"{c['cell']!r}:{c['type']}")
def test_cell_vectors(case):
    if "error" in case:
        with pytest.raises(DecisionTableError) as exc:
            parse_cell(case["cell"], case["type"])
        assert exc.value.code == case["error"]
        return
    test = parse_cell(case["cell"], case["type"])
    for value in case["pass"]:
        assert cell_matches(test, value), value
    for value in case["fail"]:
        assert not cell_matches(test, value), value


@pytest.mark.parametrize("case", TABLES["cases"], ids=lambda c: str(c["inputs"]))
def test_table_vectors(case):
    table = decode_table(TABLES["tables"][case["table"]])
    matches, first = evaluate_table(table, case["inputs"])
    assert matches == case["matches"]
    assert (first[0] if first else None) == case["first"]
    _, rows = evaluate_table(table, case["inputs"], "rule_order")
    assert [row[0] for row in rows] == case["list"]


@pytest.mark.parametrize("case", TABLES["cases"], ids=lambda c: str(c["inputs"]))
def test_expansion_gives_the_vector_result(case):
    weight, age = case["inputs"]
    env = {"w": weight, "a": age}
    assert run(expand("DMN('diazepam', \"w\", \"a\")"), env) == case["first"]
    assert run(expand("DMNList('diazepam', \"w\", \"a\")"), env) == case["list"]
    # literals and null are folded at expansion: same result, no reference
    literal = lambda v: "null" if v is None else str(v)  # noqa: E731
    folded = expand(f"DMN('diazepam', {literal(weight)}, {literal(age)})")
    assert (run(folded, {}) or None) == case["first"]  # no row: empty
    assert run(expand(f"DMNList('diazepam', {literal(weight)}, {literal(age)})"), {}) == case["list"]


# ---------------------------------------------------------------- parsing


def test_table_functions_keep_their_name():
    for name in ("DMN", "DMNFirst", "DMNList", "DrugDosage"):
        op = transform_cql_to_operation(f"{name}('diazepam', \"w\")")
        assert op.operator == TriccOperator.DMN
        assert op.reference[0] == TriccStatic(value=name)


def test_tuple_is_a_named_argument_map():
    op = transform_cql_to_operation("DMN('diazepam', Tuple{ weight: null, \"age\": \"a\" })")
    tup = op.reference[-1]
    assert tup.operator == TriccOperator.TUPLE
    assert tup.reference == [TriccStatic(value="weight"), None, TriccStatic(value="age"), TriccReference("a")]


# ---------------------------------------------------------------- binding


def test_policy_override():
    assert expand("DMN('diazepam', \"w\", \"a\")").operator == TriccOperator.IFS
    assert expand("DMNFirst('diazepam', \"w\", \"a\")").operator == TriccOperator.IFS
    assert expand("DMNList('diazepam', \"w\", \"a\")").operator == TriccOperator.LIST_IF
    rule_order = DecisionTable(**{**DIAZEPAM.__dict__, "hit_policy": "rule_order"})
    assert expand("DMN('diazepam', \"w\", \"a\")", {"diazepam": rule_order}).operator == TriccOperator.LIST_IF
    assert expand("DMNFirst('diazepam', \"w\", \"a\")", {"diazepam": rule_order}).operator == TriccOperator.IFS


def test_left_out_inputs_read_their_concept():
    expr = expand("DMN('diazepam')")
    assert {r.value for r in expr.get_references()} == {"CHE.B6.DE07", "age_in_months"}
    assert run(expr, {"CHE.B6.DE07": 11.5, "age_in_months": 24}) == "1.2"


def test_integer_input_rounds_down():
    expr = expand("DMN('diazepam', null, \"a\")")
    assert run(expr, {"a": 35.9}) == "1.2"
    assert run(expr, {"a": 36}) == "1.7"


def test_named_null_creates_no_reference():
    expr = expand("DMN('diazepam', Tuple{ weight: null })")
    assert {r.value for r in expr.get_references()} == {"age_in_months"}
    assert run(expr, {"age_in_months": 24}) == "1.2"
    assert run(expr, {"age_in_months": 1}) is None


def test_named_binds_by_input_name():
    expr = expand("DMN('diazepam', Tuple{ age: \"a\", weight: \"w\" })")
    assert run(expr, {"w": 25, "a": 40}) == "2.5"
    positional_then_named = expand("DMN('diazepam', \"w\", Tuple{ age: 3 })")
    assert {r.value for r in positional_then_named.get_references()} == {"w"}


def test_builtin_alias_drug_dosage():
    # DrugDosage(table, age, weight): arguments mapped to inputs by name
    expr = expand("DrugDosage('diazepam', \"a\", \"w\")")
    assert run(expr, {"w": 11.5, "a": 24}) == "1.2"
    assert run(expr, {"w": None, "a": 40}) == "1.7"


def test_project_alias():
    aliases = decode_aliases({"Dose": {"function": "DMNList", "args": ["weight", "table"]}})
    expr = expand("Dose(\"w\", 'diazepam')", aliases=aliases)
    assert expr.operator == TriccOperator.LIST_IF
    assert run(expr, {"w": 25}) == ["2.5"]
    # a project alias overrides the built-in one of the same name
    swapped = decode_aliases({"DrugDosage": {"function": "DMN", "args": ["table", "weight", "age"]}})
    assert run(expand("DrugDosage('diazepam', \"w\", \"a\")", aliases=swapped), {"w": 11.5, "a": 1}) == "1.2"


def test_named_output():
    two = DecisionTable(
        id="t",
        inputs=[DIAZEPAM.inputs[0]],
        outputs=[DIAZEPAM.outputs[0], DIAZEPAM.outputs[0].__class__(name="note", type="string")],
        rules=[[">= 20", "big", "adult dose"], ["-", "small", "child dose"]],
    )
    assert run(expand("DMN('t.note', \"w\")", {"t": two}), {"w": 3}) == "child dose"
    assert run(expand("DMN('t', \"w\")", {"t": two}), {"w": 30}) == "big"


def test_calls_inside_expressions_and_used_tables():
    used = set()
    expr = expand("if \"x\" then DMN('diazepam', \"w\", \"a\") else 'none'", used=used)
    assert expr.operator == TriccOperator.IF
    assert expr.reference[1].operator == TriccOperator.IFS
    assert used == {"diazepam"}


@pytest.mark.parametrize(
    "cql, code",
    [
        ("DMN('nope', 1)", "E_DMN_TABLE_UNKNOWN"),
        ("DMN('diazepam.nope', 1)", "E_DMN_TABLE_UNKNOWN"),
        ("DMN(\"t\", 1)", "E_DMN_TABLE_NOT_STATIC"),
        ("DMN('diazepam', 1, 2, 3)", "E_CALL_ARITY"),
        ("DrugDosage('diazepam', 1, 2, 3)", "E_CALL_ARITY"),
        ("DMN('diazepam', Tuple{ height: 1 })", "E_CALL_ARG_UNKNOWN"),
        ("DMN('diazepam', 1, Tuple{ weight: 2 })", "E_CALL_ARG_TWICE"),
        ("Coalesce(DMN('diazepam', 1), Tuple{ weight: 2 })", "E_CALL_ARG_UNKNOWN"),
    ],
)
def test_call_errors(cql, code):
    with pytest.raises(DecisionTableError) as exc:
        expand(cql)
    assert exc.value.code == code


def test_alias_unknown_input_and_unbound_input_without_concept(caplog):
    aliases = {"Bad": FunctionAlias(function="DMN", args=["table", "height"])}
    with pytest.raises(DecisionTableError) as exc:
        expand("Bad('diazepam', 1)", aliases=aliases)
    assert exc.value.code == "E_ALIAS_UNKNOWN_INPUT"
    # an input left out with no fallback has no value (feature/20261125-calculate-functions.md §2.3)
    bare = DecisionTable(**{**DIAZEPAM.__dict__})
    bare.inputs = [c.__class__(name=c.name, type=c.type) for c in DIAZEPAM.inputs]
    with caplog.at_level(logging.WARNING, logger="default"):
        expr = expand("DMN('diazepam', 25)", {"diazepam": bare})
    assert "W_PARAM_NO_VALUE" in caplog.text
    assert not expr.get_references() if hasattr(expr, "get_references") else True
    assert run(expr, {}) == "2.5"


# ---------------------------------------------------------------- table files


def test_table_file_is_written_as_the_editor_writes_it():
    expected = "\n".join(
        [
            "id: diazepam",
            "title: Diazepam, rectal (ml)",
            "hit_policy: first",
            "inputs:",
            "  - name: weight",
            "    concept: CHE.B6.DE07",
            "    type: decimal",
            "  - name: age",
            "    concept: age_in_months",
            "    type: integer",
            "outputs:",
            "  - name: dose",
            "    type: string",
            "rules:",
            '  - [">= 20",    "-",        "2.5"]',
            '  - ["[15..20)", "-",        "1.7"]',
            '  - ["[10..15)", "-",        "1.2"]',
            '  - ["[6..10)",  "-",        "0.75"]',
            '  - ["[3..6)",   "-",        "0.4"]',
            '  - ["-",        ">= 36",    "1.7"]',
            '  - ["-",        "[12..36)", "1.2"]',
            '  - ["-",        "[5..12)",  "0.75"]',
            '  - ["-",        "[2..5)",   "0.4"]',
            "",
        ]
    )
    assert encode_table(DIAZEPAM) == expected
    assert encode_table(read_table(expected, "diazepam.yaml")) == expected


def test_unquoted_cells_keep_what_was_written():
    table = read_table(
        "id: t\ninputs: [{name: x, type: boolean}]\noutputs: [{name: y, type: decimal}]\nrules:\n  - [true, 2.0]\n"
        "  - [null, 1.5]\n",
        "t.yaml",
    )
    assert table.rules == [["true", "2"], ["null", "1.5"]]


def test_unique_overlap_and_located_cell_errors():
    unique = "id: u\nhit_policy: unique\ninputs: [{name: x, type: decimal}]\noutputs: [{name: y}]\nrules:\n"
    with pytest.raises(DecisionTableError) as exc:
        read_table(unique + '  - [">= 5", "a"]\n  - ["[0..6)", "b"]\n', "u.yaml")
    assert exc.value.code == "E_DMN_OVERLAP"
    assert read_table(unique + '  - [">= 5", "a"]\n  - ["[0..5)", "b"]\n', "u.yaml").hit_policy == "unique"
    with pytest.raises(DecisionTableError) as exc:
        read_table(unique.replace("unique", "first") + '  - [">= 5", "a"]\n  - ["[6..5)", "b"]\n', "u.yaml")
    assert exc.value.code == "E_DMN_CELL"
    assert "row 2, column 1" in str(exc.value)


def test_list_values_without_spaces():
    table = DecisionTable(
        id="l", hit_policy="rule_order", inputs=[DIAZEPAM.inputs[0]], outputs=[DIAZEPAM.outputs[0]],
        rules=[["-", "two words"]],
    )
    assert [p.code for p in table_problems(table)] == ["E_DMN_LIST_VALUE"]


def test_project_config_keys():
    config = TriccProjectConfig(
        decision_tables=["tables/*.yaml", " "], aliases={"Dose": {"function": "DMNList", "args": ["table"]}}
    )
    assert config.decision_tables == ["tables/*.yaml"]
    assert decode_aliases(config.aliases)["Dose"] == FunctionAlias(function="DMNList", args=["table"])


# ---------------------------------------------------------------- serialisation


@pytest.fixture(scope="module")
def yaml_project():
    return load_yaml_project(YAML_FIXTURE)


def _small_table(policy="first"):
    return {
        "s": DecisionTable(
            id="s",
            hit_policy=policy,
            inputs=[DIAZEPAM.inputs[0], DIAZEPAM.inputs[1]],
            outputs=[DIAZEPAM.outputs[0]],
            rules=[[">= 20", "-", "2.5"], ["-", "[12..36)", "1.2"]],
        )
    }


def test_xlsform_serialisation(yaml_project, tmp_path):
    from tricc_oo.strategies.output.xls_form import XLSFormStrategy

    strategy = XLSFormStrategy(yaml_project, str(tmp_path))
    first = strategy.get_tricc_operation_expression(expand("DMN('s', \"w\", \"a\")", _small_table()))
    assert first == "if(${w}>=20,'2.5',if(int(${a})>=12 and int(${a})<36,'1.2',''))"
    listed = strategy.get_tricc_operation_expression(expand("DMNList('s', \"w\", \"a\")", _small_table()))
    assert listed == "normalize-space(concat(if(${w}>=20,'2.5',''),' ',if(int(${a})>=12 and int(${a})<36,'1.2','')))"
    spaced = {"s": _small_table()["s"]}
    spaced["s"].rules = [["-", "-", "two words"]]
    with pytest.raises(DecisionTableError) as exc:
        strategy.get_tricc_operation_expression(expand("DMNList('s', \"w\", \"a\")", spaced))
    assert exc.value.code == "E_DMN_LIST_VALUE"


def test_fhirpath_and_cql_serialisation(yaml_project, tmp_path):
    from tricc_oo.strategies.output.fhir_form import FHIRStrategy

    strategy = FHIRStrategy(yaml_project, str(tmp_path))
    listed = expand("DMNList('s', 2, \"a\")", _small_table())
    fhirpath = strategy.get_tricc_operation_expression_fhirpath(listed)
    assert fhirpath.startswith("iif(") and ".floor()" in fhirpath and fhirpath.endswith(", '1.2', {})")
    assert ".combine(" not in fhirpath  # one row left: the weight row is folded away
    both = strategy.get_tricc_operation_expression_fhirpath(expand("DMNList('s', 25, \"a\")", _small_table()))
    assert both.startswith("('2.5').combine(iif(") or both.startswith("'2.5'.combine(iif(")
    first = strategy.get_tricc_operation_expression(expand("DMN('s', 2, \"a\")", _small_table()))
    assert first.startswith("if Floor(") and first.endswith("then '1.2' else null")
    cql_list = strategy.get_tricc_operation_expression(expand("DMNList('s', 25, \"a\")", _small_table()))
    assert cql_list.startswith("flatten { { '2.5' }, if Floor(") and cql_list.endswith("then { '1.2' } else { } }")


def test_openmrs_and_dhis2_ifs_read_pairs():
    from tricc_oo.strategies.output.dhis2_form import DHIS2Strategy
    from tricc_oo.strategies.output.openmrs_form import OpenMRSStrategy

    def bare(cls):
        # OpenMRSStrategy is still abstract; only its serialisers are tested here
        stub = type(f"Bare{cls.__name__}", (cls,), {"generate_relevance": None, "validate": None})
        stub.__abstractmethods__ = frozenset()
        return object.__new__(stub)

    openmrs = bare(OpenMRSStrategy)
    assert openmrs.tricc_operation_ifs([["c1", "'a'"], ["c2", "'b'"]]) == "((c1) ? 'a' : ((c2) ? 'b' : null))"
    assert openmrs.tricc_operation_list_if([["c1", "'a'"], "'b'"]) == (
        "[((c1) ? 'a' : null), 'b'].filter(v => v !== null).join(' ')"
    )
    assert openmrs.tricc_operation_floor(["x"]) == "Math.floor(x)"
    dhis2 = bare(DHIS2Strategy)
    assert dhis2.tricc_operation_ifs([["c1", "'a'"], "'b'"]) == "if(c1, 'a', 'b')"
    assert dhis2.tricc_operation_list_if([["c1", "'a'"], ["c2", "'b'"]]) == (
        "d2:concatenate(if(c1, 'a', ''), ' ', if(c2, 'b', ''))"
    )


# ---------------------------------------------------------------- end to end


def _build(tmp_path, strategy):
    logging.disable(logging.WARNING)
    try:
        assert run_project_build(PROJECT, str(tmp_path / "out"), cli_output_strategy=strategy) == 0
    finally:
        logging.disable(logging.NOTSET)
    return tmp_path / "out"


def _calculations(out):
    (form,) = glob.glob(str(out / "**" / "dosing.xlsx"), recursive=True)
    survey = pd.read_excel(form, sheet_name="survey", dtype=str).fillna("")
    assert not any("drugs.js" in c for c in survey["calculation"])
    return dict(zip(survey["name"], survey["calculation"]))


def test_odk_form_computes_the_dose_inline(tmp_path):
    calc = _calculations(_build(tmp_path, "XLSFormStrategy"))
    assert calc["dose"].startswith("if(coalesce(${weight},-2147483648)>=20,'2.5',")
    assert calc["dose"] == calc["legacy_dose"] == calc["alias_dose"]
    assert calc["doses"].startswith("normalize-space(concat(")
    assert "${weight}" not in calc["dose_by_age"] and calc["dose_by_age"].startswith("if(int(coalesce(${age_in_months}")
    assert "count-selected(${doses})" in calc["dose_count"]


def test_cht_form_calls_the_project_library(tmp_path):
    out = _build(tmp_path, "XLSFormCHTStrategy")
    calc = _calculations(out)
    lib = "cht:extension-lib('dmn-decision-tables.js', 'diazepam'"
    assert calc["dose"] == f"{lib}, 'first', 'dose', ${{weight}}, ${{age_in_months}})"
    assert calc["dose"] == calc["legacy_dose"] == calc["alias_dose"]
    assert calc["doses"] == f"{lib}, 'rule_order', 'dose', ${{weight}}, ${{age_in_months}})"
    assert calc["dose_by_age"] == f"{lib}, 'first', 'dose', '', ${{age_in_months}})"
    assert "count-selected(${doses})" in calc["dose_count"]
    (path,) = glob.glob(str(out / "**" / "extension-libs" / "dmn-decision-tables.js"), recursive=True)
    with open(path, encoding="utf-8") as file:
        assert file.read() == build_dmn_js({"diazepam": read_table(open(TABLE_FILE).read(), TABLE_FILE)},
                                           "Decision tables")


def test_kept_call_wraps_the_inline_expansion():
    tables = {"diazepam": DIAZEPAM}
    call = expand_decision_tables(transform_cql_to_operation("DMN('diazepam', Tuple{ weight: null })"), tables,
                                  keep_calls=True)
    assert call.operator == TriccOperator.DMN_CALL
    assert call.reference[0] == expand("DMN('diazepam', Tuple{ weight: null })")
    assert call.reference[1:] == [
        TriccStatic(value="diazepam"), TriccStatic(value="first"), TriccStatic(value="dose"),
        TriccStatic(value=""), TriccReference("age_in_months"),
    ]
    assert call.get_datatype() == call.reference[0].get_datatype()  # the wrapper is transparent
    folded = expand_decision_tables(transform_cql_to_operation("DMN('diazepam', 11.5, 24)"), tables, keep_calls=True)
    assert folded == TriccStatic(value="1.2")


def test_library_name_carries_the_project():
    assert library_name("Global Almanach (L4)") == "dmn-global-almanach-l4.js"
    assert library_name(None) == "dmn.js"


def test_fhir_questionnaire_computes_the_dose(tmp_path):
    out = _build(tmp_path, "OpenSRPStrategy")
    (path,) = glob.glob(str(out / "**" / "questionnaire" / "*.json"), recursive=True)
    with open(path, encoding="utf-8") as file:
        questionnaire = json.load(file)
    expressions = {}

    def walk(items):
        for item in items:
            for ext in item.get("extension", []):
                if "valueExpression" in ext:
                    expressions[item["linkId"]] = ext["valueExpression"]["expression"]
            walk(item.get("item", []))

    walk(questionnaire["item"])
    assert expressions["dose"].startswith("iif(") and "'2.5'" in expressions["dose"]
    assert ".combine(iif(" in expressions["doses"]
    repeats = {}

    def walk_items(items):
        for item in items:
            repeats[item["linkId"]] = item.get("repeats", False)
            walk_items(item.get("item", []))

    walk_items(questionnaire["item"])
    assert repeats["doses"] is True and repeats["dose"] is False
    assert expressions["dose_count"].endswith(".where(linkId='doses').answer.count()")


def test_unknown_table_fails_the_build(tmp_path):
    project = tmp_path / "p"
    shutil.copytree(PROJECT, project)
    activity = project / "activities" / "dosing.activity.yaml"
    activity.write_text(activity.read_text(encoding="utf-8").replace("DMNList('diazepam')", "DMNList('nope')"))
    logging.disable(logging.WARNING)
    try:
        with pytest.raises(DecisionTableError, match="E_DMN_TABLE_UNKNOWN: node 'doses'"):
            run_project_build(str(project), str(tmp_path / "out"), cli_output_strategy="XLSFormStrategy")
    finally:
        logging.disable(logging.NOTSET)


# ---------------------------------------------------------------- Global drugs.js


@pytest.fixture(scope="module")
def drugs():
    with open(DRUGS_JS, encoding="utf-8") as file:
        return read_drugs_js(file.read())


def test_drugs_js_gives_one_valid_table_per_drug(drugs, tmp_path):
    tables = drug_tables(drugs)
    assert len(tables) == 33
    paths = write_tables(tables, str(tmp_path))
    for path, table in zip(paths, tables):
        with open(path, encoding="utf-8") as file:
            text = file.read()
        assert encode_table(read_table(text, path)) == text
        assert table.rules[0][1] == "-" or table.rules[0][0] == "-"


WEIGHTS = [None, 1, 1.4, 2, 2.5, 3, 3.9, 4, 5.5, 6, 9.99, 10, 11.5, 14, 15, 19.9, 20, 35]
AGES = [1, 2, 3, 4, 6, 11, 12, 23, 24, 35, 36, 59, 60, 120]

NODE_SCRIPT = """
console.log = () => {};
const fn = require(process.argv[1]);
const [drugs, weights, ages] = JSON.parse(process.argv[2]);
const arg = (v) => (v === null ? { t: 'arr', v: [] } : { t: 'num', v: { textContent: String(v) } });
const out = {};
for (const d of drugs) for (const w of weights) for (const a of ages)
  out[`${d}|${w}|${a}`] = fn({ v: d }, arg(a), arg(w)).v;
process.stdout.write(JSON.stringify(out));
"""


LIBRARY_SCRIPT = """
const lib = require(process.argv[1]);
const calls = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const arg = (v) => (v === null ? { t: 'arr', v: [] } : { t: 'num', v: { textContent: String(v) } });
const str = (v) => ({ t: 'str', v });
process.stdout.write(JSON.stringify(calls.map(([table, policy, output, inputs]) =>
  lib(str(table), str(policy), str(output), ...inputs.map(arg)).v)));
"""


def run_library(source, calls, tmp_path):
    """Call the generated library with node as CHT does: ``[(table, policy, output, inputs)]``."""
    path = tmp_path / "dmn.js"
    path.write_text(source, encoding="utf-8")
    result = subprocess.run(
        ["node", "-e", LIBRARY_SCRIPT, str(path)], input=json.dumps(calls), capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is needed to run the library")
def test_library_gives_the_vector_results(tmp_path):
    source = build_dmn_js(TABLE_MAP, "Vectors")
    cases = TABLES["cases"]
    calls = [[c["table"], "first", "dose", c["inputs"]] for c in cases]
    calls += [[c["table"], "rule_order", "dose", c["inputs"]] for c in cases]
    got = run_library(source, calls, tmp_path)
    assert got[: len(cases)] == [c["first"] or "" for c in cases]
    assert got[len(cases):] == [" ".join(c["list"]) for c in cases]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is needed to run the library")
def test_library_reads_every_cell_form(tmp_path):
    table = DecisionTable(
        id="cells",
        inputs=[
            DIAZEPAM.inputs[0].__class__(name="n", type="decimal"),
            DIAZEPAM.inputs[0].__class__(name="s", type="string"),
            DIAZEPAM.inputs[0].__class__(name="b", type="boolean"),
        ],
        outputs=[DIAZEPAM.outputs[0].__class__(name="out", type="integer")],
        rules=[
            ["null", "-", "-", "1"],
            ["(3..6]", "'a', 'b'", "-", "2"],
            ["1, 3, [5..7)", "-", "true", "3"],
            ["not(null)", "-", "-", "4"],
        ],
    )
    inputs = [[None, None, None], [6, "b", None], [3, "c", True], [3, "c", False], [4.5, "a", None]]
    path = tmp_path / "cells.js"
    path.write_text(build_dmn_js({"cells": table}), encoding="utf-8")
    script = (
        "const lib = require(process.argv[1]);"
        "const s = (v) => (v === null ? { t: 'arr', v: [] } : { t: 'str', v: { textContent: String(v) } });"
        "process.stdout.write(JSON.stringify(JSON.parse(process.argv[2]).map((i) =>"
        " lib('cells', 'first', 'out', ...i.map(s)))));"
    )
    result = subprocess.run(["node", "-e", script, str(path), json.dumps(inputs)], capture_output=True, text=True,
                            check=True)
    got = json.loads(result.stdout)
    expected = [evaluate_table(table, i)[1] for i in inputs]
    assert [g["v"] if g["v"] != "" else None for g in got] == [e[0] if e else None for e in expected]
    assert got[0] == {"t": "num", "v": 1}


@pytest.mark.skipif(shutil.which("node") is None, reason="node is needed to run drugs.js")
def test_library_gives_the_dose_drugs_js_gives(drugs, tmp_path):
    tables = drug_tables(drugs)
    expected = subprocess.run(
        ["node", "-e", NODE_SCRIPT, os.path.abspath(DRUGS_JS), json.dumps([[t.id for t in tables], WEIGHTS, AGES])],
        capture_output=True,
        text=True,
        check=True,
    )
    expected = json.loads(expected.stdout)
    keys, calls = [], []
    for table in tables:
        for weight in WEIGHTS:
            for age in AGES:
                keys.append(f"{table.id}|{'null' if weight is None else weight}|{age}")
                calls.append([table.id, "first", "dose", [weight, age]])
    got = run_library(build_dmn_js({t.id: t for t in tables}, "Global"), calls, tmp_path)
    assert dict(zip(keys, got)) == expected


@pytest.mark.skipif(shutil.which("node") is None, reason="node is needed to run drugs.js")
def test_tables_give_the_dose_drugs_js_gives(drugs):
    """Weight 0 counts as not entered in drugs.js; age 0 gives no dose there at all, and no age
    gives the last age class: both are left out (the tables give no dose without an age)."""
    tables = drug_tables(drugs)
    result = subprocess.run(
        ["node", "-e", NODE_SCRIPT, os.path.abspath(DRUGS_JS), json.dumps([[t.id for t in tables], WEIGHTS, AGES])],
        capture_output=True,
        text=True,
        check=True,
    )
    expected = json.loads(result.stdout)
    for table in tables:
        call = expand(f"DrugDosage('{table.id}', \"a\", \"w\")", {table.id: table})
        for weight in WEIGHTS:
            for age in AGES:
                got = run(call, {"w": weight, "a": age})
                key = f"{table.id}|{'null' if weight is None else weight}|{age}"
                assert (got or "") == expected[key], key
