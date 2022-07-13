'''
Strategy to build the skyp logic following the XLSForm way

'''

import datetime
from typing import Dict

import pandas as pd
from tricc.converters.tricc_to_xls_form import generate_xls_form_calculate, generate_xls_form_condition,  generate_xls_form_relevance
from tricc.models import TriccNodeActivity,walktrhough_tricc_node


from tricc.serializers.xls_form import CHOICE_MAP, SURVEY_MAP, end_group, generate_xls_form_export, start_group
from tricc.strategies.base_strategy import BaseStrategy
import logging
logger = logging.getLogger('default')


class XLSFormStrategy(BaseStrategy):
    processed_nodes = {}
    stashed_nodes = {}
    used_calculates = {}
    calculates = {}
    df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
    df_choice = pd.DataFrame(columns=CHOICE_MAP.keys())
    
    
            # add save nodes and merge nodes
    
    def generate_base(self,node, **kwargs):
        return generate_xls_form_condition(node, **kwargs)
            
    def generate_relevance(self, node, **kwargs):
        return  generate_xls_form_relevance(node, **kwargs)

    def generate_calculate(self, node, **kwargs):
        return generate_xls_form_calculate( node, **kwargs)
    

    def do_clean(self, **kwargs):
        self.calculates= {}
        self.processed_nodes = {}
        self.stashed_nodes = {}
        self.used_calculates = {}
    
    def get_kwargs(self):  
        return { 
            'processed_nodes':self.processed_nodes, 
            'stashed_nodes':self.stashed_nodes,
            'df_survey':self.df_survey, 
            'df_choice':self.df_choice,
            'calculates':self.calculates,
            'used_calculates':self.used_calculates
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
        writer.save()

        # run this on a windows python instance because if not then the generated xlsx file remains open
        #writer.close()
        writer.handles = None
    
    def process_export(self, activity,  **kwargs):
        # The stashed node are all the node that have all their prevnode processed but not from the same group
        # This logic works only because the prev node are ordered by group/parent .. 
    
        groups= {}
        cur_group=activity
        groups[activity.id] = 0
        # keep the vesrions on the group id, max version
        start_group( cur_group=cur_group, groups=groups, **self.get_kwargs())
        walktrhough_tricc_node(activity.root, self.generate_export, cur_group = activity.root.group, **self.get_kwargs() )
        end_group( cur_group =activity, groups=groups, **self.get_kwargs())
        
        # we save the survey data frame
        df_survey_final = self.df_survey
        self.df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
        
        ## MANAGE STASHED NODES
        
        while len(self.stashed_nodes)>0:
            if len(self.stashed_nodes)>0:
                s_node = self.stashed_nodes.pop(list(self.stashed_nodes.keys())[0])
                start_group( cur_group =s_node.group, groups=groups, relevance= isinstance(s_node, TriccNodeActivity),  **self.get_kwargs())          
                # arrange empty group
                walktrhough_tricc_node(s_node, self.generate_export, groups=groups,cur_group = s_node.group, **self.get_kwargs() )
                # add end group if new node where added OR if the previous end group was removed
                end_group( cur_group =s_node.group, groups=groups, **self.get_kwargs())
                
                # if two line then empty grou
                if len(self.df_survey)>2:
                    if cur_group == s_node.group:
                        # drop the end group (to merge)
                        df_survey_final.drop(index=df_survey_final.index[-1], axis=0, inplace=True)
                        df_survey_final  =pd.concat([df_survey_final,self.df_survey[1:]])
                    ## only caalculate
                    elif len(self.df_survey[self.df_survey['type']=='calculate']) == len(self.df_survey) -2:
                        df_survey_final =pd.concat([df_survey_final, self.df_survey[1:-1]])
                    else:
                        df_survey_final =pd.concat([df_survey_final, self.df_survey])
                    cur_group = s_node.group
                else:
                    find_dependants(s_node, self.stashed_nodes)
                    
                self.df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
        self.df_survey = df_survey_final    
                
def find_dependants(node, stashed_nodes, loop_control = []):
    if node in loop_control:
        logger.error("loop involving node {0}".format(node.get_name()))
        exit(-1)
    loop_control_prev = loop_control.copy()
    loop_control_prev.append(node)
    if hasattr(node, 'prev_nodes'):
        for prev_node in list(stashed_nodes.values()) if isinstance(stashed_nodes, Dict) else stashed_nodes:
            if prev_node.id in stashed_nodes:
                logger.debug("node {0} depends on a stached node {1}".format(node.get_name(),stashed_nodes[prev_node.id].get_name() ))
                return None
            else:
                for prev_stashed_node in list(stashed_nodes.values()) if isinstance(stashed_nodes, Dict) else stashed_nodes:
                    if hasattr(prev_stashed_node, 'prev_nodes'):
                        find_dependants(prev_node, prev_stashed_node.prev_nodes, loop_control_prev)
                find_dependants(prev_node, stashed_nodes, loop_control_prev)
    if loop_control == []:
        logger.warning("group {} without content".format(node.group.label))
            
    