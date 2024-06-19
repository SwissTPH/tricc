import base64
import os
import re
from curses.ascii import isalnum, isalpha, isdigit

from numpy import isnan

from tricc_oo.converters.utils import OPERATION_LIST, clean_name, remove_html
from tricc_oo.models import *

from tricc_oo.visitors.tricc import set_prev_next_node,walktrhough_tricc_node_processed_stached,has_loop

import logging

logger = logging.getLogger("default")
MC_NODE_NAME = "id_{}"

def get_registration_nodes():
    js_nodes={}
    js_nodes['first_name'] = {
          "id":'first_name' ,
          "label": {
            "en": "First Name",
            "fr": "Prénom"
          },
          "type": "Question",
          "category": "patient_data",
          "value_format": "String"
    }
    js_nodes['last_name'] = {
        "id":'last_name' ,
        "label": {
        "en": "Last Name",
        "fr": "Nom de famille"
        },
        "type": "Question",
        "category": "patient_data",
        "value_format": "String"
    }
    js_nodes['birth_date'] = {
        "id":'birth_date' ,
        "label": {
        "en": "Date of birth",
        "fr": "Date de naissance"
        },
        "type": "Question",
        "category": "patient_data",
        "value_format": "Date"
    }
    return js_nodes

def get_last_node(node_dict):
    return max(node_dict.values(), key=lambda node: node.path_len)

def create_activity(full_order, name, media_path, json_nodes,  last_page, js_trad):
    groups = []
    nodes = {}
    # create start
    if last_page is None:
        prev = TriccNodeMainStart(id = generate_id()) 
    else:
        prev =TriccNodeActivityStart(id = generate_id())
    prev.path_len=1
    #create activity
    label = js_trad[name] if name in js_trad else name
    activity = TriccNodeActivity(
                root= prev,
                name=name,
                id=get_mc_name(name),       
                label=label
    )
    activity.group = activity
    activity.activity = activity
    # add activity to start
    prev.activity = activity
    prev.group = activity

    #loop on full order
    if isinstance(full_order, Dict): # Older/neonal
        if "older" in full_order:
            group = create_group('older',activity)
            gr_nodes = create_node_list(
                full_order['older'], 
                json_nodes = json_nodes, 
                root=prev, 
                group = group, 
                activity = activity,
                path_len = prev.path_len)
            if len(gr_nodes)>0:
                    nodes = {**nodes, **gr_nodes} 
                    prev=get_last_node(gr_nodes)
                    groups.append( group)      
        if "neonat" in full_order:
            group = create_group('neonat',activity)
            gr_nodes = create_node_list(full_order['neonat'], json_nodes = json_nodes, root=prev,   group = group, activity = activity)
            if len(gr_nodes)>0:
                nodes = {**nodes, **gr_nodes} 
                prev=get_last_node(gr_nodes)
                groups.append( group)
    elif isinstance(full_order, list) and len(full_order)>0: # simple list of tuple
        if isinstance(full_order[0], (int, str)):
            gr_nodes = create_node_list(full_order, json_nodes = json_nodes,  root=prev, activity = activity)
            if len(gr_nodes)>0:
                nodes = {**nodes, **gr_nodes}  
                prev=get_last_node(gr_nodes)        
        elif "data" in   full_order[0]:
            for grp in full_order:
                group = create_group(grp['title'],activity)
                gr_nodes = create_node_list(grp['data'], json_nodes = json_nodes, root=prev,   group = group, activity = activity)
                if len(gr_nodes)>0:
                    nodes = {**nodes, **gr_nodes}
                    groups.append( group)
                    prev=get_last_node(gr_nodes)    
    if len(nodes)>0:
        activity.groups = groups
        activity.nodes = nodes
        end = TriccNodeActivityEnd(
            activity = activity,
            group = activity
        )
        set_prev_next_node(get_last_node(activity.nodes), end)
        activity.nodes[end.id] = end
        
        return activity

    else:
        logger.warning("no node found for that activity {0}".format(name))
 
def get_mc_name(name, prefix = False):
    
    if prefix != False:
        return f"{prefix}{name}"
    elif isinstance(name, str) and not isdigit(name[0]):
        return name 
    else:
        return MC_NODE_NAME.format(name)
    

    
def to_node(model, json_node, activity, group = None, extra= {}, prefix='id.'):
    node =  model(
        id = f"{prefix}{json_node['id']}" ,
        name = get_mc_name(json_node['id'], prefix=prefix),
        label= dict(json_node['label']),
        group=group if group else activity,
        activity=activity,
        **extra
    )
    activity.nodes[node.id] = node
    if issubclass(node.__class__, TriccNodeCalculateBase):
            activity.calculates.append(node)
    elif issubclass(node.__class__, TriccNodeInputModel):
        if 'is_mandatory' in json_node and json_node["is_mandatory"]==True:
            node.required = 1
        if 'description' in json_node:
            node.help = json_node['description'] 
    return node

def create_node( json_node, relevance = '' ,activity = None, group = None):
    if 'type' not in json_node:
        node = to_node(TriccNodeCalculate, json_node, activity, group, prefix = 'qual.')
    #elif json_node['type']  == 'QuestionsSequence':
    #    node = to_node(TriccNodeCalculate, json_node, activity, group, prefix = 'qs.')
    elif    (json_node['type']  == 'Question' and 'formula'  in json_node ) :
        node = to_node(TriccNodeCalculate, json_node, activity, group, prefix = 'flag.')
    #elif json_node['type']  == 'FinalDiagnosis' :
    #    node = to_node(TriccNodeCalculate, json_node, activity, group, prefix = 'df.')
        
    elif json_node['type']  == 'Question':
        if json_node['value_format']=="Integer":
            node = to_node(TriccNodeInteger, json_node, activity, group)
        
        elif json_node['value_format']=="String":
            node =  to_node(TriccNodeText, json_node, activity, group)
        elif json_node['value_format']=="Date":
            node = to_node(TriccNodeDate, json_node, activity, group)
        elif json_node['value_format']=="Float":
            node =  to_node(TriccNodeDecimal, json_node, activity, group)
        else:
            extra = {'list_name':get_mc_name(json_node['id'])}
            node =  to_node(TriccNodeSelectOne, json_node, activity, group, extra)
            node.options = get_options(json_node['answers'],node)
            if len(node.options) == 0:
                logger.warning("SelectOne {} without options, value_format : {}".format(str(json_node['label']), json_node['value_format']))
    
    return node


def create_node_list(full_order, json_nodes, activity,root=None,group = None,  relevance = None, path_len=0):
    nodes = {}
    prev = root
    for elm in full_order:
        json_node = json_nodes[str(elm)]
        node = create_node(json_node, relevance, activity, group)
        node.path_len = path_len
        path_len += 1
        if node is not None:
            nodes[node.id]=(node)
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
            id= str(elm['id']),
            label = dict(elm['label']),
            name= get_mc_name(elm['id']),
            select = node,
            list_name= get_mc_name(node.id),
            ref_def= elm['reference'] if 'reference' in elm else None,
            activity= node.activity,
            group= node.group
        )
        i+=1
    return options


def get_mc_id(cur_node, js_nodes):
    id_parts = cur_node.id.split('.') if '.' in cur_node.id else ['',cur_node.id]
    json_node = None
    return    id_parts[0]  , '.'.join(id_parts[1:])


        
def build_relevance(all_nodes, age_node, js_nodes, js_diagnoses, js_final_diangnoses,  prefix = ''):
    for cur_node in all_nodes.values():
        id_parts = get_mc_id(cur_node, js_nodes)
        json_node = None
        if id_parts[0] not in ('dd_path', 'df') and id_parts[1] in js_nodes:
            if hasattr(cur_node, 'relevance'):
                json_node = js_nodes[id_parts[1]]
                build_question_relevance(cur_node, json_node, age_node, all_nodes, js_diagnoses, js_nodes)
        elif id_parts[0] not in ('df') and id_parts[1] in js_diagnoses:
            json_node = js_diagnoses[id_parts[1]]
            #TODO
        elif id_parts[1] in js_final_diangnoses:
            json_node = js_final_diangnoses[id_parts[1]]
            #TODO
        elif id_parts[0] != 'ref' and not isinstance(cur_node, TriccNodeActivityEnd):
            raise Exception(f"node {id_parts[1]} not found in the extended medalcreator source")
            
            
            
def build_question_expression( json_node, age_node,all_nodes, js_diagnoses, js_nodes):
    exp = []
    exp += generate_cut_off_exp( age_node, json_node)
    exp += generate_relevance_from_dd( json_node, js_diagnoses, all_nodes)
    exp += generate_relevance_from_qs( json_node, js_nodes, all_nodes)

    return exp

    
def build_question_relevance(cur_node, json_node, age_node,all_nodes, js_diagnoses, js_nodes):    
    exp = build_question_expression(json_node, age_node,all_nodes, js_diagnoses, js_nodes)
    if len(exp) == 1:
        cur_node.relevance = exp[0]
    elif len(exp) > 1:
        op = TriccOperation(TriccOperator.AND)
        op.reference = exp
        cur_node.relevance = op
    else:
        # no constrainst means root node
        set_prev_next_node(cur_node.activity.root, cur_node)
    if cur_node.relevance:
        prev_next_from_operation(cur_node, cur_node.relevance)


                
                





def generate_cut_off_exp(age_node, js_node):
    exp = []
    if 'cut_off_start' in js_node or 'cut_off_end' in js_node:
        if 'cut_off_start' in js_node and js_node['cut_off_start'] is not None:
            cs = TriccOperation(TriccOperator.MORE_OR_EQUAL)
            cs.append(age_node)
            cs.append(TriccStatic(js_node['cut_off_start']))
            exp.append(cs)
            
        if 'cut_off_end' in js_node and js_node['cut_off_end'] is not None: 
            ce = TriccOperation(TriccOperator.LESS)
            ce.append(age_node)
            ce.append(TriccStatic(js_node['cut_off_end']))
            exp.append(ce)

    return exp 

            
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

                
def generate_logic_exp( json_node, all_nodes):
    if 'conditions' in json_node:
        return  generate_condition_exp( json_node['conditions'], all_nodes)
    return []


def generate_condition_exp(list_conditions, all_nodes):        
    exp = []
    expr = None
    cond_params = []
    for condition in list_conditions:
        # save the param for factorisation
        val = None
        ref = resolve_reference(str(condition['node_id']), all_nodes)
        if ref:
            if isinstance(ref, TriccNodeSelectOne):
                val = resolve_reference(str(condition['answer_id']), ref.options, 'id.')
                select = TriccOperation(TriccOperator.SELECTED)
                select.append(ref)
                select.append(val)
                exp.append(select)
            elif 'answer_id' in condition:
                val = None
                eq = TriccOperation(TriccOperator.EQUAL)
                eq.append(ref) 
                eq.append(TriccStatic(condition['answer_id']))    
                exp.append(eq)        
        else:
            raise Exception(f"Reference not found for {condition['node_id']} with prefix '{prefix}' ")
    if len(exp)>1:
        ret = TriccOperation(TriccOperator.OR)
        ret.reference = exp
        return [ret]
    return exp
        
    

        
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
    "out.":"",
    "qual.":"out.",
    "dd_path.":"qual.",
    "flag.":"dd_path.",
    "qs.":'flag.',
    "qs_path.":'qs.',
    "id.":"qs_path.",
    "diag.":'id.'
}

def resolve_reference(ref, all_nodes, prefix = 'id.', full_search = True):
    if isinstance(ref, (str,int)):
        refs = list(filter(lambda n: n.id == f"{prefix}{ref}" and not isinstance(n,     TriccGroup)  , all_nodes.values()))
        if len(refs)==1:
            return refs[0]
        elif len(refs)>1:
            logger.warning("reference {}  found multiple times ".format( ref))
        elif prefix != '' and full_search:
            return resolve_reference(ref, all_nodes, prefix = PREV_STAGE.get(prefix,''))
        else:
            logger.warning("reference {} not found".format( ref))

    else:
        logger.warning("reference not a string ({})".format(ref.__class__))

def get_category_nodes(category, json_nodes):
    return list(filter(lambda n: n['category'] ==  category , json_nodes.values()))

def get_type_nodes(type, json_nodes):
    return list(filter(lambda n: n['type'] ==  type , json_nodes.values()))

def add_age_calcualte_nodes(all_nodes):
    brith_date_node = all_nodes['id.birth_date']
    age_day = TriccOperation('age_day')
    age_day.append(TriccStatic('id.birth_date'))
    # add p_age
    age_node = TriccNodeCalculate(
        name = 'ref.age_day',
        expression_reference = age_day,
        id = 'ref.age_day',
        activity = brith_date_node.activity,
        group = brith_date_node.activity
    )
    brith_date_node.activity.calculates.append(age_node)
    age_month = TriccOperation('age_month')
    age_month.append(TriccStatic('id.birth_date'))
    all_nodes[age_node.id]=age_node
    age_m_node = TriccNodeCalculate(
        name = 'ref.age_month',
        expression_reference = age_month,
        id = 'ref.age_month',
        activity = brith_date_node.activity,
        group = brith_date_node.activity
    )
    brith_date_node.activity.calculates.append(age_m_node)
    all_nodes[age_m_node.id]=age_m_node
   
    return age_node


def generate_relevance_from_dd(json_node, js_diagnoses, all_nodes):
    exp = []
    if json_node['id'] == 8005:
        pass
    if 'dd' in json_node:
        for dd in json_node['dd']:
            dd_exp = []
            if str(dd) in js_diagnoses:
                json_parent = js_diagnoses[str(dd)]
                dd_exp = generate_expression_from_instance(json_parent, json_node['id'], all_nodes)
                if dd_exp:
                    op = TriccOperation('and_or')
                    op.append(all_nodes[f"dd_path.{dd}"])
                    op.reference += dd_exp
                    exp.append(op)
                else:
                    op = TriccOperation('istrue')
                    op.append(all_nodes[f"dd_path.{dd}"])
                    exp.append(op)
    return exp


def generate_relevance_from_qs(json_node, json_nodes, all_nodes):
    exp = []
    if 'qs' in json_node:
        for qs in json_node['qs']:
            if str(qs) in json_nodes:
                json_parent = json_nodes[str(qs)]
                qs_exp = generate_expression_from_instance(json_parent, json_node['id'], all_nodes)
            else:
                raise Exception(f"qs {qs} not found")     
            if qs_exp:
                op = TriccOperation('and_or')
                op.append(all_nodes[f"qs_path.{qs}"])
                op.reference += qs_exp
                exp.append(op)
            else:
                op = TriccOperation('istrue')
                op.append(all_nodes[f"qs_path.{qs}"])
                exp.append(op)        
    return exp

# function to build relevance from instances of parents
# @param json_parent that have instance section, can be diagnostic or QS
# @param all nodes
# 

def generate_expression_from_instance(json_parent, mc_id, all_nodes):
    if str(mc_id) in json_parent['instances']:
        json_instance = json_parent['instances'][str(mc_id)]
        return generate_logic_exp( json_instance, all_nodes)
    return []    

        
def add_qd_dd_nodes(start_page, pages,age_node, json_nodes,js_diagnoses, all_nodes):
    
    bkg_nodes = get_type_nodes('QuestionsSequence', json_nodes)
    for bkg_json in bkg_nodes:
        node_id = f"qs.{bkg_json['id']}"
        if not node_id in all_nodes:
            activity = pages[bkg_json['system']] if 'system' in bkg_json  and bkg_json['system'] in pages else start_page
            node = to_node(TriccNodeCalculate, bkg_json, activity, prefix='qs.') 
            all_nodes[node.id] = node
        else:
            activity = all_nodes[node_id].activity
        node = to_node(TriccNodeCalculate, bkg_json, activity, prefix='qs_path.') 
        all_nodes[node.id] = node
    for diag_json in js_diagnoses.values():
        node = to_node(TriccNodeCalculate, diag_json, activity, prefix='dd_path.')
        node.expression_reference = TriccOperation(TriccOperator.ISTRUE)
        cc_node = resolve_reference(diag_json['complaint_category'],all_nodes )
        if cc_node:
            node.expression_reference.append(cc_node)
            all_nodes[node.id] = node
        else:
            raise Exception(f"CC {diag_json['complaint_category']} not found ")    
        
    for bkg_json in bkg_nodes:
        node_id = f"qs.{bkg_json['id']}"
        node = all_nodes[node_id]
        exp = generate_logic_exp(bkg_json, all_nodes)
        if len(exp) == 1:
            node.expression_reference = exp[0]
            prev_next_from_operation(node, exp[0])
        elif len(exp) > 1:
            op = TriccOperation(TriccOperator.AND)
            op.reference = exp
            node.expression_reference = op    
            prev_next_from_operation(node, op)
        
        exp = build_question_expression( bkg_json, age_node,all_nodes, js_diagnoses, json_nodes)
        node_id = f"qs_path.{bkg_json['id']}"
        node = all_nodes[node_id]
        if len(exp) == 1:
            node.expression_reference = exp[0]
            prev_next_from_operation(node, exp[0])
        elif len(exp) > 1:
            op = TriccOperation(TriccOperator.AND)
            op.reference = exp
            node.expression_reference = op
            prev_next_from_operation(node, op)
        else:
            raise Exception(f"no logic for qs {bkg_json['id']}")    

def prev_next_from_operation(node, operation):
    for r in operation.get_references():
        set_prev_next_node(r,node)   
            
def add_background_calculations(start_page, pages, json_nodes, all_nodes):
    bkg_nodes = get_category_nodes('background_calculation', json_nodes)
    for bkg_json in bkg_nodes:
        activity = pages[bkg_json['system']] if 'system' in bkg_json  and bkg_json['system'] in pages else start_page
        node = to_node(TriccNodeCalculate, bkg_json, activity, prefix='flag.') 
        all_nodes[node.id] = node


def build_calculations(start_page, pages, json_nodes, all_nodes):
    bkg_nodes = get_category_nodes('background_calculation', json_nodes)
    for bkg_json in bkg_nodes:
        node= all_nodes[f'flag.{bkg_json["id"]}']
        add_background_calculation_options(node, bkg_json, all_nodes)
        prev_next_from_operation(node,node.expression_reference)


    
def add_background_calculation_options(node, bkg_json, all_nodes):
        op = TriccOperation(TriccOperator.CASE)
        for a in bkg_json['answers'].values():
            if 'operator' in a:
                ref = get_formula_ref(bkg_json,  all_nodes)
                if ref:                                 # Manage slices
                    op.append(get_answer_operation(ref, a)) 
                    #op.append(TriccStatic(str(a['id'])))
                elif 'reference_table_x_id' in bkg_json: # manage ZScore
                    x_node =None
                    y_node =None
                    z_node =None
                    # run the code only if there is data in the setup fields, case condition
                    opa_c = TriccOperation('exists')
                    if bkg_json['reference_table_x_id'] is not None and bkg_json['reference_table_x_id']!= '':
                        x_node = resolve_reference(bkg_json['reference_table_x_id'], all_nodes)
                        opa_c.append(x_node)
                    if bkg_json['reference_table_y_id'] is not None and bkg_json['reference_table_y_id']!= '':
                        y_node = resolve_reference(bkg_json['reference_table_y_id'], all_nodes)
                        opa_c.append(y_node)
                    if bkg_json['reference_table_z_id'] is not None and bkg_json['reference_table_z_id']!= '':
                        z_node = resolve_reference(bkg_json['reference_table_z_id'], all_nodes)
                        opa_c.append(z_node)
                    
                    op.append(opa_c)
                    opa_v = None
                    if x_node and z_node:
                        opa_v = TriccOperation('izscore')
                        opa_v.append(x_node)
                        opa_v.append(z_node)
                    elif x_node and y_node:
                        opa_v = TriccOperation('zscore')
                        opa_v.append(x_node)
                        opa_v.append(y_node)

                    else:
                        pass
                    if opa_v:
                        op.append(opa_v)
                else:
                    raise NotImplementedError("opertaion not implemented, only slice and tables are")
        node.expression_reference = op
        node.activity.nodes[node.id] = node

def get_formula_ref(bkg_json, all_nodes):
    if 'formula' in bkg_json:
        if bkg_json["formula"] == "ToMonth":
            return all_nodes['ref.age_month']
        elif bkg_json["formula"] == "ToDay":
            return all_nodes['ref.age_day']
        elif bkg_json["formula"][0] == '[' and bkg_json["formula"][-1] == ']':
            return resolve_reference(bkg_json["formula"][1:-1], all_nodes)

def get_answer_operation(ref, a):
    opa = None
    val = a['value'].split(',')
    opa = TriccOperation(a['operator'])
    opa.append(ref)
    expected_values = 1 + int(a['operator'] == 'between')
    if len(val) != expected_values:
        raise ValueError(f"value for operator {a['operator']} in {a.id} needs {expected_values} values but {a['value']} found")
    for v in val:
        opa.append(v)
    return opa

#### WIP
# UNLOOP
# 1 - build the algorithm
# 2 - check for loops
# 3 - once on loop work with the chain X-a-s-d-f-r-X wher X is the duplicated node 
# 4 - loop reverse on the chain edges X-r then r-f ... to find the least expensive edge to replace (i.e. belonging to only 1 dd (take the dd of the qs if the question is in qs))
# 5 - remove the cheap edge and replace it with a link to a new instance of X that will take over the next edge from the base instance.abs
      
def  unloop_queston(root, pages, age, js_nodes,js_diagnoses, all_nodes):
    walktrhough_tricc_node_processed_stached(
        root, 
        has_loop, 
        processed_nodes = [], 
        stashed_nodes = [], 
        path_len = 0, 
        recursive=True, 
        warn = False,
        node_path=[],
        action_on_loop=unloop,
#        action_on_other=update_dd,
#        updates=[],
        all_nodes=all_nodes,
        js_nodes=js_nodes,
        js_diagnoses=js_diagnoses,
        )



    
def unloop(loop, js_nodes = None, js_diagnoses= None, all_nodes= None, **kwagrs):
    idx = len(loop)-1
    if js_nodes is None or js_diagnoses is None or  all_nodes is None:
        raise Exception(f"unloop needs those param js_nodes = dict(id: nodejs), updates = List(Dict(node: nodejs, dd:dd id)) ")
    update = unloop_steps(loop[idx],loop, idx, js_nodes, js_diagnoses, all_nodes)
    
    

                        
        
    
def unloop_steps(duplicate_node, loop, idx, js_nodes, js_diagnoses, all_nodes):
    prev_node= loop[idx-1]
    next_node = loop[idx]
    next_id_parts = get_mc_id(next_node, js_nodes)
    prev_id_parts = get_mc_id(prev_node, js_nodes)
    
    age_node = all_nodes['ref.age_day']
    # dd qns qs path should not trigger loop
        
    shared_dd_fw, shared_dd_bw, shared_dd = get_shared_dd(js_nodes[next_id_parts[1]], js_nodes[prev_id_parts[1]], js_nodes, js_diagnoses)
    if len(shared_dd_bw) == 1:

        if next_id_parts[0] in ('dd_path', 'qs_path'):
            #take the first node and duplicated it (unless the duplicated node is the QS itself)
            if next_node != duplicate_node:
                #get first node
                prev_node= loop[idx]
                next_node = loop[idx+1]
            

        #create new node instance
        new_node =next_node.make_instance(next_node.instance +1 )
        # update the Tricc tree
        set_prev_next_node(prev_node, new_node, next_node)
        exc_node = TriccNodeExclusive()
        set_prev_next_node(loop[0], exc_node )
        set_prev_next_node( exc_node, duplicate_node )
        new_json =js_nodes[next_id_parts[1]].copy()
        #update nodes_json
        new_json['dd']=[shared_dd_fw[0]]
        new_json['id'] = f"{id_parts[0]}.{node.id}"
        new_json['conditions'] = [js_nodes[id_parts[1]]['conditions'][prev_id_parts]]
        del js_nodes[id_parts[1]]['conditions'][prev_id_parts[1]]
        js_nodes[id_parts[1]]['dd'].remove(shared_dd_fw[0])
        # updates    js_diagnoses       
        
        for n in next_node.next_nodes:
            n_id_parts = get_mc_id(n, js_nodes)
            if  n_id_parts[1] in js_diagnoses[shared_dd_fw[0]]['instance']:
                if id_parts[1] in js_diagnoses[shared_dd_fw[0]]['instance'][n_id_parts[0]]['conditions']:
                    js_diagnoses[shared_dd_fw[0]]['instance'][n_id_parts[0]]['conditions'][id_parts[1]]['node_id']  =f"{id_parts[0]}.{node.id}"
                    # we add the reference to the new node
                    build_question_relevance(n, js_nodes[n_id_parts[1]], age_node, all_nodes, js_diagnoses, js_nodes)
            
                    
        
    elif idx>1: 
        return unloop_steps(duplicate_node, loop, idx-1, js_nodes, js_diagnoses, all_nodes)
    else:
        raise Exception(f"Unable to unloop {next_id_parts[0]}")
 

#def forkout_node(js_node, js_nodes, js_diagnoses, all_nodes):
    # check if QS, Calculate or Q
    # if QS, duplicate all content
    
        
def get_shared_dd(node_1, node_2, js_nodes, js_diagnoses):
    shared_dd = []
    shared_dd_fw = []
    shared_dd_bw = []
    node_1_dd = get_dd_hierachy(node_1, js_nodes)
    node_2_dd = get_dd_hierachy(node_2, js_nodes)
    node_1_id = str(node_1['id'])
    node_2_id = str(node_2['id'])
    
    #we look for shared diagnoses because that the only place were the edge n1 -> n2 or n2-> n1 might exist
    for dd in node_1_dd:
        if dd in node_2_dd:
            shared_dd.append(dd)
    # we look for diagnoses that have n1->n2
    for dd in set(shared_dd):
        js_diag = js_diagnoses[str(dd)]
        if node_1_id in js_diag['instances'] and node_2_id in js_diag['instances']:
            for c in js_diag['instances'][node_2_id]['conditions']:
                if 'node_id' in c and  c['node_id'] == node_1['id'] :
                    shared_dd_fw.append(dd)
            for c in js_diag['instances'][node_1_id]['conditions']:
               if 'node_id' in c and  c['node_id'] == node_2['id'] :
                    shared_dd_bw.append(dd)
            if dd in shared_dd_bw and dd in shared_dd_fw:
                raise Exception(f'loop detected inside the definition fo the diagnose {dd}')
    return shared_dd_fw, shared_dd_bw, shared_dd
        
    # we look for diagnose that have n2-> n1

            


def get_dd_hierachy(js_node, js_nodes):
    dd_list = []
    for dd in js_node['dd']:
        dd_list.append(dd)
    for  qs  in js_node['qs']:
        dd_list += get_dd_hierachy(js_nodes[str(qs)], js_nodes )  
    return set(dd_list)