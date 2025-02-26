import abc
import logging
from tricc_oo.visitors.tricc import stashed_node_func
import datetime

logger = logging.getLogger('default')


class BaseOutPutStrategy:
    processes = ['main']
    project = None
    output_path = None
    # list of supported processes for the strategy, 
    # the order of the list will be apply
    
    def __init__(self, project, output_path):
        self.output_path = output_path
        self.project = project
    
    def get_tricc_operation_expression(self, operation):
        raise NotImplemented("get_tricc_operation_expression not implemented")
    
    def execute(self):
        
        version = datetime.datetime.now().strftime("%Y%m%d%H%M")
        logger.info(f"build version: {version}")
        if 'main' in self.project.start_pages:
            self.process_base(self.project.start_pages, pages=self.project.pages, version=version)
        else:
            logger.critical("Main process required")


        logger.info("generate the relevance based on edges")

        
        
        # create relevance Expression

        # create calculate Expression
        self.process_calculate(self.project.start_pages, pages=self.project.pages)
        logger.info("generate the export format")
         # create calculate Expression
        self.process_export(self.project.start_pages, pages=self.project.pages)
             
        logger.info("print the export")
        
        self.export(self.project.start_pages, version=version)
    
    ### walking function
    def process_base(self, start_pages, **kwargs):
        # for each node, check if condition is required issubclass(TriccNodeDisplayModel)
        # process name
        stashed_node_func(start_pages[self.processes[0]].root, self.generate_base, **{**self.get_kwargs(),**kwargs} )
        self.do_clean( **{**self.get_kwargs(),**kwargs})
        
    def process_relevance(self, start_pages, **kwargs):
        
        stashed_node_func(start_pages[self.processes[0]].root, self.generate_relevance, **{**self.get_kwargs(),**kwargs} )
        self.do_clean( **{**self.get_kwargs(),**kwargs})
        
    def process_calculate(self, start_pages, **kwargs):
        # call the strategy specific code
        stashed_node_func(start_pages[self.processes[0]].root, self.generate_calculate, **{**self.get_kwargs(),**kwargs} )
        self.do_clean(**{**self.get_kwargs(),**kwargs})
        
    def process_export(self, start_pages, **kwargs):
        stashed_node_func(start_pages[self.processes[0]].root, self.generate_export, **{**self.get_kwargs(),**kwargs} )
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
    def export(self, **kwargs):
        pass
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
    def tricc_operation_concatenate(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
## Utils
    def do_clean(self, **kwargs):
        pass
    def get_kwargs(self):
        return {} 
