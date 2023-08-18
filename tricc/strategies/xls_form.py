'''
Strategy to build the skyp logic following the XLSForm way

'''

import datetime
import logging
import os

import pandas as pd

from tricc.converters.tricc_to_xls_form import (generate_xls_form_calculate,
                                                generate_xls_form_condition,
                                                generate_xls_form_relevance)
from tricc.models.tricc import (TriccNodeActivity, check_stashed_loop,
                          walktrhough_tricc_node_processed_stached, TriccGroup)
from tricc.serializers.xls_form import (CHOICE_MAP, SURVEY_MAP, end_group,
                                        generate_xls_form_export, start_group)
from tricc.strategies.base_output_strategy import BaseOutPutStrategy

logger = logging.getLogger('default')


class XLSFormStrategy(BaseOutPutStrategy):

    df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
    df_calculate = pd.DataFrame(columns=SURVEY_MAP.keys())
    df_choice = pd.DataFrame(columns=CHOICE_MAP.keys())
    
    
            # add save nodes and merge nodes
    
    def generate_base(self,node, **kwargs):
        return generate_xls_form_condition(node, **kwargs)
            
    def generate_relevance(self, node, **kwargs):
        return  generate_xls_form_relevance(node, **kwargs)

    def generate_calculate(self, node, **kwargs):
        return generate_xls_form_calculate( node, **kwargs)


    def __init__(self, output_path):
        super().__init__( output_path)
        self.do_clean()

    def do_clean(self, **kwargs):
        self.calculates= {}
        self.used_calculates = {}
        
    
    def get_kwargs(self):  
        return { 
            'df_survey':self.df_survey, 
            'df_choice':self.df_choice,
            'df_calculate':self.df_calculate
            }  

    def generate_export(self, node, **kwargs):
        return generate_xls_form_export(node, **kwargs)

    def do_export(self, title , file_name, form_id):
        # make a 'settings' tab
        now = datetime.datetime.now()
        version=now.strftime('%Y%m%d%H%M')
        indx=[[1]]

        settings={'form_title':title,'form_id':form_id,'version':version,'default_language':'English (en)','style':'pages'}
        df_settings=pd.DataFrame(settings,index=indx)
        df_settings.head()
        
        newpath = os.path.join(self.output_path, file_name)
        #create a Pandas Excel writer using XlsxWriter as the engine
        writer = pd.ExcelWriter(newpath, engine='xlsxwriter')
        self.df_survey.to_excel(writer, sheet_name='survey',index=False)
        self.df_choice.to_excel(writer, sheet_name='choices',index=False)
        df_settings.to_excel(writer, sheet_name='settings',index=False)

        #close the Pandas Excel writer and output the Excel file
        #writer.save()

        # run this on a windows python instance because if not then the generated xlsx file remains open
        writer.close()
        #writer.handles = None
    
    def process_export(self, activity,  **kwargs):
        # The stashed node are all the node that have all their prevnode processed but not from the same group
        # This logic works only because the prev node are ordered by group/parent .. 
        processed_nodes = []
        stashed_nodes =  []
        skip_header = 0
        groups= {}
        cur_group=activity
        groups[activity.id] = 0
        path_len = 0
        # keep the vesrions on the group id, max version
        start_group( cur_group=cur_group, groups=groups, **self.get_kwargs())
        walktrhough_tricc_node_processed_stached(activity.root, self.generate_export, processed_nodes, stashed_nodes,path_len , cur_group = activity.root.group, **self.get_kwargs() )
        end_group( cur_group =activity, groups=groups, **self.get_kwargs())
        # we save the survey data frame
        df_survey_final =   pd.DataFrame(columns=SURVEY_MAP.keys())
        self.df_calculate=   pd.DataFrame(columns=SURVEY_MAP.keys())
        if len(self.df_survey)>(2+skip_header):
            df_survey_final = self.df_survey
        ## MANAGE STASHED NODES
        prev_stashed_nodes = stashed_nodes.copy()
        loop_count = 0
        len_prev_processed_nodes = 0
        while len(stashed_nodes)>0:
            self.df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
            loop_count = check_stashed_loop(stashed_nodes,prev_stashed_nodes, processed_nodes,len_prev_processed_nodes, loop_count)
            prev_stashed_nodes = stashed_nodes.copy()
            len_prev_processed_nodes = len(processed_nodes)   
            if len(stashed_nodes)>0:
                s_node = stashed_nodes.pop()
                #while len(stashed_nodes)>0 and isinstance(s_node,TriccGroup):
                #    s_node = stashed_nodes.pop()
                if len(s_node.prev_nodes)>0:
                    path_len = sorted(s_node.prev_nodes, key=lambda p_node:p_node.path_len, reverse=True )[0].path_len+1
                if s_node.group is None:
                    logger.error("ERROR group is none for node {}".format(s_node.get_name()))
                start_group( cur_group =s_node.group, groups=groups, relevance= True,  **self.get_kwargs())
                # arrange empty group
                walktrhough_tricc_node_processed_stached(s_node, self.generate_export, processed_nodes, stashed_nodes, path_len, groups=groups,cur_group = s_node.group, **self.get_kwargs() )
                # add end group if new node where added OR if the previous end group was removed
                end_group( cur_group =s_node.group, groups=groups, **self.get_kwargs())
                # if two line then empty grou
                if len(self.df_survey)>(2+skip_header):
                    if cur_group == s_node.group:
                        # drop the end group (to merge)
                        logger.debug("printing same group {}::{}::{}::{}".format(s_node.group.__class__, s_node.group.get_name(),s_node.id, s_node.group.instance))
                        df_survey_final.drop(index=df_survey_final.index[-1], axis=0, inplace=True)
                        self.df_survey = self.df_survey[(1+skip_header):]
                        df_survey_final=pd.concat([df_survey_final, self.df_survey], ignore_index=True)

                    else:
                        logger.debug("printing group {}::{}::{}::{}".format(s_node.group.__class__, s_node.group.get_name(),s_node.id,s_node.group.instance))
                        df_survey_final =pd.concat([df_survey_final, self.df_survey], ignore_index=True)
                    cur_group = s_node.group
                    
                    
        # add the calulate
        self.df_survey = pd.concat([df_survey_final,self.df_calculate], ignore_index=True)
        
        # remove duplicate calculate
        
        df_calculate = self.df_survey[self.df_survey.type == 'calculate']
        
        for index, calc_row in df_calculate.iterrows():
            df_calculate_duplicate = df_calculate[(df_calculate.calculation == calc_row.calculation) & (df_calculate.name != calc_row.name)]
            if len(df_calculate_duplicate)>0:
                for id_d, calc_row_d in df_calculate_duplicate.iterrows():
                    logger.debug('duplicate found and removed for %s: %s', calc_row.name, calc_row.calculation)
                    self.df_survey.drop(id_d)
                    self.df_survey.replace(calc_row_d.name, calc_row.name)
                    
            

