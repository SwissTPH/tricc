import logging
from tricc_og.models.base import TriccMixinRef, FlowType, TriccBaseModel, to_scv_str, TriccSCV

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
    return [n[1]['data'] for n in filter(lambda node:  node[0].startswith(ref), graph.nodes(data=True))]


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


def is_ready_to_process(G, node, processed):
    references = []
    if hasattr(node, 'expression') and node.expression:
        references = node.expression.get_references()
    return all([
        *[e[0] in processed for e in list(G.in_edges(node.scv(), keys = True))],
        *[any(p.startswith("{r}.") for p in processed) for r in references if isinstance(r, TriccSCV)]
    ])


def walktrhough_tricc_node_processed_stached(G, scv, callback, processed_nodes, stashed_nodes, strategy,
                                             warn=False, node_path=[], **kwargs):
    # logger.debug("walkthrough::{}::{}".format(callback.__name__, node.get_name()))
    node = G.nodes[scv]['data']
    df_survey = kwargs.get('df_survey')
    df_choices = kwargs.get('df_choices')
    if (callback(G, node, processed_nodes, out_strategy= strategy, df_survey= df_survey, df_choices=df_choices)):
        node_path.append(node)
        # node processing succeed
        if scv not in processed_nodes:
            processed_nodes.add(scv)
            logger.debug("{}::{}: processed ({})".format(callback.__name__, node.get_name(), len(processed_nodes)))
        if scv in stashed_nodes:
            stashed_nodes.remove(node)
        # reorder_node_list(stashed_nodes, node.group)
        stashed_nodes._add_items(list(G.successors(scv)))
        #for el in list(G.successors(scv)):
        #    stashed_nodes.add(el)
    else:
        if scv not in processed_nodes and scv not in stashed_nodes:
            if node not in stashed_nodes:
                stashed_nodes.insert_at_bottom(node.scv())
                logger.debug("{}::{}: stashed({})".format(callback.__name__, node.get_name(), len(stashed_nodes)))

def walktrhough_tricc_processed_stached(G, start, callback, processed_nodes, stashed_nodes, strategy,
                                        warn=False, node_path=[], **kwargs):
    
    walktrhough_tricc_node_processed_stached(G, start, callback, processed_nodes, stashed_nodes, strategy,
                                             warn=False, node_path=[], **kwargs)
    while stashed_nodes:
        walktrhough_tricc_node_processed_stached(G, stashed_nodes.pop(), callback, processed_nodes, stashed_nodes, strategy,
                            warn=False, node_path=[], **kwargs)

#def export_tricc_operation(t_o, orderd_set_available_scv, export_strategy):
    # find the convertor from the strategy based on the operator
    # for all reference that are TriccOperation, recursive call
    # for all refernece that are TriccSCV, find the most recent instance in orderd_set_available_scv
    # for all triccValue, just use them as is
    # error for all other type
    # call the convertor with the list of refrence
