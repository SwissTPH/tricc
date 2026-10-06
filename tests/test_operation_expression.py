"""Unit tests: TriccOperation → XLSForm / CQL / FHIRPath.

These cases are the contract for tricc_og. Field references are
``TriccReference``; ``$this`` is the current node (``.`` in XLSForm).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference, TriccStatic
from tricc_oo.strategies.output.fhir_form import FHIRStrategy
from tricc_oo.strategies.output.xls_form import XLSFormStrategy


def op(operator, *refs):
    return TriccOperation(operator, list(refs))


def ref(name):
    return TriccReference(name)


def st(value):
    return TriccStatic(value)


# (id, operation, xls, cql, fhirpath)
CASES = [
    (
        "equal_ref_int",
        op(TriccOperator.EQUAL, ref("age"), st(18)),
        "${age}=18",
        "Helper.GetObservationValue('age') = 18",
        "%resource.repeat(item).where(linkId='age').answer.where($this.exists()).value = 18.0",
    ),
    (
        "equal_this_static",
        op(TriccOperator.EQUAL, st("$this"), st(1)),
        ".=1",
        "'$this' = 1",
        "'$this' = 1.0",
    ),
    (
        "equal_this_ref",
        op(TriccOperator.EQUAL, ref("$this"), st(1)),
        ".=1",
        "Helper.GetObservationValue('$this') = 1",
        "%resource.repeat(item).where(linkId='.').answer.where($this.exists()).value = 1.0",
    ),
    (
        "more_or_equal",
        op(TriccOperator.MORE_OR_EQUAL, ref("age"), st(18)),
        "${age}>=18",
        "Helper.GetObservationValue('age') >= 18",
        "(%resource.repeat(item).where(linkId='age').answer.where($this.exists()).value).toDecimal() >= 18.0",
    ),
    (
        "less",
        op(TriccOperator.LESS, ref("age"), st(5)),
        "${age}<5",
        "Helper.GetObservationValue('age') < 5",
        "(%resource.repeat(item).where(linkId='age').answer.where($this.exists()).value).toDecimal() < 5.0",
    ),
    (
        "and_two",
        op(
            TriccOperator.AND,
            op(TriccOperator.MORE, ref("age"), st(2)),
            op(TriccOperator.LESS, ref("age"), st(10)),
        ),
        "${age}>2 and ${age}<10",
        "Helper.GetObservationValue('age') > 2 and Helper.GetObservationValue('age') < 10",
        "(%resource.repeat(item).where(linkId='age').answer.where($this.exists()).value).toDecimal() > 2.0 and (%resource.repeat(item).where(linkId='age').answer.where($this.exists()).value).toDecimal() < 10.0",
    ),
    (
        "or_two",
        op(TriccOperator.OR, ref("a"), ref("b")),
        "${a} or ${b}",
        "Helper.GetObservationValue('a') or Helper.GetObservationValue('b')",
        "%resource.repeat(item).where(linkId='a').answer or %resource.repeat(item).where(linkId='b').answer",
    ),
    (
        "not_eq",
        op(TriccOperator.NOT, op(TriccOperator.EQUAL, ref("x"), st(1))),
        "not(${x}=1)",
        "not Helper.GetObservationValue('x') = 1",
        "(%resource.repeat(item).where(linkId='x').answer.where($this.exists()).value = 1.0).not()",
    ),
    (
        "istrue",
        op(TriccOperator.ISTRUE, ref("has_symptom")),
        "${has_symptom}>=1",
        "(Helper.GetObservationValue('has_symptom') is true)",
        "(%resource.repeat(item).where(linkId='has_symptom').answer.where($this.exists()).value = true)",
    ),
    (
        "isfalse",
        op(TriccOperator.ISFALSE, ref("has_symptom")),
        "${has_symptom}=0",
        "(Helper.GetObservationValue('has_symptom') is false)",
        "(%resource.repeat(item).where(linkId='has_symptom').answer.where($this.exists()).value = false)",
    ),
    (
        "isnottrue",
        op(TriccOperator.ISNOTTRUE, ref("has_symptom")),
        "${has_symptom}<1",
        "(Helper.GetObservationValue('has_symptom') is not true)",
        "(%resource.repeat(item).where(linkId='has_symptom').answer.where($this.exists()).value != true)",
    ),
    (
        "selected_int",
        op(TriccOperator.SELECTED, ref("weight_na"), st(1)),
        "selected(${weight_na}, '1')",
        "(1 in Helper.GetObservationValue('weight_na'))",
        "%resource.repeat(item).where(linkId='weight_na').answer.where($this.value.code = 1.0).exists()",
    ),
    (
        "selected_str",
        op(TriccOperator.SELECTED, ref("fever"), st("yes")),
        "selected(${fever}, 'yes')",
        "('yes' in Helper.GetObservationValue('fever'))",
        "%resource.repeat(item).where(linkId='fever').answer.where($this.value.code = 'yes').exists()",
    ),
    (
        "exists",
        op(TriccOperator.EXISTS, ref("age")),
        "coalesce(${age}, '')!=''",
        "(Helper.GetObservationValue('age') is not null)",
        "%resource.repeat(item).where(linkId='age').answer.exists()",
    ),
    (
        "isnull",
        op(TriccOperator.ISNULL, ref("age")),
        "${age}=''",
        "(Helper.GetObservationValue('age') is null)",
        "%resource.repeat(item).where(linkId='age').answer.empty()",
    ),
    (
        "isnotnull",
        op(TriccOperator.ISNOTNULL, ref("age")),
        "${age}!=''",
        "(Helper.GetObservationValue('age') is not null)",
        "%resource.repeat(item).where(linkId='age').answer.exists()",
    ),
    (
        "notexists",
        op(TriccOperator.NOTEXISTS, ref("age")),
        "${age}=''",
        "(Helper.GetObservationValue('age') is null)",
        "%resource.repeat(item).where(linkId='age').answer.empty()",
    ),
    (
        "between",
        op(TriccOperator.BETWEEN, ref("age"), st(1), st(5)),
        "${age}>=1 and ${age} < 5",
        "(Helper.GetObservationValue('age') between 1 and 5)",
        "((%resource.repeat(item).where(linkId='age').answer.where($this.exists()).value).toDecimal() >= 1.0 and (%resource.repeat(item).where(linkId='age').answer.where($this.exists()).value).toDecimal() <= 5.0)",
    ),
    (
        "plus",
        op(TriccOperator.PLUS, ref("a"), ref("b")),
        "${a} + ${b}",
        "Helper.GetObservationValue('a') + Helper.GetObservationValue('b')",
        "(%resource.repeat(item).where(linkId='a').answer.where($this.exists()).value).toDecimal() + (%resource.repeat(item).where(linkId='b').answer.where($this.exists()).value).toDecimal()",
    ),
    (
        "minus_bin",
        op(TriccOperator.MINUS, ref("a"), st(3)),
        "${a} - 3",
        "Helper.GetObservationValue('a') - 3",
        "(%resource.repeat(item).where(linkId='a').answer.where($this.exists()).value).toDecimal() - 3.0",
    ),
    (
        "minus_unary",
        op(TriccOperator.MINUS, st(3)),
        "-3",
        "-3",
        "-3.0",
    ),
    (
        "cast_number",
        op(TriccOperator.CAST_NUMBER, ref("age")),
        "number(${age})",
        "ToDecimal(Helper.GetObservationValue('age'))",
        "%resource.repeat(item).where(linkId='age').answer.toDecimal()",
    ),
    (
        "coalesce",
        op(TriccOperator.COALESCE, ref("age"), st(0)),
        "coalesce(${age}, 0)",
        "Coalesce(Helper.GetObservationValue('age'), 0)",
        "(%resource.repeat(item).where(linkId='age').answer.where($this.exists()).value|0.0).where($this.exists()).first()",
    ),
    (
        "if_",
        op(TriccOperator.IF, op(TriccOperator.ISTRUE, ref("x")), st(1), st(0)),
        "if(${x}>=1,1,0)",
        "if (Helper.GetObservationValue('x') is true) then 1 else 0",
        "iif((%resource.repeat(item).where(linkId='x').answer.where($this.exists()).value = true), 1.0, 0.0)",
    ),
    (
        "count",
        op(TriccOperator.COUNT, ref("sel")),
        "count-selected(${sel})",
        "Count({Helper.GetObservationValue('sel')})",
        "%resource.repeat(item).where(linkId='sel').answer.count()",
    ),
    (
        "contains",
        op(TriccOperator.CONTAINS, ref("name"), st("ab")),
        "contains(${name}, 'ab')",
        "(Helper.GetObservationValue('name') contains 'ab')",
        "%resource.repeat(item).where(linkId='name').answer.where($this.value.code = 'ab').exists()",
    ),
    (
        "concat",
        op(TriccOperator.CONCATENATE, st("A"), ref("B")),
        "concat('A',${B})",
        "'A' + Helper.GetObservationValue('B')",
        "'A' & %resource.repeat(item).where(linkId='B').answer.where($this.exists()).value",
    ),
    (
        "paren",
        op(TriccOperator.PARENTHESIS, op(TriccOperator.EQUAL, ref("age"), st(1))),
        "(${age}=1)",
        "(Helper.GetObservationValue('age') = 1)",
        "(%resource.repeat(item).where(linkId='age').answer.where($this.exists()).value = 1.0)",
    ),
    (
        "not_equal",
        op(TriccOperator.NOTEQUAL, ref("sex"), st("m")),
        "${sex}!='m'",
        "Helper.GetObservationValue('sex') != 'm'",
        "%resource.repeat(item).where(linkId='sex').answer.where($this.exists()).value != 'm'",
    ),
    (
        "and_or_mix",
        op(TriccOperator.AND, op(TriccOperator.OR, ref("a"), ref("b")), ref("c")),
        "(${a} or ${b}) and ${c}",
        "Helper.GetObservationValue('a') or Helper.GetObservationValue('b') and Helper.GetObservationValue('c')",
        "%resource.repeat(item).where(linkId='a').answer or %resource.repeat(item).where(linkId='b').answer and %resource.repeat(item).where(linkId='c').answer",
    ),
]


def _xls():
    return XLSFormStrategy.__new__(XLSFormStrategy)


def _fhir():
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    return FHIRStrategy(project, "/tmp/op_expr")


@pytest.fixture(scope="module")
def xls():
    return _xls()


@pytest.fixture(scope="module")
def fhir():
    return _fhir()


@pytest.mark.parametrize(
    "case_id,operation,xls_exp,cql_exp,fp_exp",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_xlsform_expression(xls, case_id, operation, xls_exp, cql_exp, fp_exp):
    assert xls.get_tricc_operation_expression(operation) == xls_exp


@pytest.mark.parametrize(
    "case_id,operation,xls_exp,cql_exp,fp_exp",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_cql_expression(fhir, case_id, operation, xls_exp, cql_exp, fp_exp):
    assert fhir.convert_expression_to_cql(operation) == cql_exp


@pytest.mark.parametrize(
    "case_id,operation,xls_exp,cql_exp,fp_exp",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_fhirpath_expression(fhir, case_id, operation, xls_exp, cql_exp, fp_exp):
    assert fhir.convert_expression_to_fhirpath(operation) == fp_exp
