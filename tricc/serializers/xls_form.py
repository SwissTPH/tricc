

from tricc.converters.utils import clean_name
from tricc.converters.tricc_to_xls_form import TRICC_CALC_EXPRESSION, TRICC_NEGATE
from gettext import gettext as _
from tricc.models import *

import logging
logger = logging.getLogger('default')

def start_group( cur_group, groups, df_survey, relevance = False, **kargs):
    values = []
    for column in SURVEY_MAP:
        if column == 'type':
            values.append('begin group')
        elif column == 'name':
            value = clean_name(get_attr_if_exists(cur_group,column,SURVEY_MAP))
            if cur_group.name in groups:
                groups[cur_group.name] += 1
                value = value + "_" + str(groups[cur_group.name])
            else:
                groups[cur_group.name] = 0
            values.append(value)
        elif column == 'label':
            values.append(get_attr_if_exists(cur_group,column,SURVEY_MAP))        
        elif  column == 'appearance':
            values.append('field-list')
        elif relevance and column == 'relevance':
            values.append(get_attr_if_exists(cur_group,column,SURVEY_MAP))
        else:
            values.append('')
    df_survey.loc[len(df_survey)] = values
    

def end_group( cur_group, groups, df_survey, **kargs):
    values = []
    for column in SURVEY_MAP:
        if column == 'type':
            values.append('end group')
        elif column in ('name','label'):
            value = get_attr_if_exists(cur_group,column,SURVEY_MAP)
            if cur_group.name in groups:
                value = value + "_" + str(groups[cur_group.name])
            values.append(value)
        else:
            values.append('')
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
    }

GROUP_ODK_TYPE = [TriccExtendedNodeType.page,TriccExtendedNodeType.activity]
          
SURVEY_MAP = {
    'type':ODK_TRICC_TYPE_MAP, 'name':'name',
    'label':'label', 'hint':'hint',
    'help':'help', 'default':'default', 
    'appearance':'appearance', 'constraint':'constraint', 
    'constraint_message':'constraint_message', 'relevance':'relevance',
    'disabled':'disabled','required':'required',
    'required message':'required message', 'read only':'read only', 
    'calculation':'expression','repeat_count':'repeat_count','image':'image'
}
CHOICE_MAP = {'list_name':'list_name', 'value':'name', 'label':'label' }
       

def get_attr_if_exists(node,column, map_array):
    if column in map_array:
        mapping = map_array[column]
        if isinstance(mapping, Dict) and node.odk_type in map_array[column]:
            odk_type =  map_array[column][node.odk_type]
            if odk_type[:6] == "select":
                return odk_type + " " + node.list_name
            else:
                return odk_type
        elif hasattr(node, map_array[column]):
            value =  getattr(node, map_array[column])
            if issubclass(value.__class__, TriccNodeBaseModel):
                return value.name
            elif value is not None:
                return str(value)
            else:
                return ''
        else:
            return ''
    elif hasattr(node, column) and getattr(node, column) is not None:
       return str(getattr(node, column))
    else:
        return ''
    

def generate_xls_form_export(node, processed_nodes, stashed_nodes, df_survey, df_choice,df_calculate, cur_group, **kargs):
    # check that all prev nodes were processed

    if is_ready_to_process(node,processed_nodes,stashed_nodes):
        if node not in processed_nodes :
            if node.group != cur_group :
                return False
            logger.debug("printing node {}".format(node.get_name()))
            # clean stashed node when processed
            if node in stashed_nodes:
                stashed_nodes.remove(node)
                logger.debug("generate_xls_form_export: unstashing processed node{} ".format(node.get_name()))
            if issubclass(node.__class__, ( TriccNodeDisplayCalculateBase,TriccNodeDiplayModel)):
                if isinstance(node, TriccNodeSelectOption):
                    values = []
                    for column in CHOICE_MAP:
                        values.append(get_attr_if_exists(node,column,CHOICE_MAP))
                    # add only if not existing
                    if len(df_choice[(df_choice['list_name'] == node.list_name) & (df_choice['value'] == node.name)])  == 0:
                        df_choice.loc[len(df_choice)] = values
                elif node.odk_type in ODK_TRICC_TYPE_MAP and ODK_TRICC_TYPE_MAP[node.odk_type] is not None:
                    if ODK_TRICC_TYPE_MAP[node.odk_type] =='calculate':
                        values = []
                        for column in SURVEY_MAP:
                            if column == 'default' and issubclass(node.__class__, TriccNodeDisplayCalculateBase):
                                values.append(0)
                            else:
                                values.append(get_attr_if_exists(node,column,SURVEY_MAP))
                        df_calculate.loc[len(df_calculate)] = values
                    elif  ODK_TRICC_TYPE_MAP[node.odk_type] !='':
                        values = []
                        for column in SURVEY_MAP:
                            values.append(get_attr_if_exists(node,column,SURVEY_MAP))
                        df_survey.loc[len(df_survey)] = values
                    else:
                        logger.warning("node {} have an unmapped type {}".format(node.get_name(),node.odk_type))
                else:
                    logger.warning("node {} have an unsupported type {}".format(node.get_name(),node.odk_type))
            #continue walk °
            return True
    return False


def get_diagnostic_line(node):
    return [
        'note',
        "label_"+node.name,
        node.get_name(),
        '',#hint
        '',#help
        '',#default
        '',#'appearance', 
        '',#'constraint', 
        '',#'constraint_message'
        TRICC_CALC_EXPRESSION.format(node.name),#'relevance'
        '',#'disabled'
        '',#'required'
        '',#'required message'
        '',#'read only'
        '',#'expression'
        '',#'repeat_count'
        ''#'image'  
    ]

def get_diagnostic_start_group_line():
    return [
        'begin group',
        "l_diag_list25",
        _('List des diagnostic'),
        '',#hint
        '',#help
        '',#default
        'field-list',#'appearance', 
        '',#'constraint', 
        '',#'constraint_message'
        '',#'relevance'
        '',#'disabled'
        '',#'required'
        '',#'required message'
        '',#'read only'
        '',#'expression'
        '',#'repeat_count'
        ''#'image'  
    ]
    
def get_diagnostic_none_line(diags):
    relevance = ''
    for diag in diags:
        relevance += TRICC_CALC_EXPRESSION.format(diag.name) + " or "
    
        
    
    return [
        'note',
        "l_diag_none25",
        _('Aucun diagnostic trouvé par l\'outil mais cela ne veut pas dire que le patient est en bonne santé'),
        '',#hint
        '',#help
        '',#default
        '',#'appearance', 
        '',#'constraint', 
        '',#'constraint_message'
        TRICC_NEGATE.format(relevance[:-4]),#'relevance'
        '',#'disabled'
        '',#'required'
        '',#'required message'
        '',#'read only'
        '',#'expression'
        '',#'repeat_count'
        ''#'image'  
    ]
    
def  get_diagnostic_stop_group_line():
        return [
        'end group',
        "l_diag_list25",
        '',
        '',#hint
        '',#help
        '',#default
        '',#'appearance', 
        '',#'constraint', 
        '',#'constraint_message'
        '',#'relevance'
        '',#'disabled'
        '',#'required'
        '',#'required message'
        '',#'read only'
        '',#'expression'
        '',#'repeat_count'
        ''#'image'  
    ]