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

   
    def get_contact_inputs(self, df_inputs):
       return None
        
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

    
    