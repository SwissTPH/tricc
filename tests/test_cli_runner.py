"""CLI defaults: project folder outside the TRICC repo, driven by tricc.yaml."""

from __future__ import annotations

import os

from tricc_oo.cli import parse_args
from tricc_oo.runner import build_jobs, collect_local_files
from tricc_oo.models.project_config import TriccProjectConfig


def test_parse_args_defaults_input_to_none():
    args = parse_args(["-o", "out"])
    assert args.input is None
    assert args.output == "out"
    assert args.input_strategy is None
    assert args.output_strategy is None


def test_collect_local_and_jobs_from_yaml_globs(tmp_path):
    common = tmp_path / "common"
    child = tmp_path / "child"
    common.mkdir()
    child.mkdir()
    (common / "shared.drawio").write_text("<mxfile/>", encoding="utf-8")
    (child / "pedia.drawio").write_text("<mxfile/>", encoding="utf-8")
    (tmp_path / "tricc.yaml").write_text(
        "\n".join(
            [
                "title: Demo",
                "interventions:",
                "  - id: pediatrics",
                "    title: Pediatrics",
                "    activity:",
                "      - common/*",
                "      - child/*",
            ]
        ),
        encoding="utf-8",
    )
    config = TriccProjectConfig.model_validate(
        {
            "title": "Demo",
            "interventions": [
                {
                    "id": "pediatrics",
                    "title": "Pediatrics",
                    "activity": ["common/*", "child/*"],
                }
            ],
        }
    )
    jobs = build_jobs(str(tmp_path), config, "DrawioStrategy")
    assert len(jobs) == 1
    intervention, files = jobs[0]
    assert intervention.id == "pediatrics"
    names = {os.path.basename(f) for f in files}
    assert names == {"shared.drawio", "pedia.drawio"}
    assert collect_local_files(str(tmp_path), skip_listing=True) == []
