# -*- coding: utf-8 -*-
"""
Created on Thu Sep  1 11:21:39 2022

@author: kluera

Make subforms that allow to be releoaded seperately as a 'task' in CHT, 
allowing to simulate a pause functionality. 
"""

import pandas as pd
import json

def remove_dots(s):
     return s.replace('.','_')

def chf_clean_name(s, remove_dots=False):
    # Check if there is a dot in the string
    if remove_dots:
        return remove_dots(s)
    elif "." in s:
        return f'["{s}"]'
    else:
        # If no dot is present, return None or handle it as needed
        return s

# df is the dataframe to be split
# pausepoint is the index of the row after which the form should pause
def make_breakpoints(df, pausepoint, calculate_name=None, replace_dots=False):
    """
    Creates a dataframe for a follow-up questionnaire while preserving previous inputs.
    
    Args:
        df: Input dataframe containing the questionnaire
        pausepoint: Point where the questionnaire should pause
        calculate_name: Optional name for calculation fields
    """
    
    # Get data points collected before break
    if 'input end' not in df['name'].values:
        raise ValueError("input end field not found in input dataframe")
    end_inputs_loc = df.index[df['name'] == 'input end'][0]
    next_begin_group_loc = min([i for i in df.index[df['type'] == 'begin group'] if i > end_inputs_loc])
        
    df_input = df.loc[next_begin_group_loc:pausepoint]
    
    # Define field types to handle
    typesconvert = ['integer', 'decimal', 'select_', 'text']
    typeskeep = ['hidden', 'calculate', 'string'] 
    
    # Create masks for filtering
    type_mask = df_input['type'].str.contains('|'.join(typeskeep + typesconvert))
    optin_mask = ~df_input['name'].str.contains('more_info_optin', na=False)
    
    # Filter dataframe keeping important fields
    df_input = df_input.loc[type_mask & optin_mask]
    
    # Preserve existing hidden fields and their calculations
    existing_hidden = df_input[df_input['type'] == 'hidden'].copy()
    
    # Convert specified types to hidden while preserving their data
    mask_indices = df_input.index[df_input['type'].str.contains('|'.join(typesconvert))]
    # Get hidden field names

    df_input.loc[mask_indices, 'type'] = 'hidden'
    df_input.loc[mask_indices, 'calculation'] = 'hidden'    

    # Handle label columns while preserving existing labels where needed
    label_cols = [col for col in df.columns if 'label' in col]
    df_input.loc[mask_indices, label_cols] = 'NO_LABEL'
    
    # Clear non-essential columns while preserving crucial data
    essential_cols = ['name', 'type', 'calculation'] + label_cols
    other_cols = df_input.columns.drop(essential_cols)
    df_input[other_cols] = ''
    
    # Preserve calculations for existing hidden fields
    df_input.update(existing_hidden[['calculation']])
    # SAVE THE INPUT NAMES
    hidden_names = list(df_input.loc[df_input['type']=='hidden', 'name'])
    if replace_dots:
        df_input['name'] = df_input['name'].map(remove_dots)
    # Handle indexing and grouping
    df_input.index = df_input.index.map(str)
    hidden_ids = df_input.loc[df_input['type']=='hidden'].index
    inputs_group_index = '0'
    new_hidden_ids = inputs_group_index + '.' + hidden_ids
    
    # Update indices
    index_map = dict(zip(hidden_ids, new_hidden_ids))
    df_input.rename(index=index_map, inplace=True)
    df_input.sort_index(inplace=True)
    df_input.reset_index(drop=True, inplace=True)
    
    if remove_dots:
        # Precompute replacement dictionary
        replacement_dict = {f'${old_name}': f'${remove_dots(old_name)}' for old_name in hidden_names if '.' in old_name}

        # Apply replacements to entire DataFrame
        df_input = df_input.astype(str).replace(replacement_dict, regex=False)
    

 
    
    
# put all together
    if 'data_load' not in df['name'].values:
        raise ValueError("data_load field not found in input dataframe")
    data_load_loc = df.index[df['name'] == 'data_load'][0]
    
    # Split the dataframe into three parts
    df_before_data_load = df.loc[:data_load_loc]  # Everything up to data_load
    df_until_begin_group = df.loc[data_load_loc+1:next_begin_group_loc-1]  # From data_load to next begin_group
    
    # Reset indices for proper concatenation
    df_input = df_input.reset_index(drop=True)
    df_before_data_load = df_before_data_load.reset_index(drop=True)
    df_until_begin_group = df_until_begin_group.reset_index(drop=True)
    
    # Concatenate in the correct order
    df_combined = pd.concat([
        df_before_data_load,  # First part until data_load
        df_input,            # Injected converted fields
        df_until_begin_group # Remaining part until next begin_group
    ]).reset_index(drop=True)
    
    # Handle post-break section
    df_after = df.loc[pausepoint+1:].reset_index(drop=True)
    if df_after.iloc[0,0] == 'end group':
        df_after = df_after.iloc[1:]
    
    # Final concatenation
    final_df = pd.concat([df_combined, df_after])
    if calculate_name:
        final_df.loc[final_df['name']=='hidden','calculation']='0'
    
    final_df.fillna('', inplace=True)
    final_df.reset_index(inplace=True, drop=True)
    
    return final_df, hidden_names



def get_tasksstrings(hidden_names, df_survey):
    '''This function makes a list of strings of hidden fields that will be loaded into a form that continues the consultation. 
    This is very handy as this string must be pasted into the tasks.js file in CHT. 
    @hidden_names: are the names of the 'hidden' fields in the input group of the follow up form
    @df_survey: is the survey tab of the complete (original) form without breaks, going from A to Z
    @tasks_strings: is the string that has to be pasted into tasks.js'''
    
    task_string_template = "content['{variableName}'] = getField(report, '{full_path}')"
    task_strings = {}
    for s in hidden_names:
        df_above_s = df_survey.iloc[:df_survey.loc[df_survey['name']==s].index[0]]
        df_above_s_groups = df_above_s.loc[df_above_s['type'].isin(['begin group', 'end group'])]
        above_s_grouprows = df_above_s_groups.index
        fullpath = []
        for i in above_s_grouprows:
            if df_above_s.iloc[i]['type']=='begin group':
                fullpath.append(df_above_s.iloc[i]['name'])
            else: 
                fullpath = fullpath[:-1]
        if len(fullpath)>0:
            line = task_string_template.format(
                variableName=s, full_path='.'.join(fullpath) + chf_clean_name(s)
            )
        else:
            line = task_string_template.format(
                variableName=s, full_path=chf_clean_name(s)
            )
        task_strings[s]=line
    return  list(task_strings.values())


def get_task_js(form_id, calculate_name, title, form_types, hidden_names, df_survey, repalce_dots=False, task_title="'id: '+getField(report, 'g_registration.p_id')+'; age: '+getField(report, 'p_age')+getField(report, 'g_registration.p_gender')+' months; '+getField(report, 'p_weight') + 'kg; ' + getField(report, 'g_fever.p_temp')+'°'"):
    task_name = f"{form_id}_{calculate_name}"
    task_name_upper = task_name.upper()

    
    return f"""
/* eslint-disable no-use-before-define */
/* eslint-disable */

const {{injectDataFromForm, isFormArrayHasSourceId}} = require('./stph-extras'); -> isFormArrayHasSourceId was missing from the imports

const CASE_DATA = ['{"','".join(hidden_names)}'];
    
const {{injectDataFromForm}} = require('./stph-extras');

const {task_name_upper}_FORMS = ['{"','".join(form_types)}'];

var task_title = "{task_title}"

const {task_name_upper}_TASK_FORM = '{form_id}_{calculate_name}';

const {task_name}Content =  function (content, contact, report){{

  injectDataFromForm(content, '', CASE_DATA, {task_name_upper}_FORMS, [report], {'true' if repalce_dots else  'false'});
  content['patient_id'] = report.contact._id;
  content['source_id'] = report._id;
  console.log(content);
  console.log(report);
}};
//TODO: redirect after task
/*function navigateToTask() {{
      Router.navigate(['first'])
}}*/


function {task_name}ContactLabel (){{
  task_title;
}}


function {task_name}ResolveIf(contact, report, event, dueDate) {{
  return isFormArrayHasSourceId( report, contact.reports, event, dueDate, {task_name_upper}_TASK_FORMS);
}}


module.exports = {{
  {task_name_upper}_TASK_FORM,
  {task_name_upper}_FORMS,
  {task_name}Content,
  {task_name}ContactLabel,
  {task_name}ResolveIf,
}}
// 
//// to be copied in task
//
//const {{
//  {task_name_upper}_TASK_FORM,
//  {task_name_upper}_FORMS,
//  {task_name}Content,
//  {task_name}ContactLabel,
//  {task_name}ResolveIf, }} = require('./{task_name}');
//
//module.exports = [
//
//    {{
//        name: '{task_name}',
//        icon: 'icon-healthcare-diagnosis',
//        title: 'diagnostic',
//        appliesTo: 'reports',
//        appliesToType: {task_name_upper}_FORMS,
//        actions: [
//            {{
//                type: 'report',
//                form: {task_name_upper}_TASK_FORM,
//                modifyContent: {task_name}Content
//            }}
//        ],
//        events: [
//            {{
//                id: '{task_name}',
//                days: 0,
//                start: 1,
//                end: 0
//            }}
//        ],
//        resolvedIf: {task_name}ResolveIf
//    }}
//];
"""

