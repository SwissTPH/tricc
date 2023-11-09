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
from tricc.strategies.output.base_output_strategy import BaseOutPutStrategy

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

    def export(self,start_pages ):
                
        if start_pages['registration'].root.form_id is not None:
            form_id= str(start_pages['registration'].root.form_id )
        else:
            logger.error("form id required in the first start node")
            exit()
        title = start_pages['registration'].root.label
        file_name = form_id + ".xlsx"
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
    
    def process_export(self, start_pages,  **kwargs):
        self.activity_export(start_pages['registration'], **kwargs)
    
    def activity_export(self, activity, processed_nodes = [], **kwargs):
        stashed_nodes =  []
        # The stashed node are all the node that have all their prevnode processed but not from the same group
        # This logic works only because the prev node are ordered by group/parent .. 
        skip_header = 0
        groups= {}
        cur_group = activity
        groups[activity.id] = 0
        path_len = 0
        # keep the vesrions on the group id, max version
        start_group( cur_group=cur_group, groups=groups, **self.get_kwargs())
        walktrhough_tricc_node_processed_stached(activity.root, self.generate_export, processed_nodes, stashed_nodes,path_len , cur_group = activity.root.group, **self.get_kwargs() )
        end_group( cur_group =activity, groups=groups, **self.get_kwargs())
        # we save the survey data frame
        df_survey_final =   pd.DataFrame(columns=SURVEY_MAP.keys())
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
        
        self.df_calculate=self.df_calculate.dropna(axis=0, subset=['calculation'])
        df_empty_calc  = self.df_calculate[self.df_calculate['calculation'] == '']
        self.df_calculate=self.df_calculate.drop(df_empty_calc.index)
        self.df_survey = pd.concat([df_survey_final,self.df_calculate], ignore_index=True)
        df_duplicate = self.df_calculate[self.df_calculate.duplicated(subset=['calculation'], keep='first')]
        #self.df_survey=self.df_survey.drop_duplicates(subset=['name'])
        for index, drop_calc in df_duplicate.iterrows():
            #remove the duplicate
            replace_name = False
            #find the actual calcualte 
            similar_calc =  self.df_survey[(drop_calc['calculation'] == self.df_survey['calculation']) & (self.df_survey['type'] == 'calculate')]
            same_calc = self.df_survey[self.df_survey['name'] == drop_calc['name']]
            if len(same_calc) > 1:
                # check if all calc have the same name
                if len(same_calc) == len(similar_calc):
                    # drop all but one
                    self.df_survey.drop(same_calc.index[1:])
                elif len(same_calc) < len(similar_calc):
                    self.df_survey.drop(same_calc.index)
                    replace_name = True
            elif len(same_calc) == 1:
                self.df_survey.drop(similar_calc.index)
                replace_name = True
                

            if replace_name:
                save_calc =  self.df_survey[(drop_calc['calculation'] == self.df_survey['calculation']) & (self.df_survey['type'] == 'calculate')     ]
                if len(save_calc) >= 1:
                    save_calc = save_calc.iloc[0]
                    if save_calc['name']!= drop_calc['name']:
                        self.df_survey.replace('\$\{'+drop_calc['name']+'\}', '\$\{'+save_calc['name']+'\}', regex=True)
                else:
                    logger.error("duplicate reference not found for calculation: {}".format(drop_calc['calculation']))
        for index, empty_calc in df_empty_calc.iterrows():
                 self.df_survey.replace('\$\{'+empty_calc['name']+'\}', '1', regex=True)
    
        #TODO try to reinject calc to reduce complexity
        for i,c in self.df_calculate[~self.df_calculate['name'].isin(self.df_survey['name'])].iterrows():
            real_calc = re.find(r'^number\((.+)\)$',c['calculation'])
            if real_calc is not None and real_calc != '':
                self.df_survey[~self.df_survey['name']==c['name']].replace(real_calc, '\$\{'+c['name']+'\}')
        return processed_nodes