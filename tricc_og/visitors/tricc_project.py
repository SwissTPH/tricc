import logging
from tricc_og.models.base import TriccMixinRef, FlowType, TriccBaseModel, to_scv_str, TriccSCV
import networkx as nx

logger = logging.getLogger(__name__)
NODE_ID = '7636'

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


def is_ready_to_process(G, node, processed, stashed_nodes):
    references = []
    if hasattr(node, 'expression') and node.expression:
        references = node.expression.get_references() # gives only triccSCV
    previous_node_processed = [e[0] in processed for e in list(G.in_edges(node.scv(), keys = True))]
    if previous_node_processed:
        stashed_nodes._add_items(
        e[0] for e, is_processed in 
        zip(G.in_edges(node.scv(), keys=True), previous_node_processed) 
        if not is_processed)
    calculate_references_processed = (
            [any(p.startswith(f"{r.value}") for p in processed) for r in references ]
                if references
                else [True])
    return all([
        *previous_node_processed,
        *calculate_references_processed
    ])

def add_dangling_node(G, node, stashed_nodes):
    # Check if reference that hasn't been processed has in_nodes, if 
    # it doesn't, stash it 
    if hasattr(node, 'expression') and node.expression:
        references = node.expression.get_references()
        for r in references:
            if not G.in_edges(r.value, data=True):
                element = (get_elements(G, 'questions', r.value.split('_', 1)[1])[-1] if r.value.startswith('questions') else  
                    get_elements(G, 'ActivityEnd', r.value.split('_', 1)[1])[-1] if r.value.startswith('Activity')
                else get_elements(G, 'diagnose', r.value.split('_', 1)[1])[-1]
                )
                stashed_nodes.insert_at_bottom(element.scv())


def walktrhough_tricc_node_processed_stached(G, scv, callback, processed_nodes, stashed_nodes, strategy,
                                             warn=False, node_path=[], **kwargs):
    logger.debug(f"walkthrough({len(stashed_nodes)})::{callback.__name__}::{scv}")
    node = G.nodes[scv]['data']
    df_survey = kwargs.get('df_survey')
    df_choices = kwargs.get('df_choices')
    if (
        callback(
            G,
            node,
            processed_nodes,
            df_survey,
            df_choices,
            stashed_nodes=stashed_nodes,
            out_strategy=strategy
        )
    ):
        node_path.append(node)
        # node processing succeed
        if scv not in processed_nodes:
            processed_nodes.add(scv)
            logger.debug("{}::{}: processed ({})".format(callback.__name__, node.get_name(), len(processed_nodes)))
        if scv in stashed_nodes:
            stashed_nodes.remove(scv)
        # reorder_node_list(stashed_nodes, node.group)
        stashed_nodes._add_items(list(G.successors(scv)))
        #for el in list(G.successors(scv)):
        #    stashed_nodes.add(el)
    else:
        add_dangling_node(G, node, stashed_nodes)
        if scv not in processed_nodes and scv not in stashed_nodes:
            stashed_nodes.insert_at_bottom(node.scv())
            logger.debug("{}::{}: stashed({})".format(callback.__name__, node.get_name(), len(stashed_nodes)))

def walktrhough_tricc_processed_stached(G, start, callback, processed_nodes, stashed_nodes, strategy,
                                        warn=False, node_path=[], **kwargs):
    
    walktrhough_tricc_node_processed_stached(G, start, callback, processed_nodes, stashed_nodes, strategy,
                                             warn=False, node_path=[], **kwargs)
    next_node = None
    prev_node = None
    while stashed_nodes:
        next_node = stashed_nodes.pop()
        if prev_node == next_node:
            logger.error("LOOOOOOOOOOOOOOOOOOOOOP")
        walktrhough_tricc_node_processed_stached(G, next_node, callback, processed_nodes, stashed_nodes, strategy,
                            warn=False, node_path=[], **kwargs)
        prev_node = next_node

#def export_tricc_operation(t_o, orderd_set_available_scv, export_strategy):
    # find the convertor from the strategy based on the operator
    # for all reference that are TriccOperation, recursive call
    # for all refernece that are TriccSCV, find the most recent instance in orderd_set_available_scv
    # for all triccValue, just use them as is
    # error for all other type
    # call the convertor with the list of refrence
def save_graphml(G, start_node, filename, remove_dandling=True):
    graph = G.copy()
    # Get hierarchical layout
    pos = hierarchical_pos(graph, start_node)
    for node, attr in list(graph.nodes(data=True)):
        if node not in pos:
            if remove_dandling:
                graph.remove_node(node)
            else:
                pos[node] = (-1, -1)
        if node in pos:
            tricc_node = attr['data']
            #graph.nodes[node]['viz'] = {'position': {'x': pos[node][0], 'y': pos[node][1]}}
            graph.nodes[node]['x'] = pos[node][0]
            graph.nodes[node]['y'] = pos[node][1]
            graph.nodes[node]['label'] = tricc_node.label
            del graph.nodes[node]['data']
        
    for edge in graph.edges(keys=True, data=True):
        edge[3]['flow_type'] = str(edge[3]['flow_type'])
        if edge[3]['activity']:
            edge[3]['activity'] = edge[3]['activity'].scv()
        else:
            del edge[3]['activity']
        if 'condition' in edge[3] and edge[3]['condition']:
            edge[3]['condition'] = str(edge[3]['condition'])
        
    # Draw the graph
    nx.write_gexf(graph, f"{filename}.gexf")

def hierarchical_pos(G, root, width=1., pos=None, vert_gap=0.2, vert_loc=0.0, xcenter=0.5):
    if not pos:
        pos = {root: (xcenter, vert_loc)}
    neighbors = [e[1] for e in G.out_edges(root)]
    if len(neighbors) != 0:
        dx = width / len(neighbors) 
        nextx = xcenter - width/2
        for neighbor in neighbors:
            if all([e[0] in pos for e in G.in_edges(neighbor)]):
                nextx += dx
                if neighbor in pos:
                    deltax = pos[neighbor][0] - nextx
                    deltay = pos[neighbor][1] - vert_loc + vert_gap
                    logger.warning(f"pos already updated {neighbor}: {deltax}:{deltay}")
                    if deltax > 0:
                        pos[neighbor] = (nextx, vert_loc - vert_gap)     
                else:
                    pos[neighbor] = (nextx, vert_loc - vert_gap)
                    hierarchical_pos(G, neighbor, pos=pos, width=dx, vert_gap=vert_gap, 
                                            vert_loc=vert_loc-vert_gap, xcenter=nextx)
            else:
                pass
    
    return pos