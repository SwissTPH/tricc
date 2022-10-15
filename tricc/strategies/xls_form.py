'''
Strategy to build the skyp logic following the XLSForm way

'''

import datetime
import logging

import pandas as pd

from tricc.converters.tricc_to_xls_form import (generate_xls_form_calculate,
                                                generate_xls_form_condition,
                                                generate_xls_form_relevance)
from tricc.models import (TriccNodeActivity, check_stashed_loop,
                          walktrhough_tricc_node_processed_stached)
from tricc.serializers.xls_form import (CHOICE_MAP, SURVEY_MAP, end_group,
                                        generate_xls_form_export,
                                        get_diagnostic_line,
                                        get_diagnostic_none_line,
                                        get_diagnostic_start_group_line,
                                        get_diagnostic_stop_group_line,
                                        start_group)
from tricc.strategies.base_strategy import BaseStrategy

logger = logging.getLogger('default')


class XLSFormStrategy(BaseStrategy):

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


    def __init__(self):
        self.calculates= {}
        self.used_calculates = {}

    def do_clean(self, **kwargs):
        self.__init__()
    
    def get_kwargs(self):  
        return { 
            'df_survey':self.df_survey, 
            'df_choice':self.df_choice,
            'df_calculate':self.df_calculate
            }  

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
                        logger.info("printing same group {}::{}::{}::{}".format(s_node.group.__class__, s_node.group.get_name(),s_node.id, s_node.group.instance))
                        df_survey_final.drop(index=df_survey_final.index[-1], axis=0, inplace=True)
                        self.df_survey = self.df_survey[(1+skip_header):]
                        df_survey_final=pd.concat([df_survey_final, self.df_survey], ignore_index=True)

                    else:
                        logger.info("printing group {}::{}::{}::{}".format(s_node.group.__class__, s_node.group.get_name(),s_node.id,s_node.group.instance))
                        df_survey_final =pd.concat([df_survey_final, self.df_survey], ignore_index=True)
                    cur_group = s_node.group
        # add the calulate
        self.df_survey = pd.concat([df_survey_final,self.df_calculate], ignore_index=True)
        # add the diag
        self.df_survey.loc[len(self.df_survey)] = get_diagnostic_start_group_line()
        # TODO inject flow driven diag list, the folowing fonction will fill the missing ones
        diags = self.export_diag( activity,  **kwargs)
        self.df_survey.loc[len(self.df_survey)] = get_diagnostic_none_line(diags)
        self.df_survey.loc[len(self.df_survey)] = get_diagnostic_stop_group_line()
        #TODO inject the TT flow
        
        
                

    def export_diag(self, activity, diags = [], **kwargs):
        for node in activity.nodes.values():
            if isinstance(node, TriccNodeActivity):
                diags = self.export_diag(node, diags, **kwargs)
            if hasattr(node, 'name') and node.name is not None:
                if node.name.startswith('diag_'):
                    nb_found = len(self.df_survey[self.df_survey.name == "label_"+node.name])
                    if node.last == True and nb_found == 0:
                        self.df_survey.loc[len(self.df_survey)] = get_diagnostic_line(node)
                        diags.append(node)
        return diags
