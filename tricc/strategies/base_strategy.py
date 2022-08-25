import abc

from tricc.models import check_stashed_loop, walktrhough_tricc_node


class BaseStrategy:
    def stashed_node_func(self, node,callback, **kwargs):
        walktrhough_tricc_node(node, callback , **{**self.get_kwargs(),**kwargs})
        callback( node, **kwargs)
        ## MANAGE STASHED NODES
        prev_stashed_nodes = self.stashed_nodes.copy()
        loop_count = 0
        len_prev_processed_nodes = 0
        while len(self.stashed_nodes)>0:
            loop_count = check_stashed_loop(self.stashed_nodes,prev_stashed_nodes, self.processed_nodes,len_prev_processed_nodes, loop_count)
            prev_stashed_nodes = self.stashed_nodes.copy()
            len_prev_processed_nodes = len(self.processed_nodes)   
            if len(self.stashed_nodes)>0:
                s_node = self.stashed_nodes.pop(list(self.stashed_nodes.keys())[0])
                walktrhough_tricc_node(s_node, callback , **{**self.get_kwargs(),**kwargs})
    ### walking funciton
    def process_base(self, activity, **kwargs):
        # for each node, check if condition is requried issubclass(TriccNodeDiplayModel)
        # process name
        self.stashed_node_func(activity.root, self.generate_base, **{**self.get_kwargs(),**kwargs} )
        self.do_clean( **{**self.get_kwargs(),**kwargs})
        
    def process_relevance(self, activity, **kwargs):
        
        self.stashed_node_func(activity.root, self.generate_relevance, **{**self.get_kwargs(),**kwargs} )
        self.do_clean( **{**self.get_kwargs(),**kwargs})
        
    def process_calculate(self, activity, **kwargs):
        # call the strategy specific code
        self.stashed_node_func(activity.root, self.generate_calculate, **{**self.get_kwargs(),**kwargs} )
        self.do_clean(**{**self.get_kwargs(),**kwargs})
        
    def process_export(self, activity, **kwargs):
        self.stashed_node_func(activity.root, self.generate_export, **{**self.get_kwargs(),**kwargs} )
        self.do_clean(**{**self.get_kwargs(),**kwargs})
        
 
    # node function
    @abc.abstractmethod
    def generate_calculate(self, node, **kwargs ):
        pass 
    @abc.abstractmethod
    def generate_base(self, node, **kwargs):
        pass 

    
    @abc.abstractmethod
    def generate_relevance(self, node, **kwargs):
        pass
    
        
    @abc.abstractmethod
    def generate_export(self, node, **kwargs):
        pass
    @abc.abstractmethod
    def do_export(self, **kwargs):
        pass

## Utils
    def do_clean(self, **kwargs):
        pass
    def get_kwargs(self):
        return {} 
