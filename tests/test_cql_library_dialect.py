"""Project CQL libraries: standard CQL by default, TRICC's dialect when declared (§1.8)."""

import pytest

from tricc_oo.converters.cql_library import library_dialect, parse_cql_library, parse_cql_library_functions
from tricc_oo.converters.lang import lang_version

NOT_IN = """library Helpers
define "not_sick": 'fever' not in "symptoms"
"""


def test_standard_cql_rejects_not_in():
    with pytest.raises(ValueError, match="not valid CQL"):
        parse_cql_library(NOT_IN, "helpers.cql")


def test_tricc_dialect_accepts_not_in():
    text = f"/* @dialect: tricc-cql@{lang_version()} */\n{NOT_IN}"
    assert parse_cql_library(text, "helpers.cql") == [("not_sick", "'fever' not in \"symptoms\"")]


def test_dialect_without_version():
    assert library_dialect("/*\n  @dialect: tricc-cql\n*/\nlibrary X") == ("tricc-cql", None)


def test_no_dialect_is_standard():
    assert library_dialect('library X\ndefine "a": 1') is None
    # a later comment does not declare the library's dialect
    assert library_dialect('library X\n/* @dialect: tricc-cql */\ndefine "a": 1') is None


@pytest.mark.parametrize("tag", ["@dialect: elm", "@dialect: tricc-cql@99.0.0"])
def test_unknown_dialect(tag):
    with pytest.raises(ValueError, match="E_CQL_DIALECT"):
        parse_cql_library(f"/* {tag} */\nlibrary X\ndefine \"a\": 1", "x.cql")


def test_tricc_dialect_keeps_function_tags():
    text = (
        "/* @dialect: tricc-cql */\nlibrary X\n"
        "/*\n@retrieve: false\n*/\n"
        "define function Double(v Decimal) returns Decimal: external\n"
    )
    functions = parse_cql_library_functions(text, "x.cql")
    assert functions["Double"].retrieve is False
