from tricc.models.tricc import TriccNodeActivity
from tricc.serializers.xls_form import (get_diagnostic_add_line,
                                        get_diagnostic_line,
                                        get_diagnostic_none_line,
                                        get_diagnostic_start_group_line,
                                        get_diagnostic_stop_group_line)
from tricc.converters.tricc_to_xls_form import get_export_name
from tricc.strategies.xls_form import XLSFormStrategy


class XLSFormCDSSStrategy(XLSFormStrategy):
    def process_export(self, activity,  **kwargs):
        super().process_export( activity,  **kwargs)
        # add the diag
        self.df_survey.loc[len(self.df_survey)] = get_diagnostic_start_group_line()
        # TODO inject flow driven diag list, the folowing fonction will fill the missing ones
        diags = self.export_diag( activity,  **kwargs)
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