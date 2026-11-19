"""tricc.yaml ``terminology`` (project CodeSystems) and ``libraries`` (CQL defines -> calculates)."""

from __future__ import annotations

import glob
import json
import logging
import os

import pandas as pd
import pytest

from tricc_oo.converters.cql_library import (
    build_library_calculates,
    function_signature,
    native_function_type,
    parse_cql_library,
    parse_cql_library_functions,
)
from tricc_oo.models.project_config import TriccProjectConfig
from tricc_oo.models.tricc import TriccIntervention
from tricc_oo.runner import run_project_build
from tricc_oo.strategies.input.base_input_strategy import BaseInputStrategy

MAIN_YAML = """
id: lib_main
title: Library main
process: main
nodes:
  - {id: start, type: start, label: Lib demo, name: start_lib}
  - {id: age, type: integer, name: age, label: Age in years, required: true}
  - {id: old_note, type: note, name: old_note, label: Older child, relevance: is_older}
  - {id: end, type: end, name: end_lib, label: End}
edges:
  - {source: start, target: age}
  - {source: age, target: old_note}
  - {source: old_note, target: end}
"""

LIBRARY = """library common version '1.0.0'
using FHIR version '4.0.1'
context Patient

// shared logic
define is_older: age > 5
define private very_old:
  is_older and age > 10 /* nested reference */
"""

CODESYSTEM = {
    "resourceType": "CodeSystem",
    "id": "tricc",
    "name": "tricc",
    "url": "http://example.com/fhir/CodeSystem/tricc",
    "status": "draft",
    "content": "complete",
    "concept": [
        {
            "code": "age",
            "display": "Age (years)",
            "designation": [
                {
                    "language": "fr",
                    "use": {"system": "http://terminology.hl7.org/CodeSystem/designation-usage", "code": "display"},
                    "value": "Âge (années)",
                }
            ],
        }
    ],
}


def _project(tmp_path, output="XLSFormStrategy", libraries="[cql/*]", terminology="[terminology/*]"):
    (tmp_path / "yaml").mkdir()
    (tmp_path / "cql").mkdir()
    (tmp_path / "terminology").mkdir()
    (tmp_path / "yaml" / "main.yaml").write_text(MAIN_YAML, encoding="utf-8")
    (tmp_path / "cql" / "common.cql").write_text(LIBRARY, encoding="utf-8")
    (tmp_path / "terminology" / "tricc.codesystem.json").write_text(json.dumps(CODESYSTEM), encoding="utf-8")
    (tmp_path / "tricc.yaml").write_text(
        "\n".join(
            [
                "title: Lib demo",
                "input_strategy: YamlStrategy",
                f"output_strategies: [{output}]",
                f"terminology: {terminology}",
                f"libraries: {libraries}",
                "interventions:",
                "  - id: lib",
                "    name: lib_demo",
                "    title: Lib",
                "    activity: [yaml/*]",
            ]
        ),
        encoding="utf-8",
    )


def _build(tmp_path):
    logging.disable(logging.WARNING)
    try:
        return run_project_build(str(tmp_path), str(tmp_path / "out"))
    finally:
        logging.disable(logging.NOTSET)


# --- library parsing -------------------------------------------------------------


def test_parse_library_reads_defines_and_ignores_declarations_and_comments():
    assert parse_cql_library(LIBRARY) == [
        ("is_older", "age > 5"),
        ("very_old", "is_older and age > 10"),
    ]


def test_parse_library_accepts_quoted_identifiers():
    assert parse_cql_library('define "has_fever": temperature > 37.5') == [("has_fever", "temperature > 37.5")]


@pytest.mark.parametrize(
    "text, message",
    [
        ("define function Double(x Integer): x * 2", "functions with a body are not supported"),
        ('define "Has fever": temperature > 37.5', "plain identifier"),
        ("define a: 1\ndefine a: 2", "appears twice"),
        ("define a:\n", "not valid CQL at line 2"),
        ("define a: age >\n", "not valid CQL"),
    ],
)
def test_parse_library_rejects_unsupported_defines(text, message):
    with pytest.raises(ValueError, match=message):
        parse_cql_library(text, "bad.cql")


EXTERNALS = """
library Ext version '1.0'
/*
@description: Is the child born before 37 weeks
  of gestation
@retrieve: false
*/
define function IsPreterm(gestationWeeks Integer) returns FHIR.boolean: external

// a line comment is not a tag block
define function Score(a Decimal, b List<Decimal>) returns System.Integer : external

/* @retrieve: true */
define public function LastWeight() returns Decimal: external
/* @retrieve: true */
define is_older: age > 5
"""


def test_functions_are_signatures_not_calculates():
    functions = parse_cql_library_functions(EXTERNALS)
    assert list(functions) == ["IsPreterm", "Score", "LastWeight"]
    preterm = functions["IsPreterm"]
    assert preterm.return_type == "boolean"
    assert preterm.arguments == (("gestationWeeks", "Integer"),)
    assert preterm.tags == {"description": "Is the child born before 37 weeks of gestation", "retrieve": "false"}
    assert preterm.external and not preterm.retrieve
    assert functions["Score"].return_type == "integer"
    assert functions["Score"].arguments == (("a", "Decimal"), ("b", "List<Decimal>"))
    assert functions["Score"].tags == {}
    assert functions["Score"].retrieve  # no tag: assumed to read data
    assert functions["LastWeight"].retrieve
    assert parse_cql_library(EXTERNALS) == [("is_older", "age > 5")]


@pytest.mark.parametrize(
    "text, message",
    [
        ("define function F(x Integer): external", "must declare its type"),
        ("define function F(x Integer) returns List<Integer>: external", "returns 'List<Integer>'"),
        (
            "define function F() returns Boolean: external\ndefine function F() returns Boolean: external",
            "appears twice",
        ),
        ("define function F(x Integer) returns Integer: x * 2", "body are not supported yet"),
        ("/* @retrieve: maybe */\ndefine function F() returns Boolean: external", "must be true or false"),
        ("/* @retrieve: true\n@retrieve: false */\ndefine function F() returns Boolean: external", "twice"),
        ("define function F(x) returns Boolean: external", "not valid CQL"),
    ],
)
def test_function_errors(text, message):
    with pytest.raises(ValueError, match=message):
        parse_cql_library_functions(text, "bad.cql")


def test_libraries_fill_project_function_signatures():
    project = TriccIntervention()
    BaseInputStrategy.load_libraries(project, [("ext.cql", EXTERNALS)])
    assert project.function_signatures["LastWeight"].retrieve
    assert [c.name for c in project.library_calculates] == ["is_older"]
    # case-insensitive, project first, then TRICC's own zscore / izscore
    assert function_signature(project, "ispreterm").return_type == "boolean"
    assert native_function_type(project, "ispreterm") == "boolean"
    assert native_function_type(TriccIntervention(), "Zscore") == "decimal"
    assert native_function_type(TriccIntervention(), "Foo") is None


def test_same_function_in_two_libraries_is_rejected():
    project = TriccIntervention()
    ext = "define function F() returns Boolean: external"
    with pytest.raises(ValueError, match="already declared"):
        BaseInputStrategy.load_libraries(project, [("a.cql", ext), ("b.cql", ext)])


def test_library_defines_become_calculates():
    nodes = build_library_calculates(LIBRARY, "common.cql")
    assert [n.name for n in nodes] == ["is_older", "very_old"]
    assert all(n.expression is not None for n in nodes)


def test_same_define_in_two_libraries_is_rejected():
    project = TriccIntervention()
    with pytest.raises(ValueError, match="already defined"):
        BaseInputStrategy.load_libraries(project, [("a.cql", "define x: 1"), ("b.cql", "define x: 2")])


# --- terminology loading -----------------------------------------------------------


def test_terminology_is_keyed_by_codesystem_name():
    project = TriccIntervention()
    BaseInputStrategy.load_terminology(project, [("cs.json", json.dumps(CODESYSTEM))])
    assert list(project.code_systems) == ["tricc"]
    assert project.code_systems["tricc"].concept[0].code == "age"


@pytest.mark.parametrize(
    "sources, message",
    [
        ([("vs.json", json.dumps({"resourceType": "ValueSet", "status": "draft"}))], "FHIR CodeSystem"),
        ([("a.json", json.dumps(CODESYSTEM)), ("b.json", json.dumps(CODESYSTEM))], "defined twice"),
    ],
)
def test_terminology_rejects_bad_files(sources, message):
    with pytest.raises(ValueError, match=message):
        BaseInputStrategy.load_terminology(TriccIntervention(), sources)


def test_config_cleans_terminology_and_library_globs():
    config = TriccProjectConfig(terminology=[" terminology/* ", ""], libraries=["cql/*"])
    assert config.terminology == ["terminology/*"]
    assert config.libraries == ["cql/*"]


# --- end to end --------------------------------------------------------------------


def test_library_calculate_is_exported_once_and_used_by_relevance(tmp_path):
    _project(tmp_path)
    assert _build(tmp_path) == 0
    (form,) = glob.glob(str(tmp_path / "out" / "**" / "*.xlsx"), recursive=True)
    survey = pd.read_excel(form, sheet_name="survey", dtype=str).fillna("")
    calc = survey[survey["name"] == "is_older"]
    assert len(calc) == 1
    assert calc.iloc[0]["type"] == "calculate"
    assert "${age}" in calc.iloc[0]["calculation"]
    note = survey[survey["name"] == "old_note"].iloc[0]
    assert "${is_older}" in note["relevance"]
    nested = survey[survey["name"] == "very_old"].iloc[0]
    assert "${is_older}" in nested["calculation"]


def test_terminology_is_exported_with_its_designations(tmp_path):
    _project(tmp_path, output="FHIRStrategy")
    assert _build(tmp_path) == 0
    (path,) = glob.glob(str(tmp_path / "out" / "**" / "tricc_codesystem.json"), recursive=True)
    with open(path, encoding="utf-8") as f:
        exported = json.load(f)
    age = next(c for c in exported["concept"] if c["code"] == "age")
    assert age["display"] == "Age (years)"
    assert age["designation"][0]["value"] == "Âge (années)"


def test_library_glob_matching_nothing_fails_the_build(tmp_path):
    _project(tmp_path, libraries="[missing/*]")
    assert _build(tmp_path) == 1
    assert not os.path.exists(tmp_path / "out" / "lib")
