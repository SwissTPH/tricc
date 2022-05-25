
from tricc.models import *


columns = ['type','name','label','hint','help', 'constraint', 'default', 'appearance', 'constraint', 
           'constraint_message', 'relevance','disabled','required','required message', 'read only', 
           'expression','repeat_count','image' ]

def generate_xls_form_export(node, calculates, nodes):
    if issubclass(node.__class__, TriccNodeCalculateBase) or issubclass(node.__class__, TriccNodeDiplayModel):
        # check that all prev nodes were processed
        for prev_node in node.prev_nodes:
            if prev_node.id not in nodes:
                return None
        values = []
        for column in columns:
            values.append(get_attr_if_exists(node,column))
        if node.id not in nodes:
            print('|'.join(values))
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

          
        
        
def get_attr_if_exists(node,column ):
    if hasattr(node, column) and getattr(node, column) is not None:
       return str(getattr(node, column))
    else:
        return ''