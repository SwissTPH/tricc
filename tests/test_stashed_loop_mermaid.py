"""Unit tests for stashed-loop Mermaid diagnostics."""

from tricc_oo.models.base import TriccOperator, TriccOperation, TriccReference
from tricc_oo.models.calculate import TriccNodeCalculate
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.visitors.tricc import (
    generate_stashed_loop_mermaid,
    get_all_dependant,
    iter_node_dependencies,
)


def _calc(node_id: str, name: str, ref_name: str = None) -> TriccNodeCalculate:
    node = TriccNodeCalculate(id=node_id, name=name, label=name)
    if ref_name is not None:
        node.expression_reference = TriccOperation(
            TriccOperator.ISTRUE, [TriccReference(ref_name)]
        )
        node.reference = list(node.expression_reference.get_references())
    return node


class TestStashedLoopMermaid:
    def test_resolves_reference_between_stashed_nodes(self):
        a = _calc("id_a", "calc_a")
        b = _calc("id_b", "calc_b", ref_name="calc_a")
        stashed = OrderedSet([a, b])

        diagram = generate_stashed_loop_mermaid(stashed, {}, {}, OrderedSet())

        assert "id_b -->|ref| id_a" in diagram
        assert "ref_calc_a" not in diagram
        assert "id_a" in diagram and "id_b" in diagram and "stashed" in diagram

    def test_unresolved_reference_stays_red(self):
        c = _calc("id_c", "calc_c", ref_name="missing_x")
        diagram = generate_stashed_loop_mermaid(OrderedSet([c]), {}, {}, OrderedSet())

        assert "ref_missing_x" in diagram
        assert 'ref_missing_x["Reference<br/>missing_x"]' in diagram
        assert "id_c -->|ref| ref_missing_x" in diagram
        assert "class ref_missing_x reference" in diagram

    def test_expression_reference_when_reference_list_empty(self):
        """Empty reference=[] must not hide expression_reference deps."""
        c = TriccNodeCalculate(id="id_c", name="calc_c", label="C")
        c.expression_reference = TriccOperation(
            TriccOperator.ISTRUE, [TriccReference("missing_y")]
        )
        c.reference = []

        deps = list(iter_node_dependencies(c))
        assert any(isinstance(d, TriccReference) and d.value == "missing_y" for d, _ in deps)

        diagram = generate_stashed_loop_mermaid(OrderedSet([c]), {}, {}, OrderedSet())
        assert "id_c -->|ref| ref_missing_y" in diagram
        assert "class ref_missing_y reference" in diagram

    def test_unprocessed_prev_node_linked_as_other(self):
        a = _calc("id_a", "calc_a")
        b = _calc("id_b", "calc_b")
        b.prev_nodes = OrderedSet([a])
        stashed = OrderedSet([b])

        diagram = generate_stashed_loop_mermaid(stashed, {}, {}, OrderedSet())

        assert "id_b -->|prev| id_a" in diagram
        assert "class id_a other" in diagram
        assert "class id_b stashed" in diagram

    def test_resolves_reference_to_processed_node(self):
        a = _calc("id_a", "calc_a")
        b = _calc("id_b", "calc_b", ref_name="calc_a")
        stashed = OrderedSet([b])
        processed = OrderedSet([a])

        diagram = generate_stashed_loop_mermaid(stashed, {}, {}, processed)

        assert "id_b -->|ref| id_a" in diagram
        assert "ref_calc_a" not in diagram
        assert "class id_a processed" in diagram
        assert "class id_b stashed" in diagram

    def test_resolves_reference_to_unprocessed_activity_node(self):
        """Ref target in activity.nodes but not stashed/processed → gray other."""
        unprocessed = _calc("id_u", "calc_u")
        b = _calc("id_b", "calc_b", ref_name="calc_u")

        class _Activity:
            nodes = {"id_u": unprocessed}

        b.activity = _Activity()
        unprocessed.activity = b.activity
        stashed = OrderedSet([b])

        diagram = generate_stashed_loop_mermaid(stashed, {}, {}, OrderedSet())

        assert "id_b -->|ref| id_u" in diagram
        assert "ref_calc_u" not in diagram
        assert "class id_u other" in diagram

    def test_prev_nodes_link_stashed_to_stashed(self):
        a = _calc("id_a", "calc_a")
        b = _calc("id_b", "calc_b")
        b.prev_nodes = OrderedSet([a])
        stashed = OrderedSet([a, b])

        diagram = generate_stashed_loop_mermaid(stashed, {}, {}, OrderedSet())

        assert "id_b -->|prev| id_a" in diagram
        assert "ref_calc_a" not in diagram

    def test_waited_and_looped_draw_edges_to_parent(self):
        a = _calc("id_a", "calc_a")
        b = _calc("id_b", "calc_b")
        missing = TriccReference("ghost")
        unprocessed = _calc("id_u", "calc_u")
        stashed = OrderedSet([a, b])
        looped = {str(b): [a]}
        waited = {str(a): [missing, unprocessed]}

        diagram = generate_stashed_loop_mermaid(stashed, waited, looped, OrderedSet())

        assert "id_b -->|loop| id_a" in diagram or "id_b -->|ref| id_a" in diagram
        assert "id_a -->|ref| ref_ghost" in diagram
        assert "id_a -->|wait| id_u" in diagram
        assert "class ref_ghost reference" in diagram
        assert "class id_u other" in diagram


class TestGetAllDependantResolution:
    def test_looped_stores_resolved_stashed_node(self):
        a = _calc("id_a", "calc_a")
        b = _calc("id_b", "calc_b", ref_name="calc_a")
        stashed = OrderedSet([a, b])

        waited, looped = get_all_dependant(stashed, stashed, OrderedSet())

        assert str(b) in looped
        assert a in looped[str(b)]
        assert not any(isinstance(d, TriccReference) for d in looped[str(b)])

    def test_empty_reference_list_still_finds_expression_ref(self):
        c = TriccNodeCalculate(id="id_c", name="calc_c", label="C")
        c.expression_reference = TriccOperation(
            TriccOperator.ISTRUE, [TriccReference("missing_z")]
        )
        c.reference = []
        stashed = OrderedSet([c])

        waited, looped = get_all_dependant(stashed, stashed, OrderedSet())

        assert str(c) in waited
        assert any(isinstance(d, TriccReference) and d.value == "missing_z" for d in waited[str(c)])
