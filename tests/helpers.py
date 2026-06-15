"""
Test helpers for TRICC transformation testing.

These utilities make it much easier to write focused regression tests
against the core transformation logic (inheritance, calculate loading,
relevance propagation, etc.) using the YAML input strategy.

Example usage:

    from tests.helpers import load_yaml_project, assert_last_version

    project = load_yaml_project("tests/data/yaml/inheritance_versioning_basic.yaml")
    activity = project.pages["inheritance_override"]

    eligible = get_node_by_name(activity, "is_eligible")
    assert_last_version(eligible, last=True, version=1)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

from tricc_oo.models.tricc import TriccProject, TriccNodeBaseModel
from tricc_oo.strategies.input.yaml import YamlStrategy


def load_yaml_project(
    yaml_path: Union[str, Path],
    media_path: Optional[str] = None,
    run_full_pipeline: bool = True,
) -> TriccProject:
    """
    Load a YAML test fixture and (optionally) run the full transformation pipeline.

    This is the recommended way to write transformation-focused tests.
    It exercises exactly the same code path as real usage but with
    human-readable, git-friendly input.

    Args:
        yaml_path: Path to a .yaml file (can contain multiple documents/activities)
        media_path: Optional directory for any media artifacts
        run_full_pipeline: If True (default), calls execute_linked_process + process_pages
                           so that inheritance, calculates, relevance etc. are fully resolved.

    Returns:
        A fully (or partially) processed TriccProject.
    """
    yaml_path = Path(yaml_path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML fixture not found: {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        content = f.read()

    if media_path is None:
        media_path = os.path.join(os.path.dirname(yaml_path), "media-tmp")

    os.makedirs(media_path, exist_ok=True)

    strategy = YamlStrategy([str(yaml_path)])
    project = strategy.execute([content], media_path)

    if project is None:
        raise RuntimeError(f"Failed to load project from {yaml_path}")

    if run_full_pipeline:
        # Ensure the main linked process and full calculate loading runs
        # (this is what normally happens in tests/build.py)
        if "main" in project.start_pages:
            app = project.start_pages["main"]
            # Re-process to guarantee all visitors ran
            strategy.process_pages(app, project)
        # For projects without "main", the strategy already did its best

    return project


def get_node_by_name(activity, name: str) -> Optional[TriccNodeBaseModel]:
    """Find a node inside an activity by its 'name' attribute (case-sensitive)."""
    for node in activity.nodes.values():
        if getattr(node, "name", None) == name:
            return node
    # Also check calculates (they are sometimes stored separately)
    for node in getattr(activity, "calculates", []):
        if getattr(node, "name", None) == name:
            return node
    return None


def assert_last_version(node, last: bool = True, version: Optional[int] = None, msg: str = ""):
    """Assert on the inheritance/versioning state of a node."""
    prefix = f"{msg + ': ' if msg else ''}Node {getattr(node, 'name', node.id)}"
    assert getattr(node, "last", None) == last, (
        f"{prefix}: expected last={last}, got last={getattr(node, 'last', None)}"
    )
    if version is not None:
        assert getattr(node, "version", None) == version, (
            f"{prefix}: expected version={version}, got version={getattr(node, 'version', None)}"
        )


def get_calculate_by_name(project_or_activity, name: str) -> Optional[TriccNodeBaseModel]:
    """Search for a calculate (by name) anywhere in a project or single activity."""
    candidates = []
    if hasattr(project_or_activity, "pages"):
        for act in project_or_activity.pages.values():
            candidates.extend(getattr(act, "calculates", []))
            candidates.extend(
                n for n in act.nodes.values()
                if getattr(n, "name", None) == name and "calc" in str(type(n)).lower()
            )
    else:
        act = project_or_activity
        candidates.extend(getattr(act, "calculates", []))
    for c in candidates:
        if getattr(c, "name", None) == name:
            return c
    return None


# Convenience re-exports for tests
__all__ = [
    "load_yaml_project",
    "get_node_by_name",
    "get_calculate_by_name",
    "assert_last_version",
]
