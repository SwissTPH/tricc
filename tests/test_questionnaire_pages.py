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
from tests.test_questionnaire_flat_sections import (
    CALCULATED,
    ENABLE_WHEN,
    HIDDEN,
    build_questionnaires,
    expression,
    gate,
    item_control,
    unresolved_paths,
    walk,
)

DATA = Path(__file__).parent / "data" / "yaml"


def _load_yaml(name: str):
    path = DATA / name
    strategy = YamlStrategy(str(path))
    return strategy.execute([path.read_text(encoding="utf-8")], media_path=str(DATA / "media-tmp"))


def _instances(project, activity_id):
    return dict(project.pages[activity_id].instances)


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


# ── Paginated FHIR Questionnaire ──


class TestPagesForm:
    """pages_form.yaml: two page activities, a page calling a page, loose items, groups."""

    @pytest.fixture(scope="class")
    def q(self):
        (q,) = build_questionnaires("pages_form.yaml").values()
        return q

    def test_every_section_is_a_page(self, q):
        sections = [i for i in q["item"] if i["type"] == "group"]
        assert sections
        assert all(item_control(s) == "page" for s in sections)
        # top-level items are sections or hidden activity items
        assert all(i["type"] == "group" or {"url": HIDDEN, "valueBoolean": True} in i["extension"] for i in q["item"])

    def test_page_activities_and_default_pages_in_order(self, q):
        sections = [i["linkId"] for i in q["item"] if i["type"] == "group"]
        assert sections == [
            "main_Ss_d1", "act_a_Ss_1", "act_c_Ss_1", "act_a_Ss_2", "main_Ss_d2", "act_b_Ss_1", "extra_Ss_1",
        ]
        items = {i["linkId"]: i for i, _ in walk(q["item"])}
        assert [i["linkId"] for i in items["main_Ss_d1"]["item"]] == ["loose1"]
        assert [i["linkId"] for i in items["act_c_Ss_1"]["item"]] == ["c_q"]
        assert [i["linkId"] for i in items["act_a_Ss_2"]["item"]] == ["a_after"]
        # loose2 and the non-page activity N share one default page
        assert [i["linkId"] for i in items["main_Ss_d2"]["item"]] == ["loose2", "n_q"]
        assert expression(items["main_Ss_d2"], ENABLE_WHEN) is None

    def test_non_page_activity_items_gated_by_its_hidden_item(self, q):
        items = {i["linkId"]: i for i, _ in walk(q["item"])}
        assert expression(items["n_q"], ENABLE_WHEN) == gate("act_n")
        # the relevance itself lives once, in the hidden item
        assert "loose2" in expression(items["act_n"], CALCULATED)
        assert "loose2" not in expression(items["n_q"], ENABLE_WHEN)

    def test_groups(self, q):
        items = {i["linkId"]: i for i, _ in walk(q["item"])}
        # a group without page: a sub-heading inside its page
        assert [i["linkId"] for i in items["act_b_Ss_1"]["item"]] == ["b_q", "vitals"]
        assert items["vitals"]["type"] == "group" and items["vitals"]["text"] == "Vitals"
        assert item_control(items["vitals"]) is None
        # a group with page: its own page, shown with its activity
        assert [i["linkId"] for i in items["extra_Ss_1"]["item"]] == ["b_extra"]
        assert items["extra_Ss_1"]["text"] == "Extra"
        assert expression(items["extra_Ss_1"], ENABLE_WHEN) == gate("act_b")

    def test_paths_resolve(self, q):
        assert unresolved_paths(q) == []


def test_goto_page_false_overrides_activity_page_in_questionnaire():
    (q,) = build_questionnaires("pages_goto_resolution.yaml").values()
    sections = [i["linkId"] for i in q["item"] if i["type"] == "group"]
    # instance 2 of page_mod is a page (goto_a); paged_act is not (goto_c page: false)
    assert "page_mod_Ss_1" in sections
    assert not [s for s in sections if s.startswith("paged_act_Ss_")]
    items = {i["linkId"]: i for i, _ in walk(q["item"])}
    assert expression(items["pa_weight"], ENABLE_WHEN) == gate("paged_act")


def test_block_and_inlined_call_with_page_are_wrapped_in_a_page_group():
    (q,) = build_questionnaires("pages_block.yaml").values()
    sections = [i for i in q["item"] if i["type"] == "group"]
    assert all(item_control(s) == "page" for s in sections)
    by_first = {s["item"][0]["linkId"]: s["linkId"] for s in sections if s.get("item")}
    assert by_first["m_temp"].startswith("measure_Ii_")
    assert by_first["im_age"].startswith("inline_mod_Ii_")
    assert by_first["q0"].startswith("main_Ss_d")
    assert unresolved_paths(q) == []


def test_as_group_false_gives_the_same_questionnaire_as_instance_minus_one():
    (with_alias,) = build_questionnaires("goto_snippet_injection.yaml").values()
    (with_flag,) = build_questionnaires("goto_as_group_false.yaml").values()
    assert with_flag["item"] == with_alias["item"]
