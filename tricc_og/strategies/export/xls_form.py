import abc
import logging
from tricc_oo.visitors.tricc import stashed_node_func
import datetime
from .base_export_strategy import BaseExportStrategy

logger = logging.getLogger('default')


class XLSFormStrategy(BaseExportStrategy):
    processes = ['main']
    output_path = None
    project = None
    # list of supported processes for the strategy, 
    # the order of the list will be apply
    
    def __init__(self, project, output_path):
        self.output_path = output_path
        self.project = project
    
    @abc.abstractmethod
    def execute(self, processes=[]):
        dandling_calculates = []
        # context need to have their own rules/calculate
        # all QS context will take the apply the upstream context
        # therefore the parser need to know current contextes AND between level and 
        # OR for concurrent contextes
        # all the node with only 1 context in the in_edge should be grouped together
        
        #1 creating the calculates for the contexts
        processed = []
        stashed = []
        
        if 'main' in self.project.impl_graph_process_start:
            main_start = self.project.impl_graph_process_start['main'][0]
            
        recursive_print(self.project.impl_graph, main_start, )
        
        

    def tricc_operation_equal(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_not_equal(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_not(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_and(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_or(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_or_and(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_native(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_istrue(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_isfalse(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_selected(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_more_or_equal(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_less_or_equal(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_more(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_less(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_between(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_case(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_if(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_contains(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_exists(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_has_qualifier(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_zscore(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_izscore(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_age_day(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_age_month(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_age_year(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")

## Utils
    def do_clean(self, **kwargs):
        pass
    def get_kwargs(self):
        return {} 
