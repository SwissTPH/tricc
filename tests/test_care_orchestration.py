"""CHT follow-up task module and properties.json for intervention start."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tricc_oo.models.project_config import TriccInterventionConfig
from tricc_oo.strategies.output.xlsform_cht import XLSFormCHTStrategy


def test_cht_demand_properties_json(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    project = MagicMock()
    project.intervention = TriccInterventionConfig(
        id="pediatrics",
        title="Pediatrics",
        activity=["a/*"],
        start=[{"on": "demand", "condition": "AgeInMonths() < 60"}],
    )
    strategy = XLSFormCHTStrategy.__new__(XLSFormCHTStrategy)
    strategy.project = project
    strategy.output_path = str(out)
    strategy._write_demand_properties("pediatrics", "Pediatrics")
    payload = (out / "pediatrics.properties.json").read_text(encoding="utf-8")
    assert "ageInMonths(contact)" in payload
    assert "< 60" in payload


def test_cht_follow_up_js_and_parent_calculate(tmp_path):
    parent_out = tmp_path / "parent"
    child_out = tmp_path / "child"
    parent_out.mkdir()
    child_out.mkdir()
    parent_project = MagicMock()
    parent_project.intervention = TriccInterventionConfig(
        id="pediatrics", title="Pediatrics", activity=["a/*"]
    )
    child_cfg = TriccInterventionConfig(
        id="pediatrics_followup",
        title="Pediatrics follow-up",
        activity=["b/*"],
        start=[
            {
                "on": "follow_up",
                "intervention": "pediatrics",
                "condition": "classification = 'pneumonia'",
                "due": "3 d",
                "window": {"before": "0 d", "after": "4 d"},
            }
        ],
    )
    child_project = MagicMock()
    child_project.intervention = child_cfg
    parent = XLSFormCHTStrategy.__new__(XLSFormCHTStrategy)
    parent.project = parent_project
    parent.output_path = str(parent_out)
    parent._form_id = "pediatrics"
    parent._cht_title = "Pediatrics"
    parent.df_survey = pd.DataFrame(
        [{"type": "select_one cls", "name": "classification", "calculation": ""}]
    )
    parent.df_choice = pd.DataFrame()
    child = XLSFormCHTStrategy.__new__(XLSFormCHTStrategy)
    child.project = child_project
    child.output_path = str(child_out)
    child._form_id = "pediatrics_followup"
    child.df_survey = pd.DataFrame(
        [{"type": "select_one cls", "name": "classification", "calculation": ""}]
    )
    with patch.object(
        XLSFormCHTStrategy,
        "get_tricc_operation_expression",
        return_value="${classification} = 'pneumonia'",
    ):
        parent.link_follow_up(child, child_cfg.start[0])
    assert "start_pediatrics_followup" in set(parent.df_survey["name"])
    calc = parent.df_survey.loc[
        parent.df_survey["name"] == "start_pediatrics_followup", "calculation"
    ].iloc[0]
    assert "${classification} = 'pneumonia'" in str(calc)
    js = (child_out / "pediatrics_followup.js").read_text(encoding="utf-8")
    assert 'getField(report, "start_pediatrics_followup") === "true"' in js
    assert "days: 3" in js
    assert "start: 0" in js
    assert "end: 4" in js
    assert "classification" in js


def _cht_parent_child(tmp_path, start, parent_names=("classification",)):
    parent_out = tmp_path / "parent"
    child_out = tmp_path / "child"
    parent_out.mkdir()
    child_out.mkdir()
    parent_project = MagicMock()
    parent_project.intervention = TriccInterventionConfig(
        id="pediatrics", title="Pediatrics", activity=["a/*"]
    )
    child_cfg = TriccInterventionConfig(
        id="pediatrics_followup",
        title="Pediatrics follow-up",
        activity=["b/*"],
        start=[start],
    )
    child_project = MagicMock()
    child_project.intervention = child_cfg
    parent = XLSFormCHTStrategy.__new__(XLSFormCHTStrategy)
    parent.project = parent_project
    parent.output_path = str(parent_out)
    parent._form_id = "pediatrics"
    parent._cht_title = "Pediatrics"
    parent.df_survey = pd.DataFrame(
        [{"type": "text", "name": name, "calculation": ""} for name in parent_names]
    )
    parent.df_choice = pd.DataFrame()
    child = XLSFormCHTStrategy.__new__(XLSFormCHTStrategy)
    child.project = child_project
    child.output_path = str(child_out)
    child._form_id = "pediatrics_followup"
    child.df_survey = pd.DataFrame(
        [{"type": "text", "name": "classification", "calculation": ""}]
    )
    return parent, child, child_cfg, child_out


def test_cht_follow_up_unknown_parent_name_fails(tmp_path):
    parent, child, child_cfg, _ = _cht_parent_child(
        tmp_path,
        {
            "on": "follow_up",
            "intervention": "pediatrics",
            "condition": "classification = 'pneumonia'",
            "due": "3 d",
        },
        parent_names=("other",),
    )
    with patch.object(
        XLSFormCHTStrategy,
        "get_tricc_operation_expression",
        return_value="${classification} = 'pneumonia'",
    ):
        with pytest.raises(ValueError, match="not in parent form"):
            parent.link_follow_up(child, child_cfg.start[0])


def test_cht_follow_up_without_condition_always_applies(tmp_path):
    parent, child, child_cfg, child_out = _cht_parent_child(
        tmp_path,
        {
            "on": "follow_up",
            "intervention": "pediatrics",
            "due": "3 d",
        },
    )
    parent.link_follow_up(child, child_cfg.start[0])
    js = (child_out / "pediatrics_followup.js").read_text(encoding="utf-8")
    assert "return true" in js
    assert "start_pediatrics_followup" not in set(parent.df_survey["name"])
