import base64
import os
import re
from curses.ascii import isalnum, isalpha, isdigit

from numpy import isnan

from tricc.converters.utils import OPERATION_LIST, clean_name, remove_html
from tricc.models.tricc import *
from tricc.parsers.xml import (get_edges_list, get_mxcell,
                               get_mxcell_parent_list, get_tricc_type,
                               get_tricc_type_list)


import logging

logger = logging.getLogger("default")
MC_NODE_NAME = "id_{}"

def create_activity(full_order, name, media_path, json_nodes, last_page):
    # step can be
    # - list of id
    # - list of group
    # - older/neonat group
    groups = []
    nodes = []
    if last_page is None:
    
        prev = TriccNodeMainStart(id = generate_id()) 
        
    else:
        prev =TriccNodeActivityStart(id = generate_id())
    
    activity = TriccNodeActivity(
                root= prev,
                name=name,
                id=get_mc_name(name),       
                label=name
    )
    prev.activity = activity
    prev.group = activity
    activity.group = activity
    if last_page is not None:
        set_prev_next_node(last_page.nodes[len(last_page.nodes)-1],activity)
    

    
    if isinstance(full_order, Dict): # Older/neonal
        
        if "older" in full_order:
            group = create_group('older',activity)
            gr_nodes = create_node_list(full_order['older'], json_nodes = json_nodes, root=prev, group = group, activity = activity)
            if len(gr_nodes)>0:
                    nodes.extend(gr_nodes) 
                    prev=gr_nodes[len(gr_nodes)-1]
                    groups.append( group)      
        if "neonat" in full_order:
            group = create_group('neonat',activity)
            gr_nodes = create_node_list(full_order['neonat'], json_nodes = json_nodes, root=prev,   group = group, activity = activity)
            if len(gr_nodes)>0:
                nodes.extend(gr_nodes) 
                prev=gr_nodes[len(gr_nodes)-1]
                groups.append( group)
    elif isinstance(full_order, list) and len(full_order)>0: # simple list of tuple
        if isinstance(full_order[0], (int, str)):
            gr_nodes = create_node_list(full_order, json_nodes = json_nodes,  root=prev, activity = activity)
            if len(gr_nodes)>0:
                nodes.extend(gr_nodes)   
                prev=gr_nodes[len(gr_nodes)-1]        
        elif "data" in   full_order[0]:
            for grp in full_order:
                group = create_group(grp['title'],activity)
                gr_nodes = create_node_list(grp['data'], json_nodes = json_nodes, root=prev,   group = group, activity = activity)
                if len(gr_nodes)>0:
                    nodes.extend(gr_nodes) 
                    groups.append( group)
                    prev=gr_nodes[len(gr_nodes)-1]    
    if len(nodes)>0:
        activity.groups = groups
        activity.nodes = nodes
        return activity

    else:
        logger.warning("no node found for that activity {0}".format(name))
 
def get_mc_name(name, prefix = False):
    
    if prefix != False:
        return f"{prefix}.{name}"
    elif isinstance(name, str) and not isdigit(name[0]):
        return name 
    else:
        return MC_NODE_NAME.format(name)
    
       
def create_node( json_node, relevance = '' ,activity = None, group = None):
    if 'type' not in json_node or json_node['type']  == 'QuestionsSequence' or (json_node['type']  == 'Question' and 'formula'  in json_node ) or  json_node['type']  == 'FinalDiagnosis' :

        sub_type = 'qual' if 'type' not in json_node else 'diag' if json_node['type']  == 'FinalDiagnosis' else 'out' if json_node['type']  == 'QuestionsSequence' else 'flag'
        
        node =  TriccNodeCalculate(
            id = str(json_node['id']),
            name = get_mc_name(json_node['id'],sub_type),
            label= dict(json_node['label']),
            group=group if group is not None else activity,
            activity=activity
        )
        
    elif json_node['type']  == 'Question':
        if json_node['value_format']=="Integer":
            node =  TriccNodeInteger(
                id = str(json_node['id']),
                name = get_mc_name(json_node['id']),
                label= dict(json_node['label']),
                required = 1 if 'is_mandatory' in json_node and json_node["is_mandatory"]==True else None,
                group=group if group is not None else activity,
                activity=activity
            )            
        elif json_node['value_format']=="String":
            node =  TriccNodeText(
                id = str(json_node['id']),
                name = get_mc_name(json_node['id']),
                label= dict(json_node['label']),
                required = 1 if 'is_mandatory' in json_node and json_node["is_mandatory"]==True else None,
                group=group if group is not None else activity,
                activity=activity
            )
        elif json_node['value_format']=="Date":
            node =  TriccNodeDate(
                id = str(json_node['id']),
                name = get_mc_name(json_node['id']),
                label= dict(json_node['label']),
                required = 1 if 'is_mandatory' in json_node and json_node["is_mandatory"]==True else None,
                group=group if group is not None else activity,
                activity=activity
            )
        elif json_node['value_format']=="Float":
            node =  TriccNodeDecimal(
                id = str(json_node['id']),
                name = get_mc_name(json_node['id']),
                label= dict(json_node['label']),
                required = 1 if 'is_mandatory' in json_node and json_node["is_mandatory"]==True else None,
                group=group if group is not None else activity,
                activity=activity
            )            
        else:
            node =  TriccNodeSelectOne(
                id = str(json_node['id']),
                name = get_mc_name(json_node['id']),
                list_name = get_mc_name(json_node['id']),
                label= dict(json_node['label']),
                required = 1 if 'is_mandatory' in json_node and json_node["is_mandatory"]==True else None,
                group=group if group is not None else activity,
                activity=activity
            )
            node.options = get_options(json_node['answers'],node)
            if len(node.options) == 0:
                logger.warning("SelectOne {} without options, value_format : {}".format(str(json_node['label']), json_node['value_format']))
 
    return node
def create_node_list(full_order, json_nodes, activity,root=None,group = None,  relevance = None):
    nodes = []
    prev = root
    for elm in full_order:
        json_node = json_nodes[str(elm)]
        node = create_node(json_node, relevance, activity, group)
        if node is not None:
            if root is not None:
                set_prev_next_node(root,node)
            #prev=node
            nodes.append(node)
            #if isinstance(node, TriccNodeSelectOne):
            #    nodes.extend([value for value in node.options.values()])
    return nodes

def create_group(name,activity, relevance = None):
    return TriccGroup(
        id=name,
        relevance = relevance,
        label = name,
        name = get_mc_name(name),
        group= activity
    )
        
def get_options(answers,node):
    options = {}
    i = 0
    for key, elm in answers.items():
        options[i]= TriccNodeSelectOption(
            id= elm['id'],
            label = dict(elm['label']),
            name= get_mc_name(elm['id']),
            select = node,
            list_name= get_mc_name(node.id),
            ref_def= elm['reference'] if 'reference' in elm else None
        )
        i+=1
    return options
    
    
OPERATORS = {
    'more_or_equal':"{0}>={1}",
    'between':"{0}>={1} and {0}<{2}",
    'less':"{0}<{1}",
}
MC_IF_EXP = "if({0},{1},{2})"

MC_AND_EXP = "({0}) and ({1}) "
MC_COND_EXP = "${{{0}}} = '{1}'"

# int((today()-date(${date_naissance})) div 30.4)

def get_expression(node, json_node,all_nodes, prefix = ''):
    ref_str = None
    reference = []
    formula = None

    if 'formula' in json_node:
        if  json_node['formula'] == 'ToMonth':
            ref_str='birth_date'
            formula = "int((today()-date(${{{}}})) div 30.4)"
        elif  json_node['formula'] == 'ToDay':
            ref_str='birth_date'
            formula = "int((today()-date(${{{}}})))"
        elif isinstance(json_node['formula'],list) and len(json_node['formula'])==1 :
            ref_str=json_node['formula'][0]
            formula = "${{{}}}"
        elif json_node['formula'].startswith('[') and json_node['formula'].endswith(']'):
            ref_str=json_node['formula'][1:-1]
            formula = "${{{}}}"
        else:
            logger.warning('reference {} not found for {}'.format(json_node['formula'], json_node['id']))
            return None, None
        
        if ref_str is not None:
            ref = resolve_reference(ref_str, all_nodes, prefix)
            if ref is not None:

                expression = "''"
                if 'answers' in json_node and len(json_node['answers'].keys())>0:
                    for key, item in json_node['answers'].items():
                        item_exp = None
                        values = item['value'].split(',')
                        if  item['operator'] in OPERATORS  :
                            if item['operator'] == 'between':
                                reference = [*reference,ref,ref]
                            else:
                                reference = [*reference,ref]
                                
                            expression = MC_IF_EXP.format(
                                OPERATORS[item['operator']].format("__formula__",*values),
                                f"'{get_mc_name(item['id'])}'",
                                expression)
                            
                        elif item['operator'] is not None:
                            logger.warning('operator {} not found'.format(item['operator']))
                            return None, None
                        else:
                            pass
                    expression =  expression.replace('__formula__', formula )
                else:
                    expression = formula
                    reference = [*reference,ref]
                if reference is None or len(reference) == 0:
                    logger.warning('empty reference')   
                if node.reference is None:

                    node.reference =  reference
                    node.expression_reference=expression
                elif node.expression_reference is not None and expression is not None :
                    node.reference =  [*node.reference,*reference]
                    node.expression_reference = MC_AND_EXP.format(node.expression_reference,expression)
                
                
    return None, None

                

        
def build_relevance(all_nodes, age_node, js_nodes,  prefix = ''):
    for node in all_nodes:
        cur_node = node
        json_node = js_nodes[str(cur_node.id)] if str(cur_node.id) in js_nodes else None
        if json_node is not  None:
            cut_off_expr = generate_cut_off_exp(cur_node, age_node, json_node)
            if cut_off_expr is not None:
                rhombus = get_relevance_rhombus(cur_node,age_node,cut_off_expr, None, None )
                if rhombus is not None:
                    set_prev_next_node(rhombus, cur_node)
                    cur_node = rhombus
            if 'conditions' in json_node :
                process_relevance(cur_node, all_nodes,age_node,json_node['conditions'],  prefix )




def generate_cut_off_exp(node, age_node, js_parent):
    cond_exp=None
    ans_calc=None
    has_cut_off = False
    if 'cut_off_start' in js_parent or 'cut_off_end' in js_parent:
        has_cut_off = True
        if 'cut_off_start' in js_parent and js_parent['cut_off_start'] is not None:
            cond_exp = OPERATORS['more_or_equal'].format('${{{}}}',js_parent['cut_off_start'])
        if 'cut_off_end' in js_parent and js_parent['cut_off_end'] is not None: 
            cut_off_s = OPERATORS['less'].format('${{{}}}',js_parent['cut_off_end'])
            if cond_exp is not None:
                cond_exp = MC_AND_EXP.format(cond_exp,cut_off_s)             
            else:
                cond_exp = cut_off_s  
        return cond_exp      


            
def fetch_reference(all_nodes, prefix = ''):
    calculate_nodes = list(filter(lambda node: issubclass(node.__class__, TriccNodeCalculateBase), all_nodes))
    for node in calculate_nodes:
        if isinstance(node.reference, str):
            ref = resolve_reference(node.reference, all_nodes, prefix)
            if ref is not None:
                node.reference = [ref]
            else:
                logger.warning("reference {} not found for node {}".format(node.reference, node.id))
        elif isinstance(node.reference, list) and len(node.reference)>0 and isinstance(node.reference[0], str):
            str_refs =  node.reference
            refs=[]
            for str_ref in str_refs:
                ref = resolve_reference(str_ref, all_nodes, prefix)
                if ref is not None:
                    refs.append(ref)
                else:
                    break
            if len(refs) == len(str_refs):
                node.reference = refs
        elif node.reference is not None and not issubclass(node.__class__, TriccBaseModel):
            logger.warning(f"unsuported ref {node.reference.__class__}") 
                
def fetch_condition(all_nodes, js_nodes, prefix=''):
    age_node = resolve_reference("p_age_day", all_nodes, prefix)
    for node in all_nodes:
        if node.id in js_nodes:
            js_node = js_nodes[str(node.id)]
            get_expression(node,js_node, all_nodes, prefix)
            
            if 'conditions' in js_node:
                process_condition(node,all_nodes,age_node, js_node['conditions'],prefix)
                

                
def process_relevance(node,all_nodes, age_node, conditions, prefix = ''):
    reference = []
    expr = None
    cond_params = []
    pure_refs = []
    for condition in conditions:
        # save the param for factorisation
        val = None
        ref = resolve_reference(condition['node_id'], all_nodes, prefix)
        if isinstance(ref, TriccNodeSelectOne):
            val = resolve_reference(condition['answer_id'], list(ref.options.values()), prefix)
        elif 'answer_id' in condition:
            val = None
            expr = f"${{}} = '{condition['answer_id']}'"
        cut_off_exp = generate_cut_off_exp(node, age_node, condition)
        
        if expr is None and cut_off_exp is None:
            pure_refs.append(ref if val is None else val)
        else:
            rhombus = get_relevance_rhombus(node,age_node,cut_off_exp, (ref if val is None else val), expr )
            if rhombus is not None:
                
                pure_refs.append(rhombus)
        

    for pure_ref in pure_refs:
        set_prev_next_node(pure_ref,node)
    

        
def get_relevance_rhombus(node,age_node,cut_off_exp, ref, ref_expr ):
    expr = None
    reference = []
    prev = []
    # Merge exp
    if  ref_expr is not None:
        reference = [ref]
        if cut_off_exp is not None:
            expr = MC_AND_EXP.format(ref_expr,cut_off_exp)
        else:
            expr = ref_expr
    else:
        if cut_off_exp is not None :
            expr = cut_off_exp
        if ref is not None:
            prev = [ref]
        
    # Merge ref
        
    if cut_off_exp is not None:
        nb_age_ref = len(re.findall("\{\}", cut_off_exp))
        if nb_age_ref == 2:
            reference = [*reference,age_node, age_node]
        elif nb_age_ref == 1:
            reference = [*reference,age_node]
        else:
            logger.error(f"something not right with cut off {cut_off_exp}")
    
    if len(reference)>0 and expr is not None:
        rhombus =  TriccNodeRhombus(
            id=generate_id(),
            activity=node.activity,
            group=node.activity,
            reference = reference,
            expression_reference = expr,
            
        
        )
        for prev_node in [*reference]:
            set_prev_next_node(prev_node,rhombus )
        if ref is not None:
            set_prev_next_node(ref,rhombus )

        return rhombus
    
                

PREV_STAGE = {
    "id":"",
    "flag":"id",
    "out":"flag",
    "qual":"out",
    "diag":"quat"
    
}

def resolve_reference(ref, all_nodes, prefix = ''):
    if isinstance(ref, (str,int)):
        refs = list(filter(lambda n: n.name.endswith( str(ref)) and not isinstance(n,     TriccGroup) and (prefix == '' or n.name.startswith(prefix)) , all_nodes))
        if len(refs)==1:
            return refs[0]
        elif len(refs)>1:
            logger.warning("reference {}  found multiple times ".format( ref))
        elif prefix != '':
            return resolve_reference(ref, all_nodes, prefix = PREV_STAGE.get(prefix,''))
        else:
            logger.warning("reference {} not found".format( ref))

    else:
        logger.warning("reference not a string ({})".format(ref.__class__))
        
        
#####  deprecated #############################################################################3
#####  deprecated #############################################################################3
#####  deprecated #############################################################################3
#####  deprecated #############################################################################3
#####  deprecated #############################################################################3
#####  deprecated #############################################################################3
def process_condition(node,all_nodes, age_node, conditions, prefix = ''):
    reference = []
    expression = None
    for condition in conditions:
        ref = resolve_reference(condition['node_id'], all_nodes, prefix)
        if isinstance(ref, TriccNodeSelectOne):
            val = resolve_reference(condition['answer_id'], list(ref.options.values()), prefix)
        else:
            val = None
        if val is not None:
            process_cut_off(node, age_node, condition,expression = None,reference = [val])
        elif ref is not None  and 'answer_id' in condition:
            process_cut_off(node, age_node, condition,
                    expression = MC_COND_EXP.format("{{}}",get_mc_name(condition['answer_id'])),reference = [ref])
        elif  ref is not None:
            process_cut_off_old(node, age_node, condition,expression = None,reference = [ref])
            
def process_cut_off_old(node, age_node, js_parent,expression = None,reference = []):
    cond_exp = ''
    ans_calc=None
    has_cut_off = False
    if 'cut_off_start' in js_parent or 'cut_off_end' in js_parent:
        has_cut_off = True
        reference = [*reference, age_node]
        if 'cut_off_start' in js_parent and js_parent['cut_off_start'] is not None:
            cond_exp = OPERATORS['more_or_equal'].format('${{{}}}',js_parent['cut_off_start'])
        if 'cut_off_end' in js_parent and js_parent['cut_off_end'] is not None: 
            cut_off_s = OPERATORS['less'].format('${{{}}}',js_parent['cut_off_end'])
            if cond_exp != '':
                cond_exp = MC_AND_EXP.format(cond_exp,cut_off_s)             
            else:
                cond_exp = cut_off_s
    if cond_exp != '' and expression is not None:
        cond_exp = MC_AND_EXP.format(expression,cond_exp)
    elif expression is not None and isinstance(expression,str) :
        cond_exp = expression
    elif expression is not None:
        logger.warning("expression with a wrong type")
    elif reference is not None and isinstance(reference, list) and len(reference)>0 :
        #just a previous node
        ans_calc =   TriccNodeCalculate(
            id=generate_id(),
            prev_nodes=reference,
            activity = node.activity,
            group = node.activity
        )
        set_prev_next_node(reference[0],ans_calc)
        node.activity.nodes.append(ans_calc)
    if cond_exp != '':
        if hasattr(node, 'expression_reference') and node.expression_reference is not None:
            cond_exp = MC_AND_EXP.format(node.expression_reference, cond_exp)
        cond_exp = cond_exp if ans_calc is None else MC_AND_EXP.format(cond_exp,"${{{}}}>0")
        if not isinstance(cond_exp,str):
            logger.warning("wrong type")
        if hasattr(node, 'reference') and node.reference is not None and len(node.reference)>0:
            reference = [*node.reference, *reference]
        if has_cut_off and ans_calc is not None:
            reference =  [*reference,age_node,ans_calc]
        elif ans_calc is not None:
            reference = [*reference,ans_calc]
        if   issubclass(node.__class__, TriccNodeCalculateBase) and node.expression_reference is None:
            node.expression_reference = cond_exp
            if reference is None or len(reference) == 0:
                logger.warning('emptsy reference')
            if node.reference is not None and len(node.reference)>0:
                node.reference = [*node.reference, *reference]
            else:
                node.reference = reference
            if ans_calc is not None:
                set_prev_next_node(ans_calc,node)
        else:
            node_calc =   TriccNodeCalculate(
                id=generate_id(),
                expression_reference = cond_exp,
                reference=reference ,
                activity = node.activity,
                group = node.activity
                
            ) 
            set_prev_next_node(age_node,node_calc)
            set_prev_next_node(node_calc,node)
            if ans_calc is not None:
                set_prev_next_node(ans_calc,node_calc)
                
            node.activity.nodes.append(node_calc)