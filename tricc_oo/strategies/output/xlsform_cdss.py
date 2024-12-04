import logging
from tricc_oo.models.tricc import TriccNodeActivity
from tricc_oo.serializers.xls_form import (get_diagnostic_add_line,
                                        get_diagnostic_line,
                                        get_diagnostic_none_line,
                                        get_diagnostic_start_group_line,
                                        get_diagnostic_stop_group_line)
from tricc_oo.converters.tricc_to_xls_form import get_export_name
from tricc_oo.strategies.output.xls_form import XLSFormStrategy
from tricc_oo.models.lang import SingletonLangClass
langs = SingletonLangClass()
logger = logging.getLogger("default")



class XLSFormCDSSStrategy(XLSFormStrategy):

            
    
    def process_export(self, start_pages,  **kwargs):
        diags = []
        self.activity_export(start_pages[self.processes[0]], **kwargs)

        diags += self.export_diag( start_pages[self.processes[0]],  **kwargs)

        # add the diag
        self.df_survey.loc[len(self.df_survey)] = get_diagnostic_start_group_line()
        # TODO inject flow driven diag list, the folowing fonction will fill the missing ones
        
        if len(diags)>0:
            for diag in diags:
                self.df_survey.loc[len(self.df_survey)] = get_diagnostic_line(diag)
            self.df_survey.loc[len(self.df_survey)] = get_diagnostic_none_line(diags)
            self.df_survey.loc[len(self.df_survey)] = get_diagnostic_add_line(diags, self.df_choice)
            
            self.df_survey.loc[len(self.df_survey)] = get_diagnostic_stop_group_line()
        #TODO inject the TT flow
        self.add_tab_breaks_choice()
        self.add_wfx_choice()
        
                

    def export_diag(self, activity, diags = [], **kwargs):
        for node in activity.nodes.values():
            if isinstance(node, TriccNodeActivity):
                diags = self.export_diag(node, diags, **kwargs)
            if hasattr(node, 'name') and node.name is not None:
                if node.name.startswith('diag') and node.last\
                    and not any([get_export_name(diag)  == get_export_name(node) for diag in diags]):
                        diags.append(node)
        return diags
    def tricc_operation_has_qualifier(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_age_day(self, ref_expressions):
        dob_node_name=  ref_expressions[0].value if  ref_expressions else 'birthday'
        return f'int((today()-date(${{{dob_node_name}}})))'
    def tricc_operation_age_month(self, ref_expressions):
        dob_node_name=  ref_expressions[0].value if ref_expressions else 'birthday'
        return f'int((today()-date(${{{dob_node_name}}})) div 30.25)'
    def tricc_operation_age_year(self, ref_expressions):
        dob_node_name=  ref_expressions[0].value if ref_expressions else 'birthday'
        return f'int((today()-date(${{{dob_node_name}}})) div 365.25)'
    
    
    def add_wfx_choice(self):
        new_rows = [
            ['wfl', 'y45_0', 'f', 0, 110, -0.3833, 0.09029, 2.4607],
            ['wfa', 'y45_1', 'f', 0, 18500, -0.3833, 0.0903, 2.4777],
            ['wfh', 'y45_2', 'f', 0, 125, -0.3833, 0.0903, 2.4947],
        ]
        
        for row in new_rows:
            self.df_choice.loc[len(self.df_choice)] = row
            
        label = langs.get_trads('hidden', force_dict =True)
        empty = langs.get_trads('', force_dict =True)
        self.df_survey.loc[len(self.df_survey)] = [
            'select_one wfl',
            "wfl",
            *list(label.values()) ,
            *list(empty.values()) ,#hint
            *list(empty.values()) ,#help
            '',#default
            '',#'appearance', clean_name
            '',#'constraint', 
            *list(empty.values()) ,#'constraint_message'
            '0',#'relevance'
            '',#'disabled'
            '1',#'required'
            *list(empty.values()) ,#'required message'
            '',#'read only'
            '',#'expression'
            '',#'repeat_count'
            ''#'image'  
        ]
        self.df_survey.loc[len(self.df_survey)] = [
            'select_one wfa',
            "wfa",
            *list(label.values()) ,
            *list(empty.values()) ,#hint
            *list(empty.values()) ,#help
            '',#default
            '',#'appearance', clean_name
            '',#'constraint', 
            *list(empty.values()) ,#'constraint_message'
            '0',#'relevance'
            '',#'disabled'
            '1',#'required'
            *list(empty.values()) ,#'required message'
            '',#'read only'
            '',#'expression'
            '',#'repeat_count'
            ''#'image'  
        ]
        self.df_survey.loc[len(self.df_survey)] = [
            'select_one wfh',
            "wfh",
            *list(label.values()) ,
            *list(empty.values()) ,#hint
            *list(empty.values()) ,#help
            '',#default
            '',#'appearance', clean_name
            '',#'constraint', 
            *list(empty.values()) ,#'constraint_message'
            '0',#'relevance'
            '',#'disabled'
            '1',#'required'
            *list(empty.values()) ,#'required message'
            '',#'read only'
            '',#'expression'
            '',#'repeat_count'
            ''#'image'  
        ]
    
    def add_tab_breaks_choice(self):
        label = langs.get_trads('hidden', force_dict =True)
        empty = langs.get_trads('', force_dict =True)
        self.df_survey.loc[len(self.df_survey)] = [
            'select_one tab-label-4',
            "tab_label_4",
            *list(label.values()) ,
            *list(empty.values()) ,#hint
            *list(empty.values()) ,#help
            '',#default
            '',#'appearance', clean_name
            '',#'constraint', 
            *list(empty.values()) ,#'constraint_message'
            '0',#'relevance'
            '',#'disabled'
            '1',#'required'
            *list(empty.values()) ,#'required message'
            '',#'read only'
            '',#'expression'
            '',#'repeat_count'
            ''#'image'  
        ]
        new_rows = [
            ['tab-label-4', 0, langs.get_trads('--'),'','','','',''],
            ['tab-label-4', 1, langs.get_trads('--'),'','','','',''],
            ['tab-label-4', 2, langs.get_trads('1/2'),'','','','',''],
            ['tab-label-4', 3, langs.get_trads('1/2'),'','','','',''],
            ['tab-label-4', 4, langs.get_trads('1'),'','','','',''],
            ['tab-label-4', 5, langs.get_trads('1'),'','','','',''],
            ['tab-label-4', 6, langs.get_trads('1 and 1/2'),'','','','',''],
            ['tab-label-4', 7, langs.get_trads('1 and 1/2'),'','','','',''],
            ['tab-label-4', 8, langs.get_trads('2'),'','','','',''],
            ['tab-label-4', 9, langs.get_trads('2'),'','','','',''],
            ['tab-label-4', 10, langs.get_trads('2 and 1/2'),'','','','',''],
            ['tab-label-4', 11, langs.get_trads('2 and 1/2'),'','','','',''],
            ['tab-label-4', 12, langs.get_trads('3'),'','','','',''],
            ['tab-label-4', 13, langs.get_trads('3'),'','','','',''],
            ['tab-label-4', 14, langs.get_trads('3 and 1/2'),'','','','',''],
            ['tab-label-4', 15, langs.get_trads('3 and 1/2'),'','','','',''],
            ['tab-label-4', 16, langs.get_trads('4'),'','','','',''],
            ['tab-label-4', 17, langs.get_trads('4'),'','','','',''],
            ['tab-label-4', 18, langs.get_trads('4 and 1/2'),'','','','',''],
            ['tab-label-4', 19, langs.get_trads('4 and 1/2'),'','','','',''],
            ['tab-label-4', 20, langs.get_trads('5'),'','','','',''],
            ['tab-label-4', 21, langs.get_trads('5'),'','','','',''],
            ['tab-label-4', 22, langs.get_trads('5 and 1/2'),'','','','',''],
            ['tab-label-4', 23, langs.get_trads('5 and 1/2'),'','','','',''],
            ['tab-label-4', 24, langs.get_trads('6'),'','','','',''],
            ['tab-label-4', 25, langs.get_trads('6'),'','','','',''],
            ['tab-label-4', 26, langs.get_trads('6 and 1/2'),'','','','',''],
            ['tab-label-4', 27, langs.get_trads('6 and 1/2'),'','','','',''],
            ['tab-label-4', 28, langs.get_trads('7'),'','','','',''],
            ['tab-label-4', 29, langs.get_trads('7'),'','','','',''],
            ['tab-label-4', 30, langs.get_trads('7 and 1/2'),'','','','',''],
            ['tab-label-4', 31, langs.get_trads('7 and 1/2'),'','','','',''],
            ['tab-label-4', 32, langs.get_trads('8'),'','','','',''],
            ['tab-label-4', 33, langs.get_trads('8'),'','','','',''],
            ['tab-label-4', 34, langs.get_trads('8 and 1/2'),'','','','',''],
            ['tab-label-4', 35, langs.get_trads('8 and 1/2'),'','','','',''],
            ['tab-label-4', 36, langs.get_trads('9'),'','','','',''],
            ['tab-label-4', 37, langs.get_trads('9'),'','','','',''],
            ['tab-label-4', 38, langs.get_trads('9 and 1/2'),'','','','',''],
            ['tab-label-4', 39, langs.get_trads('9 and 1/2'),'','','','',''],
            ['tab-label-4', 40, langs.get_trads('10'),'','','','','']
        ]
        for row in new_rows:
            self.df_choice.loc[len(self.df_choice)] = row