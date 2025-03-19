import datetime
import logging
import os
import shutil

import pandas as pd

from tricc_oo.models.lang import SingletonLangClass
from tricc_oo.models.calculate import TriccNodeEnd
from tricc_oo.serializers.xls_form import SURVEY_MAP, get_input_line
from tricc_oo.strategies.output.xlsform_cdss import XLSFormCDSSStrategy
from tricc_oo.converters.tricc_to_xls_form import get_export_name
from tricc_oo.converters.utils import clean_name, remove_html
from tricc_oo.visitors.xform_pd import make_breakpoints, get_task_js

langs = SingletonLangClass()
logger = logging.getLogger("default")

class XLSFormCHTStrategy(XLSFormCDSSStrategy):
    
    
    def process_export(self, start_pages,  **kwargs):
        diags = []
        self.activity_export(start_pages[self.processes[0]], **kwargs)
        #self.add_tab_breaks_choice()
        cht_header = pd.DataFrame(columns=SURVEY_MAP.keys())
        cht_input_df = self.get_cht_input( start_pages,  **kwargs)
        self.df_survey= self.df_survey[~self.df_survey['name'].isin(cht_input_df['name'])]
        self.df_survey.reset_index(drop=True, inplace=True)

        
        self.df_survey = pd.concat([cht_input_df, self.df_survey ,self.get_cht_summary() ], ignore_index=True)
 
    def get_cht_input(self, start_pages, **kwargs):
        df_input = pd.DataFrame(columns=SURVEY_MAP.keys())
         #[ #type, '',#name ''#label, '',#hint '',#help '',#default '',#'appearance',  '',#'constraint',  '',#'constraint_message' '',#'relevance' '',#'disabled' '',#'required' '',#'required message' '',#'read only' '',#'expression' '',#'repeat_count' ''#'image' ],
        df_input.loc[len(df_input)] = [ 'begin group', 'inputs' ,*list(langs.get_trads('Inputs', force_dict = True).values()), *list(langs.get_trads('', force_dict = True).values()), *list(langs.get_trads('', force_dict = True).values()), '',  'field-list',  '', *list(langs.get_trads('', force_dict = True).values()), './source = "user"', '','', *list(langs.get_trads('', force_dict = True).values()) ,'', '', '', '', '' ]
        df_input.loc[len(df_input)] = [ 'hidden', 'source', *list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()) ,'', '', '', '', '' ]
        df_input.loc[len(df_input)] = [ 'hidden', 'source_id',*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()) ,'', '', '', '', '' ]
        inputs = self.export_inputs( start_pages[self.processes[0]],  **kwargs)
        for input in inputs:
            df_input.loc[len(df_input)] = get_input_line(input)
        df_input.loc[len(df_input)] = [ 
            'string', 'data_load',
            *list(langs.get_trads('NO_LABEL', force_dict = True).values()),
            *list(langs.get_trads('', force_dict = True).values()),
            *list(langs.get_trads('', force_dict = True).values()),
            '',  'hidden',  '',
            *list(langs.get_trads('', force_dict = True).values()),
            '', '','',
            *list(langs.get_trads('', force_dict = True).values())
            ,'', '', '', '' 
        ]      
        df_input.loc[len(df_input)] = [ 'hidden', 'task_id' ,*list(langs.get_trads('Task ID', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()) ,'', '', '', '', '' ]
        df_input.loc[len(df_input)] = [ 'begin group	', 'contact' ,*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()) ,'', '', '', '', '' ]
        df_input.loc[len(df_input)] = [ 'db:person', '_id', *list(langs.get_trads('Patient ID', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', 'db-object',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()) ,'', '', '', '', '' ]
        df_input.loc[len(df_input)] = [ 'string', 'patient_id' ,*list(langs.get_trads('Medic ID', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', 'hidden',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()) ,'', '', '', '', '' ]
        df_input.loc[len(df_input)] = [ 'string', 'patient_name',*list(langs.get_trads('Patient Name', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', 'hidden',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()) ,'', '', '', '', '' ]
        df_input.loc[len(df_input)] = [ 'date', 'date_of_birth',*list(langs.get_trads('Date of birth', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', 'hidden',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()) ,'', '', '', '', '' ]
        df_input.loc[len(df_input)] = [ 'string', 'sex',*list(langs.get_trads('Patient Sex', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', 'hidden',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()) ,'', '', '', '', '' ]
        df_input.loc[len(df_input)] = [ 'end group', '' ,*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()) ,'', '', '', '', '' ]
        df_input.loc[len(df_input)] = [ 'end group', '' ,*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()) ,'', '', '', '', '' ]
        df_input.loc[len(df_input)] = [ 'calculate', '_id' ,*list(langs.get_trads('label', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '',  '../inputs/contact/_id', '', '' , '' ]
        df_input.loc[len(df_input)] = [ 'calculate', 'patient_uuid' ,*list(langs.get_trads('label', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '',  '../inputs/contact/patient_id', '', '' , '' ]
        df_input.loc[len(df_input)] = [ 'calculate', 'p_name' ,*list(langs.get_trads('label', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', '../inputs/contact/patient_name', '', '' , '' ]

        df_input.loc[len(df_input)] = [ 'calculate', 'p_age_days' ,*list(langs.get_trads('label', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', 'int((today()-date(${date_of_birth})))', '', '' , '' ]
        df_input.loc[len(df_input)] = [ 'calculate', 'p_age_months' ,*list(langs.get_trads('label', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', 'int(${id.age_day} div 30.4)', '', '' , '' ]
        df_input.loc[len(df_input)] = [ 'calculate', 'p_age_years' ,*list(langs.get_trads('label', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', 'int(${p_age_month} div 12)', '', '' , '' ]
        df_input.loc[len(df_input)] = [ 'calculate', 'p_sex' ,*list(langs.get_trads('label', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', '../inputs/contact/sex', '', '' , '' ]
        df_input.loc[len(df_input)] = [ 'calculate', 'p_dob',*list(langs.get_trads('Date of birth', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()),*list(langs.get_trads('', force_dict = True).values()), '', '',  '',  *list(langs.get_trads('', force_dict = True).values()), '', '', '', *list(langs.get_trads('', force_dict = True).values()), '', 'date(../inputs/contact/date_of_birth)',  '','' , '' ]

        
        return df_input
        
    def get_cht_summary(self):
        
        df_summary = pd.DataFrame(columns=SURVEY_MAP.keys())
         #[ #type, '',#name ''#label, '',#hint '',#help '',#default '',#'appearance',  '',#'constraint',  '',#'constraint_message' '',#'relevance' '',#'disabled' '',#'required' '',#'required message' '',#'read only' '',#'expression' '',#'repeat_count' ''#'image' ],
        #df_summary.loc[len(df_summary)] = [ 'begin group', 'group_summary' , 'Summary',                                  '', '', '',  'field-list summary',  '', '', '', '', '', '', '', '', '', '' ]
        #df_summary.loc[len(df_summary)] = [ 'note',        'r_patient_info', '**${patient_name}** ID: ${patient_id}',  '', '', '',  '',                    '', '', '', '', '', '', '', '', '', '' ]
        #df_summary.loc[len(df_summary)] = [ 'note',        'r_followup', 'Follow Up <i class=“fa fa-flag”></i>', '', '', '',  '',  '', '','', '', '', '', '', '', '', '' ]
        #df_summary.loc[len(df_summary)] = [ 'note',        'r_followup_note' ,'FOLLOWUP instruction', '', '', '',  '',  '', '', '','', '', '', '', '', '', '' ]
        #df_summary.loc[len(df_summary)] = [ 'end group', '' ,'', '', '', '',  '',  '', '', '', '', '', '', '', '','', '' ]
        return df_summary
    
    def export(self, start_pages, version, **kwargs):
        form_id = None
        if start_pages[self.processes[0]].root.form_id is not None:
            form_id= str(start_pages[self.processes[0]].root.form_id )
        else:
            logger.critical("form id required in the first start node")
            exit(1)
        title = remove_html(start_pages[self.processes[0]].root.label)
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
        writer.close()
        # pause
        ends = []
        for p in self.project.pages.values():
            p_ends = list(filter(lambda x:  issubclass(x.__class__, TriccNodeEnd) and hasattr(x, 'hint'), p.nodes.values() ))
            if p_ends:
                ends += p_ends
        if ends:
            ends_prev = []
            for e in ends:
                
                latest = None
                for p in e.prev_nodes:
                    if not latest or latest.path_len < p.path_len:
                        latest = p
                if hasattr(latest, 'select'):
                    latest = latest.select 
                ends_prev.append(
                    (int(self.df_survey[self.df_survey.name == latest.export_name].index.values[0]), e,)
                )
            forms = [form_id]
            for i, e in ends_prev:
                new_form_id = f"{form_id}_{clean_name(e.name)}"
                newfilename = f"{new_form_id}.xlsx"
                newpath = os.path.join(self.output_path, newfilename)
                settings={'form_title':title,'form_id':f"{new_form_id}",'version':version,'default_language':'English (en)','style':'pages'}
                df_settings=pd.DataFrame(settings,index=indx)
                df_settings.head()
                task_df, hidden_names = make_breakpoints(self.df_survey, i, e.name, replace_dots=True)
                # deactivate the end node
                task_df.loc[task_df['name'] == get_export_name(e), 'calculation'] = 0
                #print fileds
                writer = pd.ExcelWriter(newpath, engine='xlsxwriter')
                task_df.to_excel(writer, sheet_name='survey',index=False)
                self.df_choice.to_excel(writer, sheet_name='choices',index=False)
                df_settings.to_excel(writer, sheet_name='settings',index=False)
                writer.close()
                newfilename = f"{new_form_id}.js"
                newpath = os.path.join(self.output_path, newfilename)
                with open(newpath, 'w') as f:
                    f.write(
                        get_task_js(
                            new_form_id,
                            e.name,
                            f"continue {title}",
                            forms,
                            hidden_names,
                            self.df_survey,
                            repalce_dots=False,
                            task_title=e.hint
                        )
                    )
                    f.close()
                forms.append(new_form_id)
                
            
            
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
            
    def tricc_operation_zscore(self, ref_expressions):
        y, ll, m, s = self.get_zscore_params(ref_expressions)
        #  return ((Math.pow((y / m), l) - 1) / (s * l));
        return f"cht:extension-lib('{ref_expressions[0][1:-1]}.js',{ref_expressions[1]} ,{ref_expressions[2]} ,{ref_expressions[3]}  )"
   
    
    def tricc_operation_izscore(self, ref_expressions):
        z, ll, m, s = self.get_zscore_params(ref_expressions)
        #  return  (m * (z*s*l-1)^(1/l));
        return f"cht:extension-lib('{ref_expressions[0][1:-1]}.js',{ref_expressions[1]} ,{ref_expressions[2]} ,{ref_expressions[3]}  )"

    def tricc_operation_drug_dosage(self, ref_expressions):
        # drug name
        # age
        #weight
        return f"cht:extension-lib('drugs.js',{','.join(ref_expressions)})"