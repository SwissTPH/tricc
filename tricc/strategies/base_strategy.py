import abc

from tricc.models import walktrhough_tricc_node


class BaseStrategy:
    
    ### walking funciton
    def process_base(self, activity, **kwargs):
        # for each node, check if condition is requried issubclass(TriccNodeDiplayModel)
        # process name
        walktrhough_tricc_node(activity.root, self.generate_base , **{**self.get_kwargs(),**kwargs})
        self.do_clean( **{**self.get_kwargs(),**kwargs})
        
    def process_relevance(self, activity, **kwargs):
        
        walktrhough_tricc_node(activity.root, self.generate_relevance, **{**self.get_kwargs(),**kwargs} )
        self.do_clean( **{**self.get_kwargs(),**kwargs})
        
    def process_calculate(self, activity, **kwargs):
        # call the strategy specific code
        walktrhough_tricc_node(activity.root, self.generate_calculate, **{**self.get_kwargs(),**kwargs} )
        self.do_clean(**{**self.get_kwargs(),**kwargs})
        
    def process_export(self, activity, **kwargs):
        walktrhough_tricc_node(activity.root, self.generate_export, **{**self.get_kwargs(),**kwargs} )
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
