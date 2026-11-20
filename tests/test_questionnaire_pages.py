"""Form pages and asGroup (feature/20261120-questionnaire-pages.md).

Resolution of ``page`` / ``asGroup`` at linking, the deprecation of ``instance: -1``, and
the paginated FHIR Questionnaire.
"""

import warnings
from pathlib import Path

import pytest

from tricc_oo.converters.xml_to_tricc import TriccPageConflictError, parse_bool_attribute
from tricc_oo.models.tricc import TriccNodeActivity, TriccNodeGoTo
from tricc_oo.strategies.input.yaml import YamlStrategy

DATA = Path(__file__).parent / "data" / "yaml"


def _load_yaml(name: str):
    path = DATA / name
    strategy = YamlStrategy(str(path))
    return strategy.execute([path.read_text(encoding="utf-8")], media_path=str(DATA / "media-tmp"))


def _instances(project, activity_id):
    page = project.pages[activity_id]
    return {nb: inst for nb, inst in page.instances.items()}


# ── Resolution at linking ──


@pytest.mark.parametrize(
    "value, expected",
    [(True, True), (False, False), ("true", True), ("FALSE", False), ("1", True), ("0", False), (1, True), (0, False)],
)
def test_parse_bool_attribute(value, expected):
    assert parse_bool_attribute(value, "page", "n") is expected


def test_parse_bool_attribute_not_a_boolean_is_ignored(caplog):
    assert parse_bool_attribute("maybe", "page", "n") is None
    assert "not a boolean" in caplog.text


def test_shared_instance_follows_the_goto_that_sets_page(caplog):
    project = _load_yaml("pages_goto_resolution.yaml")
    shared = _instances(project, "page_mod")[2]
    assert shared.page is True
    assert shared.page_set_by == "goto_a"
    assert "different page values" not in caplog.text


def test_goto_page_false_overrides_activity_page_true():
    project = _load_yaml("pages_goto_resolution.yaml")
    instances = [i for i in _instances(project, "paged_act").values() if i.base_instance is not None]
    assert instances and all(i.page is False for i in instances)


def test_conflicting_page_on_shared_instance_is_an_error():
    with pytest.raises(TriccPageConflictError, match="goto_a.*goto_b|goto_b.*goto_a"):
        _load_yaml("pages_goto_conflict.yaml")


def test_as_group_on_start_inlines_and_goto_overrides():
    project = _load_yaml("pages_as_group_start.yaml")
    parent = project.start_pages["main"]
    nodes = list(parent.nodes.values())
    assert not any(isinstance(n, TriccNodeGoTo) for n in nodes)
    # goto_x inlined the module into the caller ...
    assert any(getattr(n, "name", None) == "im_age" for n in nodes)
    # ... goto_y (asGroup: true) opened it as an activity instance
    nested = [n for n in nodes if isinstance(n, TriccNodeActivity)]
    assert len(nested) == 1
    assert any(getattr(n, "name", None) == "im_age" for n in nested[0].nodes.values())


def test_instance_minus_one_still_inlines_with_deprecation():
    with pytest.warns(DeprecationWarning, match="instance = -1 is deprecated"):
        project = _load_yaml("goto_snippet_injection.yaml")
    parent = project.start_pages["main"]
    assert any(getattr(n, "name", None) == "mod_age" for n in parent.nodes.values())


def test_as_group_false_has_no_deprecation():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        _load_yaml("goto_as_group_false.yaml")
    assert not [w for w in caught if "instance = -1" in str(w.message)]


def test_drawio_attributes_page_and_as_group():
    from lxml import etree

    from tricc_oo.converters.xml_to_tricc import _goto_inlined_at_parse, set_additional_attributes
    from tricc_oo.models.tricc import TriccIntervention

    goto = TriccNodeGoTo(id="g1", name="g1", link="target_page")
    elm = etree.fromstring('<object page="1" asGroup="maybe"/>')
    set_additional_attributes(["page", "asGroup"], elm, goto)
    assert goto.page is True
    assert goto.as_group is None
    # the called page's start node says asGroup="false": the goto is inlined at parse time
    project = TriccIntervention(start_as_group={"target_page": False})
    assert _goto_inlined_at_parse(goto, project)
    goto.link = "target_page__p0123abcd"  # a page built for parameter values
    assert _goto_inlined_at_parse(goto, project)
    goto.as_group = True
    assert not _goto_inlined_at_parse(goto, project)


def test_drawio_container_page_reads_page():
    from lxml import etree

    from tricc_oo.converters.xml_to_tricc import add_group

    diagram = etree.fromstring(
        '<diagram id="d1" name="d1"><mxGraphModel><root>'
        '<object id="grp" tricc_type="container_page" name="vitals" label="Vitals" page="true"/>'
        "</root></mxGraphModel></diagram>"
    )
    activity = TriccNodeActivity(id="a1", name="a1", root=TriccNodeGoTo(id="r", link="x"))
    group = add_group(diagram.find(".//object"), diagram, {}, {}, activity, activity)
    assert group.page is True
