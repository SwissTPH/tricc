import logging
from tricc_og.models.base import TriccMixinRef, FlowType, TriccBaseModel, to_scv_str

logger = logging.getLogger(__name__)

def get_element(graph, system, code, version=None, instance=None, white_list=None):
    try:
        if not white_list:
            # list(filter(lambda x: hasattr(x, 'attributes')  and  'id' in x.attributes and x.attributes == code, set_of_elements))
            ref = to_scv_str(
                code=code,
                system=system,
                version=version,
                instance=instance
            )
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
    except Exception as e:
        pass


def get_elements(graph, system, code, version=None):
    ref = TriccMixinRef(code=code, system=system, version=version).scv()
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
        attributes['label'] = label
    if not isinstance(from_, (str, int)):
        from_ = from_.scv()
    if not isinstance(to_, (str, int)):
        to_ = to_.scv()
    graph.add_edge(
        from_,
        to_,
        flow_type=flow_type,
        activity=activity,
        **attributes
    )

