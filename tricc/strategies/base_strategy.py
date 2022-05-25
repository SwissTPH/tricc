#import abc


from tricc.models import *
from tricc.services.utils import walktrhough_tricc_node

class BaseStrategy():
    def process_base(self,activity):
        # for each node, check if condition is requried issubclass(TriccNodeDiplayModel)
        # process name
        walktrhough_tricc_node(activity.root, self.generate_base , **self.get_kwargs())
    def process_relevance(self,activity):
        
        walktrhough_tricc_node(activity.root, self.generate_relevance, **self.get_kwargs() )

    def process_calculate(self,activity):
        # call the strategy specific code
        walktrhough_tricc_node(activity.root, self.generate_calculate, **self.get_kwargs() )
        
    def process_export(self,activity):
        walktrhough_tricc_node(activity.root, self.generate_export, **self.get_kwargs() )
        
    #@abc.abstractmethod
    def generate_calculate(self,node, **kwargs ):
        pass 
    
 
    def get_kwargs(self):
        return {} 

    #@abc.abstractmethod
    def generate_base(self,node, **kwargs):
        pass 

    
    #@abc.abstractmethod
    def generate_relevance(self,node, **kwargs):
        pass
    
        
    #@abc.abstractmethod
    def generate_export(self,node, **kwargs):
        pass
    
    
