"""Decision-table cells on the shared FEEL grammar (feature/20261125-expression-languages.md §1.5, §3)."""

import pytest

from tricc_oo.converters.feel_cell import cell_value, parse_cell_tree
from tricc_oo.converters.lang import load_lang_json
from tricc_oo.models.decision_table import DecisionTableError, parse_cell

FEEL_TEXT = load_lang_json("meaning.json")["feel_text"]


@pytest.mark.parametrize(
    "cell", ["-", "null", "not(null)", "< 5", ">= -2.5", "[1..5)", "(0..10]", "'yes', 'no'", "'it''s'", "true", "5"]
)
def test_grammar_accepts(cell):
    tree, problem = parse_cell_tree(cell)
    assert tree is not None and problem == ""


@pytest.mark.parametrize(
    "cell, problem",
    [("foo bar", "syntax"), ("[1..", "unclosed"), ("'open", "unclosed"), ("1, -", "any_in_list"),
     ("1,, 2", "empty_item"), ("[3,6)", "range")],
)
def test_grammar_rejects(cell, problem):
    assert parse_cell_tree(cell) == (None, problem)


@pytest.mark.parametrize("case", FEEL_TEXT, ids=lambda c: c["tricc"])
def test_tricc_text_is_feel_text(case):
    """meaning.json: TRICC's 'text' and FEEL's "text" are the same test."""
    column = "string" if "'" in case["tricc"] else "decimal"
    assert parse_cell(case["tricc"], column) == parse_cell(case["feel"], column)


@pytest.mark.parametrize(
    "text, value", [("'a\\'b'", "a'b"), ("'it''s'", "it's"), ('"x"', "x"), ("-2.5", -2.5), ("3", 3), ("false", False)]
)
def test_cell_value(text, value):
    assert cell_value(text) == value


def test_hex_is_not_a_cell_number():
    with pytest.raises(DecisionTableError) as exc:
        parse_cell("0x1F", "integer")
    assert exc.value.code == "E_DMN_CELL"
