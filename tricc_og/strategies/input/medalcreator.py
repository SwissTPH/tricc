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
    import_mc_flow_from_qs,
    make_implementation,
    unloop_from_node,
    get_start_node,
    QUESTION_SYSTEM,
    DIAGNOSE_SYSTEM
)
from tricc_og.models.base import TriccBaseModel, TriccProject
from tricc_og.strategies.input.base_input_strategy import BaseInputStrategy
from tricc_og.parsers.xml import read_drawio
from tricc_og.visitors.tricc_project import get_element

logger = logging.getLogger("default")


import random


class MedalCStrategy(BaseInputStrategy):
    processes = [
        "triage",
        "registration",
        "emergency-care",
        "local-urgent-care",
        "acute-tertiary-care",
        "history-and-physical",
        "diagnostic-testing",
        "determine-diagnosis",
        "provide-counseling",
        "dispense-medications",
        "monitor-and-follow-up-of-patient",
        "alerts-reminders-education",
        "discharge-referral-of-patient",
        "charge-for-service",
        "record-and-report",
    ]

    def execute(self, in_filepath, media_path):
        # reading input file
        # pages = {}
        diagrams = []
        # start_pages = {}
        # read all pages
        logger.info("# Reading the input file")

        if os.path.isfile(in_filepath):
            f = open(in_filepath)
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
        # generate and add generic nodes
        std_nodes = get_registration_nodes()
        for node_id in std_nodes:
            import_mc_nodes(std_nodes[node_id], "questions", project)
        # load on questions
        for node_id in js_nodes:
            import_mc_nodes(js_nodes[node_id], "questions", project)
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
        start = get_start_node(project)
        for node_id in js_diagnoses:
            import_mc_flow_from_diagnose(
                js_diagnoses[node_id], DIAGNOSE_SYSTEM, project, start
            )

        # make the implementation version
        make_implementation(project)
        logger.info(f"implementatin graph have {project.impl_graph.number_of_edges()} edges")
        start_impl = start.instances[0]
        self.save_simple_graph(project.impl_graph, start_impl, "loaded.png")
        # find cycle
        unloop_from_node(project.impl_graph, start_impl)
        logger.info(f"implementatin graph have {project.impl_graph.number_of_edges()} edges")

        self.save_simple_graph(project.impl_graph, start_impl, "unlooped.png")
        # make QS
        # 1- create QS flow
        # 2- attached named output (conditionnal flow or calculate)
        # 3- "inject" qs as question list / or activity abstract + implementation
        for node_id in js_nodes:
            if js_nodes[node_id]["type"] == "QuestionsSequence":
                import_mc_flow_from_qs(
                    js_nodes[node_id], "questions", project, start_impl
                )
        self.save_simple_graph(project.impl_graph, start_impl, "qs_loaded.png")
        logger.info(f"implementatin graph have {project.impl_graph.number_of_edges()} edges")

        unloop_from_node(project.impl_graph, start)
        self.save_simple_graph(project.impl_graph, start_impl, "qs_unlooped.png")
        # unloop / make instance
        logger.info(f"implementatin graph have {project.impl_graph.number_of_edges()} edges")

        # add calculate ?  how to design activity outcome ?
        # named ends with a default one (None)
        
        
        

        
        # build the question sequences

        # implement activity by generating new question instance

        # Merge questions when possible
        
        
        
        
        
        self.save_simple_graph(project.graph, start, 'loaded.png')

        
        
        
        self.save_simple_graph(project.graph, start, 'loaded.png')
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


def left_to_right_layout(G, ref_node):
    path_lengths = dict(nx.single_source_shortest_path_length(G, ref_node))
    nodes = {}
    for node in G.nodes():
        nodes[node] = (path_lengths[node] if node in path_lengths else -1, random.random())
        if nodes[node][0] == -1:
            logger.error(f"node {node} is dandling")    
    return nodes