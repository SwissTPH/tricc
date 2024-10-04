import logging
import networkx as nx
import re
from networkx.exception import NetworkXNoCycle, NetworkXNoPath, NetworkXError
from tricc_og.models.operators import TriccOperator
from tricc_og.models.base import to_scv_str

logger = logging.getLogger("default")

from tricc_og.builders.utils import remove_html, clean_str, generate_id
from tricc_og.models.base import (
    TriccMixinRef,
    TriccTask,
    TriccActivity,
    TriccContext,
    FlowType,
    TriccBaseModel,
    TriccOperation,
    TriccStatic,
    TriccSCV,
)
from tricc_og.models.tricc import TriccNodeType
from tricc_og.visitors.tricc_project import (
    get_element,
    get_elements,
    add_flow,
)

QUESTION_SYSTEM = "questions"
DIAGNOSE_SYSTEM = "diagnose"
ACTIVITY_END_SYSTEM = "ActivityEnd"
STAGE_SYSTEM = "step"
MANDATORY_STAGE = [
    "registration_step",
    "patient_data",
    "first_look_assessment_step",
    "complaint_category",
]
# FIXME to be removed after dev OK
NODE_ID = "7331"


def import_mc_nodes(json_node, system, project, js_fullorder, start):
    if json_node["type"] == "QuestionsSequence":
        node = to_activity(json_node, system, project.graph)
        node.attributes['expended'] = False
    else:
        tricc_type = get_mc_tricc_type(json_node)
        node = to_node(
            json_node=json_node,
            tricc_type=tricc_type,
            system=system,
            project=project,
            graph=project.graph,
            js_fullorder=js_fullorder,
        )
        
    if json_node["category"] in (
        "background_calculation",
        "basic_demographic"
    ):
        add_background_calculation_options(json_node, node)

    return node


def import_mc_flow_from_diagram(js_diagram, system, graph, start):
    context = TriccContext(label="basic questions", code="main", system=system)
    dandling = add_flow_from_instances(graph, js_diagram["instances"].values(), context)

    for n in dandling:
        add_flow(graph, context, start.scv(), n.scv())


def import_mc_flow_from_diagnose(json_node, system, project, start):
    diag = to_activity(json_node, system, project.graph, generate_end=False)
    diag.attributes['expended'] = True
    # FIXME answer for the CC must be true reference == 1
    if json_node["complaint_category"]:
        cc = get_element(
            project.graph, QUESTION_SYSTEM, str(json_node["complaint_category"])
        )
        add_flow(project.graph, diag, cc.scv(), diag.scv())
    else:
        add_flow(project.graph, diag, start.scv(), diag.scv())
    node_list = get_node_list_from_instance(project.graph, json_node["instances"].values())
    dandling = add_flow_from_instances(
        diag.graph, json_node["instances"].values(), diag, white_list=node_list
    )

    for n in dandling:
        add_flow(diag.graph, diag, diag.scv(), n.scv())
    project.graph = nx.compose(project.graph, diag.graph)


def add_flow_from_instances(graph, instances, activity, white_list=None):
    dandling = set()
    for instance in instances:
        if str(instance["id"]) == NODE_ID:
            pass
        _to = get_element(graph, QUESTION_SYSTEM, instance["id"], white_list=white_list)
        _to_activity_end = None
        if isinstance(_to, TriccActivity) and _to == activity:
            _to_activity_end = get_element(graph, ACTIVITY_END_SYSTEM, instance["id"], white_list=white_list)

        _to = _to_activity_end if _to_activity_end else _to
        if no_forced_link(graph, _to):
            # if activity is a real activity then we add the edges on the activity level
            # else we add it on the main graph
            if instance["conditions"]:
                add_flow_from_condition(
                    graph, instance["conditions"], _to, activity, white_list=white_list
                )
            # add edge if no other edges
            else:
                dandling.add(_to)
    return dandling


def no_forced_link(graph, node):
    return not any(
        [
            "triage" in e[0] and ("conditions" not in e[2] or not e[2]["conditions"])
            for e in graph.in_edges(node.scv(), data=True)
        ]
    )


def get_node_list_from_instance(graph, instances, white_list=None):
    node_list = []
    for instance in instances:
        node = get_element(
            graph, QUESTION_SYSTEM, instance["id"], white_list=white_list
        )
        node_list.append((node.scv(), {"data": node}))
    return node_list


def add_flow_from_condition(
    graph, conditions, _to, activity, white_list=None, flow_type="SEQUENCE"
):
    for cond in conditions:
        _from = get_element(
            graph, QUESTION_SYSTEM, cond["node_id"], white_list=white_list
        )
        # if the node start fron the activity (start) but NOT inside the that activity
        _from_activity_end = None
        #if isinstance(_from, TriccActivity) and _from != activity:
        #    _from_activity_end = to_scv_str(ACTIVITY_END_SYSTEM, _from.code, _from.version, _from.instance)
        condition = None
        if not _from or "answer_id" not in cond:
            logger.error(f"node {cond['node_id']} not found")
        elif "answer_id" in cond:
            condition = TriccOperation(
                TriccOperator.EQUAL,
                ## Seems like with the else statement it has an infinite loop? why? FIXME
                [TriccSCV(_from.get_name()), TriccStatic(cond["answer_id"])] if not _from_activity_end else
                    [TriccSCV(_from_activity_end), TriccStatic(cond["answer_id"])]
            )
        add_flow(
            activity.graph if hasattr(activity, "graph") else graph,
            activity,
            _from_activity_end if _from_activity_end != None else _from, 
            _to,
            label=None,
            condition=condition,
            flow_type=flow_type,
        )


def import_qs_inner_flow(json_node, QUESTION_SYSTEM, project):
    qs_start = project.graph.nodes[
        to_scv_str(
            QUESTION_SYSTEM,
            json_node['id'],
        )
    ]["data"]
    if json_node["value_format"] != "Boolean":
        logger.error(f"value_format {json_node['value_format']} is not supported")
        exit(-1)
    # get node from main graph
    i_nodes = get_node_list_from_instance(project.graph, json_node["instances"].values()) 
    # add node to internal graph
    qs_start.graph.add_nodes_from(i_nodes)
    # create expression for output
    output = qs_start.attributes['output']
    output.expression = add_expression_from_condition(qs_start.graph, json_node['conditions'])
    # add flow to output
    add_flow_from_condition(
        qs_start.graph,
        json_node["conditions"],
        output.scv(),
        qs_start,
        flow_type="ASSOCIATION",
    )
    dangling = add_flow_from_instances(
        qs_start.graph,
        json_node["instances"].values(),
        qs_start,
    )
    # attached the node that no "in" edges inside the QS
    # we assume they are the first node inside the QS 
    for n in dangling:
        add_flow(qs_start.graph, qs_start, qs_start.scv(), n.scv())
    return qs_start


def import_mc_flow_from_activities(project, start, order):
    qs_processed = {}
    # looping on all activity
    for node_id, attr in project.impl_graph.nodes(data=True):
        node = attr['data']
        if isinstance(node, TriccActivity) and node.attributes['expended']==False:
            attempt_import_mc_flow_from_activity(
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
                attempt_import_mc_flow_from_activity(
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
        qs_processed[node.code] += unprocessed
    else:
        # adding the activity graph may have created loops
        new_activities = unloop_from_node(project.impl_graph, start, order)
        # new activity from unlooping are not extended so we will need to do that later
        for act_code, qs_start_list in new_activities.items():
            if act_code in qs_processed:
                qs_processed[node.code] += qs_start_list


def import_mc_flow_from_activity(node, project, start, qs_processed, qs_impl=[]):
    logger.info(f"loading Activity {node.label}")
    # getting node defintion
    qs_nodes = [a['data'] for (n, a) in node.instantiate.graph.nodes(data=True)]
    main_result = node.attributes['output']
    # for each unextended instance of the question sequence,
    # we extend it by adding the contained node and the ActuvityEnd
    unprocessed = []
    # don't load the QS if the start node is isolated/dangling
    # because when creatin the implementation graph every QS 
    # got at least one instance, it makes no sense to extend it now 
    # and could messup the unlooping
    if not list(project.impl_graph.in_edges(node.scv())):
        unprocessed.append(node)
    else:
        is_unprocessed = expend_impl_activity(
            node,
            main_result,
            qs_nodes,
            project,
            start,
            qs_processed
        )
        if is_unprocessed:
            unprocessed.append(node)
    return unprocessed


def add_expression_from_condition(graph, conditions):
    expression_or = TriccOperation(TriccOperator.OR)
    expression = None
    for condition in conditions:
        if (NODE_ID) == str(condition['node_id']):
            pass
        expression = TriccOperation(TriccOperator.EQUAL)
        ref = get_elements(
            graph, QUESTION_SYSTEM, condition['node_id']
        )[-1]
        val = str(ref.attributes[f'options_{condition["answer_id"]}'].reference)
        ref = TriccSCV(ref.scv())
        expression.append(ref)
        expression.append(val)
        if len(conditions) > 1:
            expression_or.append(expression)
    return expression_or if len(conditions) > 1 else expression


def expend_impl_activity(
    node, main_result, qs_nodes, project, start, qs_processed
):
    if "expended" in node.attributes and node.attributes["expended"]:
        logger.error(f"trying to expend an activity already expended")
        return None
    node_def = node.instantiate
    output_def = node_def.attributes['output']
    # avoid expending an activity not connected to main start
    try:
        # will raise an exception if no path found
        paths = list(
            nx.node_disjoint_paths(project.impl_graph, start.scv(), node.scv())
        )
    # if QS start not attached to start, SHOULD NOT be use
    except NetworkXNoPath:
        print("NOT CONNECTED WITH START:: ", node)
        return node
    except Exception as e:
        logger.error(f"unexpected error {e}")
        exit(-1)
    # add node to graph (if any new)
    node.attributes["expended"] = True
    output = output_def.make_instance(instance=node.instance)
    i_nodes = [
        (output.scv(), {"data": output},),
        (node.scv(), {"data": node},)
        ]
    # getting the list of the nodes instance that need to be used inside the QS
    i_nodes += [
        get_most_probable_instance(
            project.impl_graph, paths, QUESTION_SYSTEM, n.code, n.version
        )
        for n in qs_nodes
    ]
    node.graph.add_nodes_from(i_nodes)
    edges_def = list(node_def.graph.edges(keys=True, data=True))
    for e in edges_def:
        u = node_def.graph.nodes[e[0]]['data']
        imp_u = get_element(project.impl_graph, u.system, u.code, u.version, white_list=i_nodes)
        v = node_def.graph.nodes[e[1]]['data']
        imp_v = get_element(project.impl_graph, v.system, v.code, v.version, white_list=i_nodes)
        
        data = {}
        for key, value in e[3].items():
            data[key] = value if key != 'activity' else node
        node.graph.add_edge(imp_u.scv(), imp_v.scv(), **data)
    
    # add calculate
    # rebase node following the QS after the result (before adding the internal QS nod
    project.impl_graph = nx.compose(project.impl_graph, node.graph)
    rebase_edges(project.impl_graph, node, output, black_list=[scv for (scv, n,) in i_nodes])


def get_most_probable_instance(
    graph, paths, system, code, version=None, force_new=False
):
    nodes = get_elements(graph, system, code)
    if not force_new:
        # look if the exisitng instance of the inner node are already 
        # in a path leading to the QS start, 
        # if it the case it would for sure lead to a loop
        for n in nodes:
            if not any(n.scv() in path for path in paths):
                return (n.scv(), {"data": n})
    # no instance found that won't lead to a loop
    # then create a new one
    if nodes:
        new = nodes[0].make_instance(sibling=True)
        return (new.scv(), {"data": new})
    else:
        logger.error(f"node not found {to_scv(system, code, version)}")


def get_start_node(project):
    start = TriccBaseModel(
        code="triage",
        system="cpg-common-processes",
        label="Start",
        type_scv=TriccMixinRef(system="tricc_type", code=str(TriccNodeType.start)),
    )
    project.graph.add_node(start.scv(), data=start)
    project.graph_process_start["main"] = [start]
    return start


def to_activity(json_node, system, graph, generate_end=True):
    node = TriccActivity(
        code=get_mc_name(json_node["id"]),
        system=system,
        label=json_node["label"][list(json_node["label"].keys())[0]],
        type_scv=TriccMixinRef(system="tricc_type", code=str(TriccNodeType.activity)),
    )
    graph.add_node(node.scv(), data=node)
    get_options(json_node, node, str(TriccNodeType.activity), system)
    generate_cut_off_exp(json_node, node)
    if generate_end:
        end = TriccBaseModel(
            code=get_mc_name(json_node["id"]),
            system=ACTIVITY_END_SYSTEM,
            label=json_node["label"][list(json_node["label"].keys())[0]],
            type_scv=TriccMixinRef(system="tricc_type", code="calculate"),
        )
        node.attributes['output'] = end
        node.graph.add_node(end.scv(), data=end)
        node.graph.add_node(node.scv(), data=node)
    return node


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


def to_node(json_node, tricc_type, system, project, graph, js_fullorder):
    node = TriccBaseModel(
        code=get_mc_name(json_node["id"]),
        system=system,
        label=json_node["label"][list(json_node["label"].keys())[0]],
        type_scv=TriccMixinRef(system="tricc_type", code=str(tricc_type)),
    )
    generate_cut_off_exp(json_node, node)
    set_additional_attributes(
        node,
        json_node,
        ["is_mandatory", "type", "id", "description", "formula"],
    )
    context_code = get_context_from_fullorder(json_node["id"], js_fullorder)
    if not context_code:
        if "category" in json_node and json_node["category"]:
            context_code = json_node["category"]
        
    if context_code:
        node.context = project.get_context(STAGE_SYSTEM, context_code)
        get_options(json_node, node, tricc_type, system)
        graph.add_node(node.scv(), data=node)
    else:
        pass
    return node


def get_options(json_node, select_node, tricc_type, system):
    if "answers" in json_node and json_node["answers"]:
        i = 0
        for key, elm in json_node["answers"].items():
            label = elm['label']['en'] if isinstance(elm['label'], dict) else elm['label']
            option = TriccBaseModel(
                code=key,
                system=select_node.system,
                type_scv=TriccMixinRef(
                    system="tricc_type", code=str(TriccNodeType.select_option)
                ),
                label=label,
                reference=elm['reference']
            )
            set_additional_attributes(
                option,
                json_node,
                ["id", "type", "reference", "cut_off_start", "cut_off_end"],
            )
            select_node.attributes[f"options_{key}"] = option
            i += 1

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
        project.impl_graph.add_node(impl_node.scv(), data=impl_node)

    for process, start_nodes in project.graph_process_start.items():
        for start_node in start_nodes:
            if process not in project.impl_graph_process_start:
                project.impl_graph_process_start[process] = []
            project.impl_graph_process_start[process].append(start_node.instances[0])

    for u, v, data in project.graph.edges(data=True):
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


def get_code_from_scv(scvi):
    sc = scvi.split("|")
    if len(sc) > 1:
        return sc[1].split("::")[0]


def unloop_from_node(graph, start, order):
    no_cycle_found = True
    new_activity_instances = {}
    while no_cycle_found:
        try:
            loop = list(nx.find_cycle(graph, start.scv()))
            activities = {}
            old_edge = []
            scores = {}
            # get edges data
            for k, e in enumerate(loop):
                loop[k] += (graph.get_edge_data(*e),)
                edge_activity = loop[k][3]["activity"].scv()
                if edge_activity not in activities:
                    activities[edge_activity] = 1
                else:
                    activities[edge_activity] += 1

            # looking for edge that once replace with a new node will open the loop
            # meaning that the context of the node is not going back to the loop
            # lower the score will be more likely will be the unlooping
            for e in loop:
                out_edge = list(graph.edges(e[0], keys=True, data=True))
                in_edge = list(graph.in_edges(e[1], keys=True, data=True))
                # avoid moving instance > 1 of e[1] for e TODO
                scores[e[0]] = 3 if graph.nodes[e[1]]["data"].instance > 1 else 0
                # activity end cannot be duplicated
                to_node = graph.nodes[e[1]]["data"]

                if to_node.system == ACTIVITY_END_SYSTEM:
                    scores[e[0]] += 99
                if isinstance(to_node, TriccActivity):
                    scores[e[0]] += 80
                if e[3]["flow_type"] != "SEQUENCE":
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
                        ie[0] != start.scv()
                        and ie[0] != e[0]
                        and ie[3]["flow_type"] == "SEQUENCE"
                        and (ie[3]["activity"] == e[3]["activity"])
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
                        scores[e[0]] += 99
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
            if min(scores.values()) > 90:
                pass
            # find the edge data, it includes activity
            # create another instance of the target node

            old_node = graph.nodes[old_edge[1]]["data"]
            new_node = old_node.make_instance(sibling=True)
            if isinstance(old_node, TriccActivity):
                if old_node.code not in new_activity_instances:
                    new_activity_instances[str(old_node.code)] = []
                new_activity_instances[str(old_node.code)].append(new_node)

            graph.add_node(new_node.scv(), data=new_node)
            # replace all edges between those node with the same context (used for select multiple)
            out_edge = list(graph.edges(old_edge[0], keys=True, data=True))
            for se in out_edge:
                if se[1] == old_edge[1]:
                    graph.remove_edge(*se[:3])
                    # create new edge
                    graph.add_edge(se[0], new_node.scv(), **se[3])
            # find edge form node with the same activity, using a list to fix its size2
            # edges_to_assess = list(graph.edges(old_edge[1], keys=True, data=True))
            # for e in edges_to_assess:
            #    if old_edge[3]["activity"] == e[3]["activity"]:
            #        # remove the edge, the data e[3] must not be part of the call
            #        graph.remove_edge(*e[:3])
            #        graph.add_edge(new_node.scv(), e[1], **e[3])
            #        logger.debug(
            #            f"source of edge from {old_edge} to {e[1]} replaced by {new_node}"
            #        )
        except NetworkXNoCycle:
            no_cycle_found = False
    return new_activity_instances


def rebase_edges(graph, old_node, new_node, black_list=[]):
    # get all edges from old node
    node_edges = [e for e in graph.edges(old_node.scv(), keys=True, data=True) if e[1] not in black_list]
    # assign each one to the new node
    for e in node_edges:
        graph.remove_edge(*e[:3])
        data = e[3]
        # update condition
        if "condition" in data and data["condition"]:
            ref = f'"{old_node.instantiate.scv() if old_node.instantiate else old_node.scv()}"'
            if ref in data["condition"]:
                data["condition"] = data["condition"].replace(
                    ref,
                    f'"{new_node.instantiate.scv() if new_node.instantiate else new_node.scv()}"',
                )
        graph.add_edge(new_node.scv(), e[1], **data)


def get_mc_name(name):
    return f"{name}"


def get_context_from_fullorder(js_id, js_fullorder):
    return walkthrough_fullorder(
        js_fullorder,
        lambda data, context, value: context if str(data) == str(value) else None,
        value=js_id,
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
    js_nodes["age_day"] = {
        "id": "age_day",
        "label": {"en": "Age in days", "fr": "Age en jours"},
        "type": "Question",
        "category": "basic_demographic",
        "value_format": "Float",
        "formula":"ToDay"
    }
    js_nodes["age_month"] = {
        "id": "age_month",
        "label": {"en": "Age in Months", "fr": "age en mois"},
        "type": "Question",
        "category": "basic_demographic",
        "value_format": "Float",
        "formula":"ToMonth"
    }
    return js_nodes


def all_simple_paths(graph, start, end, cutoff=5, max_len=5):
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
        map(
            lambda n: get_simple_paths(graph, n, end, paths, current_path, cutoff - 1),
            graph.edges(start),
        )


def walkthrough_fullorder(js_fullorder, callback=None, **kwargs):
    # section name
    for context in js_fullorder:
        if isinstance(js_fullorder[context], dict):
            # for dict of id at level 1, each dict the titel as section and list of id as section value
            for sub in js_fullorder[context]:
                if isinstance(js_fullorder[context][sub], list):
                    for sub_sub in js_fullorder[context][sub]:
                        res = callback(sub_sub, context=f"{context}.{sub}", **kwargs)
                        if res:
                            return res
                else:
                    logger.error("unexpected format")
        elif isinstance(js_fullorder[context], list):
            # for list of dict of id at level 1, each dict having title and data
            for sub in js_fullorder[context]:
                if isinstance(sub, dict):
                    if "data" in sub:
                        for sub_sub in sub["data"]:
                            res = callback(
                                sub_sub, context=f"{context}.{sub['title']}", **kwargs
                            )
                            if res:
                                return res

                    else:
                        logger.error("unexpected format")
                # for list of id at level 1
                elif isinstance(sub, (str, int)):
                    res = callback(sub, context=context, **kwargs)
                    if res:
                        return res

        else:
            logger.error("unexpected format")


def fullorder_to_order(js_fullorder):
    order = []
    walkthrough_fullorder(
        js_fullorder, lambda data, context, order: order.append(str(data)), order=order
    )
    return order


### TODO tranlate it for

#  node_age_day=[], node_age_month=[], node_age_year=[] are mutable, they will be shared between all the calls of the function

def add_background_calculation_options(json_node, node, node_age_day=[], node_age_month=[], node_age_year=[]):
    # in a previous functions basic_demographic node should be identified (How to keep the old id ?) use a filter ? 
    #   toDay -> age_data
    #   toMonth -> age_month
    #   toYear -> age year
    # if not found must be created
    # here retrieve thos 3 nodes and replace all other ToMonth/toDay/toYear reference with the equivalent node
    op = None
    if json_node["category"] in (
        "basic_demographic"
    ) and 'formula' in json_node:
        # the expression must be created to do the proper calcualtion for toYear, ToMonth, ToDay
        ref = to_scv_str(QUESTION_SYSTEM, "birth_date")
        if json_node["formula"] == "ToMonth":
            op = TriccOperation(TriccOperator.AGE_MONTH)
            op.append(TriccSCV(ref))
            node_age_month.append(node)
        elif json_node["formula"] == "ToDay":
            op = TriccOperation(TriccOperator.AGE_DAY)
            op.append(TriccSCV(ref))
            node_age_day.append(node)
        else:
            logger.error("basic_demographic unrelated to age not supported")
            exit(-1)
    else:
        op = TriccOperation(TriccOperator.IFS)
        for a in json_node["answers"].values():
            if "operator" in a:
                ref = get_formula_ref(json_node, node_age_day, node_age_month, node_age_year)
                if ref:  # Manage slices
                    op.append(get_answer_operation(ref, a))
                    # op.append(TriccStatic(str(a['id'])))
                elif "reference_table_x_id" in json_node:  # manage ZScore
                    x_node = None
                    y_node = None
                    z_node = None
                    # run the code only if there is data in the setup fields, case condition
                    opa_c = TriccOperation("exists")
                    if (
                        json_node["reference_table_x_id"] is not None
                        and json_node["reference_table_x_id"] != ""
                    ):
                        x_node = to_scv_str(
                            QUESTION_SYSTEM, json_node["reference_table_x_id"]
                        )
                        opa_c.append(x_node)
                    if (
                        json_node["reference_table_y_id"] is not None
                        and json_node["reference_table_y_id"] != ""
                    ):
                        y_node = to_scv_str(
                            QUESTION_SYSTEM, json_node["reference_table_y_id"]
                        )
                        opa_c.append(y_node)
                    if (
                        json_node["reference_table_z_id"] is not None
                        and json_node["reference_table_z_id"] != ""
                    ):
                        z_node = to_scv_str(
                            QUESTION_SYSTEM, json_node["reference_table_z_id"]
                        )
                        opa_c.append(z_node)

                    op.append(opa_c)
                    opa_v = None
                    if x_node and z_node:
                        opa_v = TriccOperation("izscore")
                        opa_v.append(TriccSCV(x_node))
                        opa_v.append(TriccSCV(z_node))
                    elif x_node and y_node:
                        opa_v = TriccOperation("zscore")
                        opa_v.append(TriccSCV(x_node))
                        opa_v.append(TriccSCV(y_node))
                    if opa_v:
                        op.append(opa_v)
                else:
                    raise NotImplementedError(
                        "opertaion not implemented, only slice and tables are"
                    )
                    exit(-1)
    node.expression = op


def get_formula_ref(json_node, node_age_day, node_age_month, node_age_year):
    if "formula" in json_node:
        if json_node["formula"] == "ToMonth" and node_age_month:
            return node_age_month[-1].scv()
        elif json_node["formula"] == "ToDay" and node_age_day:
            return node_age_day[-1].scv()
        elif json_node["formula"][0] == "[" and json_node["formula"][-1] == "]":
            return to_scv_str(QUESTION_SYSTEM, json_node["formula"][1:-1])
        else:
            logger.error(f"ref {json_node['formula']} not supported or not yet known")
            exit(-1)


def get_answer_operation(ref, a):
    opa = None
    val = a["value"].split(",")
    opa = TriccOperation(a["operator"])
    opa.append(TriccSCV(ref))
    expected_values = 1 + int(a["operator"] == "between")
    if len(val) != expected_values:
        raise ValueError(
            f"value for operator {a['operator']} in {a.id} needs {expected_values} values but {a['value']} found"
        )
    for v in val:
        opa.append(v)
    return opa


def generate_cut_off_exp(js_node, node):
    exp = []
    if "cut_off_start" in js_node or "cut_off_end" in js_node:
        if "cut_off_start" in js_node and js_node["cut_off_start"] is not None:
            cs = TriccOperation(TriccOperator.MORE_OR_EQUAL)
            cs.append(TriccSCV(to_scv_str(QUESTION_SYSTEM, "age_day")))
            cs.append(TriccStatic(js_node["cut_off_start"]))
            exp.append(cs)

        if "cut_off_end" in js_node and js_node["cut_off_end"] is not None:
            ce = TriccOperation(TriccOperator.LESS)
            ce.append(TriccSCV(to_scv_str(QUESTION_SYSTEM, "age_day")))
            ce.append(TriccStatic(js_node["cut_off_end"]))
            exp.append(ce)
    if exp:
        node.applicability = (
            TriccOperation(TriccOperator.OR, exp) if len(exp) > 1 else exp[0]
        )
