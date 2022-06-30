'''
Strategy to build the skyp logic following the XLSForm way

'''

import datetime

import pandas as pd
from tricc.converters.tricc_to_xls_form import generate_xls_form_calculate, generate_xls_form_condition,  generate_xls_form_relevance
from tricc.models import TriccNodeActivity


from tricc.serializers.xls_form import CHOICE_MAP, SURVEY_MAP, end_group, generate_xls_form_export, start_group
from tricc.services.utils import walktrhough_tricc_node
from tricc.strategies.base_strategy import BaseStrategy
import logging
logger = logging.getLogger('default')


class XLSFormStrategy(BaseStrategy):
    calculates= {}
    processed_nodes = {}
    df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
    df_choice = pd.DataFrame(columns=CHOICE_MAP.keys())
    
    def generate_base(self,node, **kwargs):
        return generate_xls_form_condition(node, **kwargs)
            
    def generate_relevance(self, node, **kwargs):
        return generate_xls_form_relevance(node, **kwargs)

    def generate_calculate(self, node, **kwargs):
        return generate_xls_form_calculate(node, **kwargs )
    

    def do_clean(self, **kwargs):
        self.calculates= {}
        self.processed_nodes = {}
    
    def get_kwargs(self):  
        return {'calculates':self.calculates, 'processed_nodes':self.processed_nodes, 'df_survey':self.df_survey, 'df_choice':self.df_choice }  

    def generate_export(self, node, **kwargs):
        return generate_xls_form_export(node, **kwargs)

    def do_export(self, title , output_file, form_id):
        # make a 'settings' tab
        now = datetime.datetime.now()
        version=now.strftime('%Y%m%d%H%M')
        indx=[[1]]

        settings={'form_title':title,'form_id':form_id,'version':version,'default_language':'English (en)','style':'pages'}
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
    
    def process_export(self, activity, **kwargs):
        # The stashed node are all the node that have all their prevnode processed but not from the same group
        # This logic works only because the prev node are ordered by group/parent .. 
        stashed_nodes = {}
        groups= {}
        cur_group=activity
        groups[activity.id] = 0
        # keep the vesrions on the group id, max version
        start_group( cur_group=cur_group, groups=groups, **self.get_kwargs())
        walktrhough_tricc_node(activity.root, self.generate_export, stashed_nodes=stashed_nodes, cur_group = activity.root.group, **self.get_kwargs() )
        end_group( cur_group =activity, groups=groups, **self.get_kwargs())
        while len(stashed_nodes)>0:
            if len(stashed_nodes)>0:
                delta_len = 0
                s_node = stashed_nodes.pop(list(stashed_nodes.keys())[0])
                previous_len = len(self.df_survey)
                if cur_group == s_node.group:
                    # drop the end group
                    delta_len = -1
                    self.df_survey.drop(index=self.df_survey.index[-1], axis=0, inplace=True)
                else:
                    delta_len = +1
                    start_group( cur_group =s_node.group, groups=groups, relevance= isinstance(s_node, TriccNodeActivity),  **self.get_kwargs())          
                # arrange empty group
                walktrhough_tricc_node(s_node, self.generate_export, stashed_nodes=stashed_nodes, groups=groups,cur_group = s_node.group, **self.get_kwargs() )
                # add end group if new node where added OR if the previous end group was removed
                if delta_len == 1 and previous_len == (len(self.df_survey) - 1):
                    # remove start for empty group
                    logger.warning("group {} without content".format(s_node.group.label))
                    self.df_survey.drop(index=self.df_survey.index[-1], axis=0, inplace=True)
                else:
                    end_group( cur_group =s_node.group, groups=groups, **self.get_kwargs())
                cur_group = s_node.group