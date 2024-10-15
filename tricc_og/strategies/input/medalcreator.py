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
    fullorder_to_order,
    get_start_node,
    QUESTION_SYSTEM,
    DIAGNOSE_SYSTEM,
    MANDATORY_STAGE,
    import_mc_flow_from_diagram,
    import_qs_inner_flow,
)
from tricc_og.models.base import TriccBaseModel, TriccProject
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
            code=Path(in_filepath).stem,
            label=Path(in_filepath).stem,
        )
        logger.info("# loading the nodes")
        js_nodes = js_full["medal_r_json"]["nodes"]
        js_diagram = js_full["medal_r_json"]["diagram"]
        js_fullorder = js_full['medal_r_json']['config']['full_order']

        # generate and add generic nodes
        std_nodes = get_registration_nodes()
        start = get_start_node(project)
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
            'birth_date'
        )
        age_month = get_element(
            project.graph,
            QUESTION_SYSTEM,
            'birth_date'
        )
        # load on questions
        for node_id in js_nodes:
            n = import_mc_nodes(js_nodes[node_id], QUESTION_SYSTEM, project, js_fullorder, start)
            if js_nodes[node_id]["category"] in (
                "background_calculation",
                "basic_demographic"
            ):
                n.expression = add_background_calculation_options(
                    js_nodes[node_id],
                    age_day,
                    age_month,
                    dob
                )
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
        yi_cc_id = js_full["medal_r_json"]["config"]["basic_questions"]["general_cc_id"]
        child_cc_id = js_full["medal_r_json"]["config"]["basic_questions"][
            "yi_general_cc_id"
        ]
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


        order = fullorder_to_order(js_fullorder)

        ### TRANSFORM
        make_implementation(project)
        logger.info(f"implementing graph have {project.impl_graph.number_of_edges()} edges")
        start_impl = start.instances[0]
        save_graphml(project.graph, start.scv(), "graph")
        # image
        #self.save_simple_graph(project.impl_graph, start_impl, "loaded.png")
        
        new_activities = unloop_from_node(project.impl_graph, start_impl, order)
        
        logger.info(f"Unlooped graph has {project.impl_graph.number_of_edges()} edges")
        # image
        #self.save_simple_graph(project.impl_graph, start_impl, "unlooped.png")
        # make QS
        # 1- create QS flow
        # 2- attached named output (conditionnal flow or calculate)
        # 3- "inject" qs as question list / or activity abstract + implementation
        import_mc_flow_from_activities(
                project, start_impl, order
            )
        # image
        # self.save_simple_graph(project.impl_graph, start_impl, "qs_loaded.png")
        # self.save_simple_tree(project.impl_graph, start_impl.scv(), "tree.png")
        # save_graphml(project.impl_graph, start_impl.scv(), "decisiontree.graphml")
        logger.info(f"Final graph has {project.impl_graph.number_of_edges()} edges")

        # add calculate ?  how to design activity outcome ?

        # named ends with a default one (None)

        # build the question sequences

        # implement activity by generating new question instance

        # Merge questions when possible

        logger.info("extending the diagrams")
        
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