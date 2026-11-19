"""XLSFormCDSSStrategy.export_inputs walks each page once (fix/20261113-cht-export-inputs-recursion.md)."""
from tricc_oo.models.calculate import TriccNodeActivityStart, TriccNodePopulate
from tricc_oo.models.tricc import TriccNodeActivity
from tricc_oo.strategies.output.xlsform_cdss import XLSFormCDSSStrategy


def _activity(aid):
    root = TriccNodeActivityStart(id=f"{aid}_start", name=f"{aid}_start")
    return TriccNodeActivity(id=aid, name=aid, root=root, nodes={})


def _populate(pid):
    return TriccNodePopulate(id=pid, name=pid)


def _strategy():
    return XLSFormCDSSStrategy.__new__(XLSFormCDSSStrategy)


def test_activity_listing_itself_does_not_recurse():
    main, sub = _activity("main"), _activity("sub")
    age = _populate("age")
    sub.nodes = {sub.id: sub, age.id: age}  # a page reached by goto lists itself
    main.nodes = {sub.id: sub}
    assert _strategy().export_inputs(main) == [age]


def test_page_reached_twice_gives_its_inputs_once():
    main, a, b, shared = (_activity(x) for x in ("main", "a", "b", "shared"))
    sex = _populate("sex")
    shared.nodes = {sex.id: sex}
    a.nodes = {shared.id: shared}
    b.nodes = {shared.id: shared, a.id: a}
    a.nodes[b.id] = b  # a and b contain each other
    main.nodes = {a.id: a, b.id: b}
    assert _strategy().export_inputs(main) == [sex]


def test_inputs_do_not_carry_over_between_calls():
    main = _activity("main")
    age = _populate("age")
    main.nodes = {age.id: age}
    strategy = _strategy()
    assert strategy.export_inputs(main) == [age]
    assert strategy.export_inputs(main) == [age]
