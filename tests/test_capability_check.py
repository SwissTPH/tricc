"""The project's capability statements and the load-time check (feature/20261125-output-capabilities.md §2-§4)."""

import logging
import os
import shutil

import pytest
import yaml

from tricc_oo.converters.capabilities import TriccCapabilityError, load_project_statements
from tricc_oo.converters.project_config import load_project_config_file
from tricc_oo.runner import run_project_build

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "projects", "capabilities")


def _project(tmp_path, active=(), outputs=("XLSFormCHTStrategy",), edit=None):
    """A copy of the fixture with only the ``active`` packages active."""
    folder = tmp_path / "project"
    shutil.copytree(FIXTURE, folder)
    path = folder / "tricc.yaml"
    data = yaml.safe_load(path.read_text())
    for entry in data["capabilities"]:
        entry["active"] = entry["package"] in active
    data["output_strategies"] = list(outputs)
    if edit:
        edit(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return str(folder)


def _build(folder, tmp_path, caplog, output=None):
    caplog.set_level(logging.WARNING, logger="default")
    return run_project_build(folder, str(tmp_path / "out"), cli_output_strategy=output)


def _codes(caplog, code):
    """Messages of one code, as logged per construct (the final summary is CRITICAL)."""
    return [
        r.getMessage() for r in caplog.records
        if r.getMessage().startswith(code) and r.levelno in (logging.ERROR, logging.WARNING)
    ]


def test_capabilities_read_and_written_back_unchanged():
    with open(os.path.join(FIXTURE, "tricc.yaml"), encoding="utf-8") as file:
        raw = yaml.safe_load(file)["capabilities"]
    config = load_project_config_file(os.path.join(FIXTURE, "tricc.yaml"))
    assert [e.model_dump(exclude_none=True) for e in config.capabilities] == raw


def test_only_active_statements_are_returned():
    config = load_project_config_file(os.path.join(FIXTURE, "tricc.yaml"))
    statements = load_project_statements(FIXTURE, config.capabilities)
    assert [s.id for s in statements] == ["@tricc/capabilities-xlsform-cht"]
    assert statements[0].chain[-1] == "@tricc/capabilities-xlsform@1.0.0"


def test_bad_sha256_fails(tmp_path):
    folder = _project(tmp_path, edit=lambda d: d["capabilities"][0].update(sha256="0" * 64))
    config = load_project_config_file(os.path.join(folder, "tricc.yaml"))
    with pytest.raises(TriccCapabilityError) as exc:
        load_project_statements(folder, config.capabilities)
    assert exc.value.code == "E_CAPABILITY_FILE"


def test_missing_parent_fails(tmp_path, caplog):
    def drop_fhir(data):
        data["capabilities"] = [e for e in data["capabilities"] if e["package"] != "@tricc/capabilities-fhir"]

    folder = _project(tmp_path, active={"@acme/capabilities-fhir-strict"}, edit=drop_fhir)
    assert _build(folder, tmp_path, caplog) == 1
    assert any("E_CAPABILITY_EXTENDS" in r.getMessage() for r in caplog.records)


def test_fhir_errors_and_limit_warning_per_active_statement(tmp_path, caplog):
    folder = _project(tmp_path, active={"@tricc/capabilities-fhir", "@acme/capabilities-fhir-strict"},
                      outputs=("FHIRStrategy",))
    assert _build(folder, tmp_path, caplog) == 1
    errors = _codes(caplog, "E_OUTPUT_UNSUPPORTED:")
    assert len(errors) == 2  # Max inline, once per active statement
    assert all("'heavy' (check) uses Max" in e and "cannot write inline" in e for e in errors)
    assert {e.rsplit("(", 1)[1] for e in errors} == {"@tricc/capabilities-fhir@1.0.0)",
                                                     "@acme/capabilities-fhir-strict@1.0.0)"}
    limits = _codes(caplog, "W_OUTPUT_LIMIT:")
    assert len(limits) == 1 and "'diazepam' (9 rows)" in limits[0] and "limit of 5 rows" in limits[0]


def test_unsupported_retrieval_context(tmp_path, caplog):
    folder = _project(tmp_path, active={"@tricc/capabilities-xlsform"}, outputs=("XLSFormStrategy",))
    assert _build(folder, tmp_path, caplog) == 1
    errors = _codes(caplog, "E_OUTPUT_UNSUPPORTED:")
    assert errors == [
        "E_OUTPUT_UNSUPPORTED: retrieval #age_months uses a retrieval from the patient context, which the "
        "XLSFormStrategy output (@tricc/capabilities-xlsform@1.0.0) cannot write"
    ]


def test_loaded_but_inactive_is_not_checked(tmp_path, caplog):
    folder = _project(tmp_path, active={"@tricc/capabilities-xlsform-cht"})
    assert _build(folder, tmp_path, caplog) == 0
    assert not _codes(caplog, "E_OUTPUT_UNSUPPORTED") and not _codes(caplog, "W_OUTPUT_LIMIT")


def test_no_active_statement_no_check(tmp_path, caplog):
    folder = _project(tmp_path, active=())
    assert _build(folder, tmp_path, caplog) == 0
    assert not _codes(caplog, "E_OUTPUT_UNSUPPORTED") and not _codes(caplog, "W_OUTPUT_NO_STATEMENT")


def test_output_without_statement_is_built_unchecked(tmp_path, caplog):
    folder = _project(tmp_path, active={"@tricc/capabilities-xlsform-cht"},
                      outputs=("XLSFormCHTStrategy", "XLSFormCHTHFStrategy"))
    assert _build(folder, tmp_path, caplog) == 0
    assert _codes(caplog, "W_OUTPUT_NO_STATEMENT:") == [
        "W_OUTPUT_NO_STATEMENT: XLSFormCHTHFStrategy has no active capability statement; it is built unchecked"
    ]


def test_active_statement_checked_even_when_not_built(tmp_path, caplog):
    folder = _project(tmp_path, active={"@tricc/capabilities-fhir"}, outputs=("XLSFormCHTStrategy",))
    assert _build(folder, tmp_path, caplog) == 1
    assert len(_codes(caplog, "E_OUTPUT_UNSUPPORTED:")) == 1
