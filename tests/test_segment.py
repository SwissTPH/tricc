"""TriccSegment is the activity container whose root is a main start."""

from pathlib import Path

import yaml as yaml_lib

from tricc_oo.models.calculate import TriccNodeActivityStart
from tricc_oo.models.tricc import (
    TriccNodeActivity,
    TriccNodeMainStart,
    TriccProject,
    TriccSegment,
    node_container_for_root,
)
from tricc_oo.strategies.input.yaml import YamlActivity, YamlStrategy
from tests.helpers import load_yaml_project


def test_factory_main_start_is_segment():
    root = TriccNodeMainStart(id="s", name="start", label="Start", process="registration")
    container = node_container_for_root(root, id="seg", name="reg", label="Registration")
    assert isinstance(container, TriccSegment)
    assert isinstance(container, TriccNodeActivity)
    assert container.root is root
    assert container.tricc_type == "segment"


def test_factory_activity_start_is_activity():
    root = TriccNodeActivityStart(id="as", name="act_start", label="Act start")
    container = node_container_for_root(root, id="act", name="mod", label="Module")
    assert isinstance(container, TriccNodeActivity)
    assert not isinstance(container, TriccSegment)
    assert container.tricc_type == "activity"


def test_yaml_start_page_is_segment():
    project = load_yaml_project("tests/data/yaml/basic_flow_with_calc.yaml")
    page = project.pages["basic_flow"]
    assert isinstance(page, TriccSegment)
    assert isinstance(page.root, TriccNodeMainStart)
    assert "main" in project.segments
    assert page in project.segments["main"]


def test_yaml_activity_start_page_is_not_segment():
    project = load_yaml_project("tests/data/yaml/concept_repeat_activity_inherit.yaml")
    page = project.pages["activity_repeat_override"]
    assert isinstance(page, TriccNodeActivity)
    assert not isinstance(page, TriccSegment)
    assert isinstance(page.root, TriccNodeActivityStart)
    assert project.segments == {}


def test_yaml_two_main_starts_same_process_both_indexed():
    # Build pages only (no execute_linked_process / walk).
    path = Path("tests/data/yaml/inheritance_versioning_basic.yaml")
    strategy = YamlStrategy(str(path))
    project = TriccProject()
    for doc in yaml_lib.safe_load_all(path.read_text(encoding="utf-8")):
        if not doc:
            continue
        activity = strategy._build_activity(YamlActivity(**doc), project)
        project.pages[activity.id] = activity
        strategy._assign_start_page(activity, project)
    ids = {s.id for s in project.segments.get("main", [])}
    assert "inheritance_base" in ids
    assert "inheritance_override" in ids
    for segment in project.segments["main"]:
        assert isinstance(segment, TriccSegment)
        assert isinstance(segment.root, TriccNodeMainStart)
