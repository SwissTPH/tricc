"""Output capability statements against the writers (feature/20261125-output-capabilities.md §1, §4).

Every ``TriccOperator`` and catalogue function is fed to each strategy's expression writer: a
construct the writer handles must be in the strategy's resolved statement (after ``extends``),
one it rejects must not. The retrieval contexts are probed the same way.
"""

import json
import os

import pytest

from tricc_oo.converters.capabilities import (
    SCHEMA_FILE,
    TABLE_OPERATORS,
    TriccCapabilityError,
    resolve_statement,
    satisfies,
    validate_statement,
)
from tricc_oo.converters.lang import lang_version, load_lang_json
from tricc_oo.models.base import TriccNodeType, TriccOperator, TriccStatic

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGES = os.path.join(ROOT, "capabilities")


def _load_packages():
    statements, packages = {}, {}
    for name in sorted(os.listdir(PACKAGES)):
        folder = os.path.join(PACKAGES, name)
        if not os.path.isdir(folder):
            continue
        with open(os.path.join(folder, "statement.json"), encoding="utf-8") as file:
            statement = json.load(file)
        with open(os.path.join(folder, "package.json"), encoding="utf-8") as file:
            packages[statement["id"]] = json.load(file)
        statements[statement["id"]] = statement
    return statements, packages


STATEMENTS, PACKAGE_JSON = _load_packages()


def _strategy_class(name):
    import tricc_oo.strategies  # noqa: F401  (registers the built-in strategies)
    from tricc_oo.strategies.output.dhis2_form import DHIS2Strategy
    from tricc_oo.strategies.output.spice import SpiceStrategy
    from tricc_oo.strategies.registry import get_output_strategy

    unregistered = {"DHIS2Strategy": DHIS2Strategy, "SpiceStrategy": SpiceStrategy}
    return unregistered.get(name) or get_output_strategy(name)


def _bare_instance(cls):
    """An instance without ``__init__`` (no project): the writer methods only format text."""
    abstract = getattr(cls, "__abstractmethods__", ())
    if abstract:
        cls = type(f"{cls.__name__}Probe", (cls,), {name: (lambda *a, **k: None) for name in abstract})
    return cls.__new__(cls)


def _call(method, n):
    refs = [f"x{i}" for i in range(n)]
    try:
        return method(refs, [TriccStatic(f"x{i}") for i in range(n)])
    except TypeError as exc:
        if "positional argument" not in str(exc):
            raise
        return method(refs)


def writer_handles(cls, operator, context):
    """Whether the strategy's writer writes ``operator`` in ``context``.

    The writer dispatches on ``tricc_operation_<operator>`` (FHIRPath first tries
    ``tricc_operation_fhirpath_<operator>``). A missing method or a ``NotImplementedError`` is a
    rejection; a method that needs a real graph to finish still writes the operator.
    """
    instance = _bare_instance(cls)
    prefixes = ["tricc_operation_fhirpath_", "tricc_operation_"] if context == "inline" else ["tricc_operation_"]
    method = next(
        (getattr(instance, f"{p}{operator.value}") for p in prefixes if hasattr(instance, f"{p}{operator.value}")), None
    )
    if method is None:
        return False
    for n in (2, 3, 1, 4):
        try:
            _call(method, n)
            return True
        except NotImplementedError:
            return False
        except (Exception, SystemExit):
            continue
    return True


def writer_contexts(cls):
    return ["inline", "library"] if hasattr(cls, "get_tricc_operation_expression_fhirpath") else ["form"]


def helper_functions():
    """Functions the FHIR Helper library defines (the stored-data functions it writes)."""
    import inspect
    import re

    from tricc_oo.converters.fhir import populate_helper, repeat_helper

    source = inspect.getsource(repeat_helper) + inspect.getsource(populate_helper)
    return set(re.findall(r"define function \"?(\w+)", source))


def writer_functions(cls, handled_operators):
    """Catalogue functions the strategy writes: through their operator, or (no operator) as a
    function of the FHIR Helper library."""
    helpers = helper_functions() if "inline" in writer_contexts(cls) else set()
    functions = set()
    for entry in load_lang_json("functions.json")["functions"]:
        operator = entry["operator"]
        if operator in TABLE_OPERATORS:
            continue
        if operator is None:
            if entry["name"] in helpers:
                functions.add(entry["name"])
        elif operator in handled_operators:
            functions.add(entry["name"])
    return functions


def writer_retrieval_contexts(cls):
    from tricc_oo.converters.retrieval import (
        CQL_LANGUAGE,
        DEFAULT_FUNCTION,
        RETRIEVAL_CONTEXTS,
        XLSFORM_LANGUAGE,
        Retrieval,
    )

    instance = _bare_instance(cls)
    supported = set()
    for context in RETRIEVAL_CONTEXTS:
        retrieval = Retrieval(
            code="#probe", context=context, function=DEFAULT_FUNCTION.get(context), reads_code="probe",
            expressions={CQL_LANGUAGE: '"probe"', XLSFORM_LANGUAGE: "${probe}"},
        )
        try:
            instance.retrieval_expression(retrieval)
            supported.add(context)
        except Exception:
            pass
    return supported


def writer_populate_contexts(cls):
    """CHT reads prefilled values from the contact summary, FHIR from the Helper library."""
    from tricc_oo.converters.fhir.populate_helper import ALLOWED_CONTEXTS

    return set(ALLOWED_CONTEXTS) if hasattr(cls, "get_cht_input") or hasattr(cls, "_populate_reference") else set()


def writer_operators(cls):
    handled = {}
    for operator in TriccOperator:
        if operator.name in TABLE_OPERATORS:
            continue
        contexts = [c for c in writer_contexts(cls) if writer_handles(cls, operator, c)]
        if contexts:
            handled[operator.name] = set(contexts)
    return handled


def resolved(statement_id):
    return resolve_statement(statement_id, STATEMENTS)


IDS = sorted(STATEMENTS)


# ---------------------------------------------------------------- packages


@pytest.mark.parametrize("statement_id", IDS)
def test_statement_matches_the_schema(statement_id):
    validate_statement(STATEMENTS[statement_id], statement_id)


@pytest.mark.parametrize("statement_id", IDS)
def test_package_json(statement_id):
    statement, package = STATEMENTS[statement_id], PACKAGE_JSON[statement_id]
    assert package["name"] == statement["id"] and package["version"] == statement["version"]
    parent = statement.get("extends")
    if parent:
        assert package["dependencies"][parent["package"]] == parent["version"]
        assert satisfies(STATEMENTS[parent["package"]]["version"], parent["version"])
    assert os.path.isfile(os.path.join(PACKAGES, statement_id.split("capabilities-")[1], "CHANGELOG.md"))


@pytest.mark.parametrize("statement_id", IDS)
def test_lang_range_covers_this_tricc(statement_id):
    assert satisfies(lang_version(), STATEMENTS[statement_id]["lang"])


def test_shipped_schema_is_the_repository_schema():
    with open(os.path.join(PACKAGES, "statement.schema.json"), encoding="utf-8") as a, open(SCHEMA_FILE) as b:
        assert json.load(a) == json.load(b)


# ---------------------------------------------------------------- statements against the writers


@pytest.mark.parametrize("statement_id", IDS)
def test_operators_match_the_writer(statement_id):
    statement = resolved(statement_id)
    cls = _strategy_class(statement.strategy)
    assert statement.contexts == set(writer_contexts(cls))
    assert statement.operators == writer_operators(cls)


@pytest.mark.parametrize("statement_id", IDS)
def test_functions_match_the_writer(statement_id):
    statement = resolved(statement_id)
    cls = _strategy_class(statement.strategy)
    assert statement.functions == writer_functions(cls, set(writer_operators(cls)))


@pytest.mark.parametrize("statement_id", IDS)
def test_retrieval_and_populate_contexts_match_the_writer(statement_id):
    statement = resolved(statement_id)
    cls = _strategy_class(statement.strategy)
    assert statement.retrieval_contexts == writer_retrieval_contexts(cls)
    assert statement.populate_contexts == writer_populate_contexts(cls)


@pytest.mark.parametrize("statement_id", IDS)
def test_features_match_the_class(statement_id):
    statement = resolved(statement_id)
    cls = _strategy_class(statement.strategy)
    assert ("decision_table_calls" in statement.features) == bool(getattr(cls, "decision_table_calls", False))
    assert "function_bodies" not in statement.features  # #101 adds them
    assert statement.data_types <= set(TriccNodeType.__members__)


# ---------------------------------------------------------------- extends


def _child(add=None, remove=None, version="^1.0.0"):
    return {
        "id": "@x/child", "version": "1.0.0", "strategy": "X", "lang": "^1.0.0",
        "extends": {"package": "@x/parent", "version": version},
        "add": add or {}, "remove": remove or {},
    }


PARENT = {
    "id": "@x/parent", "version": "1.2.0", "strategy": "X", "lang": "^1.0.0", "contexts": ["form"],
    "operators": {"AND": ["form"], "POWER": ["form"]}, "functions": ["Abs", "Round"], "features": ["repeat"],
}


def test_child_adds_and_removes():
    child = _child(add={"operators": {"OR": ["form"]}, "functions": ["Min"]},
                   remove={"operators": {"POWER": []}, "functions": ["Round"], "features": ["repeat"]})
    statement = resolve_statement("@x/child", {"@x/parent": PARENT, "@x/child": child})
    assert set(statement.operators) == {"AND", "OR"}
    assert statement.functions == {"Abs", "Min"}
    assert statement.features == set()
    assert statement.chain == ["@x/child@1.0.0", "@x/parent@1.2.0"]


def test_missing_parent_fails():
    with pytest.raises(TriccCapabilityError) as exc:
        resolve_statement("@x/child", {"@x/child": _child()})
    assert exc.value.code == "E_CAPABILITY_EXTENDS"


def test_parent_out_of_range_fails():
    with pytest.raises(TriccCapabilityError) as exc:
        resolve_statement("@x/child", {"@x/parent": PARENT, "@x/child": _child(version="^2.0.0")})
    assert exc.value.code == "E_CAPABILITY_EXTENDS"


@pytest.mark.parametrize(
    "version, version_range, ok",
    [("1.4.0", "^1.0.0", True), ("2.0.0", "^1.0.0", False), ("1.4.0", "~1.4.0", True), ("1.5.0", "~1.4.0", False),
     ("1.0.0", ">=1.0.0 <2.0.0", True), ("0.2.1", "^0.2.0", True), ("0.3.0", "^0.2.0", False), ("1.2.3", "1.x", True),
     ("3.0.0", "^1.0.0 || ^3.0.0", True), ("1.0.0", "1.0.0", True)],
)
def test_satisfies(version, version_range, ok):
    assert satisfies(version, version_range) is ok
