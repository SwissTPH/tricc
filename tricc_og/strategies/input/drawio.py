import logging
import os
from copy import copy
from pathlib import Path
import networkx as nx
import matplotlib.pyplot as plt

from tricc_og.builders.xml_to_tricc import create_activity

# from tricc_oo.visitors.tricc import (
#     process_calculate,
#     set_prev_next_node,
#     replace_node,
#     stashed_node_func,
# )
from tricc_og.models.base import TriccBaseModel, TriccProject
from tricc_og.strategies.input.base_input_strategy import BaseInputStrategy
from tricc_og.parsers.xml import read_drawio

logger = logging.getLogger("default")


class DrawioStrategy(BaseInputStrategy):
    processes = [
        "triage",
        "registration",
        "emergency-care",
        "local-urgent-care",
        "actue-tertiary-care",
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
        files = []
        pages = {}
        diagrams = []
        start_pages = {}
        # read all pages
        logger.info("# Reading the input file")
        if os.path.isdir(in_filepath):
            files = [f for f in os.listdir(in_filepath) if f.endswith(".drawio")]
        elif os.path.isfile(in_filepath):
            files = [in_filepath]
        else:
            logger.error(f"no input file found at {in_filepath}")
            exit()
        for file in files:
            diagrams += read_drawio(file)
        logger.info("# creating the project and loading the diagrams")
        project = TriccProject(
            code=Path(in_filepath).stem,
            label=Path(in_filepath).stem,
        )
        for diagram in diagrams:
            logger.info("Create the activity {0}".format(diagram.attrib.get("name")))
            create_activity(project, diagram, media_path)

        self.save_graph(project.graph, "loaded.png")
        logger.info("extending the diagrams")

        return project

    def save_graph(self, project, filename):
        pos = nx.spring_layout(project.graph)
        scale_factor = 2
        pos = {
            node: (scale_factor * x, scale_factor * y) for node, (x, y) in pos.items()
        }
        nx.draw(
            project.graph,
            pos,
            with_labels=True,
            node_color="skyblue",
            node_size=200,
            edge_color="gray",
            font_size=8,
            font_color="black",
        )
        edge_labels = nx.get_edge_attributes(project.graph, "label")
        nx.draw_networkx_edge_labels(project.graph, pos, edge_labels=edge_labels)
        plt.savefig(filename, dpi=300)
