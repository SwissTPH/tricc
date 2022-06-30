

from tricc.converters.utils import clean_name
from tricc.converters.xml_to_tricc import is_ready_to_process
from tricc.models import *
from tricc.services.utils import walktrhough_tricc_node
import logging
logger = logging.getLogger('default')

def start_group( cur_group, groups, df_survey, relevance = False, **kargs):
    values = []
    for column in SURVEY_MAP:
        if column == 'type':
            values.append('begin group')
        elif column == 'name':
            value = clean_name(get_attr_if_exists(cur_group,column,SURVEY_MAP))
            if cur_group.id in groups:
                value = value + "_" + str(groups[cur_group.id])
                groups[cur_group.id] += 1
            else:
                groups[cur_group.id] = 0
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
            if cur_group.id in groups:
                value = value + "_" + str(groups[cur_group.id])
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
    ,'start':'begin group'
    ,'activity_start':'begin group'
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
    ,'activity_end':''
    ,'edge':''
    ,'page':'begin group'
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
CHOICE_MAP = {'list_name':'select', 'value':'name', 'label':'label' }
       

def get_attr_if_exists(node,column, map_array):
    if column in map_array:
        mapping = map_array[column]
        if isinstance(mapping, Dict) and node.odk_type in map_array[column]:
            odk_type =  map_array[column][node.odk_type]
            if odk_type[:6] == "select":
                return odk_type + " " + node.name
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
    

def generate_xls_form_export(node, processed_nodes, stashed_nodes, df_survey, df_choice, cur_group, **kargs):
    # check that all prev nodes were processed

    if is_ready_to_process(node,processed_nodes):
        if node.id not in processed_nodes :
            if node.group != cur_group :
                logger.debug("stashing node {}".format(node.get_name()))
                stashed_nodes[node.id]=node
                return False
            logger.debug("printing node {}".format(node.get_name()))
            if issubclass(node.__class__, (TriccNodeDisplayCalculateBase,TriccNodeDiplayModel)):
                if isinstance(node, TriccNodeSelectOption):
                    values = []
                    for column in CHOICE_MAP:
                        values.append(get_attr_if_exists(node,column,CHOICE_MAP))
                    df_choice.loc[len(df_choice)] = values
                elif node.odk_type in ODK_TRICC_TYPE_MAP and ODK_TRICC_TYPE_MAP[node.odk_type] is not None:
                    values = []
                    for column in SURVEY_MAP:
                        values.append(get_attr_if_exists(node,column,SURVEY_MAP))
                    df_survey.loc[len(df_survey)] = values
                else:
                    logger.warning("node {} have an unsupported type {}".format(node.get_name(),node.odk_type))
            processed_nodes[node.id] = node
            #continue walk °
            return True
    else:
        stashed_nodes[node.id]=node
    return False