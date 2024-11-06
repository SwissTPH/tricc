import logging
import os
import json
from pathlib import Path
import networkx as nx
import matplotlib.pyplot as plt

from tricc_og.builders.mc_to_tricc import (
    import_mc_nodes,
    get_registration_nodes,
    get_age_nodes,
    add_age_calculation,
    add_background_calculation_options,
    import_mc_flow_to_diagnose,
    get_start_node,
    QUESTION_SYSTEM,
    DIAGNOSE_SYSTEM,
    MANDATORY_STAGE,
    import_mc_flow_from_diagram,
    import_qs_inner_flow,
    load_villages_options,
)
from tricc_og.models.base import TriccBaseModel, TriccProject
from tricc_og.models.tricc import TriccNodeType
from tricc_og.strategies.input.base_input_strategy import BaseInputStrategy
from tricc_og.parsers.xml import read_drawio
from tricc_og.visitors.tricc_project import (
    get_element,
    add_flow,
    save_graphml,
    hierarchical_pos,
    unloop_from_node,
    import_mc_flow_from_activities,
    make_implementation,
)
from tricc_og.builders.mc_data_dictionnary import CodeSystemBuilder
from tricc_og.builders.tricc_to_bpmn import create_bpmn_from_dict
from bpmn_python.bpmn_diagram_export import BpmnDiagramGraphExport
logger = logging.getLogger("default")
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
logging.getLogger('PIL').setLevel(logging.INFO)

import random


class MedalCStrategy(BaseInputStrategy):
    def execute(self, in_filepath, media_path):
        # reading input file
        # pages = {}
        # start_pages = {}
        # read all pages
        logger.info("# Reading the input file")

        if os.path.isfile(in_filepath):
            with open(in_filepath, encoding='utf8') as f:
                js_full = json.load(f)
        else:
            logger.error(f"input file not found {in_filepath}")
            exit(-1)
        logger.info("# creating the project")
        project = TriccProject(
            code=str(js_full['id']),
            display=js_full['name'],
        )
        project.code_system = CodeSystemBuilder(project.code, project.display, js_full).code_system
        logger.info("# loading the nodes")
        js_nodes = js_full["medal_r_json"]["nodes"]
        js_diagram = js_full["medal_r_json"]["diagram"]
        js_fullorder = js_full['medal_r_json']['config']['full_order']
        # load key nodes:
        # "basic_questions": {
        #         "weight_question_id": 7805,
        #         "gender_question_id": 7852,
        #         "general_cc_id": 8341,
        #         "yi_general_cc_id": 8352
        #     },
        #     "optional_basic_questions": {
        #         "village_question_id": 8062
        #     },
        # load on questions
        village_q_id = js_full["medal_r_json"]['config'][
            'optional_basic_questions'
        ].get('village_question_id', None)
        js_basic_questions =  js_full["medal_r_json"]["config"]["basic_questions"]
        yi_cc_id =js_basic_questions["general_cc_id"]
        child_cc_id = js_basic_questions["yi_general_cc_id"]
        weight_question_id = js_basic_questions["weight_question_id"]
        gender_question_id = js_basic_questions["gender_question_id"]
        # generate and add generic nodes
        
        start = get_start_node(project)        
        sex = import_mc_nodes(js_nodes[str(gender_question_id)], QUESTION_SYSTEM, project, js_fullorder, start)
        js_node_loaded = [str(gender_question_id)]
        if village_q_id:
            village = import_mc_nodes(js_nodes[str(village_q_id)], QUESTION_SYSTEM, project, js_fullorder, start)
            load_villages_options(village, js_full["medal_r_json"]["village_json"])
            js_node_loaded.append(str(village_q_id))
            
        
        std_nodes = get_registration_nodes()
        for node_id in std_nodes:
            n = import_mc_nodes(std_nodes[node_id], QUESTION_SYSTEM, project, js_fullorder, start)
            add_flow(project.graph,
                     None,
                     start,
                     n)
        dob = get_element(
            project.graph,
            QUESTION_SYSTEM,
            'birth_date'
        )
        std_nodes = get_age_nodes()
        for node_id in std_nodes:
            n = import_mc_nodes(std_nodes[node_id], QUESTION_SYSTEM, project, js_fullorder, start)
            n.expression = add_age_calculation(std_nodes[node_id], dob)
            add_flow(project.graph,
                     None,
                     dob,
                     n,
                     flow_type="ASSOCIATION")
        age_day = get_element(
            project.graph,
            QUESTION_SYSTEM,
            'age_day'
        )
        age_month = get_element(
            project.graph,
            QUESTION_SYSTEM,
            'age_month'
        )

        for node_id in js_nodes:
            if node_id not in js_node_loaded:
                n = import_mc_nodes(js_nodes[node_id], QUESTION_SYSTEM, project, js_fullorder, start)
                if js_nodes[node_id]["category"] in (
                    "background_calculation",
                    "basic_demographic"
                ) and 'formula' in js_nodes[node_id] :
                    n.expression = add_background_calculation_options(
                        js_nodes[node_id],
                        age_day,
                        age_month,
                        dob,
                        sex
                    )
                    if n.expression:
                        n.type_scv.code = TriccNodeType.calculate 
                    bases = n.expression.get_references()
                    for b in bases:
                        add_flow(project.graph,
                            None,
                            b,
                            n,
                            flow_type="ASSOCIATION")
            
        # then build the internal qs graph
        for node_id in js_nodes:
            if js_nodes[node_id]["type"] == "QuestionsSequence":
                node = import_qs_inner_flow(js_nodes[node_id], QUESTION_SYSTEM, project)
        
        js_diagnoses = js_full["medal_r_json"]["diagnoses"]

        for node_id in js_diagnoses:
            import_mc_flow_to_diagnose(
                js_diagnoses[node_id], DIAGNOSE_SYSTEM, project, start
            )  

        #add_formula_association_flow(project)
        # build other sequences

        
        # (set_of_elements, class_name, system, code, version=None)
        main_complain_yi = get_element(project.graph, QUESTION_SYSTEM, yi_cc_id)
        main_complain_child = get_element(project.graph, QUESTION_SYSTEM, child_cc_id)
        # main start
        import_mc_flow_from_diagram(
                js_diagram, QUESTION_SYSTEM, project.graph, start
            )
        
        return project

    def save_graph(self, graph, filename):
        pos = nx.spring_layout(graph)
        scale_factor = 2
        pos = {
            node: (scale_factor * x, scale_factor * y) for node, (x, y) in pos.items()
        }
        nx.draw(
            graph,
            pos,
            with_labels=True,
            node_color="skyblue",
            node_size=200,
            edge_color="gray",
            font_size=8,
            font_color="black",
        )
        edge_labels = nx.get_edge_attributes(graph, "label")
        nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels)
        plt.savefig(filename, dpi=300)

    def save_simple_graph(self, graph, ref_node, filename):
        # Calculate node positions using the spring layout
        pos = left_to_right_layout(graph, ref_node)
        # Draw the graph
        plt.figure(figsize=(12, 8))
        nx.draw(graph, pos, node_size=10, with_labels=False)
        plt.axis("off")
        plt.savefig(filename, dpi=300)

    def save_simple_tree(self, G, start_node, filename):

        # Get hierarchical layout
        pos = hierarchical_pos(G, start_node)
        for node in G.nodes():
            if node not in pos:
                pos[node] = (random.random(), 1)

        # Draw the graph
        plt.figure(figsize=(12, 8))
        nx.draw(G, pos, with_labels=True, node_color='lightblue', 
                node_size=300, font_size=10, font_weight='bold', 
                arrows=True, edge_color='gray', arrowsize=20)

        nx.draw_networkx_labels(G, pos)

        plt.title("Hierarchical MultiDiGraph")
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(filename, dpi=300)
   
    

        



def left_to_right_layout(G, ref_node):
    path_lengths = dict(nx.single_source_shortest_path_length(G, ref_node))
    nodes = {}
    isolated = []
    for node in G.nodes():
        nodes[node] = (path_lengths[node] if node in path_lengths else -1, random.random())
        if nodes[node][0] == -1:
            if not G.in_edges(node) and not G.out_edges(node):
                isolated.append(node)
            elif not G.in_edges(node):
                logger.warning(f"node {node} is dangling")
    for node in isolated:
        logger.debug(f"node {node} is isolated")
            
                    
    return nodes