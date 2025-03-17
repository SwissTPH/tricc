import datetime
import logging
import os
import shutil

import pandas as pd

from tricc_oo.models.lang import SingletonLangClass
from tricc_oo.serializers.xls_form import SURVEY_MAP,get_input_line, get_input_calc_line
from tricc_oo.strategies.output.xlsform_cht import XLSFormCHTStrategy
from tricc_oo.visitors.xform_pd import make_breakpoints, get_tasksstrings

langs = SingletonLangClass()
logger = logging.getLogger("default")

class XLSFormCHTHFStrategy(XLSFormCHTStrategy):

    def get_cht_input(self, start_pages, **kwargs):
        empty = langs.get_trads('', force_dict =True)
        df_input = pd.DataFrame(columns=SURVEY_MAP.keys())
         #[ #type, '',#name ''#label, '',#hint '',#help '',#default '',#'appearance',  '',#'constraint',  '',#'constraint_message' '',#'relevance' '',#'disabled' '',#'required' '',#'required message' '',#'read only' '',#'expression' '',#'repeat_count' ''#'image' ],
        df_input.loc[len(df_input)] = [ 
            'begin_group', 'inputs',
            *list(langs.get_trads('NO_LABEL', force_dict = True).values()),
            *list(empty.values()),
            *list(empty.values()),
            '',  'field-list',  '',
            *list(empty.values()),
            './source = "user"', '','',
            *list(empty.values())
            ,'', '', '', '' ,''
        ]
        df_input.loc[len(df_input)] = [ 
            'hidden', 'source',
            *list(langs.get_trads('Source', force_dict = True).values()),
            *list(empty.values()),
            *list(empty.values()),
            'user',  'hidden',  '',
            *list(empty.values()),
            '', '','',
            *list(empty.values())
            ,'', '', '', '' ,''
        ]
        df_input.loc[len(df_input)] = [ 
            'hidden', 'source_id',
            *list(langs.get_trads('Source ID', force_dict = True).values()),
            *list(empty.values()),
            *list(empty.values()),
            '',  'hidden',  '',
            *list(empty.values()),
            '', '','',
            *list(empty.values())
            ,'', '', '', '' ,''
        ]
        

        df_input.loc[len(df_input)] = [ 
            'begin_group', 'user',
            *list(langs.get_trads('NO_LABEL', force_dict = True).values()),
            *list(empty.values()),
            *list(empty.values()),
            '',  'field-list',  '',
            *list(empty.values()),
            '', '','',
            *list(empty.values())
            ,'', '', '', '' ,''
        ]
        df_input.loc[len(df_input)] = [ 
            'string', 'contact_id',
            *list(langs.get_trads('NO_LABEL', force_dict = True).values()),
            *list(empty.values()),
            *list(empty.values()),
            '',  'hidden',  '',
            *list(empty.values()),
            '', '','',
            *list(empty.values())
            ,'', '', '', '' ,''
        ]
        df_input.loc[len(df_input)] = [ 
            'string', 'facility_id',
            *list(langs.get_trads('NO_LABEL', force_dict = True).values()),
            *list(empty.values()),
            *list(empty.values()),
            '',  'hidden',  '',
            *list(empty.values()),
            '', '','',
            *list(empty.values())
            ,'', '', '', '' ,''
        ]
        df_input.loc[len(df_input)] = [ 
            'string', 'name',
            *list(langs.get_trads('NO_LABEL', force_dict = True).values()),
            *list(empty.values()),
            *list(empty.values()),
            '',  'hidden',  '',
            *list(empty.values()),
            '', '','',
            *list(empty.values())
            ,'', '', '', '' ,''
        ]
        df_input.loc[len(df_input)] = [
            'end_group', 'user end' ,
            *list(empty.values()),
            *list(empty.values()),
            *list(empty.values()),
            '', '',  '',
            *list(empty.values()),
            '', '', '',
            *list(empty.values()),
            '', '', '', '',''
        ]
        df_input.loc[len(df_input)] = [ 
            'begin_group', 'contact',
            *list(langs.get_trads('NO_LABEL', force_dict = True).values()),
            *list(empty.values()),
            *list(empty.values()),
            '',  'field-list',  '',
            *list(empty.values()),
            '', '','',
            *list(empty.values())
            ,'', '', '', '' ,''
        ]
        inputs = self.export_inputs( start_pages[self.processes[0]],  **kwargs)
        for input in inputs:
            df_input.loc[len(df_input)] = get_input_line(input)
        df_input.loc[len(df_input)] = [ 
            'hidden', 'external_id',
            *list(langs.get_trads('NO_LABEL', force_dict = True).values()),
            *list(empty.values()),
            *list(empty.values()),
            '',  'hidden',  '',
            *list(empty.values()),
            '', '','',
            *list(empty.values())
            ,'', '', '', '' ,''
        ]
        
        df_input.loc[len(df_input)] = [ 
            'string', '_id',
            *list(langs.get_trads('NO_LABEL', force_dict = True).values()),
            *list(empty.values()),
            *list(empty.values()),
            '',  'hidden',  '',
            *list(empty.values()),
            '', '','',
            *list(empty.values())
            ,'', '', '', '' ,''
        ]      
        
        df_input.loc[len(df_input)] = [
            'end_group', 'contact end' ,
            *list(empty.values()),
            *list(empty.values()),
            *list(empty.values()),
            '', '',  '',
            *list(empty.values()),
            '', '', '',
            *list(empty.values()),
            '', '', '', '',''
        ]
        
        df_input.loc[len(df_input)] = [
            'end_group', 'input end' ,
            *list(empty.values()),
            *list(empty.values()),
            *list(empty.values()),
            '', '',  '',
            *list(empty.values()),
            '', '', '',
            *list(empty.values()),
            '', '', '', '',''
        ]
        df_input.loc[len(df_input)] = [
            'calculate',
            'created_by_person_uuid',
            *list(empty.values()) ,
            *list(empty.values()) ,#hint
            *list(empty.values()) ,#help
            '',#default
            '',#'appearance', clean_name
            '',#'constraint', 
            *list(empty.values()) ,#'constraint_message'
            '',#'relevance'
            '',#'disabled'
            '',#'required'
            *list(empty.values()) ,#'required message'
            '',#'read only'
            '../inputs/user/contact_id',#'expression'
            '',#'repeat_count'
            '',#'image'
            '' # choice filter
        ] 
        df_input.loc[len(df_input)] = [
            'calculate',
            'created_by_place_uuid_user',
            *list(empty.values()) ,
            *list(empty.values()) ,#hint
            *list(empty.values()) ,#help
            '',#default
            '',#'appearance', clean_name
            '',#'constraint', 
            *list(empty.values()) ,#'constraint_message'
            '',#'relevance'
            '',#'disabled'
            '',#'required'
            *list(empty.values()) ,#'required message'
            '',#'read only'
            '../inputs/user/facility_id',#'expression'
            '',#'repeat_count'
             '',#'image'
            '' # choice filter        
        ] 
        df_input.loc[len(df_input)] = [
            'calculate',
            'created_by',
            *list(empty.values()) ,
            *list(empty.values()) ,#hint
            *list(empty.values()) ,#help
            '',#default
            '',#'appearance', clean_name
            '',#'constraint', 
            *list(empty.values()) ,#'constraint_message'
            '',#'relevance'
            '',#'disabled'
            '',#'required'
            *list(empty.values()) ,#'required message'
            '',#'read only'
            '../inputs/user/name',#'expression'
            '',#'repeat_count'
            '',#'image'
            '' # choice filter
        ] 
        df_input.loc[len(df_input)] = [
            'calculate',
            'created_by_place_uuid',
            *list(empty.values()) ,
            *list(empty.values()) ,#hint
            *list(empty.values()) ,#help
            '',#default
            '',#'appearance', clean_name
            '',#'constraint', 
            *list(empty.values()) ,#'constraint_message'
            '',#'relevance'
            '',#'disabled'
            '',#'required'
            *list(empty.values()) ,#'required message'
            '',#'read only'
            '../inputs/contact/_id',#'expression'
            '',#'repeat_count'
            '',#'image'
            '' # choice filter 
        ] 

        df_input.loc[len(df_input)] = [
            'calculate',
            'source_id',
            *list(empty.values()) ,
            *list(empty.values()) ,#hint
            *list(empty.values()) ,#help
            '',#default
            '',#'appearance', clean_name
            '',#'constraint', 
            *list(empty.values()) ,#'constraint_message'
            '',#'relevance'
            '',#'disabled'
            '',#'required'
            *list(empty.values()) ,#'required message'
            '',#'read only'
            '../inputs/source_id',#'expression'
            '',#'repeat_count'
            '',#'image'
            '' # choice filter 
        ] 
        df_input.loc[len(df_input)] = [
            'calculate',
            'patient_uuid',
            *list(empty.values()) ,
            *list(empty.values()) ,#hint
            *list(empty.values()) ,#help
            '',#default
            '',#'appearance', clean_name
            '',#'constraint', 
            *list(empty.values()) ,#'constraint_message'
            '',#'relevance'
            '',#'disabled'
            '',#'required'
            *list(empty.values()) ,#'required message'
            '',#'read only'
            '../inputs/user/facility_id',#'expression'
            '',#'repeat_count'
            '',#'image'
            '' # choice filter
        ] 
        df_input.loc[len(df_input)] = [ 
            'string', 'data_load',
            *list(langs.get_trads('NO_LABEL', force_dict = True).values()),
            *list(empty.values()),
            *list(empty.values()),
            '',  'hidden',  '',
            *list(empty.values()),
            '', '','',
            *list(empty.values())
            ,'', '', '', '' ,''
        ]  
        
        for input in inputs:
            df_input.loc[len(df_input)] = get_input_calc_line(input)        

        
        
        return df_input
        
    def get_cht_summary(self):
        
        df_summary = pd.DataFrame(columns=SURVEY_MAP.keys())
         #[ #type, '',#name ''#label, '',#hint '',#help '',#default '',#'appearance',  '',#'constraint',  '',#'constraint_message' '',#'relevance' '',#'disabled' '',#'required' '',#'required message' '',#'read only' '',#'expression' '',#'repeat_count' ''#'image' ],
        #df_summary.loc[len(df_summary)] = [  'begin_group', 'group_summary' , 'Summary',                                  '', '', '',  'field-list summary',  '', '', '', '', '', '', '', '', '', '' ]
        #df_summary.loc[len(df_summary)] = [  'note',        'r_patient_info', '**${patient_name}** ID: ${patient_id}',  '', '', '',  '',                    '', '', '', '', '', '', '', '', '', '' ]
        #df_summary.loc[len(df_summary)] = [  'note',        'r_followup', 'Follow Up <i class=“fa fa-flag”></i>', '', '', '',  '',  '', '','', '', '', '', '', '', '', '' ]
        #df_summary.loc[len(df_summary)] = [  'note',        'r_followup_note' ,'FOLLOWUP instruction', '', '', '',  '',  '', '', '','', '', '', '', '', '', '' ]
        #df_summary.loc[len(df_summary)] = [  'end_group', '' ,'', '', '', '',  '',  '', '', '', '', '', '', '', '','', '' ]
        return df_summary
    
    def tricc_operation_age_day(self, exps):
        raise NotImplemented("AgeInDays Not compatible with this strategy")
    
    def tricc_operation_age_year(self, exps):
        raise NotImplemented("AgeInYears Not compatible with this strategy")
    
    def tricc_operation_age_month(self, exps):
        raise NotImplemented("AgeInMonths Not compatible with this strategy")

    
    