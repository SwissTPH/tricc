"""Build-time evaluation of constant expressions (RFC SwissTPH/tricc#86)."""

import pytest

from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference, TriccStatic
from tricc_oo.visitors.constant_eval import (
    SUPPORTED_OPERATORS,
    TriccEvalDeferred,
    TriccEvalUnsupported,
    TriccNotConstant,
    evaluate_constant,
)


def value(expression, calculates=None):
    result = evaluate_constant(expression, (calculates or {}).get)
    return None if result is None else result.value


class TestOperators:
    @pytest.mark.parametrize("expression,expected", [
        ("37 + 1", 38),
        ("38 - 0.5", 37.5),
        ("-3", -3),
        ("2 * 1.5", 3),
        ("7 / 2", 3.5),
        ("4 / 2", 2),
        ("0.1 + 0.2", 0.3),  # Decimal: no binary rounding
        ("7 mod 3", 1),
        ("Abs(-3)", 3),
        ("Min(3, 1, 2)", 1),
        ("Max(3, 1, 2)", 3),
        ("Round(40.2)", 40),
        ("Round(2.345, 2)", 2.35),
        ("Round(-1.5)", -1),  # CQL: halves toward positive infinity
        ("'axil' + 'lary'", "axillary"),
        ("Concatenate('a', 'b', 'c')", "abc"),
        ("1 = 1", True),
        ("1 != 1", False),
        ("2 > 1", True),
        ("2 < 1", False),
        ("2 >= 2", True),
        ("2 <= 1", False),
        ("'a' < 'b'", True),
        ("not (1 > 2)", True),
        ("1 < 2 and 2 < 3", True),
        ("1 > 2 or 2 < 3", True),
        ("if 1 > 2 then 'a' else 'b'", "b"),
        ("(1 + 2) * 3", 9),
    ])
    def test_value(self, expression, expected):
        result = value(expression)
        assert result == expected and type(result) is type(expected)

    def test_every_listed_operator_is_supported(self):
        listed = {"and", "or", "not", "equal", "not_equal", "more", "less", "more_or_equal", "less_or_equal",
                  "plus", "minus", "multiplied", "divided", "if", "concatenate", "abs", "min", "max", "round",
                  "istrue", "isfalse", "exists"}
        assert listed <= {str(o) for o in SUPPORTED_OPERATORS}

    def test_a_literal_is_its_value(self):
        assert value("38") == 38
        assert value("'axillary'") == "axillary"
        assert value(TriccStatic(True)) is True


class TestNull:
    def op(self, operator, *refs):
        return TriccOperation(operator, list(refs))

    def test_three_valued_logic(self):
        true, false = TriccStatic(True), TriccStatic(False)
        assert value(self.op(TriccOperator.AND, true, None)) is None
        assert value(self.op(TriccOperator.AND, false, None)) is False
        assert value(self.op(TriccOperator.OR, true, None)) is True
        assert value(self.op(TriccOperator.OR, false, None)) is None
        assert value(self.op(TriccOperator.NOT, None)) is None

    @pytest.mark.parametrize("operator", [TriccOperator.PLUS, TriccOperator.MORE, TriccOperator.EQUAL,
                                          TriccOperator.MAX, TriccOperator.CONCATENATE])
    def test_propagates(self, operator):
        assert value(self.op(operator, TriccStatic(1), None)) is None

    def test_tests_on_null(self):
        assert value(self.op(TriccOperator.ISTRUE, None)) is False
        assert value(self.op(TriccOperator.ISFALSE, None)) is False
        assert value(self.op(TriccOperator.EXISTS, None)) is False
        assert value(self.op(TriccOperator.EXISTS, TriccStatic(0))) is True
        assert value("Coalesce(null, 2)") == 2

    def test_if_with_null_condition_takes_else(self):
        assert value(self.op(TriccOperator.IF, None, TriccStatic("a"), TriccStatic("b"))) == "b"

    def test_division_by_zero(self):
        assert value("1 / 0") is None
        assert value("1 mod 0") is None

    def test_short_circuit_skips_the_rest(self):
        assert value("1 < 2 or (1 / 0 > 1)") is True


class TestReferences:
    def test_input_is_not_constant(self):
        with pytest.raises(TriccNotConstant):
            value('"weight" + 1', {"weight": None})
        with pytest.raises(TriccNotConstant):
            value('"unknown" + 1')

    def test_without_resolver_a_reference_is_not_constant(self):
        with pytest.raises(TriccNotConstant):
            evaluate_constant('"a"')

    def test_constant_calculate_nested(self):
        calcs = {"a": "37 + 1", "b": '"a" + 0.5', "c": 'if "b" > 38 then \'high\' else \'low\''}
        assert value('"b" * 2', calcs) == 77
        assert value('"c"', calcs) == "high"

    def test_a_calculate_reading_an_input_is_not_constant(self):
        with pytest.raises(TriccNotConstant):
            value('"b"', {"b": '"a" + 1', "a": None})

    def test_cycle(self):
        with pytest.raises(TriccNotConstant, match="cycle"):
            value('"a"', {"a": '"b" + 1', "b": '"a" + 1'})

    def test_reference_object(self):
        assert value(TriccReference("a"), {"a": "2"}) == 2


class TestNotConstant:
    @pytest.mark.parametrize("expression", ["Today()", "Now() > Today()", "AgeInDays() + 1"])
    def test_data_and_time(self, expression):
        with pytest.raises(TriccNotConstant):
            value(expression)


class TestFunctions:
    """A function called as written, looked up in the project's CQL libraries (``@retrieve``)."""

    def declared(self, retrieve):
        from tricc_oo.converters.cql_library import FunctionSignature

        sig = FunctionSignature("Bmi", "decimal", tags={} if retrieve is None else {"retrieve": retrieve})
        return lambda name: {"bmi": sig}.get(name.lower())

    @pytest.mark.parametrize("retrieve", ["true", None])  # no tag: assume it reads data
    def test_retrieve_true_or_no_tag_is_data(self, retrieve):
        with pytest.raises(TriccNotConstant, match="retrieve"):
            evaluate_constant("Bmi(70, 1.7)", functions=self.declared(retrieve))

    def test_retrieve_false_is_static_computed_by_the_form(self):
        with pytest.raises(TriccEvalDeferred, match="only the form") as err:
            evaluate_constant("Bmi(70, 1.7)", functions=self.declared("false"))
        assert err.value.operator == "Bmi"

    def test_undeclared(self):
        with pytest.raises(TriccEvalUnsupported, match="not declared") as err:
            evaluate_constant("Foo(1)")
        assert not isinstance(err.value, TriccEvalDeferred)

    def test_data_argument_wins(self):
        with pytest.raises(TriccNotConstant):
            evaluate_constant('Bmi("weight", 1.7)', functions=self.declared("false"))

    def test_not_cql(self):
        with pytest.raises(TriccNotConstant):
            value("1 +")


class TestUnsupported:
    def test_names_the_operator(self):
        with pytest.raises(TriccEvalUnsupported) as err:
            value("case when 1 > 0 then 2 else 3 end")
        assert err.value.operator == "case"

    def test_data_wins_over_unsupported(self):
        # reads an input: dynamic, even though `case` cannot be evaluated
        with pytest.raises(TriccNotConstant):
            value('case when "weight" > 0 then 2 else 3 end', {"weight": None})

    def test_wrong_types(self):
        with pytest.raises(TriccEvalUnsupported, match="equal"):
            value("1 = 'a'")
        with pytest.raises(TriccEvalUnsupported):
            value("1 + 'a'")
