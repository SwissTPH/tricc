import logging
from tricc_og.models.base import TriccMixinRef, FlowType, TriccBaseModel, TriccActivity, to_scv_str, TriccSCV
import networkx as nx
from networkx.exception import NetworkXNoCycle, NetworkXNoPath, NetworkXError

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


def is_ready_to_process(G, node, processed_nodes, stashed_nodes):
    references = []
    if hasattr(node, 'expression') and node.expression:
        references = node.expression.get_references() # gives only triccSCV
    previous_node_processed = [e[0] in processed_nodes and 
        (
            not e[3].get('activity', None) or
            not isinstance(e[3]['activity'], TriccActivity) or
            e[3]['activity'].scv() in processed_nodes
            
        )
        for e in list(G.in_edges(node.scv(), keys=True, data=True))]
    alarm = [ e[0] in processed_nodes and 
        isinstance(G.nodes[e[0]]['data'], TriccActivity) and e[3].get('activity', None) != G.nodes[e[0]]['data'] and
        e[3].get('activity', None) not in processed_nodes
        for e in list(G.in_edges(node.scv(), keys=True, data=True))
    ]

    calculate_references_processed = (
            [any(p.startswith(f"{r.value}") for p in processed_nodes) for r in references]
                if references
                else [True])
    return all([
        *previous_node_processed,
        *calculate_references_processed
    ])

def add_dangling_node(G, node, processed_nodes, stashed_nodes):
    # Check if reference that hasn't been processed has in_nodes, if 
    # it doesn't, stash it 
    # ies = G.in_edges(node, keys=True, data=True)
    # for n in [e[0] for e in ies if e[3]['flow_type'] == "ASSOCIATION"]:
    #     stashed_nodes.insert_at_bottom(G.nodes[n]['data'])
    
    if hasattr(node, 'expression') and node.expression:
        references = node.expression.get_references()
        
        for r in references:
            scv = r.scv()
            system = get_system_from_scv(scv)
            code = get_code_from_scv(scv)
            if not G.in_edges(r.value, keys=True, data=True):
                element = get_elements(G, system, code)
                scv = element.scv()
                if scv not in processed_nodes and scv not in stashed_nodes:
                    logger.debug("add_dangling_node::{}: stashed({})".format(node.get_name(), len(stashed_nodes)))
                    stashed_nodes.insert_at_bottom(scv)


def walktrhough_tricc_node_processed_stached(G, scv, callback, processed_nodes, stashed_nodes, strategy,
                                             warn=False, node_path=[], **kwargs):
    logger.debug(f"walkthrough({len(stashed_nodes)}|{len(processed_nodes)})::{callback.__name__}::{scv}")
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
        for s in list(G.successors(scv)):
            if s not in processed_nodes and s not in stashed_nodes:
                logger.debug("{}::{}: successor stashed({})".format(callback.__name__, node.get_name(), len(stashed_nodes)))
                stashed_nodes.insert_at_bottom(s)
        # for el in list(G.successors(scv)):
        #    stashed_nodes.add(el)
    else:
        #add_dangling_node(G, node, processed_nodes, stashed_nodes)
        if scv not in processed_nodes and scv not in stashed_nodes:
            stashed_nodes.insert_at_bottom(node.scv())
            logger.debug("{}::{}: stashed({})".format(callback.__name__, node.get_name(), len(stashed_nodes)))

def walktrhough_tricc_processed_stached(G, start, callback, processed_nodes, stashed_nodes, strategy,
                                        warn=False, node_path=[], **kwargs):
    
    walktrhough_tricc_node_processed_stached(G, start, callback, processed_nodes, stashed_nodes, strategy,
                                             warn=False, node_path=node_path, **kwargs)
    next_node = None
    prev_node = None
    while stashed_nodes:
        next_node = stashed_nodes.pop()
        if prev_node == next_node:
            logger.error("LOOOOOOOOOOOOOOOOOOOOOP")
        walktrhough_tricc_node_processed_stached(G, next_node, callback, processed_nodes, stashed_nodes, strategy,
                            warn=False, node_path=node_path, **kwargs)
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
        
    for edge in graph.out_edges(keys=True, data=True):
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



def import_mc_flow_from_activities(project, start, order):
    qs_processed = {}
    # looping on all activity
    for node_id, attr in project.impl_graph.nodes(data=True):
        node = attr['data']
        if isinstance(node, TriccActivity) and node.attributes['expended']==False:
            qs_processed = attempt_import_mc_flow_from_activity(
                node,
                project,
                start,
                qs_processed,
                order
            )
    # get the QS that have new instance to extend (QS with [] as value are filtered out)
    filtered_qs = dict((k, v) for k, v in qs_processed.items() if v)
    # process QS as long as there is unprocessed qs
    while len(filtered_qs) > 0:
        for qs_code, instances in filtered_qs.items():
            instances_copy = instances.copy()
            for instance in instances_copy:
                # we remove the instance to be processed from the list
                qs_processed[qs_code].remove(instance)
                # we tried again, if it fail it will be added again on qs_processed
                qs_processed = attempt_import_mc_flow_from_activity(
                    instance,
                    project, start,
                    qs_processed,
                    order,
                    qs_impl=instances
                )
        filtered_qs = dict((k, v) for k, v in qs_processed.items() if v)


def attempt_import_mc_flow_from_activity(node, project, start, qs_processed, order, qs_impl=None):

    unprocessed = import_mc_flow_from_activity(
        node, project, start, qs_processed, qs_impl
    )
    # adding empty list to know that this node was processed once 
    # and may need to be reprocessed if another instance if found later
    if node.code not in qs_processed:
        qs_processed[node.code] = []
    if unprocessed:
        qs_processed = merge_dict_lists(unprocessed, qs_processed)
    else:
        # adding the activity graph may have created loops
        new_activities = unloop_from_node(project.impl_graph, start, order)
        # new activity from unlooping are not extended so we will need to do that later
        if new_activities:
            qs_processed = merge_dict_lists(qs_processed, new_activities)
    return qs_processed
            

def import_mc_flow_from_activity(node, project, start, qs_processed, qs_impl=[]):
    # getting node defintion
    
    # for each unextended instance of the question sequence,
    # we extend it by adding the contained node and the ActuvityEnd
    unprocessed = {}
    # don't load the QS if the start node is isolated/dangling
    # because when creatin the implementation graph every QS 
    # got at least one instance, it makes no sense to extend it now 
    # and could messup the unlooping
    unprocessed_from_expend = expend_impl_activity(
        node,
        project,
        start,
        qs_processed
    )
    if unprocessed_from_expend:
        unprocessed = merge_dict_lists(
            unprocessed,
            unprocessed_from_expend
        )
    return unprocessed


def expend_impl_activity(
    node, project, start, qs_processed
):
    new_activity_instances = {}
    if "expended" in node.attributes and node.attributes["expended"]:
        return {}
    activity_label = node.label + (("::" + str(node.instance)) if node.instance else '')
    logger.info(f"loading Activity {activity_label}")
    node_def = node.instantiate
    output_def = node_def.attributes.get('output', None) 
    # avoid expending an activity not connected to main start
    try:
        # will raise an exception if no path found
        paths = list(
            nx.node_disjoint_paths(project.impl_graph, start.scv(), node.scv())
        )
    # if QS start not attached to start, SHOULD NOT be use
    except NetworkXNoPath:
        return {node.code: [node]}
    except Exception as e:
        logger.error(f"unexpected error {e}")
        exit(-1)
    # add node to graph (if any new)
    node.attributes["expended"] = True
    i_nodes = [
        (node.scv(), {"data": node},)
    ]
    output = node.attributes.get('output', None)
    if output:
        i_nodes.append((output.scv(), {"data": output},))
    qs_nodes = [a['data'] for (n, a) in node_def.graph.nodes(data=True)]
    qs_nodes.remove(node_def)
    if output_def:
        qs_nodes.remove(output_def)
    # getting the list of the nodes instance that need to be used inside the QS
    i_nodes += [
        get_most_probable_instance(
            project.impl_graph,
            paths,
            n.system,
            n.code,
            n.version,
            force_new=(node.instance > 1)
        )
        for n in qs_nodes
    ]
    node.graph.add_nodes_from(i_nodes)
    edges_def = list(node_def.graph.out_edges(keys=True, data=True))
    for e in edges_def:
        u = node_def.graph.nodes[e[0]]['data']
        imp_u = get_element(project.impl_graph, u.system, u.code, u.version, white_list=i_nodes)
        if(
            isinstance(imp_u, TriccActivity) and
            imp_u != node
        ):
            if imp_u.attributes.get('expended', False):
                u_output = imp_u.attributes.get('output', None)
                if u_output:
                    if u_output.scv() not in node.graph:
                        node.graph.add_node(u_output.scv(), data=u_output)
                    imp_u = u_output
            else:
                if imp_u.code not in new_activity_instances:
                    new_activity_instances[str(imp_u.code)] = []
                new_activity_instances[str(imp_u.code)].append(imp_u)
        
        v = node_def.graph.nodes[e[1]]['data']
        imp_v = get_element(project.impl_graph, v.system, v.code, v.version, white_list=i_nodes)
        
        data = {}
        for key, value in e[3].items():
            data[key] = value if key != 'activity' else node
        node.graph.add_edge(imp_u.scv(), imp_v.scv(), **data)
    
    # add calculate
    # rebase node following the QS after the result (before adding the internal QS nod
    project.impl_graph = nx.compose(project.impl_graph, node.graph)
    if output:
        rebase_edges(project.impl_graph, node, output)
    return new_activity_instances


def get_most_probable_instance(
    graph, paths, system, code, version=None, start=None, force_new=False
):
    nodes = get_elements(graph, system, code)
    score = {}
    if not force_new:
        # look if the exisitng instance of the inner node are already 
        # in a path leading to the QS start, 
        # if it the case it would for sure lead to a loop

        for n in nodes:
            score[n] = len(graph.out_edges(n.scv()))
            if any(n.scv() in path for path in paths):
                score[n] = 1000
            if start:
                try:
                    # if path found it will lead to a loop
                    sub_paths = list(
                        nx.node_disjoint_paths(graph, n.scv(), start.scv())
                    )
                    score[n] = 500
                except:
                    pass
        best = min(nodes, key=lambda n: score[n])
                
        if score[best] < 1000:
            return (best.scv(), {"data": best})
    # no instance found that won't lead to a loop
    # then create a new one
    if nodes:
        new = nodes[0].make_instance(sibling=True)
        return (new.scv(), {"data": new})
    else:
        logger.error(f"node not found {to_scv_str(system, code, version)}")


def make_implementation(project):
    for node_hash, attr in project.graph.nodes(data=True):
        node = attr["data"]
        # Create a new custom node with the same attributes
        impl_node = node.make_instance()
        # Add custom node to the new graph with the same node id
        project.impl_graph.add_node(impl_node.scv(), data=impl_node)

    for process, start_nodes in project.graph_process_start.items():
        for start_node in start_nodes:
            if process not in project.impl_graph_process_start:
                project.impl_graph_process_start[process] = []
            project.impl_graph_process_start[process].append(start_node.instances[0])

    for u, v, data in project.graph.out_edges(data=True):
        if (
            project.graph.nodes[u]["data"].code == NODE_ID
            or project.graph.nodes[v]["data"].code == NODE_ID
        ):
            pass
        u_impl = project.graph.nodes[u]["data"].instances[0]
        v_impl = project.graph.nodes[v]["data"].instances[0]
        project.impl_graph.add_edge(u_impl.scv(), v_impl.scv(), **data)


# Unlooping function
# unlooping my only work if the loop are compose of edges with different context (case 1)
# in case the loop is within a context then it might be harder to unloop them (case 2)
# case 1: look for an edge that lead to a node that don't have an edge from the same context
# going back to the loop

def merge_dict_lists(dict1, dict2):
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result:
            result[key] = result[key] + value
        else:
            result[key] = value
    return result


def get_code_from_scv(scvi):
    sc = scvi.split("|")
    if len(sc) > 1:
        return sc[1].split("::")[0]

def get_system_from_scv(scvi):
    sc = scvi.split("|")
    if len(sc) > 1:
        return sc[0]
    
def get_instance_from_scv(scvi):
    sc = scvi.split("::")
    if len(sc) > 1:
        return sc[1]
    
def get_version_from_scv(scvi):
    sc = scvi.split("|")
    if len(sc) > 2:
        return sc[2].split("::")[0]    
    
#unloop scores
UNLOOP_SCORE_CALCULATE = 1007
UNLOOP_SCORE_ASSOCIATION = 1003
UNLOOP_SCORE_ISOLATION = 1001
UNLOOP_SCORE_EXPENDED_ACTIVITY = 477
UNLOOP_SCORE_ACTIVITY = 493
UNLOOP_SCORE_INSTANCE_0 = 3
UNLOOP_SCORE_INSTANCE_1P = 0
UNLOOP_SCORE_EDGE_MULTIPLE_ACTIVITY = 11
UNLOOP_SCORE_SUB_EDGE = 91
UNLOOP_SCORE_TO_OTHER_NODE_OTHER_ACTIVITY = 7
UNLOOP_SCORE_TO_OTHER_NODE_SAME_ACTIVITY = 1
UNLOOP_SCORE_FROM_SAME_ACTIVITY = 5
UNLOOP_SCORE_REVERSE_ORDER = 3
UNLOOP_SCORE_NOT_IN_ORDER = 0

def unloop_from_node(graph, start, order):
    no_cycle_found = True
    new_activity_instances = {}
    while no_cycle_found:
        try:
            loop = list(nx.find_cycle(graph, start.scv()))
            old_edge = []
            scores = {}
            # looking for edge that once replace with a new node will open the loop
            # meaning that the context of the node is not going back to the loop
            # lower the score will be more likely will be the unlooping
            for e in loop:
                e_data = graph.get_edge_data(e[0], e[1])
                out_edge = list(graph.out_edges(e[0], keys=True, data=True))
                in_edge = list(graph.in_edges(e[1], keys=True, data=True))
                # avoid moving instance > 1 of e[1] for e TODO
                scores[e[0]] = UNLOOP_SCORE_INSTANCE_1P if graph.nodes[e[1]]["data"].instance > 1 else UNLOOP_SCORE_INSTANCE_0
                # activity end cannot be duplicated
                to_node = graph.nodes[e[1]]["data"]
                edges_activities = set(d["activity"] for k, d in e_data.items())
                if len(edges_activities) > 1:
                    scores[e[0]] += UNLOOP_SCORE_EDGE_MULTIPLE_ACTIVITY
                if to_node.type_scv.system == "tricc_type" and to_node.type_scv.code == 'output':
                    scores[e[0]] += UNLOOP_SCORE_CALCULATE
                if isinstance(to_node, TriccActivity):
                    if to_node.attributes.get('expended', False):
                        scores[e[0]] += UNLOOP_SCORE_EXPENDED_ACTIVITY
                    else:
                        scores[e[0]] += UNLOOP_SCORE_ACTIVITY
                if all([d["flow_type"] != "SEQUENCE" for k, d in e_data.items()]):
                    scores[e[0]] += UNLOOP_SCORE_ASSOCIATION
                for oe in out_edge:
                    # avoid duplicating edge that is duplicated with
                    # an edge from an activity involved in the loop
                    if e[1] != oe[1] and nx.has_path(graph, oe[1], e[1]):
                        scores[e[0]] += UNLOOP_SCORE_SUB_EDGE
                    elif oe[1] != e[1]:
                        if oe[3]['activity'] in edges_activities:
                            scores[e[0]] += UNLOOP_SCORE_TO_OTHER_NODE_SAME_ACTIVITY
                        else:
                            scores[e[0]] += UNLOOP_SCORE_TO_OTHER_NODE_OTHER_ACTIVITY
                # add a score for edge going to the to edge from the same activity but different node
                for ie in in_edge:
                    if (
                        ie[0] != start.scv()
                        and ie[0] != e[0]
                        and ie[3]["flow_type"] == "SEQUENCE"
                        and (ie[3]["activity"] in edges_activities)
                    ):
                        scores[e[0]] += UNLOOP_SCORE_FROM_SAME_ACTIVITY
                    # avoid dandling
                # check if cutting the node will make it dandling
                if nx.has_path(graph, start, e[0]):
                    buffer = []
                    for ie in in_edge:
                        if ie[:2] == e[:2]:
                            buffer.append(ie)
                            graph.remove_edge(*ie[:3])
                    if not nx.has_path(graph, start, e[1]):
                        scores[e[0]] += UNLOOP_SCORE_ISOLATION
                    for be in buffer:
                        graph.add_edge(*be[:2], **be[3])
                else:
                    pass
                # add 1 to the score if the edge goes according to fullorder
                id1 = get_code_from_scv(e[0])
                id2 = get_code_from_scv(e[1])
                # if id2 is a QS, avoid unlooping
                if order:
                    if id2 not in order:
                        scores[e[0]] += UNLOOP_SCORE_NOT_IN_ORDER
                    elif id1 in order and order.index(id2) < order.index(id1):
                        scores[e[0]] += UNLOOP_SCORE_REVERSE_ORDER
                    if not old_edge or scores[old_edge[0]] >= scores[e[0]]:
                        old_edge = e
            if min(scores.values()) > 999:
                logger.warning(f"unloop with high min score {min(scores.values())} for {old_edge}, {max(scores.values())}")
            # find the edge data, it includes activity
            # create another instance of the target node
            old_node = graph.nodes[old_edge[1]]["data"]
            new_node = old_node.make_instance(sibling=True)
            if isinstance(old_node, TriccActivity):
                if old_node.code not in new_activity_instances:
                    new_activity_instances[str(old_node.code)] = []
                new_activity_instances[str(old_node.code)].append(new_node)

            graph.add_node(new_node.scv(), data=new_node)
            # replace all edges between those node with the same from / to
            out_edge = list(graph.out_edges(old_edge[0], keys=True, data=True))
            activities = set()
            for se in out_edge:
                if se[1] == old_edge[1]:
                    graph.remove_edge(*se[:3])
                    # save the activity even None
                    activities.add(se[3].get('activity', None))
                    # create new edge
                    graph.add_edge(se[0], new_node.scv(), **se[3])
            out_edge = []
            # we will move the edge from the same activity from the old to the new node
            if ( 
                isinstance(old_node, TriccActivity) and
                old_node.attributes.get('expended', False)
            ):
                old_output = old_node.attributes.get('output', None)
                if old_output:
                    out_edge = list(graph.out_edges(old_output.scv(), keys=True, data=True))
            if not out_edge:
                out_edge = list(graph.out_edges(old_edge[1], keys=True, data=True))
            for se in out_edge:
                if se[3].get('activity', None) in activities:
                    graph.remove_edge(*se[:3])
                    # create new edge
                    graph.add_edge(new_node.scv(), se[1], **se[3])
                   
        except NetworkXNoCycle:
            no_cycle_found = False
    return new_activity_instances


def rebase_edges(graph, old_node, new_node):
    # get all edges from old node
    node_edges = [e for e in graph.out_edges(old_node.scv(), keys=True, data=True) if e[3].get('activity', None ) != old_node]
    # assign each one to the new node
    for e in node_edges:
        graph.remove_edge(*e[:3])
        data = e[3].copy()
        # update condition
        if "condition" in data and data["condition"]:
            ref = f'"{old_node.instantiate.scv() if old_node.instantiate else old_node.scv()}"'
            if ref in data["condition"]:
                data["condition"] = data["condition"].replace(
                    ref,
                    f'"{new_node.instantiate.scv() if new_node.instantiate else new_node.scv()}"',
                )
        graph.add_edge(new_node.scv(), e[1], **data)

