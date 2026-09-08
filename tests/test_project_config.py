"""Tests for tricc.yaml loading, version pin, globs, and output dirs."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from tricc_oo.converters.project_config import (
    enforce_tricc_version,
    find_project_config_path,
    load_project_config_file,
    resolve_input_strategy,
    resolve_output_dir,
    resolve_output_strategies,
    resolve_segment_globs,
)
from tricc_oo.models.project_config import TriccProjectConfig


def test_missing_config_is_defaults(tmp_path):
    assert find_project_config_path(str(tmp_path)) is None
    # load_project_config_for_input needs a path that exists as dir
    from tricc_oo.converters.project_config import load_project_config_for_input

    config = load_project_config_for_input(str(tmp_path))
    assert config.title == "My project"
    assert config.interventions == []
    assert config.image_max_width() is None


def test_load_valid_config(tmp_path):
    path = tmp_path / "tricc.yaml"
    path.write_text(
        "\n".join(
            [
                "title: Almanach Global",
                "input_strategy: DrawioStrategy",
                "output_strategies:",
                "  - XLSFormStrategy",
                "  - XLSFormCHTStrategy",
                "parameters:",
                "  tricc_version: '1.7.3'",
                "  image_max_width: 1200",
                "  image_max_height: 0",
                "  extra_flag: keep-me",
                "interventions:",
                "  - id: pediatrics",
                "    title: Pediatrics",
                "    kind: both",
                "    applicability: AgeInMonths() >= 2",
                "    description: IMCI child",
                "    activity:",
                "      - common/*",
                "      - child/*",
            ]
        ),
        encoding="utf-8",
    )
    config = load_project_config_file(str(path))
    assert config.title == "Almanach Global"
    assert config.output_strategies == ["XLSFormStrategy", "XLSFormCHTStrategy"]
    assert config.image_max_width() == 1200
    assert config.image_max_height() is None
    assert config.parameters["extra_flag"] == "keep-me"
    assert config.interventions[0].id == "pediatrics"
    assert config.interventions[0].kind == "both"


def test_broken_yaml_fails(tmp_path):
    path = tmp_path / "tricc.yaml"
    path.write_text("title: [\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid project config|must be a YAML"):
        load_project_config_file(str(path))


def test_negative_image_cap_fails(tmp_path):
    path = tmp_path / "tricc.yaml"
    path.write_text("parameters:\n  image_max_width: -1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="image_max_width"):
        load_project_config_file(str(path))


def test_duplicate_intervention_id_fails():
    with pytest.raises(ValidationError):
        TriccProjectConfig.model_validate(
            {
                "interventions": [
                    {"id": "a", "title": "A", "activity": ["a/*"]},
                    {"id": "a", "title": "B", "activity": ["b/*"]},
                ]
            }
        )


def test_empty_segment_fails():
    with pytest.raises(ValidationError):
        TriccProjectConfig.model_validate(
            {"interventions": [{"id": "a", "title": "A", "activity": []}]}
        )


def test_legacy_segment_key_fails():
    with pytest.raises(ValidationError, match="renamed to `activity`"):
        TriccProjectConfig.model_validate(
            {"interventions": [{"id": "a", "title": "A", "segment": ["a/*"]}]}
        )


def test_version_gate_exact_match():
    config = TriccProjectConfig(parameters={"tricc_version": "1.7.3"})
    with patch(
        "tricc_oo.converters.project_config.get_installed_tricc_version",
        return_value="1.7.3",
    ):
        enforce_tricc_version(config)
    with patch(
        "tricc_oo.converters.project_config.get_installed_tricc_version",
        return_value="1.8.0",
    ):
        with pytest.raises(ValueError, match="tricc_version"):
            enforce_tricc_version(config)


def test_cli_overrides_yaml_strategies():
    config = TriccProjectConfig(
        input_strategy="YamlStrategy",
        output_strategies=["OpenSRPStrategy", "XLSFormStrategy"],
    )
    assert resolve_input_strategy(None, config) == "YamlStrategy"
    assert resolve_input_strategy("DrawioStrategy", config) == "DrawioStrategy"
    assert resolve_output_strategies(None, config) == ["OpenSRPStrategy", "XLSFormStrategy"]
    assert resolve_output_strategies("XLSFormCHTStrategy", config) == ["XLSFormCHTStrategy"]


def test_segment_glob_union_and_shared(tmp_path):
    (tmp_path / "common").mkdir()
    (tmp_path / "child").mkdir()
    (tmp_path / "common" / "nested").mkdir()
    (tmp_path / "common" / "shared.drawio").write_text("<mxfile/>", encoding="utf-8")
    (tmp_path / "child" / "pedia.drawio").write_text("<mxfile/>", encoding="utf-8")
    (tmp_path / "common" / "nested" / "hidden.drawio").write_text("<mxfile/>", encoding="utf-8")
    files = resolve_segment_globs(str(tmp_path), ["common/*", "child/*"])
    names = {os.path.basename(f) for f in files}
    assert names == {"shared.drawio", "pedia.drawio"}
    shared_again = resolve_segment_globs(str(tmp_path), ["common/*"])
    assert os.path.basename(shared_again[0]) == "shared.drawio"


def test_segment_drive_url_mixed_with_local(tmp_path):
    (tmp_path / "common").mkdir()
    (tmp_path / "common" / "shared.drawio").write_text("<mxfile/>", encoding="utf-8")
    remote = tmp_path / "from-drive.drawio"
    remote.write_text("<mxfile/>", encoding="utf-8")
    url = "https://drive.google.com/drive/folders/ABC123xyz"
    cache = tmp_path / "cache"
    with patch(
        "tricc_oo.converters.project_config.resolve_google_drive_source",
        return_value=[str(remote)],
    ) as mocked:
        files = resolve_segment_globs(
            str(tmp_path),
            ["common/*", url],
            dest_dir=str(cache),
        )
    mocked.assert_called_once_with(
        url,
        str(cache),
        valid_exts=(".drawio",),
        project_root=str(tmp_path),
    )
    names = {os.path.basename(f) for f in files}
    assert names == {"shared.drawio", "from-drive.drawio"}


def test_segment_drive_empty_fails(tmp_path):
    url = "https://drive.google.com/file/d/FILEID/view"
    with patch(
        "tricc_oo.converters.project_config.resolve_google_drive_source",
        return_value=[],
    ):
        with pytest.raises(ValueError, match="matched no input files"):
            resolve_segment_globs(str(tmp_path), [url], dest_dir=str(tmp_path / "cache"))


def test_segment_unsupported_https_fails(tmp_path):
    with pytest.raises(ValueError, match="not a supported Google Drive"):
        resolve_segment_globs(str(tmp_path), ["https://example.com/foo.drawio"])


def test_empty_glob_fails(tmp_path):
    (tmp_path / "child").mkdir()
    with pytest.raises(ValueError, match="matched no input files"):
        resolve_segment_globs(str(tmp_path), ["child/*"])


def test_output_dir_layout():
    assert resolve_output_dir(
        "/out",
        "XLSFormCHTStrategy",
        "pediatrics",
        has_interventions=True,
        n_strategies=2,
    ) == os.path.join("/out", "XLSFormCHTStrategy", "pediatrics")
    assert resolve_output_dir(
        "/out",
        "XLSFormCHTStrategy",
        None,
        has_interventions=False,
        n_strategies=1,
    ) == "/out"
    assert resolve_output_dir(
        "/out",
        "XLSFormStrategy",
        None,
        has_interventions=False,
        n_strategies=2,
    ) == os.path.join("/out", "XLSFormStrategy")


def test_find_config_next_to_file(tmp_path):
    (tmp_path / "tricc.yaml").write_text("title: From file\n", encoding="utf-8")
    drawio = tmp_path / "a.drawio"
    drawio.write_text("x", encoding="utf-8")
    found = find_project_config_path(str(drawio))
    assert found == str(tmp_path / "tricc.yaml")
