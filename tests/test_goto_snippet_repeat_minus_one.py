"""Regression test: repeat=-1 ("local-only") captures injected via two independent
instance=-1 snippet calls must not be skip-suppressed against each other.

Scenario: Act B and Act C each call module_a as an instance=-1 snippet (inline
injection, no nested activity / wait - see docs/tricc-elements.md, "Navigation/linking
elements"). module_a captures node_d with repeat=-1 ("local-only" per "Concept
repeat"). When both callers fire, node_d is captured twice (once inlined per
caller). Because repeat=-1 explicitly opts out of encounter-wide dedup, the second
occurrence's relevance must depend only on its own caller's gate (trigger_c) - it
must NOT be ANDed with "the first occurrence wasn't already captured", which is
what happens to ordinary repeat=1 (default) slots (see
tests/test_concept_repeat.py::TestLoadCalculateRepeatSkip.test_same_repeat_gets_skip_relevance).
"""

import unittest
from pathlib import Path

from tricc_oo.strategies.input.yaml import YamlStrategy

DATA = Path(__file__).parent / "data" / "yaml"


def _load_yaml(name: str):
    path = DATA / name
    content = path.read_text(encoding="utf-8")
    strategy = YamlStrategy(str(path))
    return strategy.execute([content], media_path=str(DATA / "media-tmp"))


class TestGotoSnippetRepeatMinusOne(unittest.TestCase):
    def test_second_local_only_capture_is_not_skip_suppressed(self):
        project = _load_yaml("goto_snippet_repeat_minus_one.yaml")
        self.assertIsNotNone(project)
        parent = project.start_pages.get("main")
        self.assertIsNotNone(parent)

        node_ds = [n for n in parent.nodes.values() if getattr(n, "name", None) == "node_d"]
        self.assertEqual(len(node_ds), 2, "expected one node_d clone per snippet inject")
        for n in node_ds:
            self.assertEqual(getattr(n, "repeat", None), -1)

        refs_by_node = {
            n.id: {getattr(r, "name", None) for r in n.relevance.get_references()} for n in node_ds
        }

        # each clone's relevance must depend on exactly its own caller's gate - never
        # on the other clone's gate, and never on "was the other node_d captured"
        # (which is what an incorrect skip-suppression would add).
        gates_seen = set()
        for node_id, refs in refs_by_node.items():
            own_gates = refs & {"trigger_b", "trigger_c"}
            self.assertEqual(len(own_gates), 1, f"node_d[{node_id}] relevance refs: {refs}")
            gates_seen |= own_gates
            self.assertEqual(refs, own_gates, f"node_d[{node_id}] relevance refs: {refs}")
        self.assertEqual(gates_seen, {"trigger_b", "trigger_c"})


if __name__ == "__main__":
    unittest.main()
