

from tricc.models import *



def generate_xls_form_export(node, nodes, df_survey, df_choice, **kargs):
    # check that all prev nodes were processed

    if hasattr(node, 'prev_nodes' ):
        for prev_node in node.prev_nodes:
            if prev_node.id not in nodes:
                return None
    if node.id not in nodes:
        if issubclass(node.__class__, TriccNodeCalculateBase) or issubclass(node.__class__, TriccNodeDiplayModel):
            if isinstance(node, TriccNodeSelectOption):
                values = []
                for column in CHOICE_MAP:
                    values.append(get_attr_if_exists(node,column,CHOICE_MAP))
                df_choice.loc[len(df_choice)] = values
                pass
            elif node.odk_type in ODK_TRICC_TYPE_MAP and ODK_TRICC_TYPE_MAP[node.odk_type] is not None:
                values = []
                for column in SURVEY_MAP:
                    values.append(get_attr_if_exists(node,column,SURVEY_MAP))
                df_survey.loc[len(df_survey)] = values
        nodes[node.id] = node

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
    ,'activity_start':''
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
    