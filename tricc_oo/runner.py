"""Run a TRICC conversion from a local project folder (``tricc.yaml`` + drawings).

Clinical projects live *outside* this repo. After ``pip install tricc-oo`` (or an
editable install), run::

    cd /path/to/almanach
    tricc -o ./build

``-i`` defaults to the current directory, which must contain ``tricc.yaml``
(optional) and the drawings. Google Drive file/folder URLs may appear in
``activity:`` next to local globs. ``tests/build.py`` remains the debug harness.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Sequence, Tuple

import tricc_oo.strategies  # noqa: F401  — register built-in strategies
from tricc_oo.converters.project_config import (
    enforce_tricc_version,
    find_project_root,
    load_project_config_for_input,
    resolve_input_strategy,
    resolve_output_dir,
    resolve_output_strategies,
    resolve_segment_globs,
    valid_exts_for_strategy,
)
from tricc_oo.models.project_config import TriccInterventionConfig, TriccProjectConfig
from tricc_oo.strategies.registry import (
    get_input_strategy,
    get_output_strategy,
    get_test_strategy,
)

logger = logging.getLogger("default")

LOCAL_EXTS = (".drawio", ".yaml", ".yml")
Job = Tuple[Optional[TriccInterventionConfig], List[str]]


def list_local_folder_files(folder_path: str, valid_exts: Sequence[str] = (".drawio",)) -> List[str]:
    folder_path = os.path.abspath(folder_path)
    if not folder_path or not os.path.isdir(folder_path):
        return []
    files = [
        os.path.join(folder_path, name)
        for name in os.listdir(folder_path)
        if name.lower().endswith(tuple(valid_exts))
    ]
    return sorted(files)


def add_unique_files(files: List[str], new_paths: Sequence[str]) -> None:
    seen = {os.path.abspath(f) for f in files}
    for path in new_paths:
        abs_path = os.path.abspath(path)
        if abs_path not in seen:
            files.append(path)
            seen.add(abs_path)


def collect_local_files(in_filepath: str, skip_listing: bool = False) -> List[str]:
    """Collect top-level local files from comma-separated ``-i`` paths."""
    files: List[str] = []
    if skip_listing:
        return files
    for current in in_filepath.split(","):
        current = current.strip()
        if not current or current.startswith("https://"):
            continue
        if os.path.isdir(current):
            found = list_local_folder_files(current, valid_exts=LOCAL_EXTS)
            if not found:
                logger.warning("No matching files found in folder: %s", current)
            else:
                logger.info("Found %s file(s) in folder.", len(found))
                add_unique_files(files, found)
        elif os.path.isfile(current) and current.lower().endswith(LOCAL_EXTS):
            add_unique_files(files, [current])
        elif os.path.exists(current):
            logger.warning("Skipping invalid input (unknown extension): %s", current)
    return files


def read_input_file_contents(files: Sequence[str]) -> List[str]:
    file_content: List[str] = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                file_content.append(handle.read())
                logger.info("Loaded file: %s", path)
        except Exception as exc:
            logger.error("Error reading file %s: %s", path, exc)
    return file_content


def build_jobs(
    in_filepath: str,
    project_config: TriccProjectConfig,
    input_strategy: str,
    precollected_files: Optional[List[str]] = None,
    dest_dir: Optional[str] = None,
) -> List[Job]:
    """One job per intervention (globbed files), or a single job of collected files."""
    if project_config.interventions:
        project_root = find_project_root(in_filepath)
        if not project_root:
            raise ValueError(
                "tricc.yaml interventions require a local -i directory (or file) as the project root"
            )
        jobs: List[Job] = []
        for intervention in project_config.interventions:
            job_files = resolve_segment_globs(
                project_root,
                intervention.activity,
                valid_exts_for_strategy(input_strategy),
                dest_dir=dest_dir,
            )
            logger.info("Intervention %s: %s file(s)", intervention.id, len(job_files))
            jobs.append((intervention, job_files))
        return jobs
    files = precollected_files if precollected_files is not None else collect_local_files(in_filepath)
    return [(None, files)]


def run_one_export(
    files: Sequence[str],
    file_content: Sequence[str],
    out_dir: str,
    input_strategy_name: str,
    output_strategy_name: str,
    project_config: TriccProjectConfig,
    intervention: Optional[TriccInterventionConfig],
    test_strategy_name: Optional[str] = None,
) -> None:
    os.makedirs(out_dir, exist_ok=True)
    media_path = os.path.join(out_dir, "media-tmp")
    InputStrategyCls = get_input_strategy(input_strategy_name)
    input_strategy = InputStrategyCls(list(files))
    logger.info("build the graph from strategy %s", InputStrategyCls.__name__)
    project = input_strategy.execute(
        list(file_content),
        media_path,
        project_config=project_config,
        intervention=intervention,
    )
    OutputStrategyCls = get_output_strategy(output_strategy_name)
    output_strategy = OutputStrategyCls(project, out_dir)
    logger.info("Using strategy %s", OutputStrategyCls.__name__)
    output_strategy.execute()
    if test_strategy_name:
        TestStrategyCls = get_test_strategy(test_strategy_name)
        logger.info("Running test strategy %s", TestStrategyCls.__name__)
        try:
            TestStrategyCls(project, out_dir, output_strategy).execute()
        except Exception as exc:
            logger.error("Test strategy %s failed: %s", TestStrategyCls.__name__, exc)


def run_project_build(
    in_filepath: str,
    out_path: str,
    *,
    cli_input_strategy: Optional[str] = None,
    cli_output_strategy: Optional[str] = None,
    test_strategy_name: Optional[str] = None,
    precollected_files: Optional[List[str]] = None,
) -> int:
    """Load ``tricc.yaml`` from ``in_filepath`` and convert. Returns a process exit code."""
    try:
        project_config = load_project_config_for_input(in_filepath)
        enforce_tricc_version(project_config)
    except Exception as exc:
        logger.critical("%s", exc)
        return 1
    input_strategy = resolve_input_strategy(cli_input_strategy, project_config)
    output_strategies = resolve_output_strategies(cli_output_strategy, project_config)
    try:
        jobs = build_jobs(
            in_filepath,
            project_config,
            input_strategy,
            precollected_files=precollected_files,
            dest_dir=os.path.join(out_path, ".tricc-drive-cache"),
        )
    except ValueError as exc:
        logger.critical("%s", exc)
        return 1

    n_strategies = len(output_strategies)
    has_interventions = bool(project_config.interventions)
    any_loaded = False
    for intervention, job_files in jobs:
        contents = read_input_file_contents(job_files)
        if not contents:
            logger.critical("No valid input files found or loaded")
            return 1
        any_loaded = True
        intervention_id = intervention.id if intervention is not None else None
        for strategy_name in output_strategies:
            out_dir = resolve_output_dir(
                out_path,
                strategy_name,
                intervention_id,
                has_interventions=has_interventions,
                n_strategies=n_strategies,
            )
            run_one_export(
                job_files,
                contents,
                out_dir,
                input_strategy,
                strategy_name,
                project_config,
                intervention,
                test_strategy_name=test_strategy_name,
            )
    if not any_loaded:
        logger.critical("No valid drawio files found or loaded")
        return 1
    logger.info("Conversion completed successfully")
    return 0
