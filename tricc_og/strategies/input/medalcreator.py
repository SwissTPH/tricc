import logging
import os
import json
from pathlib import Path
import networkx as nx
import matplotlib.pyplot as plt

from tricc_og.builders.mc_to_tricc import (
    import_mc_nodes,
    get_registration_nodes,
    import_mc_flow_from_diagnose,
    add_formula_association_flow,
    fullorder_to_order,
    import_mc_flow_from_qss,
    make_implementation,
    unloop_from_node,
    get_start_node,
    QUESTION_SYSTEM,
    DIAGNOSE_SYSTEM,
    MANDATORY_STAGE,
    import_mc_flow_from_diagram,
)
from tricc_og.models.base import TriccBaseModel, TriccProject
from tricc_og.strategies.input.base_input_strategy import BaseInputStrategy
from tricc_og.parsers.xml import read_drawio
from tricc_og.visitors.tricc_project import get_element, add_flow

logger = logging.getLogger("default")


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
        # load on questions
        for node_id in js_nodes:
            node = import_mc_nodes(js_nodes[node_id], QUESTION_SYSTEM, project, js_fullorder, start)
            
        add_formula_association_flow(project)
        # build other sequences
        js_diagnoses = js_full["medal_r_json"]["diagnoses"]
        yi_cc_id = js_full["medal_r_json"]["config"]["basic_questions"]["general_cc_id"]
        child_cc_id = js_full["medal_r_json"]["config"]["basic_questions"][
            "yi_general_cc_id"
        ]
        
        # (set_of_elements, class_name, system, code, version=None)
        main_complain_yi = get_element(project.graph, QUESTION_SYSTEM, yi_cc_id)
        main_complain_child = get_element(project.graph, QUESTION_SYSTEM, child_cc_id)
        # main start
        import_mc_flow_from_diagram(
                js_diagram, QUESTION_SYSTEM, project.graph, start
            )
        for node_id in js_diagnoses:
            import_mc_flow_from_diagnose(
                js_diagnoses[node_id], DIAGNOSE_SYSTEM, project, start
            )

        # make the implementation version
        make_implementation(project)
        logger.info(f"implementatin graph have {project.impl_graph.number_of_edges()} edges")
        start_impl = start.instances[0]
        # image
        self.save_simple_graph(project.impl_graph, start_impl, "loaded.png")
        order = fullorder_to_order(js_fullorder)
        unloop_from_node(project.impl_graph, start_impl, order)
        logger.info(f"implementatin graph have {project.impl_graph.number_of_edges()} edges")
        # image
        self.save_simple_graph(project.impl_graph, start_impl, "unlooped.png")
        # make QS
        # 1- create QS flow
        # 2- attached named output (conditionnal flow or calculate)
        # 3- "inject" qs as question list / or activity abstract + implementation
        import_mc_flow_from_qss(
                js_nodes, project, start_impl, order
            )
        # image
        self.save_simple_graph(project.impl_graph, start_impl, "qs_loaded.png")
        self.save_simple_tree(project.impl_graph, start_impl.scv(), "tree.png")
        logger.info(f"implementatin graph have {project.impl_graph.number_of_edges()} edges")

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
        
        
def hierarchical_pos(G, root, width=1., pos=None, vert_gap=0.2, vert_loc=0, xcenter=0.5):
    if not pos:
        pos = {root: (xcenter, vert_loc)}
    neighbors = [e[1] for e in G.edges(root)]
    if len(neighbors) != 0:
        dx = width / len(neighbors) 
        nextx = xcenter - width/2 - dx/2
        for neighbor in neighbors:
            if all([e[0] in pos for e in G.in_edges(neighbor)]):
                nextx += dx
                pos[neighbor] = (nextx, vert_loc - vert_gap)
                hierarchical_pos(G, neighbor, pos=pos, width=dx, vert_gap=vert_gap, 
                                            vert_loc=vert_loc-vert_gap, xcenter=nextx)
            else:
                pass
    
    return pos


def left_to_right_layout(G, ref_node):
    path_lengths = dict(nx.single_source_shortest_path_length(G, ref_node))
    nodes = {}
    isolated = []
    for node in G.nodes():
        nodes[node] = (path_lengths[node] if node in path_lengths else -1, random.random())
        if nodes[node][0] == -1:
            if not G.in_edges(node) and not G.edges(node):
                isolated.append(node)
            elif not G.in_edges(node):
                logger.warning(f"node {node} is dandling")
    for node in isolated:
        logger.debug(f"node {node} is isolated")
            
                    
    return nodes