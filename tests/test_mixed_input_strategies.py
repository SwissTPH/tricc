"""tricc.yaml ``activity: {Strategy: [globs]}`` — one intervention, drawio and yaml inputs."""

from __future__ import annotations

import logging
import os

import pandas as pd
import pytest

from tricc_oo.models.project_config import TriccInterventionConfig, TriccProjectConfig
from tricc_oo.runner import (
    build_grouped_jobs,
    build_jobs,
    load_input_project,
    read_input_file_contents,
    run_project_build,
)

DEMO = os.path.join(os.path.dirname(__file__), "data", "demo.drawio")
DEMO_SUB_PAGE_ID = "4d3QH9IUq_qOAPruCqUX"  # a page of demo.drawio

SUB_PAGE_ID = "drawio_sub"


def _cell(cell_id, odk_type, name, label):
    return (
        f'<object label="{label}" odk_type="{odk_type}" name="{name}" id="{cell_id}">'
        f'<mxCell style="rounded=1;" vertex="1" parent="1">'
        f'<mxGeometry x="0" y="0" width="120" height="40" as="geometry"/></mxCell></object>'
    )


def _edge(edge_id, source, target):
    return (
        f'<mxCell id="{edge_id}" edge="1" source="{source}" target="{target}" parent="1">'
        f'<mxGeometry relative="1" as="geometry"/></mxCell>'
    )


# One drawio page = one sub-activity (activity_start -> note -> activity_end).
SUB_DRAWIO = (
    f'<mxfile><diagram id="{SUB_PAGE_ID}" name="Drawio sub"><mxGraphModel><root>'
    '<mxCell id="0"/><mxCell id="1" parent="0"/>'
    + _cell("s1", "activity_start", "sub_start", "Drawio sub")
    + _cell("n1", "note", "drawio_note", "Note from drawio")
    + _cell("e1", "activity_end", "sub_end", "Sub end")
    + _edge("ed1", "s1", "n1")
    + _edge("ed2", "n1", "e1")
    + "</root></mxGraphModel></diagram></mxfile>"
)

MAIN_YAML = f"""
id: mixed_main
title: Mixed main
process: main
nodes:
  - {{id: start, type: start, label: Mixed demo, name: start_mixed, form_id: mixed_demo}}
  - {{id: intro, type: note, name: intro_note, label: Intro from yaml}}
  - {{id: to_drawio, type: goto, name: to_drawio, label: Drawio sub-activity, link: {SUB_PAGE_ID}}}
  - {{id: end, type: end, name: end_mixed, label: End}}
edges:
  - {{source: start, target: intro}}
  - {{source: intro, target: to_drawio}}
  - {{source: to_drawio, target: end}}
"""


def _mixed_project(tmp_path):
    (tmp_path / "drawio").mkdir()
    (tmp_path / "yaml").mkdir()
    (tmp_path / "drawio" / "sub.drawio").write_text(SUB_DRAWIO, encoding="utf-8")
    (tmp_path / "yaml" / "main.yaml").write_text(MAIN_YAML, encoding="utf-8")
    (tmp_path / "tricc.yaml").write_text(
        "\n".join(
            [
                "title: Mixed",
                "output_strategies: [XLSFormStrategy]",
                "interventions:",
                "  - id: mixed",
                "    title: Mixed",
                "    activity:",
                "      YamlStrategy: [yaml/*]",
                "      DrawioStrategy: [drawio/*]",
            ]
        ),
        encoding="utf-8",
    )


def test_activity_list_form_is_one_group_with_default_strategy():
    item = TriccInterventionConfig(id="a", title="A", activity=["common/*", " child/* "])
    assert item.activity_groups("DrawioStrategy") == [("DrawioStrategy", ["common/*", "child/*"])]


def test_activity_mapping_form_keeps_authoring_order():
    item = TriccInterventionConfig(
        id="a",
        title="A",
        activity={"YamlStrategy": ["y/*.yaml"], "DrawioStrategy": ["d/*"]},
    )
    assert item.activity_groups("DrawioStrategy") == [
        ("YamlStrategy", ["y/*.yaml"]),
        ("DrawioStrategy", ["d/*"]),
    ]


@pytest.mark.parametrize("bad", [{}, {"DrawioStrategy": []}, {"  ": ["x/*"]}, {"YamlStrategy": ["  "]}])
def test_activity_mapping_rejects_empty_groups(bad):
    with pytest.raises(ValueError):
        TriccInterventionConfig(id="a", title="A", activity=bad)


def test_grouped_jobs_filter_each_glob_by_its_strategy_extensions(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "page.drawio").write_text("<mxfile/>", encoding="utf-8")
    (src / "act.yaml").write_text("id: x", encoding="utf-8")
    config = TriccProjectConfig.model_validate(
        {
            "interventions": [
                {
                    "id": "both",
                    "title": "Both",
                    "activity": {"DrawioStrategy": ["src/*"], "YamlStrategy": ["src/*"]},
                }
            ]
        }
    )
    (intervention, groups), = build_grouped_jobs(str(tmp_path), config, "DrawioStrategy")
    assert intervention.id == "both"
    assert [(name, [os.path.basename(f) for f in files]) for name, files in groups] == [
        ("DrawioStrategy", ["page.drawio"]),
        ("YamlStrategy", ["act.yaml"]),
    ]
    # Flat legacy view still lists every file once per group, in order.
    (_, files), = build_jobs(str(tmp_path), config, "DrawioStrategy")
    assert [os.path.basename(f) for f in files] == ["page.drawio", "act.yaml"]


def test_mixed_build_follows_yaml_goto_into_drawio_page(tmp_path):
    logging.disable(logging.WARNING)
    try:
        _mixed_project(tmp_path)
        out = tmp_path / "out"
        assert run_project_build(str(tmp_path), str(out)) == 0
    finally:
        logging.disable(logging.NOTSET)
    forms = [os.path.join(d, f) for d, _, fs in os.walk(out) for f in fs if f.endswith(".xlsx")]
    assert len(forms) == 1
    survey = pd.read_excel(forms[0], sheet_name="survey", dtype=str).fillna("")
    names = " ".join(survey["name"])
    assert "intro_note" in names  # from the yaml activity
    assert "drawio_note" in names  # from the drawio page reached through the yaml goto


def test_duplicate_id_across_formats_is_rejected(tmp_path):
    clash = MAIN_YAML.replace("id: mixed_main", f"id: {SUB_PAGE_ID}")
    with pytest.raises(ValueError, match="already loaded"):
        load_input_project(
            [
                ("DrawioStrategy", ["sub.drawio"], [SUB_DRAWIO]),
                ("YamlStrategy", ["main.yaml"], [clash]),
            ],
            str(tmp_path / "media-tmp"),
            TriccProjectConfig(),
            None,
        )


def test_single_group_reads_like_before(tmp_path):
    files = [DEMO]
    project = load_input_project(
        [("DrawioStrategy", files, read_input_file_contents(files))],
        str(tmp_path / "media-tmp"),
        TriccProjectConfig(),
        None,
    )
    assert DEMO_SUB_PAGE_ID in project.pages
