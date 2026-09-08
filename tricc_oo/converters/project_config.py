"""Load `tricc.yaml`, pin converter version, and resolve intervention file globs."""

from __future__ import annotations

import glob
import logging
import os
from typing import Iterable, List, Optional, Sequence, Tuple

import yaml

from tricc_oo.converters.google_drive import is_google_drive_source, resolve_google_drive_source
from tricc_oo.models.project_config import TriccProjectConfig, coerce_max_dimension

logger = logging.getLogger("default")

CONFIG_FILENAMES = ("tricc.yaml", "tricc.yml")
DEFAULT_INPUT_STRATEGY = "DrawioStrategy"
DEFAULT_OUTPUT_STRATEGY = "XLSFormCHTStrategy"
DRAWIO_EXTS = (".drawio",)
YAML_EXTS = (".yaml", ".yml")


def get_installed_tricc_version() -> str:
    """Return the installed ``tricc-oo`` package version."""
    try:
        from importlib.metadata import version
    except ImportError:  # pragma: no cover - Python 3.8
        from importlib_metadata import version
    return version("tricc-oo")


def enforce_tricc_version(config: TriccProjectConfig) -> None:
    """Fail the build when ``parameters.tricc_version`` does not match exactly."""
    expected = config.tricc_version()
    if not expected:
        return
    installed = get_installed_tricc_version()
    if installed != expected:
        raise ValueError(
            f"tricc.yaml requires tricc_version {expected!r} but this converter is {installed!r}"
        )


def find_project_root(in_filepath: str) -> Optional[str]:
    """Directory that should contain ``tricc.yaml`` (first local ``-i`` path)."""
    if not in_filepath:
        return None
    for current in in_filepath.split(","):
        current = current.strip()
        if not current:
            continue
        if current.startswith("https://"):
            continue
        if os.path.isdir(current):
            return os.path.abspath(current)
        if os.path.isfile(current):
            return os.path.abspath(os.path.dirname(current))
    return None


def find_project_config_path(in_filepath: str) -> Optional[str]:
    """Return the first ``tricc.yaml`` / ``tricc.yml`` next to ``-i``, or None."""
    root = find_project_root(in_filepath)
    if not root:
        return None
    found = None
    for name in CONFIG_FILENAMES:
        candidate = os.path.join(root, name)
        if os.path.isfile(candidate):
            found = candidate
            break
    _warn_if_later_configs_differ(in_filepath, found)
    return found


def _warn_if_later_configs_differ(in_filepath: str, chosen: Optional[str]) -> None:
    if not chosen:
        return
    chosen_abs = os.path.abspath(chosen)
    for current in in_filepath.split(",")[1:]:
        current = current.strip()
        if not current or current.startswith("https://"):
            continue
        other_root = None
        if os.path.isdir(current):
            other_root = os.path.abspath(current)
        elif os.path.isfile(current):
            other_root = os.path.abspath(os.path.dirname(current))
        if not other_root:
            continue
        for name in CONFIG_FILENAMES:
            other = os.path.join(other_root, name)
            if os.path.isfile(other) and os.path.abspath(other) != chosen_abs:
                logger.warning(
                    "Ignoring extra project config %s; using %s",
                    other,
                    chosen,
                )


def load_project_config_file(path: str) -> TriccProjectConfig:
    """Parse and validate a ``tricc.yaml`` file. Broken YAML is a hard error."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid project config {path}: {exc}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be a YAML mapping")
    try:
        config = TriccProjectConfig.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"Invalid project config {path}: {exc}") from exc
    # Surface typed parameter errors now (not later at first image).
    coerce_max_dimension(config.parameters.get("image_max_width"), "image_max_width")
    coerce_max_dimension(config.parameters.get("image_max_height"), "image_max_height")
    return config


def load_project_config_for_input(in_filepath: str) -> TriccProjectConfig:
    """Load config for ``-i``, or an empty default config when no file exists."""
    path = find_project_config_path(in_filepath)
    if not path:
        return TriccProjectConfig()
    logger.info("Loaded project config: %s", path)
    return load_project_config_file(path)


def resolve_input_strategy(cli_value: Optional[str], config: TriccProjectConfig) -> str:
    return (cli_value or "").strip() or config.input_strategy or DEFAULT_INPUT_STRATEGY


def resolve_output_strategies(cli_value: Optional[str], config: TriccProjectConfig) -> List[str]:
    if cli_value and cli_value.strip():
        return [cli_value.strip()]
    if config.output_strategies:
        return list(config.output_strategies)
    return [DEFAULT_OUTPUT_STRATEGY]


def resolve_segment_globs(
    project_root: str,
    patterns: Sequence[str],
    valid_exts: Iterable[str] = DRAWIO_EXTS,
    *,
    dest_dir: Optional[str] = None,
) -> List[str]:
    """Expand one-level globs and Google Drive URLs. ``*`` does not cross ``/``."""
    exts = tuple(e.lower() for e in valid_exts)
    matched: List[str] = []
    seen = set()
    drive_dest = dest_dir or os.path.join(project_root, ".tricc-drive-cache")
    for pattern in patterns:
        pattern = (pattern or "").strip().replace("\\", "/")
        if not pattern:
            continue
        if pattern.startswith("https://"):
            files = _resolve_segment_drive_url(pattern, drive_dest, exts, project_root)
        else:
            files = _resolve_local_segment_glob(project_root, pattern, exts)
        new_files = []
        for abs_hit in files:
            if abs_hit in seen:
                continue
            seen.add(abs_hit)
            new_files.append(abs_hit)
        if not new_files:
            raise ValueError(
                f"activity glob {pattern!r} under {project_root} matched no input files "
                f"(expected extensions {', '.join(exts)})"
            )
        matched.extend(sorted(new_files))
    if not matched:
        raise ValueError(f"no input files resolved under {project_root}")
    return matched


def _resolve_local_segment_glob(project_root: str, pattern: str, exts: Tuple[str, ...]) -> List[str]:
    full_pattern = os.path.join(project_root, *pattern.split("/"))
    hits = glob.glob(full_pattern)
    if not hits and os.path.isfile(full_pattern):
        hits = [full_pattern]
    files = []
    for hit in hits:
        if not os.path.isfile(hit):
            continue
        if not hit.lower().endswith(exts):
            continue
        files.append(os.path.abspath(hit))
    return files


def _resolve_segment_drive_url(
    url: str,
    dest_dir: str,
    exts: Tuple[str, ...],
    project_root: str,
) -> List[str]:
    if not is_google_drive_source(url):
        raise ValueError(f"activity URL is not a supported Google Drive file or folder: {url}")
    return resolve_google_drive_source(
        url,
        dest_dir,
        valid_exts=exts,
        project_root=project_root,
    )


def valid_exts_for_strategy(input_strategy: str) -> Tuple[str, ...]:
    name = (input_strategy or "").lower()
    if "yaml" in name:
        return YAML_EXTS
    return DRAWIO_EXTS


def resolve_output_dir(
    out_path: str,
    strategy_name: str,
    intervention_id: Optional[str],
    *,
    has_interventions: bool,
    n_strategies: int,
) -> str:
    """``-o`` layout: ``{out}/{strategy}/{intervention_id}/`` when interventions are listed."""
    if has_interventions:
        if not intervention_id:
            raise ValueError("intervention id required when tricc.yaml lists interventions")
        return os.path.join(out_path, strategy_name, intervention_id)
    if n_strategies > 1:
        return os.path.join(out_path, strategy_name)
    return out_path
