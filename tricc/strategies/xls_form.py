'''
Strategy to build the skyp logic following the XLSForm way

'''

import datetime
import pandas as pd
from tricc.converters.tricc_to_xls_form import generate_xls_form_calculate, generate_xls_form_condition,  generate_xls_form_relevance


from tricc.serializers.xls_form import CHOICE_MAP, SURVEY_MAP, generate_xls_form_export
from tricc.strategies.base_strategy import BaseStrategy


class XLSFormStrategy(BaseStrategy):
    calculates= {}
    nodes = {}
    df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
    df_choice = pd.DataFrame(columns=CHOICE_MAP.keys())
    
    def generate_base(self,node, **kwargs):
        generate_xls_form_condition(node)
            


    def generate_relevance(self, node, **kwargs):
        generate_xls_form_relevance(node)

    def generate_calculate(self, node, **kwargs):
        generate_xls_form_calculate(node )
    
    
    def get_kwargs(self):
        
        return {'calculates':self.calculates, 'nodes':self.nodes, 'df_survey':self.df_survey, 'df_choice':self.df_choice }

        
        
    def generate_export(self, node, **kwargs):
        generate_xls_form_export(node, **kwargs)
    
    def do_export(self, output_file, form_id):
        # make a 'settings' tab
        now = datetime.datetime.now()
        version=now.strftime('%Y%m%d%H%M')
        indx=[[1]]

        settings={'form_title':'MSF - pediatric','form_id':form_id,'version':version,'default_language':'English (en)','style':'pages'}
        df_settings=pd.DataFrame(settings,index=indx)
        df_settings.head()

        #create a Pandas Excel writer using XlsxWriter as the engine
        writer = pd.ExcelWriter(output_file, engine='xlsxwriter')


        self.df_survey.to_excel(writer, sheet_name='survey',index=False)
        self.df_choice.to_excel(writer, sheet_name='choices',index=False)
        df_settings.to_excel(writer, sheet_name='settings',index=False)

        #close the Pandas Excel writer and output the Excel file
        writer.save()

        # run this on a windows python instance because if not then the generated xlsx file remains open
        #writer.close()
        writer.handles = None