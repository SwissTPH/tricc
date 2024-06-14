import logging
from tricc_og.models.base import TriccMixinRef, FlowType, TriccBaseModel

logger = logging.getLogger(__name__)

def get_element(graph, system, code, version=None, instance=None, white_list=None):
    
    if not white_list:
        # list(filter(lambda x: hasattr(x, 'attributes')  and  'id' in x.attributes and x.attributes == code, set_of_elements))
        ref = TriccMixinRef(
            code=code,
            system=system,
            version=version,
            instance=instance
        ).__resp__()
        match = graph.nodes[ref]
        if match:
            return match['data']
        if instance is None:
            matches = get_elements(graph, system, code, version)
            if matches:
                matches = list(sorted(matches, instance, reverse=True))
                if matches:
                    return matches[0]
    else:
        for n in white_list:
            if isinstance(n, tuple) and isinstance(n[1], dict) and 'data' in n[1]:
                n = n[1]['data']
            if not issubclass(n.__class__, TriccBaseModel):
                logger.error(f"not expected object {n}")
                return None
            if n.system == system and str(n.code) == str(code):
                return n
        logger.error(f"question {system}:{code} not found")


def get_elements(graph, system, code, version=None):
    ref = TriccMixinRef(code=code, system=system, version=version).__resp__()
    return [ n[1]['data'] for n in filter(lambda node:  node[0].startswith(ref), graph.nodes(data=True))]


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
