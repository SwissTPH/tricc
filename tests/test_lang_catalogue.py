"""The function catalogue and the meaning rules (feature/20261125-expression-languages.md §1.3, §1.4, §3)."""

import logging

import pytest

from tricc_oo.converters.cql_to_operation import FUNCTION_MAP, stored_data_functions, transform_cql_to_operation
from tricc_oo.converters.lang import load_lang_json
from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference, TriccStatic
from tricc_oo.models.params import is_expression_arg, literal_value
from tricc_oo.visitors.constant_eval import SUPPORTED_OPERATORS
from tricc_oo.visitors.expression_checks import check_unknown_functions

CATALOGUE = load_lang_json("functions.json")["functions"]
MEANING = load_lang_json("meaning.json")

# FUNCTION_MAP as it was before the catalogue (develop 61905ed)
FUNCTION_MAP_BEFORE = {
    "AgeInYears": TriccOperator.AGE_YEAR,
    "AgeInMonths": TriccOperator.AGE_MONTH,
    "AgeInDays": TriccOperator.AGE_DAY,
    "Coalesce": TriccOperator.COALESCE,
    "Concatenate": TriccOperator.CONCATENATE,
    "iZScore": TriccOperator.IZSCORE,
    "ZScore": TriccOperator.ZSCORE,
    "Izscore": TriccOperator.IZSCORE,
    "Zscore": TriccOperator.ZSCORE,
    "Round": TriccOperator.ROUND,
    "Integer": TriccOperator.CAST_INTEGER,
    "DMN": TriccOperator.DMN,
    "DMNFirst": TriccOperator.DMN,
    "DMNList": TriccOperator.DMN,
    "DrugDosage": TriccOperator.DMN,
    "HasQualifier": TriccOperator.HAS_QUALIFIER,
    "DateTimeToDecimal": TriccOperator.DATETIME_TO_DECIMAL,
    "ToDate": TriccOperator.CAST_DATE,
    "ToDecimal": TriccOperator.CAST_NUMBER,
    "ToInteger": TriccOperator.CAST_INTEGER,
    "ToString": TriccOperator.CAST_STRING,
    "ToBoolean": TriccOperator.CAST_BOOLEAN,
    "Count": TriccOperator.COUNT,
    "DiagnosisList": TriccOperator.DIAGNOSIS_LIST,
    "Today": TriccOperator.TODAY,
    "Now": TriccOperator.NOW,
    "GetContentVersion": TriccOperator.CONTENT_VERSION,
    "Abs": TriccOperator.ABS,
    "Min": TriccOperator.MIN,
    "Max": TriccOperator.MAX,
    "Sum": TriccOperator.SUM,
    "FormatDate": TriccOperator.FORMAT_DATE,
    "Length": TriccOperator.LENGTH,
    "NormalizeSpace": TriccOperator.NORMALIZE_SPACE,
    "Matches": TriccOperator.MATCHES,
    "CountSelected": TriccOperator.COUNT_SELECTED,
    "GetRepeatedValue": TriccOperator.GET_REPEATED_VALUE,
}

# stored_data_functions.json as it was before the catalogue (+ Retrieve, feature/retrievals)
STORED_BEFORE = {
    "AgeInDays": "patient", "AgeInMonths": "patient", "AgeInYears": "patient", "GetPatientValue": "patient",
    "GetEncounterValue": "encounter", "GetEncounterObservationValue": "encounter",
    "GetEncounterConditionValue": "encounter", "GetObservationValue": "encounter",
    "GetConditionValue": "encounter", "GetRepeatedValue": "encounter",
    "GetHistoryObservation": "history", "GetHistoryObservationValue": "history",
    "GetHistoryObservationSince": "history", "GetHistoryObservationValueSince": "history",
    "GetHistoryObservationCodesSince": "history", "GetHistoryCondition": "history",
    "GetHistoryConditionValue": "history", "Retrieve": "history", "GetPractitionerValue": "context", "GetLocationValue": "context",
    "GetFacilityValue": "context",
}


class TestCatalogue:
    def test_every_operator_mapped_before_is_in_it(self):
        assert FUNCTION_MAP == FUNCTION_MAP_BEFORE

    def test_stored_data_functions_unchanged(self):
        assert stored_data_functions() == STORED_BEFORE

    def test_decision_table_calls(self):
        names = {e["name"]: e for e in CATALOGUE}
        assert {"DMN", "DMNFirst", "DMNList"} <= set(names)
        assert all(names[n]["operator"] == "DMN" for n in ("DMN", "DMNFirst", "DMNList"))

    @pytest.mark.parametrize("entry", CATALOGUE, ids=lambda e: e["name"])
    def test_entry_shape(self, entry):
        assert set(entry) == {"name", "params", "returns", "operator", "reads", "foldable"}
        assert entry["reads"] in ("none", "patient", "encounter", "history", "context")
        assert entry["operator"] is None or entry["operator"] in TriccOperator.__members__
        for param in entry["params"]:
            assert set(param) <= {"name", "type", "optional", "variadic"} and param["name"] and param["type"]

    @pytest.mark.parametrize("entry", CATALOGUE, ids=lambda e: e["name"])
    def test_foldable_matches_constant_eval(self, entry):
        runs = bool(entry["operator"]) and TriccOperator[entry["operator"]] in SUPPORTED_OPERATORS
        assert entry["foldable"] == (runs and entry["reads"] == "none")

    def test_names_unique(self):
        names = [e["name"] for e in CATALOGUE]
        assert len(names) == len(set(names))


class TestMeaning:
    @pytest.mark.parametrize("case", MEANING["parse"], ids=lambda c: c["text"])
    def test_parse(self, case):
        parsed = transform_cql_to_operation(case["text"], quiet=True)
        kind = case["kind"]
        if kind == "reference":
            assert isinstance(parsed, TriccReference) and parsed.value == case["value"]
        elif kind == "operation":
            assert isinstance(parsed, TriccOperation)
        elif kind == "null":
            assert parsed is None
        else:
            assert isinstance(parsed, TriccStatic) and parsed.value == case["value"]
            expected_type = {"text": str, "number": (int, float), "boolean": bool}[kind]
            assert isinstance(parsed.value, expected_type)

    @pytest.mark.parametrize("case", MEANING["expression_arg"], ids=lambda c: c["arg"] or "<empty>")
    def test_is_expression_arg(self, case):
        assert is_expression_arg(case["arg"]) is case["expression"]

    @pytest.mark.parametrize("case", MEANING["literal_value"], ids=lambda c: c["arg"])
    def test_literal_value(self, case):
        assert literal_value(case["arg"]) == case["value"]


class _Node:
    def __init__(self, name, expression):
        self.name = name
        self.id = name
        self.expression = expression


class _Project:
    def __init__(self, expression, aliases=None, function_signatures=None):
        page = type("Page", (), {})()
        page.nodes = {"n": _Node("n", expression)}
        self.pages = {"p": page}
        self.library_calculates = []
        self.aliases = aliases or {}
        self.function_signatures = function_signatures or {}


class TestUnknownFunction:
    def test_warns_once_per_name(self, caplog):
        caplog.set_level(logging.WARNING, logger="default")
        project = _Project(transform_cql_to_operation('Foo("a") > 1 and Foo(2)'))
        assert list(check_unknown_functions(project)) == ["Foo"]
        assert caplog.text.count("W_CQL_UNKNOWN_FUNCTION") == 1

    def test_catalogue_alias_and_declared_are_known(self):
        expression = transform_cql_to_operation("GetPatientValue('x') + DrugDose(1) + Mine(2) + Zscore('a', 1, 2, 3)")
        project = _Project(expression, aliases={"DrugDose": object()}, function_signatures={"mine": object()})
        assert check_unknown_functions(project) == {}
