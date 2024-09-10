import abc
import logging
from tricc_oo.visitors.tricc import stashed_node_func
from tricc_og.models.base import TriccOperator
import datetime

logger = logging.getLogger('default')


class BaseExportStrategy:
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
        pass

    @staticmethod
    def tricc_operation_equal(ref_expressions):
        return ' = '.join(ref_expressions)
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    
    @staticmethod
    def tricc_operation_not_equal(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_not(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_and(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_or(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_or_and(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_native(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_istrue(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_isfalse(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_selected(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_more_or_equal(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_less_or_equal(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_more(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_less(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_between(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_case(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_if(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_contains(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_exists(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_has_qualifier(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_zscore(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_izscore(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_age_day(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_age_month(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    @staticmethod
    def tricc_operation_age_year(ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")

    OPERATOR_EXPORT = {
        TriccOperator.EQUAL: tricc_operation_equal,

    }  
## Utils
    def do_clean(self, **kwargs):
        pass
    def get_kwargs(self):
        return {} 
