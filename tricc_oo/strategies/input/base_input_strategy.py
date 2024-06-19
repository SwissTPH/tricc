import abc

from tricc_oo.models import (
    TriccNodeMainStart,
    TriccNodeActivity,
    TriccEdge,
)
from tricc_oo.converters.utils import generate_id
from tricc_oo.visitors.tricc import get_activity_wait, stashed_node_func, set_prev_next_node
from itertools import chain
import logging

logger = logging.getLogger("default")


class BaseInputStrategy:
    input_path = None

    processes = ["main"]

    def execute_linked_process(self, start_pages, pages):
        # create an overall activity only if not specified
        if "main" not in start_pages:
            # set the first proess as the first form the list
            if not self.processes[0] in start_pages:
                logger.error(
                    f"MainStart without process or process in (None, main, {self.processes[0]}) mandatory or this strategy {self.__class__.__name__}"
                )
            # copie the first root process data to use it on the app level
            root_process = start_pages[self.processes[0]][0].root
            root = TriccNodeMainStart(
                id=generate_id(), form_id=root_process.form_id, label=root_process.label
            )
            # first sets of activities don't require wait node
            root.next_nodes = set(start_pages[self.processes[0]])

            nodes = {page.id: page for x in start_pages for page in start_pages[x]}
            nodes[root.id] = root
            app = TriccNodeActivity(
                id=generate_id(), name=root_process.name, root=root, nodes=nodes
            )
            root.activity = app
            # loop back to app to avoid None
            app.activity = app
            app.group = app
            # setting the activity/group to main
            for n in nodes.values():
                n.activity = app
                n.group = app
            # put a wait between group pf activities
            prev_process = start_pages[self.processes[0]]
            for p in prev_process:
                set_prev_next_node(root, p, edge_only=True)
            for process in self.processes[1:]:
                if process in start_pages:
                    wait = get_activity_wait(
                        app.root,
                        prev_process,
                        start_pages[process],
                        edge_only=True,
                        activity=app,
                    )
                    app.nodes[wait.id] = wait
                    prev_process = start_pages[process]
                    # for p in prev_process:
                    #    set_prev_next_node(root,p)

            return app
        else:
            return start_pages["main"]

    def __init__(self, input_path):
        self.input_path = input_path

    ### walking function
    @abc.abstractmethod
    def execute(in_filepath, media_path):
        pass
