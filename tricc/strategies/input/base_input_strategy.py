import abc

from tricc.models.tricc import stashed_node_func, TriccNodeMainStart, TriccNodeActivity, TriccEdge
from tricc.converters.utils import generate_id
from tricc.visitors.tricc import get_activity_wait
from itertools import chain
class BaseInputStrategy:

    input_path = None
    
    processes = [
        'main'
    ]
        
    def execute_linked_process(self, start_pages, pages):
        
        # create an overall activity only if not specified
        if 'main' not in  start_pages:
            # set the first proess as the first form the list
            if not self.processes[0] in start_pages:
                logger.error(f"MainStart without process or process in (None, main, {self.processes[0]}) mandatory or this strategy {self.__class__.__name__}")
            # copie the first root process data to use it on the app level
            root_process = start_pages[self.processes[0]][0].root
            root = TriccNodeMainStart(id = generate_id(), form_id =root_process.form_id , label = root_process.label)
            # first sets of activities don't require wait node
            root.next_nodes = start_pages[self.processes[0]]
            
            nodes = {page.id: page  for x in start_pages for page in start_pages[x] }
            nodes[root.id]=root 
            app = TriccNodeActivity(
                id = generate_id(),
                name = root_process.name,
                root = root,
                nodes = nodes,
                edges = [TriccEdge(id = generate_id(), source = root.id, target = x.id) for x in start_pages[self.processes[0]]]
            )
            root.activity = app
            # loop back to app to avoid None
            app.activity = app
            app.group = app
            # setting the activity/group to main
            for n in nodes.values():
                n.activity = app
                n.group = app
            #put a wait between group pf activities
            prev_process = start_pages[self.processes[0]]
            for process in self.processes[1:]:
                if process in start_pages:
                    wait = get_activity_wait([app.root], prev_process, start_pages[process])
                    prev_process = start_pages[process]
                    app.nodes[wait.id] = wait
            
            return app
    
    def __init__(self, input_path):
        self.input_path = input_path
    

    ### walking function
    @abc.abstractmethod
    def execute(in_filepath, media_path):
        pass