"""Calculate functions and call binding (feature/20261125-calculate-functions.md, RFC #101).

Phase 1: the shared call binding (``E_CALL_*``), the two stages of a decision table call
(checked at load, bound and expanded at instantiation), the fallback steps of a left-out
parameter, free-standing calculates and the data needs report.

Run with:
    python -m pytest tests/test_calculate_functions.py -v
"""

from __future__ import annotations

import glob
import json
import logging
import os

import pytest

from tricc_oo.converters.call_binding import (
    MISSING,
    NULL,
    CallError,
    bind_arguments,
    split_named,
)
from tricc_oo.converters.cql_to_operation import transform_cql_to_operation
from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference, TriccStatic
from tricc_oo.models.calculate import TriccNodeRetrieval
from tricc_oo.models.decision_table import read_table, encode_table
from tricc_oo.models.project_config import TriccProjectConfig
from tricc_oo.runner import load_input_project, read_input_file_contents, run_project_build

HERE = os.path.dirname(__file__)
PROJECT = os.path.join(HERE, "data", "projects", "calculate_functions")
YAML = os.path.join(HERE, "data", "yaml")


def _sources(folder, pattern):
    paths = sorted(glob.glob(os.path.join(PROJECT, folder, pattern)))
    return [(p, open(p, encoding="utf-8").read()) for p in paths]


def load(*fixtures, libraries=(), tmp_path=None, quiet=True):
    """Load YAML activities with the project's tables, terminology and libraries (no export)."""
    files = [os.path.join(YAML, f) if not os.path.isabs(f) else f for f in fixtures]
    config = TriccProjectConfig(retrieve_code_system="demo-retrieve")
    media = str(tmp_path / "media") if tmp_path is not None else os.path.join(YAML, "media-tmp")
    if quiet:
        logging.disable(logging.WARNING)
    try:
        return load_input_project(
            [("YamlStrategy", files, read_input_file_contents(files))],
            media,
            config,
            None,
            terminology=_sources("terminology", "*.json"),
            libraries=list(libraries),
            decision_tables=_sources("tables", "*.yaml"),
        )
    finally:
        logging.disable(logging.NOTSET)


def steps(project, calculate):
    """``[(parameter, step, source)]`` of the call held by ``calculate`` (data needs report)."""
    records = [r for r in project.data_needs if r["calculate"] == calculate]
    assert len(records) == 1, records
    return [(p["name"], p["step"], p["source"]) for p in records[0]["parameters"]]


def expr(calc):
    """The (instantiated) expression of a calculate."""
    return calc.expression_reference if calc.expression_reference is not None else calc.expression


def node(project, name):
    found = [n for page in project.pages.values() for n in page.nodes.values() if getattr(n, "name", None) == name]
    assert found, name
    return found


# ---------------------------------------------------------------- shared binding (§2.1)


def test_split_named_reads_the_trailing_tuple():
    op = transform_cql_to_operation("F(1, Tuple{ b: \"x\", c: null })")
    positional, named = split_named(op.reference[1:])
    assert positional == [TriccStatic(value=1)]
    assert named == [("b", TriccReference("x")), ("c", None)]


def test_bind_arguments_passed_null_and_missing():
    values = bind_arguments("F", ["a", "b", "c"], [TriccStatic(1)], [("E_CALL_ARG_UNKNOWN", "c", None)])
    assert values == [TriccStatic(1), MISSING, NULL]


def test_bind_arguments_matches_names_case_insensitively():
    assert bind_arguments("F", ["Age"], [], [("E_CALL_ARG_UNKNOWN", "age", TriccStatic(3))]) == [TriccStatic(3)]


@pytest.mark.parametrize(
    "positional, named, code",
    [
        ([1, 2, 3], [], "E_CALL_ARITY"),
        ([], [("E_CALL_ARG_UNKNOWN", "z", 1)], "E_CALL_ARG_UNKNOWN"),
        ([1], [("E_CALL_ARG_UNKNOWN", "a", 2)], "E_CALL_ARG_TWICE"),
    ],
)
def test_bind_arguments_errors(positional, named, code):
    with pytest.raises(CallError) as exc:
        bind_arguments("F", ["a", "b"], positional, named)
    assert exc.value.code == code


def test_table_input_retrievals_round_trip():
    path = os.path.join(PROJECT, "tables", "t_weight.yaml")
    text = open(path, encoding="utf-8").read()
    table = read_table(text, path)
    assert table.inputs[0].retrievals == ["#prev_weight"]
    assert read_table(encode_table(table), path).inputs[0].retrievals == ["#prev_weight"]
    assert "retrievals" not in encode_table(read_table(text.replace('    retrievals:\n      - "#prev_weight"\n', ""),
                                                       path))


# ---------------------------------------------------------------- fallback steps (§2.3)


@pytest.fixture(scope="module")
def binding(tmp_path_factory):
    return load("call_binding_steps.yaml", tmp_path=tmp_path_factory.mktemp("binding"))


def test_passed_argument(binding):
    assert steps(binding, "a_passed") == [("x", "passed", "w_measured")]


def test_left_out_takes_the_earlier_call(binding):
    assert steps(binding, "b_earlier") == [("x", "earlier_call", "w_measured")]


def test_null_is_no_value_even_with_an_earlier_call(binding):
    assert steps(binding, "c_null") == [("x", "null", None)]
    (c,) = node(binding, "c_null")
    assert not [r for r in expr(c).get_references() if getattr(r, "name", None) == "w_measured"]


def test_left_out_before_its_concept_takes_the_listed_retrieval(binding):
    assert steps(binding, "e_retrieval") == [("w", "retrieval", "#prev_weight")]
    (e,) = node(binding, "e_retrieval")
    refs = expr(e).get_references()
    assert any(isinstance(r, TriccNodeRetrieval) and r.name == "#prev_weight" for r in refs)


def test_a_retrieval_listed_only_on_a_parameter_is_built(binding):
    assert "#prev_weight" in binding.retrievals
    assert [n.name for n in binding.retrieval_nodes] == ["#prev_weight"]
    main = binding.start_pages["main"]
    assert any(n.name == "#prev_weight" for n in main.calculates)


def test_nothing_gives_no_value(binding):
    assert steps(binding, "f_none") == [("age", "none", None)]


def test_the_collected_concept_wins_over_an_earlier_call(binding):
    assert steps(binding, "g_passed") == [("w", "passed", "w_measured")]
    assert steps(binding, "h_form") == [("w", "form", "weight")]
    (h,) = node(binding, "h_form")
    assert [r.name for r in expr(h).get_references()] == ["weight"]


def test_calls_are_expanded_after_instantiation(binding):
    for name in ("a_passed", "b_earlier", "e_retrieval", "h_form"):
        (calc,) = node(binding, name)
        assert expr(calc).operator == TriccOperator.IFS, name


# ---------------------------------------------------------------- carry-over (§2.3 step 2, §2.6)


@pytest.fixture(scope="module")
def carry(tmp_path_factory):
    return load("call_carry_over.yaml", tmp_path=tmp_path_factory.mktemp("carry"))


def test_a_bare_concept_resolves_to_its_newer_version(carry):
    v1, v2 = sorted(node(carry, "v"), key=lambda n: n.path_len)
    (a,) = node(carry, "a_bare")
    (b,) = node(carry, "b_bare")
    assert steps(carry, "b_bare") == [("x", "earlier_call", "v")]

    def first_v(calc):
        refs = list(expr(calc).get_references())
        return [r for r in refs if getattr(r, "name", None) == "v"][0]

    assert first_v(a) is v1
    assert first_v(b) is v2


def test_an_expression_carries_over(carry):
    assert steps(carry, "c_expr") == [("age", "passed", "multiplied(q, 12)")]
    assert steps(carry, "d_expr") == [("age", "earlier_call", "multiplied(q, 12)")]
    (d,) = node(carry, "d_expr")
    # the carried expression is read by both rows of t_age: a sub-calculate of the call (§2.4)
    (sub,) = expr(d).get_references()
    assert sub.name == "d_expr_t_age_band_age"
    assert [r.name for r in sub.expression.get_references()] == ["q"]


def test_a_constant_carries_over(tmp_path):
    project = _inline(
        tmp_path,
        [
            "  - {id: a, type: calculate, name: a, label: A, calculate: \"DMN('t_free', 12)\"}",
            "  - {id: b, type: calculate, name: b, label: B, calculate: \"DMN('t_free')\"}",
        ],
    )
    assert steps(project, "b") == [("x", "earlier_call", "12")]
    (b,) = node(project, "b")
    assert expr(b) == TriccStatic(value="big")


def _inline(tmp_path, nodes, process="main", activity_id="inline", libraries=()):
    """A flow ``start -> nodes… -> end`` written to ``tmp_path``."""
    ids = [line.split("id: ")[1].split(",")[0] for line in nodes]
    chain = ["start", *ids, "end"]
    text = "\n".join(
        [
            f"id: {activity_id}",
            f"title: {activity_id}",
            f"process: {process}",
            "nodes:",
            f"  - {{id: start, type: start, name: start_{activity_id}, label: Start}}",
            *nodes,
            f"  - {{id: end, type: end, name: end_{activity_id}, label: End}}",
            "edges:",
            *[f"  - {{id: e{i}, source: {s}, target: {t}}}" for i, (s, t) in enumerate(zip(chain, chain[1:]))],
            "",
        ]
    )
    path = tmp_path / f"{activity_id}.yaml"
    path.write_text(text, encoding="utf-8")
    return load(str(path), libraries=libraries, tmp_path=tmp_path)


# ---------------------------------------------------------------- the walk (§2.2)


def test_only_passed_arguments_block(binding):
    # e_retrieval reads t_weight's input concept (weight), collected after it in the flow: the
    # call did not wait for it (it is instantiated before weight, from the retrieval)
    (e,) = node(binding, "e_retrieval")
    (weight,) = node(binding, "weight")
    assert e.path_len < weight.path_len


def test_a_left_out_input_no_longer_blocks_a_free_calculate(tmp_path):
    project = _inline(
        tmp_path,
        [
            "  - {id: f, type: calculate, name: f, label: F, calculate: \"DMN('t_age')\"}",
            "  - {id: n, type: note, name: n, label: \"Band ${f}\"}",
        ],
    )
    assert steps(project, "f") == [("age", "none", None)]


# ---------------------------------------------------------------- free-standing (§2.5)


@pytest.fixture(scope="module")
def free(tmp_path_factory):
    return load("call_free_standing.yaml", tmp_path=tmp_path_factory.mktemp("free"))


def test_free_standing_is_bound_at_its_first_reader(free):
    # read by the note, after weight was collected: weight is the form value
    assert steps(free, "fs_read") == [("w", "form", "weight")]


def test_free_standing_unread_and_saved_is_bound_at_the_end(free):
    assert steps(free, "fs_saved") == [("age", "none", None)]
    (saved,) = node(free, "fs_saved")
    assert expr(saved) == TriccStatic(value="")  # bound and expanded: null matches no row


def test_free_standing_unread_and_not_saved_is_dropped(free):
    assert not [r for r in free.data_needs if r["calculate"] == "fs_dropped"]
    assert not [n for page in free.pages.values() for n in page.nodes.values() if n.name == "fs_dropped"]


# ---------------------------------------------------------------- data needs report (§4)


def test_data_needs_report_is_written(tmp_path):
    from tricc_oo.visitors.calls import write_data_needs

    project = load("call_binding_steps.yaml", tmp_path=tmp_path)
    path = write_data_needs(project, str(tmp_path / "out"), "binding")
    with open(path, encoding="utf-8") as file:
        report = json.load(file)
    assert report["form"] == "binding"
    by_calc = {r["calculate"]: r for r in report["calls"]}
    assert by_calc["e_retrieval"]["target"] == "t_weight.class"
    assert by_calc["e_retrieval"]["kind"] == "decision_table"
    assert by_calc["e_retrieval"]["activity"]
    assert {p["step"] for r in report["calls"] for p in r["parameters"]} == {
        "passed", "earlier_call", "null", "retrieval", "none", "form"
    }


def test_no_report_without_calls(tmp_path):
    from tricc_oo.visitors.calls import write_data_needs

    project = load("basic_flow_with_calc.yaml", tmp_path=tmp_path)
    assert write_data_needs(project, str(tmp_path / "out")) is None


def test_the_tuple_of_an_unknown_function_is_left_to_it():
    # a Tuple is read by a function call's own binding; elsewhere it is an error
    op = transform_cql_to_operation("Foo(Tuple{ a: 1 })")
    assert isinstance(op, TriccOperation) and op.operator == TriccOperator.NATIVE


# ================================================================ phase 2: functions

from tricc_oo.converters.cql_library import (  # noqa: E402
    FunctionError,
    link_functions,
    parse_cql_library_functions,
)
from tricc_oo.converters.call_binding import TriccParameterReference  # noqa: E402

LIBRARY = os.path.join(PROJECT, "libraries", "functions.cql")
ACTIVITIES = [os.path.join(PROJECT, "activities", f"{a}.activity.yaml") for a in ("visit", "triage", "registration")]


def load_project(tmp_path):
    """The calculate_functions project (one visit: triage then registration)."""
    return load(*ACTIVITIES, libraries=_sources("libraries", "*.cql"), tmp_path=tmp_path)


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    return load_project(tmp_path_factory.mktemp("functions"))


TEMPLATES = ("triage", "registration")


def used(project, name, activity=None):
    """The nodes called ``name`` in the walked pages (not the activity templates)."""
    return [
        n for page_id, page in project.pages.items() if page_id not in TEMPLATES
        for n in page.nodes.values()
        if getattr(n, "name", None) == name and (activity is None or n.activity.name == activity)
    ]


def calls_of(project, calculate, activity=None):
    return [
        [(p["name"], p["step"], p["source"]) for p in r["parameters"]]
        for r in project.data_needs
        if r["calculate"] == calculate and (activity is None or r["activity"] == activity)
    ]


# ---------------------------------------------------------------- definitions and link (§1)


def test_library_function_with_a_body_and_param_tags():
    (signature,) = parse_cql_library_functions(open(LIBRARY, encoding="utf-8").read(), "functions.cql").values()
    assert signature.name == "IsAdult" and not signature.external and not signature.retrieve
    assert signature.body.operator == TriccOperator.COALESCE
    assert isinstance(signature.body.reference[0], TriccParameterReference)
    age = signature.params[0]
    assert (age.name, age.fallback, age.retrievals) == ("age", "age_years", ("#age_years",))
    assert signature.params[1].fallback is None


@pytest.mark.parametrize(
    "tag",
    [
        "@param.height: fallback=x",  # no such parameter
        "@param.age: default=x",  # no such key
        "@param.age: x",  # no key
    ],
)
def test_param_tag_errors(tag):
    text = f"/*\n{tag}\n*/\ndefine function F(age Integer) returns Integer: age"
    with pytest.raises(FunctionError) as exc:
        parse_cql_library_functions(text, "bad.cql")
    assert exc.value.code == "E_PARAM_TAG_UNKNOWN"


def test_param_tag_names_match_case_insensitively():
    text = "/*\n@param.AGE: fallback=x retrievals=#a #b\n*/\ndefine function F(age Integer) returns Integer: age"
    (signature,) = parse_cql_library_functions(text, "f.cql").values()
    assert signature.params[0].retrievals == ("#a", "#b")


def test_dictionary_parameters_and_library_body_are_one_function(project):
    is_adult = project.function_signatures["IsAdult"]
    assert is_adult.sources == ("dictionary", "library")
    assert is_adult.body is not None
    assert [(p.name, p.type, p.fallback) for p in is_adult.params] == [
        ("age", "Integer", "age_years"),
        ("declared", "Boolean", None),
    ]
    bmi = project.function_signatures["BMI"]
    assert bmi.sources == ("dictionary",) and bmi.body_text == "weight / (height * height)"
    assert bmi.params[0].fallback == "weight" and bmi.params[0].retrievals == ("#last_weight",)


def _sig(text):
    return parse_cql_library_functions(text, "lib.cql")


def test_two_bodies_fail():
    library = _sig("define function F(a Integer) returns Integer: a")
    dictionary = _sig("define function F(a Integer) returns Integer: a + 1")
    with pytest.raises(FunctionError) as exc:
        link_functions(library, dictionary)
    assert exc.value.code == "E_FUNCTION_TWICE"


@pytest.mark.parametrize(
    "dictionary",
    [
        "define function F(b Integer) returns Integer: external",  # name
        "define function F(a String) returns Integer: external",  # type
        "define function F(a Integer, b Integer) returns Integer: external",  # count
        "/* @param.a: fallback=y */ define function F(a Integer) returns Integer: external",  # metadata
    ],
)
def test_mismatched_parameters_fail(dictionary):
    library = _sig("/* @param.a: fallback=x */\ndefine function F(a Integer) returns Integer: a")
    with pytest.raises(FunctionError) as exc:
        link_functions(library, _sig(dictionary))
    assert exc.value.code == "E_FUNCTION_SIGNATURE_MISMATCH"


def test_function_name_shared_with_a_calculate_warns(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="default"):
        load(*ACTIVITIES, libraries=_sources("libraries", "*.cql"), tmp_path=tmp_path, quiet=False)
    assert "W_FUNCTION_NAME_SHARED: function 'BMI'" in caplog.text


def test_unknown_function_with_named_arguments_fails(tmp_path):
    with pytest.raises(FunctionError) as exc:
        _inline(tmp_path, ["  - {id: f, type: calculate, name: f, label: F, calculate: \"Foo(Tuple{ a: 1 })\"}"])
    assert exc.value.code == "E_FUNCTION_UNKNOWN"


def test_function_call_arity_fails(tmp_path):
    with pytest.raises(FunctionError) as exc:
        _inline(
            tmp_path,
            ["  - {id: f, type: calculate, name: f, label: F, calculate: \"IsAdult(1, true, 3)\"}"],
            libraries=_sources("libraries", "*.cql"),
        )
    assert exc.value.code == "E_CALL_ARITY"


@pytest.mark.parametrize(
    "tag, code",
    [("fallback=nowhere", "E_PARAM_FALLBACK_UNKNOWN"), ("retrievals=#nope", "E_PARAM_RETRIEVAL_UNKNOWN")],
)
def test_unknown_fallback_or_retrieval_fails(tmp_path, tag, code):
    library = [("bad.cql", f"/* @param.a: {tag} */\ndefine function G(a Integer) returns Integer: a + 1")]
    with pytest.raises(FunctionError) as exc:
        _inline(tmp_path, ["  - {id: f, type: calculate, name: f, label: F, calculate: \"G()\"}"],
                libraries=library)
    assert exc.value.code == code


# ---------------------------------------------------------------- binding functions (§2)


def test_the_is_adult_case_builds_without_a_stashed_loop(project):
    # the #54 regression: two versions of is_adult in two activities; registration leaves age out
    # and takes the triage call's argument
    assert calls_of(project, "is_adult", "triage") == [[("age", "passed", "age_estimated"), ("declared", "none", None)]]
    assert calls_of(project, "is_adult", "registration") == [
        [("age", "earlier_call", "age_estimated"), ("declared", "passed", "equal(declared_adult, yes)")]
    ]


def test_left_out_function_parameter_takes_its_listed_retrieval(project):
    assert calls_of(project, "bmi_record") == [[("weight", "retrieval", "#last_weight"), ("height", "passed", "1.7")]]
    assert "#last_weight" in project.retrievals


def test_the_carry_over_is_shared_by_the_walks(project):
    # one CallState per project (§2.6): what the walks of every start page read and update
    assert project.call_state is not None
    assert str(project.call_state.arguments["F:IsAdult"]["age"]) == "age_estimated"


def test_a_pure_function_of_constants_folds(project):
    (calc,) = used(project, "adult_const")
    assert expr(calc) == TriccStatic(True)


def test_an_impure_function_of_constants_does_not_fold(project):
    (calc,) = used(project, "bmi_reference")
    assert isinstance(expr(calc), TriccOperation)


# ---------------------------------------------------------------- sub-calculates (§2.4)


def test_an_argument_used_twice_is_a_sub_calculate(project):
    (bmi,) = used(project, "bmi")
    (sub,) = used(project, "bmi_bmi_height")
    assert sub in expr(bmi).get_references()
    (height,) = used(project, "height_cm")
    assert [r for r in sub.expression.get_references()] == [height]  # instantiated with the call
    assert sub.path_len == bmi.path_len


def test_an_argument_used_once_is_injected(project):
    (adult,) = used(project, "is_adult", "registration")
    assert not [n for n in node_names(project) if n.startswith("is_adult_isadult")]
    assert "declared_adult" in {getattr(r, "name", None) for r in expr(adult).get_references()}


def node_names(project):
    return [getattr(n, "name", "") or "" for page in project.pages.values() for n in page.nodes.values()]


# ---------------------------------------------------------------- version inheritance (§3)


def test_no_inherited_value_between_versions_calling_the_same_function(project):
    (adult,) = used(project, "is_adult", "registration")
    (triage,) = used(project, "is_adult", "triage")

    def operators(e, found):
        if isinstance(e, TriccOperation):
            found.add(e.operator)
            for r in e.reference:
                operators(r, found)
        elif isinstance(e, list):
            for r in e:
                operators(r, found)
        return found

    assert TriccOperator.GET_INHERITED_VALUE not in operators(expr(adult), set())
    assert triage not in expr(adult).get_references()


def test_other_versions_still_inherit():
    from tricc_oo.models.calculate import TriccNodeCalculate
    from tricc_oo.visitors.calls import CallState

    class Project:
        function_signatures = parse_cql_library_functions(open(LIBRARY, encoding="utf-8").read(), "f.cql")
        decision_tables = {}
        aliases = {}

    state = CallState(Project())
    calc = lambda i, e: TriccNodeCalculate(id=i, name="is_adult", expression=transform_cql_to_operation(e))  # noqa
    same = calc("a", 'IsAdult("age")')
    other = calc("b", '"declared" = true')
    current = calc("c", "IsAdult(Tuple{ declared: true })")
    assert state.drop_same_call_versions(current, [same, other]) == [other]
    assert state.drop_same_call_versions(other, [same]) == [same]


# ---------------------------------------------------------------- export (§3, §4)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("built")
    logging.disable(logging.WARNING)
    try:
        for strategy in ("XLSFormStrategy", "XLSFormCHTStrategy", "FHIRStrategy"):
            assert run_project_build(PROJECT, str(out / strategy), cli_output_strategy=strategy) == 0
    finally:
        logging.disable(logging.NOTSET)
    return out


def _calculations(out, strategy):
    import pandas as pd

    (form,) = glob.glob(str(out / strategy / "**" / "functions.xlsx"), recursive=True)
    survey = pd.read_excel(form, sheet_name="survey", dtype=str).fillna("")
    return dict(zip(survey["name"], survey["calculation"]))


@pytest.mark.parametrize("strategy", ["XLSFormStrategy", "XLSFormCHTStrategy"])
def test_xlsform_writes_the_body_inline(built, strategy):
    calc = _calculations(built, strategy)
    assert calc["is_adult_Vv_1"] == "number(coalesce(${age_estimated},-2147483648)>=18)"
    assert calc["is_adult"] == (
        "number(coalesce(coalesce(${declared_adult},'')='yes', coalesce(${age_estimated},-2147483648)>=18))"
    )
    assert calc["bmi_bmi_height"] == "number(coalesce(${height_cm},'') div 100)"
    assert calc["bmi"] == "number(coalesce(${weight},'') div (${bmi_bmi_height}*${bmi_bmi_height}))"
    assert calc["bmi_record"] == "number(${r_last_weight} div (1.7*1.7))"
    assert calc["adult_const"] == "1"


def _questionnaire_expressions(out):
    (path,) = glob.glob(str(out / "FHIRStrategy" / "**" / "questionnaire" / "*.json"), recursive=True)
    with open(path, encoding="utf-8") as file:
        questionnaire = json.load(file)
    found = {}

    def walk(items):
        for item in items:
            for ext in item.get("extension", []):
                if "valueExpression" in ext:
                    found[item["linkId"]] = ext["valueExpression"]
            walk(item.get("item", []))

    walk(questionnaire["item"])
    return found


def test_fhir_inline_when_an_argument_is_an_item(built):
    found = _questionnaire_expressions(built)
    assert found["bmi"]["language"] == "text/fhirpath"
    assert "linkId='bmi_bmi_height'" in found["bmi"]["expression"]
    assert "Helper" not in found["bmi"]["expression"]


def test_fhir_calls_a_helper_function_otherwise(built):
    found = _questionnaire_expressions(built)
    assert found["bmi_reference"] == {"language": "text/cql-identifier", "expression": "Calc_bmi_reference"}
    (main,) = glob.glob(str(built / "FHIRStrategy" / "**" / "functions-main.cql"), recursive=True)
    (helper,) = glob.glob(str(built / "FHIRStrategy" / "**" / "functions-Helper.cql"), recursive=True)
    assert 'define Calc_bmi_reference: Helper."BMI"(70, 1.75)' in open(main, encoding="utf-8").read()
    helper_cql = open(helper, encoding="utf-8").read()
    assert 'define function "BMI"(weight Decimal, height Decimal) returns Decimal:\n  weight / (height * height)' in (
        helper_cql
    )
    assert helper_cql.count('define function "BMI"') == 1
    assert 'define function "IsAdult"' not in helper_cql  # only called inline


def test_a_body_the_output_cannot_write_fails():
    from tricc_oo.visitors.calls import inline_function_call

    call = TriccOperation(TriccOperator.FUNCTION_CALL, [TriccOperation(TriccOperator.NOW, []), TriccStatic("F")])

    def serialise(_):
        raise NotImplementedError("now")

    with pytest.raises(FunctionError) as exc:
        inline_function_call(call, serialise, "SomeStrategy")
    assert exc.value.code == "E_FUNCTION_NOT_EXPORTABLE"
    assert "'F'" in exc.value.message and "SomeStrategy" in exc.value.message


def test_every_build_writes_the_data_needs_report(built):
    for strategy in ("XLSFormStrategy", "XLSFormCHTStrategy", "FHIRStrategy"):
        (path,) = glob.glob(str(built / strategy / "**" / "functions.data-needs.json"), recursive=True)
        with open(path, encoding="utf-8") as file:
            report = json.load(file)
        by_calc = {(r["calculate"], r["activity"]): r for r in report["calls"]}
        record = by_calc[("is_adult", "registration")]
        assert record["kind"] == "function" and record["target"] == "IsAdult"
        assert record["sources"] == ["dictionary", "library"]
        assert record["parameters"][0] == {"name": "age", "step": "earlier_call", "source": "age_estimated"}
