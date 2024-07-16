import logging
import networkx as nx
import re
from networkx.exception import NetworkXNoCycle, NetworkXNoPath, NetworkXError

logger = logging.getLogger("default")

from tricc_og.builders.utils import remove_html, clean_str, generate_id
from tricc_og.models.base import (
    TriccMixinRef,
    TriccTask,
    TriccActivity,
    TriccContext,
    FlowType,
    TriccBaseModel,
)
from tricc_og.models.tricc import TriccNodeType
from tricc_og.visitors.tricc_project import (
    get_element,
    get_elements,
    add_flow,
)

QUESTION_SYSTEM = "questions"
DIAGNOSE_SYSTEM = "diagnose"
QUESTIONS_SEQUENCE_SYSTEM = "questionssequence"
STAGE_SYSTEM = "step"
MANDATORY_STAGE = [
    'registration_step',
    'patient_data',
    'first_look_assessment_step',
    'complaint_category'
]

NODE_ID = "7719"


def import_mc_nodes(json_node, system, project, js_fullorder, start):
    if json_node["type"] == "QuestionsSequence":
        node = to_activity(json_node, system, project)
    else:
        tricc_type = get_mc_tricc_type(json_node)
        node = to_node(
            json_node=json_node,
            tricc_type=tricc_type,
            system=system,
            project=project,
            js_fullorder=js_fullorder
        )
    return node


def import_mc_flow_from_diagram(js_diagram, system, graph, start):
    context = TriccContext(
        label='basic questions',
        code='main',
        system=system
    )
    dandling = add_flow_from_instances(graph, js_diagram['instances'].values(), context)
    
    for n in dandling:
        add_flow(
            graph,
            context,
            start.__resp__(),
            n.__resp__()
        )

def import_mc_flow_from_diagnose(json_node, system, graph, start):

    diag = TriccContext(
        code=get_mc_name(json_node["id"]),
        system=system,
        label=json_node["label"][list(json_node["label"].keys())[0]],
        type_scv=TriccMixinRef(system="tricc_type", code=str(TriccNodeType.context)),
    )
    set_additional_attributes(
        diag, json_node, ["complaint_category", "id", "cut_off_start", "cut_off_end"]
    )
    cc = get_element(
        graph, 
        QUESTION_SYSTEM,
        str(json_node["complaint_category"])
    )
    dandling = add_flow_from_instances(graph, json_node["instances"].values(), diag)
    
    for n in dandling:
        if cc:
            add_flow(
                graph,
                diag,
                cc.__resp__(),
                n.__resp__()
            )
        else:
            logger.error("not in mandatory stage neither conditioned by CC")


def add_flow_from_instances(graph, instances, context, white_list=None):
    dandling = set()
    for instance in instances:
        if str(instance['id']) == NODE_ID:
            pass
        _to = get_element(
            graph,
            QUESTION_SYSTEM,
            instance["id"],
            white_list=white_list
        )
        
        if no_forced_link(graph, _to):
            if instance["conditions"]:
                add_flow_from_condition(
                    graph,
                    instance["conditions"],
                    _to,
                    context,
                    white_list=white_list
                )
            # add edge if no other edges
            else:
                dandling.add(_to)
    return dandling


def no_forced_link(graph, node):
    return not any(
        [
            "triage" in e[0] and ('conditions' not in e[2] or not e[2]['conditions']) for e in graph.in_edges(node.__resp__(), data=True)
        ]
    )


def add_flow_from_condition(graph, conditions, _to, context, white_list=None, flow_type = "SEQUENCE"):
    for cond in conditions:
        _from = get_element(
            graph,
            QUESTION_SYSTEM,
            cond["node_id"],
            white_list=white_list
        )
        condition = None
        if not _from or  "answer_id" not in cond:
            logger.error(f"node {cond['node_id']} not found")
        elif "answer_id"  in cond:
            condition = (
                f""""{_from.get_name()}" = '{cond['answer_id']}'"""
            )
        add_flow(
            graph,
            context,
            _from,
            _to,
            label=None,
            condition=condition,
            flow_type=flow_type
        )




def import_mc_flow_from_qss(js_nodes, project, start, order):
    qs_processed = {}
    for node_id in js_nodes:
        if js_nodes[node_id]["type"] == "QuestionsSequence":
            import_mc_flow_from_qs(
                js_nodes[node_id], project, start, qs_processed
            )
            qs_processed[str(node_id)] = []
            unloop_from_node(project.impl_graph, start, order)

    filtered_qs = dict((k, v) for k, v in qs_processed.items() if v)
    for qs_code, instances in filtered_qs.items():
        import_mc_flow_from_qs(
                js_nodes[qs_code], 
                project, 
                start, 
                qs_processed,
                qs_impl=instances
            )
  


def import_mc_flow_from_qs(json_node, project, start, qs_processed, qs_impl=[]):
    if str(json_node['id']) == NODE_ID:
        pass
    if not list(project.graph.in_edges(f'{QUESTION_SYSTEM}|{str(json_node["id"])}')):
        return
        logger.info(f"Skipping isolated QS {json_node['label']}")
    
    logger.info(f"loading QS {json_node['label']}")
    # 1- generate output
    # 2- generate graph
    # 3- look for implementation
    # 4- if instance 1, then add graph and result.
    #        then take the link over out link from the QS
    # 5- else:
    #       create new instance of all nodes in the QS
    #       add all links
    if json_node["value_format"] != "Boolean":
        logger.error(f"value_format {json_node['value_format']} is not supported")
        exit(-1)

    if not qs_impl:
        qs_impl = get_elements(project.impl_graph, QUESTION_SYSTEM, json_node["id"])

    qs_nodes = [
        get_element(project.graph, QUESTION_SYSTEM, i["id"])
        for i in json_node["instances"].values()
    ]

    main_result = TriccBaseModel(
        code=get_mc_name(json_node["id"]),
        system=QUESTIONS_SEQUENCE_SYSTEM,
        label=json_node["label"][list(json_node["label"].keys())[0]],
        type_scv=TriccMixinRef(system="tricc_type", code="calculate"),
    )

    project.graph.add_node(main_result.__resp__(), data=main_result)
    
    for i in qs_impl:
        process_qs(i, json_node,  main_result, qs_nodes, project,  start, qs_processed)


def process_qs(qs_start, json_node,  main_result, qs_nodes, project,  start, qs_processed):
    # context to be used by the flow
    # qs_start.attributes['processed'] = True
    qs_context = TriccContext(
            code=get_mc_name(json_node["id"]),
            system='qs',
            label=json_node["label"][list(json_node["label"].keys())[0]],
            type_scv=TriccMixinRef(
                system="tricc_type", code=str(TriccNodeType.context)
            ),
            instance=qs_start.instance,
        )
    result = main_result.make_instance()
    i_nodes = [(result.__resp__(), {'data': result})]
    # if i.instance > 1:
    #     i_nodes = [n.make_instance() for n in qs_nodes]
    # else:
    try:
        # will raise an exception if no path found
        paths = list(nx.node_disjoint_paths(
                project.impl_graph, start.__resp__(), qs_start.__resp__()
            ))
        i_nodes += [
            get_most_probable_instance(
                project.impl_graph, 
                paths, 
                QUESTION_SYSTEM, 
                n.code, 
                n.version
            )
            for n in qs_nodes
        ]
        
    except NetworkXNoPath:
        i_nodes = []
        for n in qs_nodes:
            node = get_most_probable_instance(
                project.impl_graph,
                [],
                n.system,
                n.code,
                version=n.version,
                force_new=True
            )
            i_nodes.append(node)
            # in case the QS instance were already processed, save it for later
            if n.code in qs_processed:
                qs_processed[str(n .code)].append(n)
                
    except Exception as e:
        logger.error(f"unexpected error {e}")
    # add node to graph (if any new)
    project.impl_graph.add_nodes_from(i_nodes)
    # rebase node following the QS after the result (before adding the internal QS node)
    rebase_edges(project.impl_graph, qs_start, result)
    # add the flow using the i_nodes
    dandling = add_flow_from_instances(
        project.impl_graph,
        json_node["instances"].values(),
        qs_context,
        white_list=i_nodes
    )
    
    for n in dandling:
        if NODE_ID in n.__resp__():
            pass
        add_flow(
            project.impl_graph,
            qs_context,
            qs_start.__resp__(),
            n.__resp__()
        )
        

    # add calculate
    project.impl_graph.add_node(result.__resp__(), data=result)
    i_nodes.append((result.__resp__(), {'data': result}))
    # add calculate flow
    add_flow_from_condition(
        project.impl_graph,
        json_node["conditions"],
        result.__resp__(),
        qs_context,
        white_list=i_nodes, 
        flow_type='ASSOCIATION'
    )
  
    

def get_most_probable_instance(graph, paths, system, code, version=None, force_new=False):
    nodes = get_elements(graph, system, code)
    if not force_new:
        for n in nodes:
            if not any(n.__resp__() in path for path in paths):
                return (n.__resp__(), {"data": n})
    if nodes:
        new = nodes[0].make_instance(sibling=True)
        return (new.__resp__(), {"data": new})
    else:
        logger.error(f"node not found {system}.{code}|{version or '' }")


def get_start_node(project):
    start = TriccBaseModel(
        code="triage",
        system="cpg-common-processes",
        label="Start",
        type_scv=TriccMixinRef(system="tricc_type", code=str(TriccNodeType.start)),
    )
    project.graph.add_node(start.__resp__(), data=start)
    return start


def to_activity(json_node, system, project):
    node = TriccBaseModel(
        code=get_mc_name(json_node["id"]),
        system=system,
        label=json_node["label"][list(json_node["label"].keys())[0]],
        type_scv=TriccMixinRef(system="tricc_type", code=str(TriccNodeType.activity)),
    )
    project.graph.add_node(node.__resp__(), data=node)


def get_mc_tricc_type(json_node):
    tricc_type = json_node.get("type", None)
    if tricc_type == "Question":
        if json_node["value_format"] == "Integer":
            tricc_type = TriccNodeType.integer
        elif json_node["value_format"] == "String":
            tricc_type = TriccNodeType.text
        elif json_node["value_format"] == "Date":
            tricc_type = TriccNodeType.date
        elif json_node["value_format"] == "Float":
            tricc_type = TriccNodeType.decimal
        elif "formula" in json_node and (
            "anwers" not in json_node or not json_node["anwers"]
        ):
            tricc_type = TriccNodeType.calculate
        else:
            tricc_type = TriccNodeType.select_one
    return tricc_type


def to_node(json_node, tricc_type, system, project, js_fullorder):
    node = TriccBaseModel(
        code=get_mc_name(json_node["id"]),
        system=system,
        label=json_node["label"][list(json_node["label"].keys())[0]],
        type_scv=TriccMixinRef(system="tricc_type", code=str(tricc_type)),
    )
    set_additional_attributes(
        node,
        json_node,
        ["is_mandatory", "type", "id", "description", "cut_off_start", "cut_off_end", 'formula'],
    )
    context_code = get_context_from_fullorder(json_node["id"], js_fullorder)
    if not context_code:
        if "category" in json_node and  json_node["category"]:
           context_code = json_node["category"]
       
    if context_code:   
        node.context = project.get_context(STAGE_SYSTEM, context_code)
        get_options(json_node, node, tricc_type, system, project)
        project.graph.add_node(node.__resp__(), data=node)
    return node


def get_options(json_node, select_node, tricc_type, system, project):
    if tricc_type == TriccNodeType.select_one:
        if "answers" in json_node and json_node["answers"]:
            i = 0
            for key, elm in json_node["answers"].items():
                option = TriccBaseModel(
                    code=get_mc_name(json_node["id"]),
                    system=select_node.get_name(),
                    type_scv=TriccMixinRef(
                        system="tricc_type", code=str(TriccNodeType.select_option)
                    ),
                    label=json_node["label"][list(json_node["label"].keys())[0]],
                )
                set_additional_attributes(
                    option,
                    json_node,
                    ["id", "type", "reference", "cut_off_start", "cut_off_end"],
                )
                select_node.attributes[f"output_options[{i}]"] = option
                i += 1
        else:
            raise ValueError(f"Select one {system}:{json_node['id']} must have answers")


def set_additional_attributes(node, json_node, attribute_names):
    if not isinstance(attribute_names, list):
        attribute_names = [attribute_names]
    for attributename in attribute_names:
        if attributename in json_node:
            if attributename == "is_mandatory":
                node.attributes["required"] = "1"
            if attributename == "description":
                node.attributes["help"] = json_node[attributename]
            elif json_node[attributename]:
                node.attributes[attributename] = json_node[attributename]


def make_implementation(project):
    for node_hash, attr in project.graph.nodes(data=True):
        node = attr["data"]
        # Create a new custom node with the same attributes
        impl_node = node.make_instance()
        # Add custom node to the new graph with the same node id
        project.impl_graph.add_node(impl_node.__resp__(), data=impl_node)

    for u, v, data in project.graph.edges(data=True):
        if project.graph.nodes[u]["data"].code == NODE_ID or  project.graph.nodes[v]["data"].code == NODE_ID :
            pass
        u_impl = project.graph.nodes[u]["data"].instances[0]
        v_impl = project.graph.nodes[v]["data"].instances[0]
        project.impl_graph.add_edge(u_impl.__resp__(), v_impl.__resp__(), **data)


# Unlooping function
# unlooping my only work if the loop are compose of edges with different context (case 1)
# in case the loop is within a context then it might be harder to unloop them (case 2)
# case 1: look for an edge that lead to a node that don't have an edge from the same context
# going back to the loop

def get_code_from_scv(scvi):
    sc = scvi.split('|')
    if len(sc) > 1:
        return sc[1].split('::')[0]


def unloop_from_node(graph, start, order):
    no_cycle_found = True
    while no_cycle_found:
        try:
            loop = list(nx.find_cycle(graph, start.__resp__()))
            activities = {}
            old_edge = []
            scores = {}
            # get edges data
            for k, e in enumerate(loop):
                loop[k] += (graph.get_edge_data(*e),)
                edge_activity = loop[k][3]["activity"].__resp__()
                if edge_activity not in activities:
                    activities[edge_activity] = 1
                else:
                    activities[edge_activity] += 1
                
            # looking for edge that once replace with a new node will open the loop
            # meaning that the context of the node is not going back to the loop
            # lower the score will be more likely will be the unlooping
            for e in loop:
                if NODE_ID in e[1] or NODE_ID in e[0]:
                    pass
                out_edge = list(graph.edges(e[0], keys=True, data=True))
                in_edge = list(graph.in_edges(e[1], keys=True, data=True))
                # avoid moving instance > 1 of e[1] for e TODO
                scores[e[0]] = 3 if graph.nodes[e[1]]['data'].instance > 1 else 0
                if e[3]["flow_type"] != 'SEQUENCE':
                    scores[e[0]] += 99
                for oe in out_edge:
                    # avoid duplicating edge that is duplicated with 
                    # an edge from an activity involved in the loop
                    if oe[3]["activity"] != e[3]["activity"]:
                        if e[1] == oe[1]:
                            scores[e[0]] += 2
                        elif nx.has_path(graph, oe[1], e[1]):
                            scores[e[0]] += 10
                            # scores[e[0]] += len(list(all_simple_paths(
                            #         graph,
                            #         oe[1],
                            #         e[1],
                            #         cutoff=5,
                            #         max_len=3)))
                    elif oe[1] != e[1]:
                        scores[e[0]] += 1
                # add a score for edge going to the to edge from the same activity but different node
                for ie in in_edge:
                    if (
                        ie[0] != start.__resp__() and ie[0] != e[0] and
                        ie[3]["flow_type"] == 'SEQUENCE' and (
                            ie[3]["activity"] == e[3]["activity"]
                            
                        )
                    ):
                        scores[e[0]] += 1
                    # avoid dandling
                # check if cutting the node will make it dandling
                if nx.has_path(graph, start, e[0]):
                    buffer = []
                    for ie in in_edge:
                        if ie[:2] == e[:2]:
                            buffer.append(ie)
                            graph.remove_edge(*ie[:2])
                    if not nx.has_path(graph, start, e[1]):
                        scores[e[0]] += 10
                    for be in buffer:
                        graph.add_edge(*be[:2], **be[3])
                else:
                    pass
                # add 1 to the score if the edge goes according to fullorder
                id1 = get_code_from_scv(e[0])
                id2 = get_code_from_scv(e[1])
                # if id2 is a QS, avoid unlooping 
                if id2 not in order:
                    scores[e[0]] += 4
                elif id1 in order and order.index(id2) < order.index(id1):
                    scores[e[0]] += 2     
                if not old_edge or scores[old_edge[0]] >= scores[e[0]]:
                    old_edge = e
                
            # find the edge data, it includes activity
            # create another instance of the target node
            new_node = graph.nodes[old_edge[1]]["data"].make_instance(sibling=True)
            graph.add_node(new_node.__resp__(), data=new_node)
            # replace all edges between those node with the same context (used for select multiple)
            out_edge = list(graph.edges(old_edge[0], keys=True, data=True))
            for se in out_edge:
                if se[1] == old_edge[1]:
                    graph.remove_edge(*se[:3])
                    # create new edge
                    graph.add_edge(se[0], new_node.__resp__(), **se[3])
            # find edge form node with the same activity, using a list to fix its size2
            #edges_to_assess = list(graph.edges(old_edge[1], keys=True, data=True))
            #for e in edges_to_assess:
            #    if old_edge[3]["activity"] == e[3]["activity"]:
            #        # remove the edge, the data e[3] must not be part of the call
            #        graph.remove_edge(*e[:3])
            #        graph.add_edge(new_node.__resp__(), e[1], **e[3])
            #        logger.debug(
            #            f"source of edge from {old_edge} to {e[1]} replaced by {new_node}"
            #        )
        except NetworkXNoCycle:
            no_cycle_found = False


def rebase_edges(graph, old_node, new_node, black_list=[]):
    # get all edges from old node
    node_edges = list(graph.edges(old_node.__resp__(), keys=True, data=True))
    # assign each one to the new node
    for e in node_edges:
        if e[1] not in black_list:
            graph.remove_edge(*e[:3])
            data = e[3]
            # update condition
            if 'condition' in data:
                ref = F'"{old_node.instantiate.__resp__() if old_node.instantiate else old_node.__resp__()}"' 
                if ref in data['condition']:
                    data['condition'] = data['condition'].replace(
                        ref, 
                        F'"{new_node.instantiate.__resp__() if new_node.instantiate else new_node.__resp__()}"'
                    )
                
            graph.add_edge(new_node.__resp__(), e[1], **data)

def get_mc_name(name):
    return f"{name}"


def get_context_from_fullorder(js_id, js_fullorder):
    return walkthrough_fullorder(
        js_fullorder, 
        lambda data, context, value: context if str(data) == str(value) else None, 
        value=js_id)
    

def add_formula_association_flow(project):
    dob = get_element(project.graph, QUESTION_SYSTEM, 'birth_date') 
    # add flow to edges nodes
    for node_ref, attr in project.graph.nodes(data=True):
        if 'formula' in attr['data'].attributes:
            if (
                attr['data'].attributes['formula']
                    in ('ToMonth', 'ToDay', 'ToYear')
            ):
                add_flow(
                    project.graph,
                    None,
                    dob,
                    node_ref,
                    flow_type='ASSOCIATION'
                )
            else:
                matches = re.findall(r"([0-9a-zA-Z_]+),?", attr['data'].attributes['formula'])
                for m in matches:
                    n = get_element(project.graph, QUESTION_SYSTEM, m)
                    add_flow(
                        project.graph,
                        None,
                        n,
                        node_ref,
                        flow_type='ASSOCIATION'
                    )



def get_registration_nodes():
    js_nodes = {}
    js_nodes["first_name"] = {
        "id": "first_name",
        "label": {"en": "First Name", "fr": "Prénom"},
        "type": "Question",
        "category": "patient_data",
        "value_format": "String",
    }
    js_nodes["last_name"] = {
        "id": "last_name",
        "label": {"en": "Last Name", "fr": "Nom de famille"},
        "type": "Question",
        "category": "patient_data",
        "value_format": "String",
    }
    js_nodes["birth_date"] = {
        "id": "birth_date",
        "label": {"en": "Date of birth", "fr": "Date de naissance"},
        "type": "Question",
        "category": "patient_data",
        "value_format": "Date",
    }
    return js_nodes

def  all_simple_paths(graph, start, end, cutoff=5, max_len=5):
    # return nx.all_simple_paths(graph,start,end,cutoff=5)
    paths = []
    current_path = ()
    get_simple_paths(graph, start, end, paths, current_path, cutoff, max_len)
    return paths


def get_simple_paths(graph, start, end, paths, current_path, cutoff, max_len=None):
    # get the egdes
    if max_len and len(paths) > max_len:
        return
    current_path = current_path + (start,)
    if any(e[1] == end for e in graph.edges(start)):
        current_path = current_path + (end,)
        paths.append(current_path)
    elif cutoff > 0:
        map(lambda n: get_simple_paths(graph, n, end, paths, current_path, cutoff-1), graph.edges(start))


def get_first_in_fullorder(js_fullorder, id1, id2):
    first = walkthrough_fullorder(
        js_fullorder,
        lambda data, context, list_value:
            str(data) if str(data) in list_value else None,
        list_value=[str(id1), str(id2)])
    return first == id1


def walkthrough_fullorder(js_fullorder, callback=None, **kwargs):
    # section name
    for context in js_fullorder:
        if isinstance(js_fullorder[context], dict):
            # for dict of id at level 1, each dict the titel as section and list of id as section value
            for sub in js_fullorder[context]:
                if isinstance(js_fullorder[context][sub], list):
                    for sub_sub in js_fullorder[context][sub]:
                        res = callback(sub_sub, context=f"{context}.{sub}" , **kwargs)
                        if res:
                            return res
                else:
                    logger.error("unexpected format")
        elif isinstance(js_fullorder[context], list):
            # for list of dict of id at level 1, each dict having title and data
            for sub in js_fullorder[context]:
                if isinstance(sub, dict):
                    if 'data' in sub:
                        for sub_sub in sub['data']:
                            res = callback(sub_sub, context=f"{context}.{sub['title']}" , **kwargs)
                            if res:
                                return res
                            
                    else:
                        logger.error("unexpected format")
                # for list of id at level 1
                elif isinstance(sub, (str, int)):
                    res = callback(sub, context=context,**kwargs)
                    if res:
                        return res
                        
        else:
            logger.error("unexpected format")


def fullorder_to_order(js_fullorder):
    order = []
    walkthrough_fullorder(
        js_fullorder,
        lambda data, context, order:
            order.append(str(data)),
        order=order)
    return order

