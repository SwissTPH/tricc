from tricc_og.models.base import TriccMixinRef, FlowType


def get_element(graph, system, code, version=None, instance=None):
    # list(filter(lambda x: hasattr(x, 'attributes')  and  'id' in x.attributes and x.attributes == code, set_of_elements))
    ref = TriccMixinRef(code=code, system=system, version=version, instance=instance).__resp__()
    match = graph.nodes[ref]
    if match and 'data' in match:
        return match['data']

def add_flow(
        graph,
        activity,
        from_,
        to_,
        label=None,
        flow_type=FlowType("SEQUENCE"),
        **kwargs
):
    attributes = kwargs if kwargs else {}
    if label:
        attributes['label']=label
    if not isinstance(from_, (str, int)):
        from_ = from_.__resp__()
    if not isinstance(to_, (str, int)):
        to_ = to_.__resp__()
    graph.add_edge(
        from_,
        to_,
        flow_type=flow_type,
        activity=activity,
        **attributes
    )
