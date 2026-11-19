"""Tests for not_available title + multiple reason options (ODK/CHT).

See feature/20260902-not-available-title-options.md.
"""

import unittest

from lxml import etree

from tricc_oo.converters.drawio_type_map import TYPE_MAP
from tricc_oo.converters.xml_to_tricc import add_tricc_base_node
from tricc_oo.models.base import TriccNodeType
from tricc_oo.models.tricc import TriccNodeActivity, TriccNodeMainStart, TriccNodeSelectNotAvailable
from tests.helpers import get_node_by_name, load_yaml_project


def _parse_not_available(diagram_xml, object_id="n1"):
    diagram = etree.fromstring(diagram_xml)
    activity = TriccNodeActivity(
        id="a1", name="act", label="Act", root=TriccNodeMainStart(id="s1", name="s", label="S")
    )
    entry = TYPE_MAP[TriccNodeType.not_available]
    elm = diagram.find(f".//*[@id='{object_id}']")
    nodes = {}
    add_tricc_base_node(
        diagram,
        nodes,
        entry["model"],
        [elm],
        activity,
        attributes=entry["attributes"],
        mandatory_attributes=entry["mandatory_attributes"],
        defaults=entry.get("defaults"),
    )
    return [n for n in nodes.values() if isinstance(n, TriccNodeSelectNotAvailable)][0]


class TestNotAvailableDrawioParse(unittest.TestCase):
    def test_no_children_does_not_invent_an_option(self):
        node = _parse_not_available(
            """
            <diagram id="d1">
              <root>
                <object id="n1" odk_type="not_available" name="etat.r.010"
                        label="Weight estimation"/>
              </root>
            </diagram>
            """
        )
        self.assertEqual(node.label, "Weight estimation")
        self.assertEqual(node.options, {})

    def test_child_options_keep_title(self):
        node = _parse_not_available(
            """
            <diagram id="d1">
              <root>
                <object id="n1" odk_type="not_available" name="etat.r.010" label="Weight estimation">
                  <mxCell parent="unused"/>
                </object>
                <object id="o1" odk_type="select_option" name="unstable" label="Not stable enough">
                  <mxCell parent="n1"/>
                </object>
                <object id="o2" odk_type="select_option" name="noscale" label="Cannot be measured">
                  <mxCell parent="n1"/>
                </object>
              </root>
            </diagram>
            """
        )
        self.assertEqual(node.label, "Weight estimation")
        self.assertEqual(len(node.options), 2)
        labels = [node.options[i].label for i in sorted(node.options)]
        names = [node.options[i].name for i in sorted(node.options)]
        self.assertEqual(labels, ["Not stable enough", "Cannot be measured"])
        self.assertEqual(names, ["unstable", "noscale"])

    def test_child_option_keeps_authored_name(self):
        node = _parse_not_available(
            """
            <diagram id="d1">
              <root>
                <object id="n1" odk_type="not_available" name="etat.r.010" label="Weight estimation">
                  <mxCell parent="unused"/>
                </object>
                <object id="o1" odk_type="select_option" name="not_stable"
                        label="Not stable enough, Weight cannot be measured">
                  <mxCell parent="n1"/>
                </object>
              </root>
            </diagram>
            """
        )
        self.assertEqual(node.label, "Weight estimation")
        self.assertEqual(len(node.options), 1)
        self.assertEqual(node.options[0].name, "not_stable")
        self.assertEqual(node.options[0].label, "Not stable enough, Weight cannot be measured")



class TestNotAvailableYaml(unittest.TestCase):
    def test_titled_options(self):
        project = load_yaml_project("tests/data/yaml/not_available_titled.yaml")
        activity = project.pages["not_available_titled"]
        node = get_node_by_name(activity, "weight_na")
        self.assertIsInstance(node, TriccNodeSelectNotAvailable)
        self.assertEqual(node.label, "Weight estimation")
        self.assertEqual(len(node.options), 2)
        self.assertEqual(node.options[0].label, "Not stable enough")
        self.assertEqual(node.options[1].label, "Cannot be measured")
        self.assertEqual(node.options[0].name, "unstable")
        self.assertEqual(node.options[1].name, "noscale")

    def test_legacy_yaml_keeps_authored_label_when_options_omitted(self):
        # YAML has no synthetic NO_LABEL path; omitting options just leaves an empty list.
        # Draw.io is the legacy authoring surface. This fixture still loads.
        project = load_yaml_project("tests/data/yaml/not_available_legacy.yaml")
        activity = project.pages["not_available_legacy"]
        node = get_node_by_name(activity, "weight_na")
        self.assertIsInstance(node, TriccNodeSelectNotAvailable)
        self.assertEqual(node.label, "Not stable enough, Weight cannot be measured")
        self.assertEqual(len(node.options), 0)
