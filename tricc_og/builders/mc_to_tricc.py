import logging
import networkx as nx
from networkx.exception import NetworkXNoCycle

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
    add_flow,
)

def import_mc_nodes(json_node, system, project):
    if json_node["type"] == "QuestionsSequence":
        to_activity(json_node, system, project)            
    else:
        tricc_type = get_mc_tricc_type(json_node)
        to_node(json_node=json_node, tricc_type=tricc_type, system=system, project=project)


def import_mc_flow_from_diagnose(json_node, system, project, start):

    
    diag = TriccContext(
        code=get_mc_name(json_node["id"]),
        system=system,
        label=json_node["label"][list(json_node["label"].keys())[0]],
        type_scv=TriccMixinRef(
            system="tricc_type",
            code=str(TriccNodeType.context)
        )
    )
    set_additional_attributes(
        diag, 
        json_node, 
        ["complaint_category", "id", "cut_off_start", "cut_off_end"]
    )

    for instance in json_node['instances'].values():
        
        _to = get_element(project.graph, 'questions', instance['id'])
        if instance['conditions']:
            for cond in instance['conditions']:
                _from = get_element(project.graph,  'questions', cond['node_id'])
                condition = None
                if 'answer_id' in cond:
                    condition = f""""{_from.get_name()}" contains '{cond['answer_id']}'"""
                    add_flow(project.graph, diag, _from, _to, label=None, condition=condition)       
        else:
            add_flow(project.graph, diag, start, _to)


def get_start_node(project):
    start = TriccBaseModel(
            code='triage',
            system='cpg-common-processes',
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
        type_scv=TriccMixinRef(
            system="tricc_type",
            code=str(TriccNodeType.activity)
        ),
    )
    project.graph.add_node(node.__resp__(), data=node)
    


def get_mc_tricc_type(json_node):
    tricc_type = json_node.get('type', None)
    if tricc_type == "Question":
        if json_node["value_format"] == "Integer":
            tricc_type = TriccNodeType.integer
        elif json_node["value_format"] == "String":
            tricc_type = TriccNodeType.text
        elif json_node["value_format"] == "Date":
            tricc_type = TriccNodeType.date
        elif json_node["value_format"] == "Float":
            tricc_type = TriccNodeType.decimal
        elif (
            "formula" in json_node and
            ('anwers' not in json_node or not json_node['anwers'])
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
        ["is_mandatory", "type", "id", "description", "cut_off_start", "cut_off_end"]
    )
    get_options(json_node, node, tricc_type, system, project)
    project.graph.add_node(node.__resp__(), data=node)
    
def get_options(json_node, select_node, tricc_type, system, project):
    if tricc_type == TriccNodeType.select_one:
        if "answers" in json_node and json_node['answers']:
            i = 0
            for key, elm in json_node['answers'].items():
                option = TriccBaseModel(
                    code=get_mc_name(json_node["id"]),
                    system=select_node.get_name(),
                    type_scv=TriccMixinRef(
                        system="tricc_type",
                        code=str(TriccNodeType.select_option)
                    ),
                    label=json_node["label"][list(json_node["label"].keys())[0]],
                )
                set_additional_attributes(
                    option, 
                    json_node, 
                    ["id", "type", "reference", "cut_off_start", "cut_off_end"]
                )
                select_node.attributes[f"output_options[{i}]"] = option
                i += 1    
        else:
            raise ValueError(f"Select one {system}:{json_node['id']} must have answers")
        

def set_additional_attributes(node, json_node, attribute_names):
    if not isinstance(attribute_names, list):
        attribute_names = [attribute_names]
    for attributename in attribute_names:
        if  attributename in json_node:
            if attributename == "is_mandatory":
                node.attributes["required"] = "1"
            if attributename == "description":
                node.attributes["help"] = json_node[attributename]
            elif json_node[attributename]:
                node.attributes[attributename] = json_node[attributename]
                

def make_implementation(project):
    for node_hash, attr in project.graph.nodes(data=True):
        node = attr['data']
        # Create a new custom node with the same attributes
        impl_node = node.make_instance()
        # Add custom node to the new graph with the same node id
        project.impl_graph.add_node(impl_node.__resp__(), data=impl_node)
    
    for u, v, data in project.graph.edges(data=True):
        u_impl = project.graph.nodes[u]['data'].instances[0]
        v_impl = project.graph.nodes[v]['data'].instances[0]
        project.impl_graph.add_edge(u_impl.__resp__(), v_impl.__resp__(), **data)


# Unlooping function
# unlooping my only work if the loop are compose of edges with different context (case 1)
# in case the loop is within a context then it might be harder to unloop them (case 2)
# case 1: look for an edge that lead to a node that don't have an edge from the same context 
# going back to the loop

def unloop_from_node(graph, node):
    no_cycle_found = True
    while no_cycle_found:
        try:
            loop = list(nx.find_cycle(graph, node.instances[0].__resp__()))
            activities = {}
            candidate_edges = []
            # get edges data
            for k, e in enumerate(loop):
                loop[k] += (graph.get_edge_data(*e),)
                edge_activity = loop[k][3]['activity'].__resp__()
                if edge_activity not in activities:
                    activities[edge_activity] = 1
                else:
                    activities[edge_activity] += 1
            # looking for edge that once replace with a new node will open the loop
            # meaning that the context of the node is not going back to the loop            
            
            for e in loop:
                if activities[e[3]['activity'].__resp__()] == 1:
                    candidate_edges.append(e)

            if not candidate_edges:
                len_loop = len(loop)
                for k, e in enumerate(loop):
                    if e[3]['activity'] != loop[(k+1)%len_loop][3]['activity']:
                        candidate_edges.append(e)
  
            nodes_in_loop = [e[0] for e in loop]
            old_edge = None
            old_edge_sibling = None
            len_old_edge_sibling = None
            for e in candidate_edges:
                node_edges = list(graph.edges(e[0], keys=True, data=True))
                # remove the current edge
                nb_node_edges = len(node_edges)
                # look for the edge with less sibling and no edges that are going to another node in the loop
                # all egdes must follow one of 3 conditions
                # - same activity of the candidate
                # - same target node as the candidate
                # - target node not in the loop
                if (
                    all([not (ne[1] in nodes_in_loop and ne[3]['activity'] == e[3]['activity']) or ne[1] == e[1] for ne in node_edges]) and
                    (not old_edge_sibling or nb_node_edges < len_old_edge_sibling)
                ):
                    old_edge_sibling = node_edges
                    len_old_edge_sibling = len(node_edges)
                    old_edge = e
            if not old_edge:
                logger.error("no way found to unloop")
            logger.debug(f"the edge {old_edge} to be removed has {len_old_edge_sibling} siblings ")
            # find the edge data, it includes activity
            # create another instance of the target node
            new_node = graph.nodes[old_edge[1]]['data'].make_instance(sibling=True)
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
                if old_edge[3]['activity'] == e[3]['activity']:
                    # remove the edge, the data e[3] must not be part of the call
                    graph.remove_edge(*e[:3])
                    graph.add_edge(new_node.__resp__(), e[1], **e[3])
                    logger.debug(f"source of edge from {old_edge} to {e[1]} replaced by {new_node}")
        except NetworkXNoCycle:
            no_cycle_found = False



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
