

import logging
#from bs4 import BeautifulSoup
from tricc_oo.converters.tricc_to_xls_form import (
        negate_term, VERSION_SEPARATOR,INSTANCE_SEPARATOR,  get_export_name)
from tricc_oo.converters.utils import clean_name, remove_html
from tricc_oo.models.lang import SingletonLangClass
from tricc_oo.models import *
import re
from tricc_oo.visitors.tricc import is_ready_to_process, process_reference, add_calculate
logger = logging.getLogger('default')

langs = SingletonLangClass()
TRICC_CALC_EXPRESSION = "${{{0}}}>0"

def start_group( strategy, cur_group, groups, df_survey, df_calculate, relevance = False, **kwargs):
    name = get_export_name(cur_group)
    
    if name in groups:
        groups[name] += 1
        name = (name + "_" + str(groups[name]))
        
    else:
        groups[name] = 0
    is_activity = isinstance(cur_group,TriccNodeActivity)
    relevance = relevance and  cur_group.relevance is not None and cur_group.relevance != '' 

    group_calc_required = False and relevance and not is_activity and len(relevance)> 100
    
    
    
    relevance_expression = cur_group.relevance
    if not relevance:
        relevance_expression = ''
    elif isinstance(relevance_expression, TriccOperation):
        relevance_expression = strategy.get_tricc_operation_expression(relevance_expression)
    elif isinstance(relevance_expression, TriccStatic):
        relevance_expression = str(relevance.value)
    
    #elif is_activity:
    #    relevance_expression = TRICC_CALC_EXPRESSION.format(get_export_name(cur_group.root))
    elif group_calc_required:
            relevance_expression = TRICC_CALC_EXPRESSION.format("gcalc_" + name)
        
## group
    values = []
    for column in SURVEY_MAP:
        if column == 'type':
            values.append('begin group')
        elif column == 'name':
            values.append(name)   
        elif  column == 'appearance':
            values.append('field-list')
        elif column == 'relevance':
            if relevance_expression is True:
                values.append('')
            else:
                values.append(relevance_expression)
            
        else:
            values.append(get_xfrom_trad(strategy, cur_group,column,SURVEY_MAP))
    df_survey.loc[len(df_survey)] = values

    ### calc
    if  group_calc_required and len(df_calculate[df_calculate['name'] == "gcalc_" + name]) == 0:
        calc_values =[]
        for column in SURVEY_MAP:
            if column == 'type':
                calc_values.append('calculate')
            elif column == 'name':
                value =  "gcalc_" + name
                calc_values.append(value)   
            elif column == 'calculation':
                calc_values.append(get_attr_if_exists(strategy, cur_group,'relevance',SURVEY_MAP))
            elif column == 'relevance':
                calc_values.append('')
            else:
                calc_values.append(get_xfrom_trad(strategy, cur_group,column,SURVEY_MAP))

        df_calculate.loc[len(df_calculate)] = calc_values
    
# def add_background_color(input_string, color):
#     """
#     Adds a background color to an HTML string or wraps a plain string in a <p> tag with the background color.
    
#     Args:
#         input_string (str): The input string, either plain text or HTML.
#         color (str): The background color to apply (e.g., 'yellow', '#ffcc00').
    
#     Returns:
#         str: The resulting HTML string with the background color applied.
#     """
#     if not input_string:
#         return input_string
#     # Parse the input string using BeautifulSoup
#     soup = BeautifulSoup(input_string, 'html.parser')
    
#     # Check if the input is already an HTML structure
#     if soup.find():  # If there are any tags in the input
#         # Add the background color to the root element's style attribute
#         root = soup.find()  # Get the first (root) element
#         existing_style = root.get('style', '')
#         root['style'] = f"{existing_style} background-color: {color};".strip()
#     else:
#         # Wrap the plain text in a <p> tag with the background color
#         soup = BeautifulSoup(f'<p style="background-color: {color};">{input_string}</p>', 'html.parser')
    
#     return str(soup)
    

def end_group( strategy, cur_group, groups, df_survey, **kwargs):
    
    values = []
    for column in SURVEY_MAP:
        if column == 'type':
            values.append('end group')
        elif column == 'relevance':
             values.append('')
        elif column in ('name'):
            value = (get_attr_if_exists(strategy, cur_group,column,SURVEY_MAP))
            
            if get_export_name(cur_group) in groups:
                value = (value + "_" + str(groups[get_export_name(cur_group)]) + "_end" )
            values.append(value)
        else:
            values.append(get_xfrom_trad(strategy, cur_group,column,SURVEY_MAP))
    df_survey.loc[len(df_survey)] = values


    # waltk thought the node,
    # if node has group, open the group (and parent group)
    # check process the next_node with the same group first, then process the other
    
    # if node has another group (not current) close the group
    # if node is an activity close  the group
    
    # during tricc object building/ or par of the stategy
    # static calculte node with same name:
    # follow same approach as the dynamic
    # if reference not in used_saves
    #   , then create calculate node reference_1 # and save is used_saves 'reference' : 1  
    # else create calculate node reference_(used_saves['reference']+1) # and update used_saves['reference'] += 1
    # once done, walkthrough again and remame  reference_(used_saves['reference']) to reference and create the other save 
ODK_TRICC_TYPE_MAP = { 'note':'note'
    ,'calculate':'calculate'
    ,'select_multiple':'select_multiple'
    ,'select_one':'select_one'
    ,'decimal':'decimal'
    ,'integer':'integer'
    ,'text':'text'
    ,'rhombus':'calculate'
    ,'goto':''#: start the linked activity within the target activity
    ,'start':''
    ,'activity_start':'calculate'
    ,'link_in':''
    ,'link_out':''
    ,'count':'calculate'
    ,'add':'calculate'
    ,'container_hint_media':''
    ,'activity':''
    ,'select_option':''
    ,'hint':''
    ,'help':''
    ,'exclusive':'calculate'
    ,'end':'calculate'
    ,'activity_end':'calculate'
    ,'edge':''
    ,'page':''
    ,'bridge':'calculate'
    ,'date':'date'
    ,'diagnosis':'calculate'
    ,'proposed_diagnosis':'calculate'
    ,'input': ''
    }

GROUP_TRICC_TYPE = [TriccNodeType.page,TriccNodeType.activity]
          
SURVEY_MAP = {
    'type':ODK_TRICC_TYPE_MAP, 'name':'name',
    **langs.get_trads_map('label'), **langs.get_trads_map('hint'),
    **langs.get_trads_map('help'), 'default':'default', 
    'appearance':'appearance', 'constraint':'constraint', 
    **langs.get_trads_map('constraint_message'), 'relevance':'relevance',
    'disabled':'disabled','required':'required',
    **langs.get_trads_map('required_message'), 'read only':'read only', 
    'calculation':'expression','repeat_count':'repeat_count','media::image':'image'
}
CHOICE_MAP = {'list_name':'list_name', 'value':'name', **langs.get_trads_map('label'), 'filter':'', 'y_min':'', 'y_max':'', 'l':'', 's':'', 'm':'' }
     
     
TRAD_MAP = ['label','constraint_message', 'required_message', 'hint', 'help']  

def get_xfrom_trad(strategy, node, column, mapping, clean_html = False ):
    arr = column.split('::')
    new_column = arr[0] if arr[0] != 'media' else "::".join(arr[0:2])
    trad =  arr[-1] if new_column != column  else None
    value = get_attr_if_exists(strategy, node, new_column, mapping)
    if (
        issubclass(node.__class__, TriccNodeDisplayCalculateBase) 
        and column == 'calculation' and isinstance(value, str) and not value.startswith('number')
    ):
        value = f"number({value})" if str(value) not in ['0', '1'] else value
    if clean_html and isinstance(value, str):
        value = remove_html(value)
    if column in TRAD_MAP:
        value = langs.get_trads(value, trad=trad)
    elif column == 'calculation' and isinstance(node, TriccNodeAcceptDiagnostic) and node.severity and not value:
         
            if node.severity == 'severe':
                value = 'severe'   
            elif node.severity == 'moderate':
                value = 'moderate'
            elif node.severity == 'light':
                value == 'light'
                

    return value

    


def get_attr_if_exists(strategy, node, column, map_array):
    if column in map_array:
        mapping = map_array[column]
        if isinstance(mapping, Dict) and getattr(node,'tricc_type', None) in map_array[column]:
            tricc_type =  map_array[column][node.tricc_type]
            if tricc_type[:6] == "select":
                return tricc_type + " " + node.list_name
            else:
                return tricc_type
        elif hasattr(node, map_array[column]):
            value =  getattr(node, map_array[column])
            if column == 'name':
                if issubclass(value.__class__, (TriccNodeBaseModel)):
                    return get_export_name(value)
                else:
                    return get_export_name(node)
            elif isinstance(value, (TriccOperation, TriccStatic, TriccReference)):
                expression =  strategy.get_tricc_operation_expression(value)
                return expression.replace('$this', '.') if isinstance(expression, str) else expression
            elif value is not None:
                return str(value) if not isinstance(value, dict) else value
            else:
                return ''
        else:
            return ''
    elif hasattr(node, column) and getattr(node, column) is not None:
        value = getattr(node, column)
        return str(value) if not isinstance(value,dict) else value
    else:
        return ''

def get_more_info_select(strategy, node):
    values = []
    for column in SURVEY_MAP:
        if column == 'type':
            values.append('select_one more_info')
        elif column == 'label':
            values.append("NO_LABEL")
        elif column == 'name':
            values.append(get_export_name(node) + '_optin')
        elif column == 'hint':
            values.append(get_xfrom_trad(strategy, node ,column,SURVEY_MAP))
        elif column == 'relevance':
            values.append(get_xfrom_trad(strategy, node.parent ,column,SURVEY_MAP))
        else:
            values.append(get_xfrom_trad(strategy, None,column,SURVEY_MAP))
    return values
    
def get_more_info_message(strategy, node):
    values = []
    for column in SURVEY_MAP:
        if column == 'type':
            values.append('note')
        elif column == 'relevance':
            values.append(f"${{{get_export_name(node)}_optin}} = 1" )
        elif column.startswith('hint'):
            values.append( langs.get_trads('', trad=None))    
        else:
            values.append(get_xfrom_trad(strategy, node,column,SURVEY_MAP))
    return values
def get_more_info_choice(strategy):
    values = []
    for column in CHOICE_MAP:
        if column == 'list_name':
            values.append('more_info')
        elif column == 'value':
            values.append('1')
        elif column.startswith('label'):
            arr = column.split('::')
            column = arr[0]
            trad =  arr[1] if len(arr)==2 else None
            values.append( langs.get_trads('more info', trad=trad))    
        else:
            values.append(get_xfrom_trad(strategy, None, column, CHOICE_MAP, True ))
    return values
 
def generate_xls_form_export(strategy, node, processed_nodes, stashed_nodes, df_survey, df_choice,df_calculate, cur_group, calculates, **kwargs):
    # check that all prev nodes were processed
    if is_ready_to_process(node,processed_nodes, strict=True) and process_reference(node, processed_nodes, calculates, replace_reference=False, codesystems= kwargs.get('codesystems', None)) :
        if node not in processed_nodes :
            add_calculate(calculates,node)  
            if node.group != cur_group and not isinstance(node,TriccNodeSelectOption) : 
                return False
            logger.debug("printing node {}".format(node.get_name()))
            # clean stashed node when processed
            if node in stashed_nodes:
                stashed_nodes.remove(node)
                logger.debug("generate_xls_form_export: unstashing processed node{} ".format(node.get_name()))
            if issubclass(node.__class__, ( TriccNodeDisplayCalculateBase,TriccNodeDisplayModel)):
                if isinstance(node, TriccNodeSelectOption):
                    values = []
                    for column in CHOICE_MAP:
                        values.append(get_xfrom_trad(strategy, node, column, CHOICE_MAP, True ))
                    # add only if not existing
                    if len(df_choice[(df_choice['list_name'] == node.list_name) & (df_choice['value'] == node.name)])  == 0:
                        df_choice.loc[len(df_choice)] = values
                elif isinstance(node, TriccNodeMoreInfo):
                        df_survey.loc[len(df_survey)] = get_more_info_select(strategy, node)
                        df_survey.loc[len(df_survey)] = get_more_info_message(strategy,node)
                        if len(df_choice[(df_choice['list_name'] == 'more_info')])  == 0:
                            df_choice.loc[len(df_choice)] = get_more_info_choice(strategy)
                elif node.tricc_type in ODK_TRICC_TYPE_MAP and ODK_TRICC_TYPE_MAP[node.tricc_type] is not None:
                    if ODK_TRICC_TYPE_MAP[node.tricc_type] =='calculate':
                        values = []
                        for column in SURVEY_MAP:
                            value = get_xfrom_trad(strategy, node, column, SURVEY_MAP )
                            if column == 'default' and issubclass(node.__class__, TriccNodeDisplayCalculateBase) and value == '':
                                    value = 0
                            values.append(value)
                        if len(df_calculate[df_calculate.name == get_export_name(node)])==0:
                            df_calculate.loc[len(df_calculate)] = values
                        else:
                            logger.error("name {} found twice".format(node.name))
                    elif  ODK_TRICC_TYPE_MAP[node.tricc_type] !='':
                        values = []
                        for column in SURVEY_MAP:
                            values.append(get_xfrom_trad(strategy, node,column,SURVEY_MAP))
                        df_survey.loc[len(df_survey)] = values
                    else:
                        logger.warning("node {} have an unmapped type {}".format(node.get_name(),node.tricc_type))
                else:
                    logger.warning("node {} have an unsupported type {}".format(node.get_name(),node.tricc_type))
            #continue walk °
            return True
    return False


def get_diagnostic_line(node):
    label = langs.get_trads(node.label, force_dict =True)
    empty = langs.get_trads('', force_dict =True)
    return [
        'select_one yes_no',
        clean_name("final.")+get_export_name(node),
        *list(label.values()) ,
        *list(empty.values()) ,#hint
        *list(empty.values()) ,#help
        '',#default
        '',#'appearance', clean_name
        '',#'constraint', 
        *list(empty.values()) ,#'constraint_message'
        TRICC_CALC_EXPRESSION.format(get_export_name(node)),#'relevance'
        '',#'disabled'
        '1',#'required'
        *list(empty.values()) ,#'required message'
        '',#'read only'
        '',#'expression'
        '',#'repeat_count'
        ''#'image'  
    ]
    
def get_input_line(node):
    label = langs.get_trads(node.label, force_dict =True)
    empty = langs.get_trads('', force_dict =True)
    return [
        'hidden',
        get_export_name(node),
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
        '',#'expression'
        '',#'repeat_count'
        ''#'image'  
    ]   
    
    

def get_diagnostic_start_group_line():
    label = langs.get_trads('List of diagnostics', force_dict =True)
    empty = langs.get_trads('', force_dict =True)
    return [
        'begin group',
        "l_diag_list25",
        *list(label.values()) ,
        *list(empty.values()) ,#hint
        *list(empty.values()) ,#help
        '',#default
        'field-list',#'appearance', 
        '',#'constraint', 
        *list(empty.values()) ,#'constraint_message'
        '',#'relevance'
        '',#'disabled'
        '',#'required'
        *list(empty.values()) ,#'required message'
        '',#'read only'
        '',#'expression'
        '',#'repeat_count'
        ''#'image'  
    ]
    
def get_diagnostic_add_line(diags, df_choice):
    for diag in diags:
        df_choice.loc[len(df_choice)] =  [
            "tricc_diag_add",
            get_export_name(diag),
            *list(langs.get_trads(diag.label, True).values()),
            '', # filter
            '', # min y
            '', # max Y
            '', # l
            '', # m
            '' # s
            
            
        ]
    label = langs.get_trads('Add a missing diagnostic', force_dict =True)
    empty = langs.get_trads('', force_dict =True)
    return [
        'select_multiple tricc_diag_add',
        "new_diag",
        *list(label.values()) ,
        *list(empty.values()) ,#hint
        *list(empty.values()) ,#help
        '',#default
        'minimal',#'appearance', 
        '',#'constraint', 
        *list(empty.values()) ,#'constraint_message',
        '',#'relevance'
        '',#'disabled'
        '',#'required'
        *list(empty.values()) ,#'required message'
        '',#'read only'
        '',#'expression'
        '',#'repeat_count'
        ''#'image'  
    ]  
    
def get_diagnostic_none_line(diags):
    relevance = ''
    for diag in diags:
        relevance += TRICC_CALC_EXPRESSION.format(get_export_name(diag)) + " or "
    label = langs.get_trads('Aucun diagnostic trouvé par l\'outil mais cela ne veut pas dire que le patient est en bonne santé', force_dict =True)
    empty = langs.get_trads('', force_dict =True)
    return [
        'note',
        "l_diag_none25",
        *list(label.values()) ,
        *list(empty.values()) ,
        *list(empty.values()) ,
        '',#default
        '',#'appearance', 
        '',#'constraint', 
        *list(empty.values()) ,
        f'not({relevance[:-4]})',#'relevance'
        '',#'disabled'
        '',#'required'
        *list(empty.values()) ,
        '',#'read only'
        '',#'expression'
        '',#'repeat_count'
        ''#'image'  TRICC_NEGATE
    ]
    
def  get_diagnostic_stop_group_line():
        label = langs.get_trads('', force_dict =True)
        return [
        'end group',
        "l_diag_list25",
        *list(label.values()) ,
        *list(label.values()) ,
        *list(label.values()) ,#help
        '',#default
        '',#'appearance', 
        '',#'constraint', 
        *list(label.values()) ,
        '',#'relevance'
        '',#'disabled'
        '',#'required'
        *list(label.values()) ,
        '',#'read only'
        '',#'expression'
        '',#'repeat_count'
        ''#'image'  
    ]