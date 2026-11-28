"""The TRICC CQL profile, tricc_cql.g4 (feature/20261125-expression-languages.md §1.2, §2, §3)."""

import pytest

from tricc_oo.converters.cql_to_operation import transform_cql_to_operation
from tricc_oo.converters.lang import load_lang_json, parse_cql_expression
from tricc_oo.models.base import TriccOperation, TriccOperator


def _message(construct):
    return next(c["message"] for c in load_lang_json("errors.json")["constructs"] if c["construct"] == construct)


@pytest.mark.parametrize(
    "text",
    [
        '"weight" > 38 and AgeInDays() < 60',
        "'rash' not in \"symptoms\"",
        "{{x}}",
        "{{ x | raw }} + 1",
        '"x" > {{t}}',
        "DMN('diazepam', Tuple{ weight: null })",
        "if \"a\" then 1 else 2",
        "{1, 2}",
    ],
)
def test_accepted(text):
    tree, errors = parse_cql_expression(text)
    assert errors == [] and tree is not None


@pytest.mark.parametrize(
    "text, construct, column",
    [
        ('"Observation" O where O.value > 3', "query", 16),
        ("[Observation]", "retrieve", 0),
        ('"a" union "b"', "union", 4),
        ('"list"[0]', "indexer", 6),
        ('"patient".birthDate', "member", 9),
        ('"weight".round()', "member", 8),
        ("5 'mg'", "unit", 2),
        ('Today() - 3 days', "unit", 12),
        ('years between "dob" and Today()', "plural_precision", 0),
        ('difference in days of "x"', "plural_precision", 14),
    ],
)
def test_rejected_with_its_message(text, construct, column):
    tree, errors = parse_cql_expression(text)
    assert tree is None and len(errors) == 1
    assert errors[0].code == "E_CQL_PROFILE"
    assert errors[0].construct == construct
    assert errors[0].message == _message(construct)
    assert (errors[0].line, errors[0].column) == (1, column)


def test_plain_syntax_error_has_the_column_of_the_expression():
    tree, errors = parse_cql_expression('"a" > ')
    assert tree is None
    assert errors[0].code == "E_CQL_SYNTAX"
    assert (errors[0].line, errors[0].column) == (1, 6)


def test_not_in_builds_a_negated_selection():
    op = transform_cql_to_operation("'rash' not in \"symptoms\"")
    assert isinstance(op, TriccOperation) and op.operator == TriccOperator.NOT


def test_rejected_construct_does_not_build(caplog):
    assert transform_cql_to_operation('"list"[0]', context="node x") is None
    assert "E_CQL_PROFILE" in caplog.text and "node x" in caplog.text
