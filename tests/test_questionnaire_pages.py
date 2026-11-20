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


# ── asGroup on blocks and groups of questions (rev. 2026-11-20) ──


class TestAsGroupBlocksAndGroups:
    """as_group_blocks.yaml: three block calls and two groups of questions, no page."""

    @pytest.fixture(scope="class")
    def q(self):
        (q,) = build_questionnaires("as_group_blocks.yaml").values()
        return q

    @staticmethod
    def _sections(q):
        return {i["linkId"]: [c["linkId"] for c in i.get("item", [])] for i in q["item"] if i["type"] == "group"}

    def test_block_call_as_group_true_is_its_own_section(self, q):
        sections = self._sections(q)
        (a_section,) = [s for s, items in sections.items() if items == ["a_q"]]
        assert a_section.startswith("blk_a_Ii_") and a_section.endswith("_Ss_1")
        # a section, not a page
        assert all(item_control(i) is None for i in q["item"])
        # the caller is split around it
        order = list(sections)
        assert order.index("main_Ss_d1") < order.index(a_section) < order.index("main_Ss_d2")

    def test_block_start_as_group_true_call_false_is_inlined(self, q):
        sections = self._sections(q)
        assert sections["main_Ss_d2"] == ["b_q"]
        assert not [s for s in sections if s.startswith("blk_b_")]

    def test_block_start_as_group_true_applies_when_the_call_leaves_it_unset(self, q):
        sections = self._sections(q)
        (c_section,) = [s for s, items in sections.items() if items == ["c_q"]]
        assert c_section.startswith("blk_c_Ii_")

    def test_group_as_group_false_has_no_group_item(self, q):
        items = {i["linkId"]: i for i, _ in walk(q["item"])}
        assert "frame" not in items
        # q1 sits in the enclosing section, next to the sub-heading of the default group
        assert self._sections(q)["main_Ss_d3"] == ["q1", "head"]
        assert items["head"]["type"] == "group" and items["head"]["text"] == "Head"

    def test_paths_resolve(self, q):
        assert unresolved_paths(q) == []


def test_block_calls_resolve_as_group_on_the_model():
    project = _load_yaml("as_group_blocks.yaml")
    main = project.start_pages["main"]
    by_name = {getattr(n, "name", None): n for n in main.nodes.values()}
    assert by_name["a_q"].group.call and by_name["a_q"].group.as_group
    assert not by_name["a_q"].group.page
    assert by_name["b_q"].group is main
    assert by_name["c_q"].group.call
    # the frame is gone, its question belongs to the activity
    assert by_name["q1"].group is main
    assert [g.name for g in main.groups.values() if not g.call] == ["head"]


def test_dissolve_inline_groups_moves_members_to_the_enclosing_section():
    from tricc_oo.converters.xml_to_tricc import dissolve_inline_groups
    from tricc_oo.models.base import TriccGroup
    from tricc_oo.models.tricc import TriccNodeInteger

    activity = TriccNodeActivity(id="a1", name="a1", root=TriccNodeGoTo(id="r", link="x"))
    head = TriccGroup(id="g_head", name="head", activity=activity, group=activity)
    frame = TriccGroup(id="g_frame", name="frame", activity=activity, group=head, as_group=False)
    inner = TriccGroup(id="g_inner", name="inner", activity=activity, group=frame)
    q1 = TriccNodeInteger(id="q1", name="q1", label="Q1", activity=activity, group=frame)
    q2 = TriccNodeInteger(id="q2", name="q2", label="Q2", activity=activity, group=inner)
    activity.nodes = {"q1": q1, "q2": q2}
    activity.groups = {g.id: g for g in (head, frame, inner)}
    dissolve_inline_groups(activity)
    assert q1.group is head
    assert q2.group is inner and inner.group is head
    assert set(activity.groups) == {"g_head", "g_inner"}


def test_drawio_container_page_reads_as_group():
    from lxml import etree

    from tricc_oo.converters.xml_to_tricc import add_group

    diagram = etree.fromstring(
        '<diagram id="d1" name="d1"><mxGraphModel><root>'
        '<object id="g1" tricc_type="container_page" name="frame" asGroup="false"/>'
        '<object id="g2" tricc_type="container_page" name="head"/>'
        "</root></mxGraphModel></diagram>"
    )
    activity = TriccNodeActivity(id="a1", name="a1", root=TriccNodeGoTo(id="r", link="x"))
    frame, head = (add_group(elm, diagram, {}, {}, activity, activity) for elm in diagram.iter("object"))
    assert frame.as_group is False
    assert head.as_group is True


def test_drawio_block_reads_as_group():
    from lxml import etree

    from tricc_oo.converters.xml_to_tricc import resolve_as_group, set_additional_attributes
    from tricc_oo.models.calculate import TriccNodeBlockStart
    from tricc_oo.models.tricc import TriccNodeBlock

    block = TriccNodeBlock(id="b1", name="b1", link="blk")
    set_additional_attributes(["page", "asGroup"], etree.fromstring('<object asGroup="1"/>'), block)
    assert block.as_group is True
    start = TriccNodeBlockStart(id="s1", name="blk", label="Block", as_group=True)
    # call value, else block_start value, else False
    assert resolve_as_group(TriccNodeBlock(id="b2", link="blk"), start) is True
    assert resolve_as_group(TriccNodeBlock(id="b3", link="blk", as_group=False), start) is False
    assert resolve_as_group(TriccNodeBlock(id="b4", link="blk"), None) is False


def test_page_true_with_as_group_false_keeps_the_page(caplog):
    _load_yaml("as_group_page_wins.yaml")
    wins = [r for r in caplog.records if "the page wins" in r.getMessage()]
    assert {r.getMessage().split(":")[0] for r in wins} == {"node call_m", "group g_page"}
    (q,) = build_questionnaires("as_group_page_wins.yaml").values()
    sections = {i["linkId"]: [c["linkId"] for c in i.get("item", [])] for i in q["item"] if i["type"] == "group"}
    assert all(item_control(i) == "page" for i in q["item"] if i["type"] == "group")
    assert any(s.startswith("measure_Ii_") and items == ["m_temp"] for s, items in sections.items())
    assert sections.get("page_frame_Ss_1") == ["q1"]


def test_drawio_nested_container_page():
    from lxml import etree

    from tricc_oo.converters.xml_to_tricc import get_groups

    diagram = etree.fromstring(
        '<diagram id="d1" name="d1"><mxGraphModel><root>'
        '<object id="grpouter001" odk_type="container_page" tricc_type="container_page" name="outer"/>'
        '<object id="grpinner002" parent="grpouter001" odk_type="container_page" tricc_type="container_page"'
        ' name="inner"/>'
        "</root></mxGraphModel></diagram>"
    )
    activity = TriccNodeActivity(id="a1", name="a1", root=TriccNodeGoTo(id="r", link="x"))
    groups = get_groups(diagram, {}, activity)
    assert groups["grpinner002"].group is groups["grpouter001"]
    assert groups["grpinner002"].activity is activity
