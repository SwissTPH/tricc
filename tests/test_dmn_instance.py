"""Large decision tables read from an ODK secondary instance; zscore on decision tables.

feature/20261123-dmn-instance-lookup.md. The lookups are evaluated with lxml (XPath 1.0), with
the JavaRosa functions the forms use (``instance``, ``int``, ``join``, ``coalesce``, ``pow``)
registered, against the shared vectors and on the XForm pyxform writes.

Run with:
    python -m pytest tests/test_dmn_instance.py -v
"""

from __future__ import annotations

import copy
import glob
import logging
import math
import re
import shutil

import pandas as pd
import pytest
from lxml import etree

from tests.test_decision_tables import (
    CELLS,
    DIAZEPAM,
    PROJECT,
    TABLES,
    expand,
    run,
    run_library,
)
from tests.test_decision_tables import yaml_project  # noqa: F401 (a fixture)
from tricc_oo.converters.cql_to_operation import transform_cql_to_operation
from tricc_oo.converters.decision_table import expand_decision_tables
from tricc_oo.converters.utils import xpath_literal
from tricc_oo.data.anthro import builtin_decision_table, get_choice_rows
from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference
from tricc_oo.models.decision_table import (
    DecisionTable,
    DecisionTableError,
    TableColumn,
    evaluate_table,
)
from tricc_oo.runner import run_project_build
from tricc_oo.serializers.dmn_instance import (
    instance_items,
    list_name,
    lookup_expression,
    valid_row_count,
)
from tricc_oo.serializers.dmn_js import build_dmn_js

# ---------------------------------------------------------------- an XPath runtime


_INSTANCES = {}


def _text(value):
    if isinstance(value, list):
        return value[0] if value and isinstance(value[0], str) else (value[0].text or "") if value else ""
    return value


def _number(value):
    value = _text(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


_functions = etree.FunctionNamespace(None)
# instance('#primary') is the primary instance's <data>, the others their <instance> node
_functions["instance"] = lambda _, name: [_INSTANCES[_text(name)]]
_functions["int"] = lambda _, v: float("nan") if math.isnan(_number(v)) else float(math.trunc(_number(v)))
_functions["join"] = lambda _, sep, nodes: _text(sep).join((n.text or "") for n in nodes)
_functions["coalesce"] = lambda _, a, b: _text(a) if _text(a) not in ("", None) else _text(b)
_functions["pow"] = lambda _, a, b: _number(a) ** _number(b)


def _instance(table, policy="first"):
    """The instance as pyxform writes it: one item per row, empty cells left out."""
    root = etree.Element("instance")
    items = etree.SubElement(root, "root")
    for item in instance_items(table, policy):
        node = etree.SubElement(items, "item")
        for key, value in item.items():
            if value != "":
                etree.SubElement(node, key).text = value
    return root


def _literal(value, column):
    """An input value as an XPath literal (the form's value: booleans 1 / 0, not entered: empty)."""
    if value is None:
        return "''"
    if isinstance(value, bool):
        return "'1'" if value else "'0'"
    return xpath_literal(value)


def lookup(table, inputs, policy="first", output=None):
    """Evaluate the list lookup on these input values (``None``: not entered)."""
    arguments = []
    for value, column in zip(inputs, table.inputs):
        raw = _literal(value, column)
        number = f"int({raw})" if column.type == "integer" else f"number({raw})"
        arguments.append((raw, number, lambda b, raw=raw: f"{raw}={1 if b else 0}"))
    expression = lookup_expression(table, policy, output or table.outputs[0].name, arguments)
    _INSTANCES[list_name(table.id)] = _instance(table, policy)
    result = etree.XPath(expression)(etree.Element("data"))
    return _text(result) if isinstance(result, list) else result


def _expected(table, inputs, policy="first"):
    _, outputs = evaluate_table(table, inputs, policy)
    if policy == "rule_order":
        return " ".join(str(row[0]) for row in outputs)
    return "" if not outputs else str(outputs[0])


# ---------------------------------------------------------------- the vectors


@pytest.mark.parametrize("case", [c for c in CELLS if "error" not in c], ids=lambda c: f"{c['cell']!r}:{c['type']}")
def test_every_cell_form_reads_like_the_evaluator(case):
    table = DecisionTable(
        id="cell",
        inputs=[TableColumn(name="x", type=case["type"])],
        outputs=[TableColumn(name="hit")],
        rules=[[case["cell"], "yes"], ["-", "no"]],
    )
    for value in case["pass"] + case["fail"]:
        assert lookup(table, [value]) == _expected(table, [value]), value


@pytest.mark.parametrize("case", TABLES["cases"], ids=lambda c: str(c["inputs"]))
def test_the_table_vectors(case):
    assert lookup(DIAZEPAM, case["inputs"]) == (case["first"] or "")
    assert lookup(DIAZEPAM, case["inputs"], "rule_order") == " ".join(case["list"])


def test_list_cells_become_one_item_per_value():
    table = DecisionTable(
        id="lists",
        inputs=[TableColumn(name="s", type="string"), TableColumn(name="n", type="integer")],
        outputs=[TableColumn(name="out")],
        rules=[["'a', 'b'", "[1..3], 7", "x"], ["-", "-", "y"]],
    )
    items = instance_items(table)
    assert [i["name"] for i in items] == ["r0_0", "r0_1", "r0_2", "r0_3", "r1"]
    for inputs in (["a", 2], ["b", 7], ["b", 7.9], ["c", 2], ["a", 4], [None, None]):
        assert lookup(table, inputs) == _expected(table, inputs), inputs
        assert lookup(table, inputs, "rule_order") == _expected(table, inputs, "rule_order"), inputs


def test_overlapping_list_values_are_refused_for_a_list_result():
    table = DecisionTable(
        id="overlap",
        inputs=[TableColumn(name="n", type="decimal")],
        outputs=[TableColumn(name="out")],
        rules=[["[1..5], [3..8]", "x"]],
    )
    assert lookup(table, [4]) == "x"  # first: the duplicate is harmless
    with pytest.raises(DecisionTableError) as exc:
        instance_items(table, "rule_order")
    assert exc.value.code == "E_DMN_LIST_OVERLAP"


def test_the_predicate_only_tests_what_the_column_uses():
    arguments = [("${w}", "number(${w})", None), ("${a}", "int(${a})", None)]
    only_weight = DecisionTable(
        id="w",
        inputs=DIAZEPAM.inputs,
        outputs=DIAZEPAM.outputs,
        rules=[["[3..6)", "-", "0.4"], ["[6..10)", "-", "0.75"]],
    )
    expression = lookup_expression(only_weight, "first", "dose", arguments)
    assert expression == (
        "instance('dmn_w')/root/item[(${w}!='' and number(${w})>=i0_lo and number(${w})<i0_hi)][1]/o0"
    )


# ---------------------------------------------------------------- zscore


def test_wfa_is_a_built_in_table():
    table = builtin_decision_table("wfa")
    assert valid_row_count(table) == len(get_choice_rows("wfa")) == 270
    assert [c.name for c in table.outputs] == ["l", "m", "s"]
    assert builtin_decision_table("nope") is None


def arithmetic(expr, env):
    """Evaluate the zscore formula: arithmetic on table lookups (``run`` for the lookups)."""
    if isinstance(expr, TriccOperation) and expr.operator in ARITHMETIC:
        values = [arithmetic(r, env) for r in expr.reference]
        return ARITHMETIC[expr.operator](values)
    return run(expr, env)


ARITHMETIC = {
    TriccOperator.PLUS: lambda v: sum(v),
    TriccOperator.MINUS: lambda v: v[0] - v[1],
    TriccOperator.MULTIPLIED: lambda v: math.prod(v),
    TriccOperator.DIVIDED: lambda v: v[0] / v[1],
    TriccOperator.POWER: lambda v: v[0] ** v[1],
}


def _lms(sex, x):
    return next(r for r in get_choice_rows("wfa") if r["sex"] == sex and r["y_min"] <= x < r["y_max"])


def test_zscore_expands_to_three_lookups():
    tables = {}
    expr = expand_decision_tables(transform_cql_to_operation("Zscore('wfa', \"sex\", \"age\", \"weight\")"), tables)
    assert set(tables) == {"wfa"}  # the built-in table, added when called
    assert expr.operator == TriccOperator.DIVIDED  # ((y / m)^l - 1) / (s * l), no zscore operator left
    row = _lms("female", 100.5)
    env = {"sex": "female", "age": 100.5, "weight": 6.5}
    l, m, s = row["l"], row["m"], row["s"]
    assert arithmetic(expr, env) == pytest.approx(((6.5 / m) ** l - 1) / (s * l))
    inverse = expand_decision_tables(transform_cql_to_operation("Izscore('wfa', \"sex\", \"age\", 2)"), tables)
    assert arithmetic(inverse, env) == pytest.approx(m * (2 * s * l + 1) ** (1 / l))


def test_a_project_table_replaces_the_built_in_one():
    own = DecisionTable(
        id="wfa",
        inputs=[TableColumn(name="sex"), TableColumn(name="x", type="decimal")],
        outputs=[TableColumn(name=n, type="decimal") for n in ("l", "m", "s")],
        rules=[["-", "-", "1", "2", "3"]],
    )
    expr = expand_decision_tables(transform_cql_to_operation("Zscore('wfa', \"sex\", \"age\", \"w\")"), {"wfa": own})
    assert arithmetic(expr, {"w": 4}) == pytest.approx(((4 / 2) ** 1 - 1) / (3 * 1))


@pytest.mark.parametrize(
    "cql, code",
    [
        ("Zscore(\"t\", \"sex\", \"age\", \"w\")", "E_DMN_TABLE_NOT_STATIC"),
        ("Zscore('nope', \"sex\", \"age\", \"w\")", "E_DMN_TABLE_UNKNOWN"),
        ("Zscore('wfa', \"sex\", \"age\")", "E_DMN_ARITY"),
    ],
)
def test_zscore_errors(cql, code):
    with pytest.raises(DecisionTableError) as exc:
        expand_decision_tables(transform_cql_to_operation(cql), {})
    assert exc.value.code == code


def test_nested_arithmetic_is_bracketed(yaml_project, tmp_path):  # noqa: F811
    from tricc_oo.strategies.output.fhir_form import FHIRStrategy
    from tricc_oo.strategies.output.xls_form import XLSFormStrategy

    formula = transform_cql_to_operation("(\"a\" + \"b\") / 2 - \"c\" * (\"d\" - 1)")
    xpath = XLSFormStrategy(yaml_project, str(tmp_path))
    assert xpath.get_tricc_operation_expression(formula) == "((${a} + ${b}) div 2) - (${c}*(${d} - 1))"
    power = TriccOperation(TriccOperator.POWER, [TriccOperation(TriccOperator.MINUS, [TriccReference("a"), 1]), 2])
    assert xpath.get_tricc_operation_expression(power) == "pow(${a} - 1, 2)"
    fhir = FHIRStrategy(yaml_project, str(tmp_path))
    cql = re.sub(r"Helper\.GetObservationValue\('(\w)'\)", r"\1", fhir.get_tricc_operation_expression(formula))
    assert cql == "((a + b) / 2) - (c * (d - 1))"
    assert ".power(2" in fhir.get_tricc_operation_expression_fhirpath(power)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is needed to run the library")
def test_the_cht_library_reads_wfa(tmp_path):
    source = build_dmn_js({"wfa": builtin_decision_table("wfa")}, "Z")
    points = [("male", 0), ("female", 100.5), ("male", 1850)]
    calls = [["wfa", "first", out, [sex, x]] for sex, x in points for out in ("l", "m", "s")]
    got = run_library(source, calls, tmp_path)
    assert got == [_lms(sex, x)[out] for sex, x in points for out in ("l", "m", "s")]


# ---------------------------------------------------------------- end to end


ZSCORE_NODES = """  - {id: sex, type: text, name: sex, label: Sex}
  - {id: days, type: decimal, name: age_days, label: Age (days)}
  - {id: z, type: calculate, name: wfa_z, label: WFA z,
     calculate: "Zscore('wfa', \\"sex\\", \\"age_days\\", \\"weight\\")"}
  - {id: w0, type: calculate, name: wfa_median, label: WFA median,
     calculate: "Izscore('wfa', \\"sex\\", \\"age_days\\", 0)"}
  - {id: znote, type: note, name: z_note, label: "z ${wfa_z} median ${wfa_median}"}
"""
ZSCORE_EDGES = """  - {id: e5, source: all, target: sex}
  - {id: e6, source: sex, target: days}
  - {id: e7, source: days, target: znote}
  - {id: e8, source: znote, target: end}"""


def _project(tmp_path, max_inline_rows=None):
    """The decision table fixture with zscore calculates, and the threshold when given."""
    project = tmp_path / "p"
    shutil.copytree(PROJECT, project)
    if max_inline_rows is not None:
        config = project / "tricc.yaml"
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                "aliases:", f"decision_table_max_inline_rows: {max_inline_rows}\naliases:"
            )
        )
    activity = project / "activities" / "dosing.activity.yaml"
    text = activity.read_text(encoding="utf-8")
    text = text.replace("  - {id: end, type: end", ZSCORE_NODES + "  - {id: end, type: end")
    text = text.replace("  - {id: e5, source: all, target: end}", ZSCORE_EDGES)
    activity.write_text(text)
    return project


def _build(project, out, strategy):
    logging.disable(logging.WARNING)
    try:
        assert run_project_build(str(project), str(out), cli_output_strategy=strategy) == 0
    finally:
        logging.disable(logging.NOTSET)
    (form,) = glob.glob(str(out / "**" / "dosing.xlsx"), recursive=True)
    return form


def _sheets(form):
    survey = pd.read_excel(form, sheet_name="survey", dtype=str).fillna("")
    choices = pd.read_excel(form, sheet_name="choices", dtype=str).fillna("")
    return survey, choices


def test_the_default_threshold_keeps_small_tables_inline(tmp_path):
    survey, choices = _sheets(_build(_project(tmp_path), tmp_path / "out", "XLSFormStrategy"))
    calc = dict(zip(survey["name"], survey["calculation"]))
    assert calc["dose"].startswith("if(")  # 9 rows
    assert "instance('dmn_wfa')" in calc["wfa_z"]  # 270 rows
    assert "dmn_diazepam" not in set(choices["list_name"])
    assert (choices["list_name"] == "dmn_wfa").sum() == 270
    hidden = survey[survey["name"] == "dmn_wfa_instance"]
    assert list(hidden["type"]) == ["select_one dmn_wfa"] and list(hidden["relevance"]) == ["false()"]


def test_threshold_zero_reads_every_table_from_an_instance(tmp_path):
    survey, choices = _sheets(_build(_project(tmp_path, 0), tmp_path / "out", "XLSFormStrategy"))
    calc = dict(zip(survey["name"], survey["calculation"]))
    assert calc["dose"].startswith("instance('dmn_diazepam')/root/item[")
    assert calc["doses"].startswith("join(' ', instance('dmn_diazepam')")
    assert (choices["list_name"] == "dmn_diazepam").sum() == 9
    assert set(survey["name"]) >= {"dmn_diazepam_instance", "dmn_wfa_instance"}


def _xform(form, path):
    from pyxform.xls2xform import xls2xform_convert

    xls2xform_convert(form, str(path), validate=shutil.which("java") is not None)
    tree = etree.parse(str(path)).getroot()
    for node in tree.iter():  # plain names, as the bind expressions read them
        if isinstance(node.tag, str):
            node.tag = etree.QName(node).localname
            for key in list(node.attrib):
                value = node.attrib.pop(key)
                node.attrib[etree.QName(key).localname] = value
    etree.cleanup_namespaces(tree)
    return tree


def _calculate(xform, name, values):
    """Evaluate the calculate of ``name`` with these field values, as JavaRosa would."""
    data = copy.deepcopy(xform.find(".//model/instance/data"))
    for field, value in values.items():
        (node,) = [n for n in data.iter() if n.tag == field]
        node.text = str(value)
    for instance in xform.findall(".//model/instance[@id]"):
        _INSTANCES[instance.get("id")] = instance
    (bind,) = [b for b in xform.iter("bind") if b.get("nodeset", "").endswith("/" + name)]
    # JavaRosa reads /data/... in the primary instance, also inside a predicate on another one
    _INSTANCES["#primary"] = data
    expression = re.sub(r"(?<![\w)\]'])/data/", "instance('#primary')/", bind.get("calculate"))
    result = etree.XPath(expression)(data)
    return _text(result) if isinstance(result, list) else result


def test_the_xform_computes_dose_and_zscore(tmp_path):
    xform = _xform(_build(_project(tmp_path, 0), tmp_path / "out", "XLSFormStrategy"), tmp_path / "f.xml")
    assert {i.get("id") for i in xform.findall(".//model/instance[@id]")} >= {"dmn_diazepam", "dmn_wfa"}
    for case in TABLES["cases"]:
        weight, age = ("" if v is None else v for v in case["inputs"])
        assert _calculate(xform, "dose", {"weight": weight, "age_in_months": age}) == (case["first"] or "")
    row = _lms("male", 30)
    z = _calculate(xform, "wfa_z", {"sex": "male", "age_days": 30, "weight": row["m"]})
    assert abs(float(z)) < 1e-9  # the median weight is z = 0
    median = _calculate(xform, "wfa_median", {"sex": "female", "age_days": 100.5})
    assert float(median) == pytest.approx(_lms("female", 100.5)["m"])
    heavy = _calculate(xform, "wfa_z", {"sex": "male", "age_days": 30, "weight": 6.0})
    l, m, s = row["l"], row["m"], row["s"]
    assert float(heavy) == pytest.approx(((6.0 / m) ** l - 1) / (s * l))


def test_cht_reads_zscore_from_the_library(tmp_path):
    survey, choices = _sheets(_build(_project(tmp_path), tmp_path / "out", "XLSFormCHTStrategy"))
    calc = dict(zip(survey["name"], survey["calculation"]))
    assert "cht:extension-lib('dmn-decision-tables.js', 'wfa', 'first', 'm', ${sex}, ${age_days})" in calc["wfa_z"]
    assert "wfa.js" not in calc["wfa_z"] and "dmn_wfa" not in set(choices["list_name"])
    (lib,) = glob.glob(str(tmp_path / "out" / "**" / "dmn-decision-tables.js"), recursive=True)
    assert '"wfa":' in open(lib, encoding="utf-8").read()


def test_expand_keeps_diazepam_vectors():
    # the inline expansion is unchanged by the instance mode
    case = TABLES["cases"][0]
    assert run(expand("DMN('diazepam', \"w\", \"a\")"), {"w": case["inputs"][0], "a": case["inputs"][1]}) == "1.2"
