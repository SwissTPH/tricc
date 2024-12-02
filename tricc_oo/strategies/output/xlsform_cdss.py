from tricc_oo.models.tricc import TriccNodeActivity
from tricc_oo.serializers.xls_form import (get_diagnostic_add_line,
                                        get_diagnostic_line,
                                        get_diagnostic_none_line,
                                        get_diagnostic_start_group_line,
                                        get_diagnostic_stop_group_line)
from tricc_oo.converters.tricc_to_xls_form import get_export_name
from tricc_oo.strategies.output.xls_form import XLSFormStrategy



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
    def tricc_operation_zscore(self, ref_expressions):
        l = "instance('z_score')/root/item[gender=${gender} and x_max>"+ ref_expressions[0]+" and x_min<="+ ref_expressions[0]+"]/l" 
        m = "instance('z_score')/root/item[gender=${gender} and x_max>"+ ref_expressions[0]+" and x_min<="+ ref_expressions[0]+"]/m"
        s = "instance('z_score')/root/item[gender=${gender} and x_max>"+ ref_expressions[0]+" and x_min<="+ ref_expressions[0]+"]/s"
        #  return ((Math.pow((y / m), l) - 1) / (s * l));
        return f"(pow({ref_expressions[1]} div ({m}), {l}) -1) div (({s}) div ({l}))"
    
    def tricc_operation_izscore(self, ref_expressions):
        raise NotImplementedError(f"This type of opreration  is not supported in this strategy")
    def tricc_operation_age_day(self, ref_expressions):
        dob_node_name=  ref_expressions[0].value if not ref_expressions else 'birthday'
        return f'int((today()-date(${{{dob_node_name}}})))'
    def tricc_operation_age_month(self, ref_expressions):
        dob_node_name=  ref_expressions[0].value if not ref_expressions else 'birthday'
        return f'int((today()-date(${{{dob_node_name}}})) div 30.25)'
    def tricc_operation_age_year(self, ref_expressions):
        dob_node_name=  ref_expressions[0].value if not ref_expressions else 'birthday'
        return f'int((today()-date(${{{dob_node_name}}})) div 365.25)'
    
    