"""Regression test: a node following a *second* instance of a repeated activity call
must still get a relevance expression and must not depend on the called activity's
own (skip-suppressed) content.

Bug: activity A calls module B as instance=1; activity C calls the same module B as
instance=2, followed by a node D. D was silently dropped from load_calculate's
walkthrough (and therefore from the export) because a TriccNodeActivity's own
next_nodes were never scheduled once its content finished processing.
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


class TestGotoInstanceMultiCaller(unittest.TestCase):
    def test_node_after_second_instance_call_is_processed(self):
        project = _load_yaml("goto_instance_multi_caller.yaml")
        self.assertIsNotNone(project)
        parent = project.start_pages.get("main")
        self.assertIsNotNone(parent)

        by_name = {getattr(n, "name", None): n for n in parent.nodes.values() if getattr(n, "name", None)}
        self.assertIn("after_b2", by_name)
        after_b2 = by_name["after_b2"]

        # must have been reached by load_calculate (not silently dropped)
        self.assertIsNotNone(after_b2.relevance)

        # its relevance must depend on the branch decision, not on the called
        # (and possibly skip-suppressed) module's own content
        references = {getattr(r, "name", None) for r in after_b2.relevance.get_references()}
        self.assertIn("choice", references)
        self.assertFalse(
            any(ref and ref.startswith("mod_") for ref in references),
            f"after_b2 relevance should not depend on module_b internals, got {references}",
        )


if __name__ == "__main__":
    unittest.main()
