# -*- coding: utf-8 -*-
"""
Created on Thu Sep  1 11:21:39 2022

@author: kluera

Make subforms that allow to be releoaded seperately as a 'task' in CHT, 
allowing to simulate a pause functionality. 
"""

import pandas as pd



def chf_clean_name(s, remove_dots=False):
    # Check if there is a dot in the string
    if "." in s:
        # Split the string into parts based on the dot
        s_p = s.split(".")
        # Return the formatted string
        if remove_dots:
          return "_".join(s_p)
        else:
          return f'["{".".join(s_p)}"]'
    else:
        # If no dot is present, return None or handle it as needed
        return s

# df is the dataframe to be split
# pausepoint is the index of the row after which the form should pause
def make_breakpoints(df, pausepoint, calculate_name=None):
    
    # get all data points that were collected before the break and convert into 'hidden' fields 
    # include the breakpoint itself
    df_input = df.loc[:pausepoint]
    
    # types you want to be loaded in the form after the pause
    typesconvert = ['hidden', 'integer', 'decimal', 'select_', 'text']
    # types you want to keep in the part that comes before the pause
    typeskeep = ['hidden', 'integer', 'decimal', 'select_', 'text', 'calculate'] 
    # mask for dropping irrelevant fields based on type
    m = df_input['type'].str.contains('|'.join(typeskeep))
    df_input = df_input.loc[m] # dropped irrelevant rows
    m = df_input['type'].str.contains('|'.join(typesconvert))
    df_input.loc[m, 'type'] = 'hidden' # convert all types into 'hidden'
    
    # add a data_load row, to load contextual parameters from the previous form
    d = {'type':['hidden'], 'name':['data_load']}
    d = pd.DataFrame.from_dict(d, orient='columns')
    df_input = pd.concat([df_input, d])
    
    cols = [col for col in df.columns if 'label' in col] # all columns that contain text for user (have 'label' in column name)
    df_input[cols] = 'NO_LABEL' # set the text of columns to NO_LABEL so that nothing shows up in CHT
    
    # drop 
    cols2 = df_input.columns.drop(cols)
    cols2 = cols2.drop(['name', 'type', 'calculation'])
    df_input[cols2]=''
    df_input.loc[df_input['type']=='hidden','calculation']=''
    
    df_input.index = df_input.index.map(str) # convert index to string for sorting 
    hidden_ids = df_input.loc[df_input['type']=='hidden'].index # extract the indices of the 'hidden' rows
    # index of the begin-group-inputs row:
    inputs_group_index = '0'
    # change index of the 'hidden' fields so that they end up in the 'inputs' group after sorting:
    new_hidden_ids = inputs_group_index + '.' + hidden_ids
    d = dict(zip(hidden_ids, new_hidden_ids))
    # put the new indices of the 'hidden' fields into the df:
    #df_input = df_input.rename(index = d)
    df_input.rename(index = d, inplace = True)
    df_input.sort_index(inplace = True) # sort the index
    df_input.reset_index(drop = True, inplace = True)
    
    hidden_names = list(df_input.loc[df_input['type']=='hidden', 'name'])
    
    # for some reason, in ODK, one cannot have empty groups that only contain 'hidden'
    # therefore we add an integer with relevance = false()
    intfill = pd.DataFrame({'type' : 'integer', 'name' : 'hidden_int', 'label::en' : 'NO_LABEL', 'relevance' : 'false()'}, index = [0.5])
        
    # wrap the entire df before the breakpoint into the 'inputs' group
    bgroup = pd.DataFrame({'type' : 'begin group', 'name' : 'inputs', 'label::en' : 'NO_LABEL', 'appearance':'field-list', 'relevance':'./source = \'user\''}, index = [-1])
    endinputgroupindex = df_input.loc[df_input['type']=='hidden'].index[-1]
    egroup = pd.DataFrame({'type' : 'end group', 'name':'inputs'}, index = [endinputgroupindex+0.5])
    df_input = pd.concat([bgroup, intfill, df_input, egroup])
    df_input.fillna('', inplace=True)
    df_input.sort_index(inplace = True)
    
    # make the df that resumes after the break, it starts right after the breakpoint
    df = df.loc[pausepoint+1:] 
    # if a breakpoint is on a page, it must be the last element of that page 
    # (it would make no sense to put a breakpoint in the middle of a page)
    # if the breakpoint was in a group the first row would be of type 'end group' and must be deleted
    if df.iloc[0,0] == 'end group':
        df = df.iloc[1:]
        
    # concat the inputs group with the form that resumes after the breakpoint
    df = pd.concat([df_input, df])
    if calculate_name:
        df.loc[df['name']=='hidden','calculation']='0'  
    df.fillna('', inplace = True)
    df.reset_index(inplace=True, drop=True)
    
    return df, hidden_names



def get_tasksstrings(hidden_names, df_survey):
    '''This function makes a list of strings of hidden fields that will be loaded into a form that continues the consultation. 
    This is very handy as this string must be pasted into the tasks.js file in CHT. 
    @hidden_names: are the names of the 'hidden' fields in the input group of the follow up form
    @df_survey: is the survey tab of the complete (original) form without breaks, going from A to Z
    @tasks_strings: is the string that has to be pasted into tasks.js'''
    d = {}
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
            fullpath = 'content.' + chf_clean_name(s, False) +' = getField(report, \'' + '.'.join(fullpath) + '.' + chf_clean_name(s) + '\');'
        else:
            fullpath = 'content.' + chf_clean_name(s, False) +' = getField(report, \'' + chf_clean_name(s) + '\');'
        d[s]=fullpath
    tasks_strings = list(d.values())
    
    return tasks_strings


def get_task_js(form_id, calculate_name, title, form_types, hidden_names, df_survey, task_title="'id: '+getField(report, 'g_registration.p_id')+'; age: '+getField(report, 'p_age')+getField(report, 'g_registration.p_gender')+' months; '+getField(report, 'p_weight') + 'kg; ' + getField(report, 'g_fever.p_temp')+'°'"):
    lines = get_tasksstrings(hidden_names, df_survey)
    indented_lines = '\n          '.join(lines)
    
    return f"""
    
const extras = require('./nools-extras');

const {{ addDays, getField}} = extras;

var task_title = "{task_title}"

module.exports = [
  {{
    name: '{form_id}_{calculate_name}',
    icon: 'icon-followup-general',
    title: '{title}',
    appliesTo: 'reports',
    appliesToType: ['{"','".join(form_types)}'],
    contactLabel: (contact, report) =>
      task_title,
    appliesIf: function (contact, report) {{
      return getField(report, 'source_id') === '' && getField(report, '{chf_clean_name(calculate_name)}') === '1';
   }},
    actions: [
      {{
        type: 'report',
        form: '{form_id}',
        modifyContent: function (content, contact, report) {{
          {indented_lines}
       }},
     }},
    ],
    events: [
      {{
        id:  '{form_id}_{calculate_name}',
        days: 1,
        start: 1,
        end: 0,
     }},
    ],
    resolvedIf: function (contact, report, event, dueDate) {{
      const startTime = Math.max(addDays(dueDate, -event.start).getTime(), report.reported_date);
      const endTime = addDays(dueDate, event.end + 1).getTime();
      const forms = ['reverse_alm_label_form_pause'];
      const matchingReports = contact.reports
        .filter((c_report) => forms.includes(c_report.form))
        .filter((c_report) => c_report.reported_date >= startTime && c_report.reported_date <= endTime)
        .filter((c_report) => getField(c_report, 'source_id') === report._id);
      return matchingReports.length > 0;
   }},
 }},
];
"""
