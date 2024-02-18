import base64
import os
import re
from curses.ascii import isalnum, isalpha, isdigit

from numpy import isnan

from tricc_oo.converters.utils import OPERATION_LIST, clean_name, remove_html
from tricc_oo.models import *
from tricc_oo.parsers.xml import (get_edges_list, get_mxcell,
                               get_mxcell_parent_list, get_tricc_type,
                               get_tricc_type_list)

from tricc_oo.visitors.tricc import set_prev_next_node
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
            prev_nodes = [prev],
            activity = activity,
            group = activity
        )
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
    elif json_node['type']  == 'QuestionsSequence':
        node = to_node(TriccNodeCalculate, json_node, activity, group, prefix = 'qs.')
    elif    (json_node['type']  == 'Question' and 'formula'  in json_node ) :
        node = to_node(TriccNodeCalculate, json_node, activity, group, prefix = 'flag.')
    elif json_node['type']  == 'FinalDiagnosis' :
        node = to_node(TriccNodeCalculate, json_node, activity, group, prefix = 'df.')
        
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
            if root is not None:
                set_prev_next_node(root,node)
            #prev=node
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


                

        
def build_relevance(all_nodes, age_node, js_nodes, js_diagnoses, js_final_diangnoses,  prefix = ''):
    for cur_node in all_nodes.values():
        id_parts = cur_node.id.split('.') if '.' in cur_node.id else ['',cur_node.id]
        json_node = None
        if id_parts[1] in js_nodes:
            if hasattr(cur_node, 'relevance'):
                json_node = js_nodes[id_parts[1]]
                build_question_relevance(cur_node, json_node, age_node, all_nodes)
        elif id_parts[1] in js_diagnoses:
            json_node = js_diagnoses[id_parts[1]]
            #TODO
        elif id_parts[1] in js_final_diangnoses:
            json_node = js_final_diangnoses[id_parts[1]]
            #TODO
        elif id_parts[0] != 'ref' and not isinstance(cur_node, TriccNodeActivityEnd):
            raise Exception(f"node {id_parts[1]} not found in the extended medalcreator source")
            
            
            
def build_question_relevance(cur_node, json_node, age_node,all_nodes):
    exp = []
    exp += generate_cut_off_exp(cur_node, age_node, json_node)
    exp += generate_dd_exp(cur_node, json_node, all_nodes)
    exp += generate_qs_exp(cur_node, json_node, all_nodes)
    exp += generate_logic_exp(cur_node, json_node, all_nodes)
    
    if len(exp) == 1:
        cur_node.relevance = exp[0]
    elif len(exp) > 1:
        op = TriccOperation(TriccOperator.AND)
        op.reference = exp
        cur_node.relevance = op
    #add prev nodes
    if cur_node.relevance:
        for r in cur_node.relevance.get_references():
            if issubclass(r.__class__, TriccNodeBaseModel):
                set_prev_next_node(r, cur_node)
         

def generate_dd_exp(cur_node, json_node, all_nodes):
    exp = []
    if 'dd' in json_node and json_node['dd']:
        for dd in json_node['dd']:
            if f"dd.{dd}" not in all_nodes:
                raise Exception(f"Missing dd {dd}")
            dde = TriccOperation('istrue')
            dde.append(all_nodes[ f"dd.{dd}"])
            exp.append(dde)
        if len(exp)>1:
            or_exp = TriccOperation('or')
            or_exp.reference = exp
            return [or_exp]

    return exp


def generate_qs_exp(cur_node, json_node, all_nodes):
    exp=[]
    if 'qs' in json_node:
        for qs in json_node['qs']:
            if f"qs.{qs}" not in all_nodes:
                raise Exception(f"Missing qs {qs}")
            qse = TriccOperation('istrue')
            qse.append(all_nodes[ f"qs.{qs}"])
            exp.append(qse)
        if len(exp)>1:
            or_exp = TriccOperation('or')
            or_exp.reference = exp
            return [or_exp]
            
    return exp


def generate_cut_off_exp(node, age_node, js_node):
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

                
def generate_logic_exp(cur_node, json_node, all_nodes): #(node,all_nodes, age_node, json_node, js_diagnoses, js_final_diangnoses, prefix = ''):
    exp = []
    expr = None
    cond_params = []
    if 'conditions' in json_node:
        for condition in json_node['conditions']:
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
    "dd.":"qual.",
    "diag.":"dd.",
    "flag.":"diag.",
    "qs.":'flag.',
    "id.":"qs.",
    
    


    
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

def add_diag_silo(activity, js_diagnoses, all_nodes):
    
    for diag_json in js_diagnoses.values():
        node = to_node(TriccNodeCalculate, diag_json, activity, prefix='dd.')
        node.expression_reference = TriccOperation(TriccOperator.ISTRUE)
        cc_node = resolve_reference(diag_json['complaint_category'],all_nodes )
        if cc_node:
            node.expression_reference.append(cc_node)
            #node.reference = node.expression_reference.get_references()        
            all_nodes[node.id] = node
        else:
            raise Exception(f"CC {diag_json['complaint_category']} not found ")    
        
def add_qs_expression(start_page, pages,age_node, json_nodes, all_nodes):
    
    bkg_nodes = get_type_nodes('QuestionsSequence', json_nodes)
    for bkg_json in bkg_nodes:
        node_id = f"qs.{bkg_json['id']}"
        if not node_id in all_nodes:
            activity = pages[bkg_json['system']] if 'system' in bkg_json  and bkg_json['system'] in pages else start_page
            node = to_node(TriccNodeCalculate, bkg_json, activity, prefix='qs.') 
            all_nodes[node.id] = node
    for bkg_json in bkg_nodes:
        node_id = f"qs.{bkg_json['id']}"
        node = all_nodes[node_id]
        exp = []
        exp += generate_cut_off_exp(node, age_node, bkg_json)
        exp += generate_dd_exp(node, bkg_json, all_nodes)
        exp += generate_logic_exp(node, bkg_json, all_nodes)
        if len(exp) == 1:
            node.expression_reference = exp[0]
        elif len(exp) > 1:
            op = TriccOperation(TriccOperator.AND)
            op.reference = exp
            node.expression_reference = op
def add_background_calculations(start_page, pages, json_nodes, all_nodes):
    bkg_nodes = get_category_nodes('background_calculation', json_nodes)
    for bkg_json in bkg_nodes:
        activity = pages[bkg_json['system']] if 'system' in bkg_json  and bkg_json['system'] in pages else start_page
        node = to_node(TriccNodeCalculate, bkg_json, activity, prefix='flag.') 
        all_nodes[node.id] = node

    
def add_background_calculation_options(node, bkg_json, all_nodes):
        op = TriccOperation(TriccOperator.CASE)
        for a in bkg_json['answers'].values():
            if 'operator' in a:
                ref = get_formula_ref(bkg_json,  all_nodes)
                if ref:                                 # Manage slices
                    op.append(get_answer_operation(ref, a)) 
                    op.append(TriccStatic(str(a['id'])))
                elif 'reference_table_x_id' in bkg_json: # manage ZScore
                    x_node =None
                    y_node =None
                    z_node =None
                    # run the code only if there is data in the setup fields, case condition
                    opa_c = TriccOperation('exists')
                    if bkg_json['reference_table_x_id']:
                        x_node = resolve_reference(bkg_json['reference_table_x_id'], all_nodes)
                        opa_c.append(x_node)
                    if bkg_json['reference_table_y_id']:
                        y_node = resolve_reference(bkg_json['reference_table_y_id'], all_nodes)
                        opa_c.append(y_node)
                    if bkg_json['reference_table_z_id']:
                        z_node = resolve_reference(bkg_json['reference_table_z_id'], all_nodes)
                        opa_c.append(z_node)
                    
                    op.append(opa_c)
                    opa_v = None
                    if x_node and z_node:
                        opa_v = TriccOperation('izscore')
                        opa_v.append(x_node)
                        opa_v.append(z_node)
                    elif x_node and z_node:
                        opa_v = TriccOperation('zscore')
                        opa_v.append(x_node)
                    op.append(opa_v)
                else:
                    raise NotImplemented("opertaion not implemented, only slice and tables are")
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