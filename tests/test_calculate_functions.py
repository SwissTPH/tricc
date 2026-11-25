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
from tricc_oo.runner import load_input_project, read_input_file_contents

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
    assert [r.name for r in expr(d).get_references()] == ["q"]


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


def _inline(tmp_path, nodes, process="main", activity_id="inline"):
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
    return load(str(path), tmp_path=tmp_path)


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
