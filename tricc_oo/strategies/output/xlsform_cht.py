import datetime
import logging
import os
import shutil

import pandas as pd

from tricc_oo.models.lang import SingletonLangClass
from tricc_oo.serializers.xls_form import SURVEY_MAP
from tricc_oo.strategies.output.xlsform_cdss import XLSFormCDSSStrategy

langs = SingletonLangClass()

class XLSFormCHTStrategy(XLSFormCDSSStrategy):
    def process_export(self, start_pages,  **kwargs):
        
        super().process_export( start_pages,  **kwargs)
        cht_header = pd.DataFrame(columns=SURVEY_MAP.keys())
        
        
        self.df_survey = pd.concat([self.get_cht_input(),self.df_survey[~self.df_survey['name'].isin(['select_sex','id.age_day','p_age_month','p_age_year','p_name','dob'])],self.get_cht_summary() ], ignore_index=True)
 
    def get_cht_input(self):
        df_input = pd.DataFrame(columns=SURVEY_MAP.keys())
         #[ #type, '',#name ''#label, '',#hint '',#help '',#default '',#'appearance',  '',#'constraint',  '',#'constraint_message' '',#'relevance' '',#'disabled' '',#'required' '',#'required message' '',#'read only' '',#'expression' '',#'repeat_count' ''#'image' ],
        df_input.loc[len(df_input)] = [ 'begin group', 'inputs' ,*list(langs.get_trads('Inputs', force_dict = True).values()), *list(langs.get_trads('', force_dict = True).values()), *list(langs.get_trads('', force_dict = True).values()), '',  'field-list',  '', *list(langs.get_trads('', force_dict = True).values()), './source = "user"', '','', *list(langs.get_trads('', force_dict = True).values()) ,'', '', '', '' ]
        df_input.loc[len(df_input)] = [  'hidden', 'source', *list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', '', '', '' ]
        df_input.loc[len(df_input)] = [  'hidden', 'source_id',*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', '', '', '' ]
        df_input.loc[len(df_input)] = [  'hidden', 'task_id' ,*list(langs.get_trads('Task ID', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', '', '', '']
        df_input.loc[len(df_input)] = [  'begin group	', 'contact' ,*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', '', '', '' ]
        df_input.loc[len(df_input)] = [  'db:person', '_id', *list(langs.get_trads('Patient ID', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', 'db-object',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', '', '', '' ]
        df_input.loc[len(df_input)] = [  'string', 'patient_id' ,*list(langs.get_trads('Medic ID', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', 'hidden',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', '', '', '' ]
        df_input.loc[len(df_input)] = [  'string', 'patient_name',*list(langs.get_trads('Patient Name', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', 'hidden',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', '',  '','' ]
        df_input.loc[len(df_input)] = [  'date', 'date_of_birth',*list(langs.get_trads('Date of birth', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', 'hidden',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', '',  '','' ]
        df_input.loc[len(df_input)] = [  'string', 'sex',*list(langs.get_trads('Patient Sex', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', 'hidden',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', '',  '','' ]
        df_input.loc[len(df_input)] = [  'end group', '' ,*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', '', '', '']
        df_input.loc[len(df_input)] = [  'end group', '' ,*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', '', '', '' ]
        df_input.loc[len(df_input)] = [  'calculate', '_id' ,*list(langs.get_trads('label', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '',  '../inputs/contact/_id', '', '' ]
        df_input.loc[len(df_input)] = [  'calculate', 'patient_uuid' ,*list(langs.get_trads('label', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '',  '../inputs/contact/patient_id', '', '' ]
        df_input.loc[len(df_input)] = [  'calculate', 'p_name' ,*list(langs.get_trads('label', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', '../inputs/contact/patient_name', '', '' ]

        df_input.loc[len(df_input)] = [  'calculate', 'id.age_day' ,*list(langs.get_trads('label', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', 'int((today()-date(${date_of_birth})))', '', '' ]
        df_input.loc[len(df_input)] = [  'calculate', 'p_age_month' ,*list(langs.get_trads('label', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', 'int(${id.age_day} div 30.4)', '', '' ]
        df_input.loc[len(df_input)] = [  'calculate', 'p_age_year' ,*list(langs.get_trads('label', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', 'int(${p_age_month} div 12)', '', '' ]
        df_input.loc[len(df_input)] = [  'calculate', 'select_sex' ,*list(langs.get_trads('label', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', '../inputs/contact/sex', '', '' ]
        df_input.loc[len(df_input)] = [  'calculate', 'dob',*list(langs.get_trads('Date of birth', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', 'date(../inputs/contact/date_of_birth)',  '','' ]

        
        return df_input
        
    def get_cht_summary(self):
        
        df_summary = pd.DataFrame(columns=SURVEY_MAP.keys())
         #[ #type, '',#name ''#label, '',#hint '',#help '',#default '',#'appearance',  '',#'constraint',  '',#'constraint_message' '',#'relevance' '',#'disabled' '',#'required' '',#'required message' '',#'read only' '',#'expression' '',#'repeat_count' ''#'image' ],
        #df_summary.loc[len(df_summary)] = [  'begin group', 'group_summary' , 'Summary',                                  '', '', '',  'field-list summary',  '', '', '', '', '', '', '', '', '', '' ]
        #df_summary.loc[len(df_summary)] = [  'note',        'r_patient_info', '**${patient_name}** ID: ${patient_id}',  '', '', '',  '',                    '', '', '', '', '', '', '', '', '', '' ]
        #df_summary.loc[len(df_summary)] = [  'note',        'r_followup', 'Follow Up <i class=“fa fa-flag”></i>', '', '', '',  '',  '', '','', '', '', '', '', '', '', '' ]
        #df_summary.loc[len(df_summary)] = [  'note',        'r_followup_note' ,'FOLLOWUP instruction', '', '', '',  '',  '', '', '','', '', '', '', '', '', '' ]
        #df_summary.loc[len(df_summary)] = [  'end group', '' ,'', '', '', '',  '',  '', '', '', '', '', '', '', '','', '' ]
        return df_summary
    
    def export(self, start_pages, version, **kwargs):
        form_id = None
        if start_pages[self.processes[0]].root.form_id is not None:
            form_id= str(start_pages[self.processes[0]].root.form_id )
        else:
            logger.error("form id required in the first start node")
            exit()
        title = start_pages[self.processes[0]].root.label
        file_name = form_id + ".xlsx"
        # make a 'settings' tab
        now = datetime.datetime.now()
        version=now.strftime('%Y%m%d%H%M')
        indx=[[1]]
        # CHT FORCE file name to be equal to id
        
        newfilename = form_id + ".xlsx"
        newpath = os.path.join(self.output_path, newfilename)
        media_path = os.path.join(self.output_path, form_id + "-media")

        settings={'form_title':title,'form_id':form_id,'version':version,'default_language':'English (en)','style':'pages'}
        df_settings=pd.DataFrame(settings,index=indx)
        df_settings.head()
        if len(self.df_survey[self.df_survey['name'] == 'version'] ):
            self.df_survey.loc[ self.df_survey['name'] == 'version', 'label'] = f"v{version}"
        #create a Pandas Excel writer using XlsxWriter as the engine
        writer = pd.ExcelWriter(newpath, engine='xlsxwriter')
        self.df_survey.to_excel(writer, sheet_name='survey',index=False)
        self.df_choice.to_excel(writer, sheet_name='choices',index=False)
        df_settings.to_excel(writer, sheet_name='settings',index=False)

        #close the Pandas Excel writer and output the Excel file
        #writer.save()

        # run this on a windows python instance because if not then the generated xlsx file remains open
        writer.close()
        media_path_tmp = os.path.join(self.output_path, 'media-tmp')
        if (os.path.isdir(media_path_tmp)):
            if os.path.isdir(media_path): # check if it exists, because if it does, error will be raised 
                shutil.rmtree(media_path)
                # (later change to make folder complaint to CHT)
            os.mkdir(media_path)
            
            file_names = os.listdir(media_path_tmp)
            for file_name in file_names:
                shutil.move(os.path.join(media_path_tmp, file_name), media_path)
            shutil.rmtree(media_path_tmp)