'''
Strategy to build the skyp logic following the XLSForm way

'''

from tricc.converters.tricc_to_xls_form import generate_xls_form_calculate, generate_xls_form_condition,  generate_xls_form_relevance

from tricc.models import *
from tricc.serializers.xls_form import generate_xls_form_export
from tricc.strategies.base_strategy import BaseStrategy


class XLSFormStrategy(BaseStrategy):
    calculates= {}
    nodes = {}

    def generate_base(self,node, **kwargs):
        generate_xls_form_condition(node)
            


    def generate_relevance(self, node, **kwargs):
        generate_xls_form_relevance(node)

    def generate_calculate(self, node, **kwargs):
        generate_xls_form_calculate(node )
    
    
    def get_kwargs(self):
        
        return {'calculates':self.calculates, 'nodes':self.nodes, }

        
        
    def generate_export(self, node, **kwargs):
        generate_xls_form_export(node, **kwargs)