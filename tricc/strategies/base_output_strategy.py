import abc

from tricc.models.tricc import stashed_node_func


class BaseOutPutStrategy:

    output_path = None
    def __init__(self, output_path):
        self.output_path = output_path
    

    ### walking function
    def process_base(self, activity, **kwargs):
        # for each node, check if condition is required issubclass(TriccNodeDisplayModel)
        # process name
        stashed_node_func(activity.root, self.generate_base, **{**self.get_kwargs(),**kwargs} )
        self.do_clean( **{**self.get_kwargs(),**kwargs})
        
    def process_relevance(self, activity, **kwargs):
        
        stashed_node_func(activity.root, self.generate_relevance, **{**self.get_kwargs(),**kwargs} )
        self.do_clean( **{**self.get_kwargs(),**kwargs})
        
    def process_calculate(self, activity, **kwargs):
        # call the strategy specific code
        stashed_node_func(activity.root, self.generate_calculate, **{**self.get_kwargs(),**kwargs} )
        self.do_clean(**{**self.get_kwargs(),**kwargs})
        
    def process_export(self, activity, **kwargs):
        stashed_node_func(activity.root, self.generate_export, **{**self.get_kwargs(),**kwargs} )
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
