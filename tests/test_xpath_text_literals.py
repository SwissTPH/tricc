"""Text written into XPath by the XLSForm family goes through ``xpath_literal``.

fix/20261125-xpath-text-literals.md. Values holding an apostrophe, and both quotes (the
``concat`` branch), are written by the real writers and read back with lxml (XPath 1.0).

Run with:
    python -m pytest tests/test_xpath_text_literals.py -v
"""

from __future__ import annotations

import glob
import logging
import math
import os
import re
import shutil
from types import SimpleNamespace

import pandas as pd
import pytest
from lxml import etree

from tests.helpers import load_yaml_project
from tests.test_decision_tables import CELLS, YAML_FIXTURE
from tricc_oo.converters.cql_to_operation import transform_cql_to_operation
from tricc_oo.converters.decision_table import expand_decision_tables
from tricc_oo.converters.utils import xpath_literal
from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference, TriccStatic
from tricc_oo.models.decision_table import DecisionTable, TableColumn, evaluate_table
from tricc_oo.models.tricc import TriccNodeSelectOne, TriccNodeSelectOption
from tricc_oo.runner import run_project_build
from tricc_oo.serializers.dmn_instance import instance_items, list_name

HERE = os.path.dirname(__file__)
PROJECT = os.path.join(HERE, "data", "projects", "xpath_text_literals")
TEXT = "it's \"x\""

# Not imported from tests/test_dmn_instance.py: importing it a second time would register
# its global lxml functions again, bound to another dict, and break its own tests.


def _text(value):
    if isinstance(value, list):
        return value[0] if value and isinstance(value[0], str) else (value[0].text or "") if value else ""
    return value


def _number(value):
    try:
        return float(_text(value))
    except (TypeError, ValueError):
        return float("nan")


def _instance(table):
    """The instance as pyxform writes it: one item per row, empty cells left out."""
    root = etree.Element("instance")
    items = etree.SubElement(root, "root")
    for item in instance_items(table):
        node = etree.SubElement(items, "item")
        for key, value in item.items():
            if value != "":
                etree.SubElement(node, key).text = value
    return root


def _expected(table, inputs):
    _, outputs = evaluate_table(table, inputs, "first")
    return "" if not outputs else str(outputs[0])


_INSTANCES = {}
#: the JavaRosa functions the expressions use, local to these evaluations (``instance`` is
#: read as ``tricc-instance``: tests/test_dmn_instance.py registers one globally, which wins)
FUNCTIONS = {
    (None, "tricc-instance"): lambda _, name: [_INSTANCES[_text(name)]],
    (None, "if"): lambda _, test, then, otherwise: _text(then) if test else _text(otherwise),
    (None, "int"): lambda _, v: float("nan") if math.isnan(_number(v)) else float(math.trunc(_number(v))),
    (None, "join"): lambda _, sep, nodes: _text(sep).join((n.text or "") for n in nodes),
    (None, "coalesce"): lambda _, a, b: _text(a) if _text(a) not in ("", None) else _text(b),
    # a space-separated list holds the value
    (None, "selected"): lambda _, values, value: _text(value) in _text(values).split(" "),
    # the arguments cht:extension-lib passes to the library, joined with |
    (None, "library-arguments"): lambda _, *args: "|".join(_text(a) for a in args),
}


def _strategy(name, tmp_path, max_inline_rows=10, tables=None):
    from tricc_oo.strategies.output.xls_form import XLSFormStrategy
    from tricc_oo.strategies.output.xlsform_cdss import XLSFormCDSSStrategy
    from tricc_oo.strategies.output.xlsform_cht import XLSFormCHTStrategy

    project = load_yaml_project(YAML_FIXTURE)
    project.decision_tables = tables or {}
    project.decision_table_max_inline_rows = max_inline_rows
    cls = {"XLSForm": XLSFormStrategy, "CDSS": XLSFormCDSSStrategy, "CHT": XLSFormCHTStrategy}[name]
    return cls(project, str(tmp_path))


def _evaluate(expression, fields=None):
    """Evaluate ``expression`` with lxml, ``${name}`` replaced by a literal of its value."""
    for name, value in (fields or {}).items():
        expression = expression.replace(f"${{{name}}}", value)
    expression = re.sub(r"\binstance\(", "tricc-instance(", expression)
    result = etree.XPath(expression, extensions=FUNCTIONS)(etree.Element("data"))
    return _text(result) if isinstance(result, list) else result


def _field(value):
    """An input value as the form holds it (booleans 1 / 0, not entered: empty)."""
    if value is None:
        return "''"
    if isinstance(value, bool):
        return "'1'" if value else "'0'"
    return xpath_literal(value)


# ---------------------------------------------------------------- the cell vectors, real writer


@pytest.mark.parametrize("mode", ["inline", "instance"])
@pytest.mark.parametrize("writer", ["XLSForm", "CDSS"])
@pytest.mark.parametrize(
    "case",
    [c for c in CELLS if "error" not in c and c["type"] == "string"],
    ids=lambda c: f"{c['cell']!r}",
)
def test_string_cells_through_the_writer(case, writer, mode, tmp_path):
    table = DecisionTable(
        id="cell",
        inputs=[TableColumn(name="x", type=case["type"])],
        outputs=[TableColumn(name="hit")],
        rules=[[case["cell"], TEXT], ["-", "no"]],
    )
    tables = {"cell": table}
    strategy = _strategy(writer, tmp_path, 0 if mode == "instance" else 10, tables)
    call = expand_decision_tables(transform_cql_to_operation("DMN('cell', \"x\")"), tables, keep_calls=True)
    expression = strategy.get_tricc_operation_expression(call)
    assert (f"instance('{list_name('cell')}')" in expression) == (mode == "instance")
    _INSTANCES[list_name("cell")] = _instance(table)
    for value in case["pass"] + case["fail"]:
        expected = _expected(table, [value])
        assert _evaluate(expression, {"x": _field(value)}) == expected, value


# ---------------------------------------------------------------- the writers that quoted by hand


def test_diagnosis_list_display(tmp_path):
    strategy = _strategy("XLSForm", tmp_path)
    concepts = [
        SimpleNamespace(code="dx_cough", display="Child's \"dry\" cough"),
        SimpleNamespace(code="dx_fever", display="Fever"),
    ]
    strategy.project.code_systems = {"cs": SimpleNamespace(concept=concepts)}
    expression = strategy.tricc_operation_diagnosis_list(
        ["${dx_cough}", "${dx_fever}"], [TriccReference("dx_cough"), TriccReference("dx_fever")]
    )
    assert _evaluate(expression, {"dx_cough": "1", "dx_fever": "1"}) == "Child's \"dry\" cough,Fever,"
    assert _evaluate(expression, {"dx_cough": "0", "dx_fever": "1"}) == "Fever,"


def test_cht_extension_lib_head(tmp_path):
    strategy = _strategy("CHT", tmp_path)
    call = TriccOperation(
        TriccOperator.DMN_CALL,
        [
            TriccStatic(value="x"),
            TriccStatic(value="child's"),
            TriccStatic(value="first"),
            TriccStatic(value=TEXT),
            TriccStatic(value=TEXT),
            TriccReference("weight"),
        ],
    )
    expression = strategy.get_tricc_operation_expression(call)
    assert expression.startswith("cht:extension-lib(")
    # the arguments as the library receives them
    arguments = _evaluate(expression.replace("cht:extension-lib(", "library-arguments("), {"weight": "'5'"})
    assert arguments.split("|")[1:] == ["child's", "first", TEXT, TEXT, "5"]


def test_selected_values(tmp_path):
    strategy = _strategy("XLSForm", tmp_path)
    select = TriccNodeSelectOne(id="s1", name="s", label="S", list_name="s")
    option = TriccNodeSelectOption(id="o", name="it's", label="It is", list_name="s", select=select)
    for value in (option, 3):
        expression = strategy.tricc_operation_selected(["${s}", value])
        assert _evaluate(expression, {"s": xpath_literal(f"a {getattr(value, 'name', value)}")}) is True
        assert _evaluate(expression, {"s": "'a'"}) is False


def test_get_choice_name_field_argument(tmp_path):
    strategy = _strategy("XLSForm", tmp_path)
    by_field = strategy.get_tricc_operation_expression(transform_cql_to_operation("GetChoiceName(\"sel\", \"sel\")"))
    assert by_field == "jr:choice-name(${sel}, '${sel}')"
    static = strategy.get_tricc_operation_expression(transform_cql_to_operation("GetChoiceName(\"sel\", 'opt')"))
    etree.XPath(_as_xpath(static))  # one literal, not ''opt''


# ---------------------------------------------------------------- end to end


XPATH_COLUMNS = ("calculation", "relevance", "constraint", "choice_filter")


def _as_xpath(expression):
    """A survey cell as lxml reads it: ``${x}`` → a path, prefixed functions → ``concat``."""
    expression = re.sub(r"\$\{([^}]+)\}", r"/data/\1", expression)
    return re.sub(r"\b(?:cht|jr):[\w-]+\(", "concat(", expression)


@pytest.mark.parametrize("strategy", ["XLSFormStrategy", "XLSFormCHTStrategy"])
def test_project_with_quotes_builds_valid_xpath(strategy, tmp_path):
    logging.disable(logging.WARNING)
    try:
        assert run_project_build(PROJECT, str(tmp_path / "out"), cli_output_strategy=strategy) == 0
    finally:
        logging.disable(logging.NOTSET)
    (form,) = glob.glob(str(tmp_path / "out" / "**" / "literals.xlsx"), recursive=True)
    survey = pd.read_excel(form, sheet_name="survey", dtype=str).fillna("")
    cells = {
        (row["name"], column): row[column]
        for _, row in survey.iterrows()
        for column in XPATH_COLUMNS
        if column in survey.columns and row[column]
    }
    for (name, column), expression in cells.items():
        try:
            etree.XPath(_as_xpath(expression))
        except etree.XPathSyntaxError as error:
            pytest.fail(f"{name}.{column}: {expression!r}: {error}")
    assert "concat('Child', \"'\", 's \"dry\" cough,')" in cells[("dx_list", "calculation")]
    assert _evaluate(cells[("joined", "calculation")].replace("coalesce(${remark},'')", "''")) == TEXT

    from pyxform.validators.odk_validate import ODKValidateError
    from pyxform.xls2xform import xls2xform_convert

    # ODK Validate (when java is present) reads every bind as JavaRosa does. A CHT form's
    # inputs group is a cycle for it; XLSFormCHTStrategy.validate accepts that too.
    try:
        xls2xform_convert(form, str(tmp_path / "f.xml"), validate=shutil.which("java") is not None)
    except ODKValidateError as error:
        if strategy != "XLSFormCHTStrategy" or "Cycle detected" not in str(error):
            raise
