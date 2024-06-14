import logging
import networkx as nx
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


NODE_ID = "7927"


def import_mc_nodes(json_node, system, project):
    if json_node["type"] == "QuestionsSequence":
        to_activity(json_node, system, project)
    else:
        tricc_type = get_mc_tricc_type(json_node)
        to_node(
            json_node=json_node, tricc_type=tricc_type, system=system, project=project
        )


def import_mc_flow_from_diagnose(json_node, system, project, start):

    diag = TriccContext(
        code=get_mc_name(json_node["id"]),
        system=system,
        label=json_node["label"][list(json_node["label"].keys())[0]],
        type_scv=TriccMixinRef(system="tricc_type", code=str(TriccNodeType.context)),
    )
    set_additional_attributes(
        diag, json_node, ["complaint_category", "id", "cut_off_start", "cut_off_end"]
    )
    add_flow_from_instances(project.graph, json_node["instances"].values(), start, diag)


def add_flow_from_instances(graph, instances, start, context, white_list=None):
    for instance in instances:
        if str(instance['id']) == NODE_ID:
            pass
        _to = get_element(
            graph,
            QUESTION_SYSTEM,
            instance["id"],
            white_list=white_list
        )
        if instance["conditions"]:
            add_flow_from_condition(
                graph,
                instance["conditions"],
                _to,
                context,
                white_list=white_list
            )
            edges_to_nodes = list(graph.in_edges(_to))
            if (
                len(edges_to_nodes) > 1 and 
                any([start.__resp__() == e[0] for e in edges_to_nodes])
            ):
                graph.remove_edge(start.__resp__(), _to.__resp__())
                pass
        # add edge if no other edges
        elif not list(graph.in_edges(_to)):
            add_flow(graph, context, start, _to)


def add_flow_from_condition(graph, conditions, _to, context, white_list=None):
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
            condition=condition
        )


def import_mc_flow_from_qs(json_node, system, project, start):
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

    qs_impl = get_elements(project.impl_graph, QUESTION_SYSTEM, json_node["id"])

    qs_nodes = [
        get_element(project.graph, QUESTION_SYSTEM, i["id"])
        for i in json_node["instances"].values()
    ]

    main_result = TriccBaseModel(
        code=get_mc_name(json_node["id"]),
        system=system,
        label=json_node["label"][list(json_node["label"].keys())[0]],
        type_scv=TriccMixinRef(system="tricc_type", code="calculate"),
    )
    qs_context = TriccContext(
            code=get_mc_name(json_node["id"]),
            system=system,
            label=json_node["label"][list(json_node["label"].keys())[0]],
            type_scv=TriccMixinRef(
                system="tricc_type", code=str(TriccNodeType.context)
            ),
        )
    project.graph.add_node(main_result.__resp__(), data=main_result)
    for i in qs_impl:
        # context to be used by the flow
        
        result = main_result.make_instance()
        qs_context.instance = result.instance
        # if i.instance > 1:
        #     i_nodes = [n.make_instance() for n in qs_nodes]
        # else:
        try:
            # will raise an exception if no path found
            paths = list(nx.node_disjoint_paths(
                    project.impl_graph, start.__resp__(), i.__resp__()
                ))
            i_nodes = [
                get_most_probable_instance(
                    project.impl_graph, paths, QUESTION_SYSTEM, n.code, n.version
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
                    version=n.version
                )
                i_nodes.append(node)
        except Exception as e:
            logger.error(f"unexpected error {e}")
        # add node to graph (if any new)
        project.impl_graph.add_nodes_from(i_nodes)
        # add the flow using the i_nodes
        add_flow_from_instances(
            project.impl_graph,
            json_node["instances"].values(),
            i,
            qs_context,
            white_list=i_nodes
        )
        # add calculate
        project.impl_graph.add_node(result.__resp__(), data=result)
        i_nodes.append((result.__resp__(), {'data': result}))
        # add calculate flow
        add_flow_from_condition(
            project.impl_graph,
            json_node["conditions"],
            result,
            qs_context,
            white_list=i_nodes
        )
        rebase_edges(project.impl_graph, i, result)

def get_most_probable_instance(graph, paths, system, code, version=None):
    nodes = get_elements(graph, system, code)
    for n in nodes:
        if not any(n.__resp__() in path for path in paths):
            return (n.__resp__(), {"data": n})
    if n:
        new = n.make_instance(sibling=True)
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
    node = TriccActivity(
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


def to_node(json_node, tricc_type, system, project):
    node = TriccBaseModel(
        code=get_mc_name(json_node["id"]),
        system=system,
        label=json_node["label"][list(json_node["label"].keys())[0]],
        type_scv=TriccMixinRef(system="tricc_type", code=str(tricc_type)),
    )
    set_additional_attributes(
        node,
        json_node,
        ["is_mandatory", "type", "id", "description", "cut_off_start", "cut_off_end"],
    )
    get_options(json_node, node, tricc_type, system, project)
    project.graph.add_node(node.__resp__(), data=node)


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
        u_impl = project.graph.nodes[u]["data"].instances[0]
        v_impl = project.graph.nodes[v]["data"].instances[0]
        project.impl_graph.add_edge(u_impl.__resp__(), v_impl.__resp__(), **data)


# Unlooping function
# unlooping my only work if the loop are compose of edges with different context (case 1)
# in case the loop is within a context then it might be harder to unloop them (case 2)
# case 1: look for an edge that lead to a node that don't have an edge from the same context
# going back to the loop


def unloop_from_node(graph, start):
    no_cycle_found = True
    while no_cycle_found:
        try:
            loop = list(nx.find_cycle(graph, start.__resp__()))
            activities = {}
            candidate_edges = []
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

            for e in loop:
                if activities[e[3]["activity"].__resp__()] == 1:
                    candidate_edges.append(e)
                    # may need to add edge from activity base or root
            # looking for edge that are not following by an edge for the same activity
            
            if not candidate_edges:
                len_loop = len(loop)
                for k, e in enumerate(loop):
                    if (
                        e[3]["activity"] != loop[(k + 1) % len_loop][3]["activity"]
                    ):
         
                        candidate_edges.append(e)
            # find the edges that have a sibling from root to avoid creating dandling nodes
            if not candidate_edges:
                for e in loop:
                    # test if there is // path from start
                    # add only the ones with // paths to candidate
                    if len(nx.all_simple_paths(graph, start, e[1])) > 1:
                        candidate_edges.append(e)
    
            nodes_in_loop = [e[0] for e in loop]
            old_edge = None
            old_edge_sibling = []
            len_old_edge_sibling = 0
            out_activity_loop = True
            for e in candidate_edges:
                node_edges = list(graph.edges(e[0], keys=True, data=True))
                nb_node_edges = len(node_edges)
                nb_node_edges_in_target = len(set([e[1] for e in list(graph.in_edges(e[1]))]))
                
                # look for the edge with less sibling and no edges that are going to another node in the loop
                # all egdes must follow one of 3 conditions
                # - same activity of the candidate
                # - same target node as the candidate
                # - target node not in the loop
                if all(
                    [
                        not (
                            ne[1] in nodes_in_loop
                            and ne[3]["activity"] == e[3]["activity"]
                        )
                        or ne[1] == e[1]
                        for ne in node_edges
                    ]
                ) and (
                    not old_edge_sibling or 
                    nb_node_edges < len_old_edge_sibling
                ) and nb_node_edges_in_target > 1:
                    old_edge_sibling = node_edges
                    len_old_edge_sibling = nb_node_edges
                    old_edge = e
            if not old_edge:
                # edge detected in an activity, unloop my be risky
                logger.warning("no clean way found to unloop, unlooping the last edge")
                old_edge = loop[-1]
                old_edge_sibling = [old_edge]
                len_old_edge_sibling = 1
                out_activity_loop = False
                # FIXME add an edge from start activity or start
            logger.debug(
                f"the edge {old_edge} to be removed has {len_old_edge_sibling} siblings "
            )
            # find the edge data, it includes activity
            # create another instance of the target node
            new_node = graph.nodes[old_edge[1]]["data"].make_instance(sibling=True)
            graph.add_node(new_node.__resp__(), data=new_node)
            # replace all edges between those node with the same context (used for select multiple)
            for se in old_edge_sibling:
                if se[1] == old_edge[1]:
                    graph.remove_edge(*se[:2])
                    # create new edge
                    graph.add_edge(se[0], new_node.__resp__(), **se[3])
            # find edge form node with the same activity, using a list to fix its size2
            edges_to_assess = list(graph.edges(old_edge[1], keys=True, data=True))
            for e in edges_to_assess:
                if old_edge[3]["activity"] == e[3]["activity"] and out_activity_loop:
                    # remove the edge, the data e[3] must not be part of the call
                    graph.remove_edge(*e[:3])
                    graph.add_edge(new_node.__resp__(), e[1], **e[3])
                    logger.debug(
                        f"source of edge from {old_edge} to {e[1]} replaced by {new_node}"
                    )
        except NetworkXNoCycle:
            no_cycle_found = False


def rebase_edges(graph, old_node, new_node):
    node_edges = list(graph.edges(old_node.__resp__(), keys=True, data=True))
    for e in node_edges:
        graph.remove_edge(*e[:3])
        graph.add_edge(new_node.__resp__(), e[1], **e[3])

def get_mc_name(name):
    return f"{name}"


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
