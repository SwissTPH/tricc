"""YamlStrategy builds one activity container per YAML activity."""

from __future__ import annotations

from tricc_oo.models.tricc import TriccIntervention
from tricc_oo.strategies.input.yaml import YamlActivity, YamlStrategy


def test_activity_end_and_edges_belong_to_the_returned_activity():
    yaml_act = YamlActivity.model_validate(
        {
            "id": "sub",
            "title": "Sub",
            "nodes": [
                {"id": "s", "type": "activity_start", "label": "Sub", "name": "sub_start"},
                {"id": "n", "type": "note", "name": "sub_note", "label": "Note"},
                {"id": "e", "type": "activity_end", "name": "sub_end"},
            ],
            "edges": [{"source": "s", "target": "n"}, {"source": "n", "target": "e"}],
        }
    )
    activity = YamlStrategy(None)._build_activity(yaml_act, TriccIntervention())
    assert set(activity.nodes) == {"s", "n", "e"}
    assert [(e.source, e.target) for e in activity.edges] == [("s", "n"), ("n", "e")]
    for node in activity.nodes.values():
        assert node.activity is activity
