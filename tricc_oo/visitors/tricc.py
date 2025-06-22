import re
import logging

from tricc_oo.converters.utils import *
from tricc_oo.models import *
from tricc_oo.visitors.tricc import *
from tricc_oo.visitors.utils import PROCESSES
from tricc_oo.converters.datadictionnary import lookup_codesystems_code

logger = logging.getLogger("default")
ONE_QUESTION_AT_A_TIME = False

TRICC_TRUE_VALUE = 'true'
TRICC_FALSE_VALUE = 'false'

def merge_node(from_node,to_node):
    if from_node.activity != to_node.activity:
        logger.critical("Cannot merge nodes from different activities")
    elif issubclass(from_node.__class__, TriccNodeCalculateBase) and issubclass(to_node.__class__, TriccNodeCalculateBase):
        for e in to_node.activity.edges:
            if e.target == from_node.id:
                e.target = to_node.id
    else:
        logger.critical("Cannot merge not calculate nodes ")
    

def get_max_version(dict):
    max_version = None
    for id, sim_node in dict.items():
        if max_version is None or  max_version.version < sim_node.version :
            max_version = sim_node
    return max_version

def get_versions(name, iterable):
    return [n for n in iterable if version_filter(name)(n)]

def version_filter(name):
    return lambda item: hasattr(item, 'name') and ( (isinstance(item, TriccNodeEnd) and name == item.get_reference()) or item.name == name ) and not isinstance(item, TriccNodeSelectOption)

def get_last_version(name, processed_nodes,  _list=None):
    max_version = None
    if isinstance(_list, dict):
        _list = _list[name].values() if name in _list else []
    if _list is None:
        if isinstance(processed_nodes, OrderedSet):
            return processed_nodes.find_last(version_filter(name))
        else:    
            _list = get_versions(name, processed_nodes)
    if _list:
        for  sim_node in _list:
            # get the max version while not taking a node that have a next node before next calc
            if ((max_version is None 
                or  max_version.activity.path_len < sim_node.activity.path_len
                or  max_version.path_len < sim_node.path_len 
                or (max_version.path_len == sim_node.path_len and hash(max_version.id) < hash(sim_node.id))
                ) ):
                max_version = sim_node
    if not max_version:
        already_processed = list(filter(lambda p_node: hasattr(p_node, 'name') and p_node.name == name , _list))
        if already_processed:
            max_version = sorted(filtered, key=lambda x: x.path_len, reverse=False)[0]
    
    return max_version


# main function to retrieve the expression from the tree
# node is the node to calculate
# processed_nodes are the list of processed nodes
def get_node_expressions(node, processed_nodes, process=None):
    get_overall_exp = issubclass(node.__class__, TriccNodeCalculateBase) and not issubclass(node.__class__, (TriccNodeDisplayBridge,TriccNodeBridge))
    expression = None
    # in case of recursive call processed_nodes will be None
    if processed_nodes is None or is_ready_to_process(node, processed_nodes=processed_nodes):
        expression = get_node_expression(node, processed_nodes=processed_nodes, get_overall_exp=get_overall_exp, process=process)
        
    # if get_overall_exp:
    #     if expression  and (not isinstance(expression, str) or expression != '') and  expression is not TriccStatic(True) :
    #         num_expression = TriccOperation(
    #             TriccOperator.CAST_NUMBER,
    #             [expression]
    #         )
    #     elif expression is TriccStatic(True)  or (not expression and get_overall_exp):
    #         expression = TriccStatic(True)               
    #     else:
    #         expression = None
    if (
        issubclass(node.__class__, TriccNodeCalculateBase) 
        and not isinstance(expression, (TriccStatic, TriccReference, TriccOperation)) 
        and str(expression) != '' 
        and not isinstance(node, (TriccNodeWait, TriccNodeActivityEnd, TriccNodeActivityStart, TriccNodeEnd))
    ):
        logger.warning("Calculate {0} returning no calculations".format(node.get_name()))
        expression = TriccStatic(True)
    return expression

def set_last_version_false(node, processed_nodes):
    if isinstance(node, (TriccNodeDiagnosis, TriccNodeSelectOption)):
        return
    node_name = node.name if not isinstance(node, TriccNodeEnd) else node.get_reference()
    #last_version = get_last_version(node_name, processed_nodes) if issubclass(node.__class__, (TriccNodeDisplayModel, TriccNodeDisplayCalculateBase, TriccNodeEnd)) and not isinstance(node, TriccNodeSelectOption)  else  None
    last_version = processed_nodes.find_prev(node, version_filter(node_name))
    if last_version and getattr(node, 'process', '') != 'pause':
        # 0-100 for manually specified instance.  100-200 for auto instance 
        node.version = get_next_version(node.name, processed_nodes, last_version.version, 0)
        last_version.last = False
        node.path_len = max(node.path_len, last_version.path_len + 1)
    return last_version
        
def get_version_inheritance(node, last_version, processed_nodes):
        # FIXME this is for XLS form where only calculate are evaluated for a activity that is not triggered
        if not issubclass(node.__class__, (TriccNodeInputModel)):
            node.last = True
            if (
                issubclass(node.__class__, (TriccNodeDisplayCalculateBase, TriccNodeEnd)) and node.name is not None
            ):
                #logger.debug("set last to false for node {}  and add its link it to next one".format(last_used_calc.get_name()))
                if node.prev_nodes:    
                    set_prev_next_node(last_version, node)
                else:
                    expression = node.expression or node.expression_reference or getattr(node, 'relevance', None)
                    expression = merge_expression(expression, last_version)
                    if node.expression:
                        node.expression = expression
                    elif node.expression_reference:
                        node.expression_reference = expression
                    elif node.relevance:
                        node.relevance = expression
        else:
            node.last = False
            calc = TriccNodeCalculate(
                id=generate_id(f"save{node.id}"),
                name=node.name,
                path_len=node.path_len+1,
                #version=get_next_version(node.name, processed_nodes, node.version+2),
                expression= merge_expression(node, last_version),
                label= f"merge{node.id}",
                last=True,
                activity=node.activity,
                group=node.group
                )
            node.activity.nodes[calc.id]=calc
            node.activity.calculates.append(calc)
            #set_last_version_false(calc, processed_nodes)
            processed_nodes.add(calc)
            if issubclass(node.__class__, TriccNodeInputModel):
                node.expression = TriccOperation(
                    TriccOperator.COALESCE,
                    [
                        '$this',
                        last_version
                    ]
                )
                
def merge_expression(expression, last_version):
    datatype = expression.get_datatype()
    if datatype == 'boolean':
        expression = or_join(
            [TriccOperation(TriccOperator.ISTRUE, [last_version]), expression]
        )
    
    elif datatype == 'number':
        expression = TriccOperation(
            TriccOperator.PLUS,
            [last_version, expression] 
        )
    else:
        expression = TriccOperation(
            TriccOperator.COALESCE,
            [last_version, expression] 
        )
    return expression

def process_calculate(node,processed_nodes, stashed_nodes, calculates, used_calculates, 
                      warn = False, process=None, **kwargs ):
     # used_calculates dict[name, Dict[id, node]]
     # processed_nodes Dict[id, node]
     # calculates  dict[name, Dict[id, node]]
     
    
    if node not in processed_nodes:
        # generate condition
        if (
            is_ready_to_process(node, processed_nodes,True)
            and process_reference(
                node, 
                processed_nodes=processed_nodes, 
                calculates=calculates,
                used_calculates=used_calculates,
                replace_reference=False, 
                warn = warn, 
                codesystems= kwargs.get('codesystems', None)
            ) 
        ):
            if kwargs.get('warn', True):
                logger.debug('Processing relevance for node {0}'.format(node.get_name()))
            # tricc diagnostic have the same name as proposed diag but will be serialised with different names

            last_version =  set_last_version_false(node, processed_nodes)
            if last_version:
                last_version = get_version_inheritance(node, last_version, processed_nodes)

            generate_calculates(node,calculates, used_calculates,processed_nodes=processed_nodes, process=process)               
       
                

        # if has prev, create condition
            if hasattr(node, 'relevance') and (node.relevance is None or isinstance(node.relevance, TriccOperation)):
                node.relevance = get_node_expressions(node, processed_nodes=processed_nodes, process=process)
                # manage not Available
                if isinstance(node, TriccNodeSelectNotAvailable):
                    # update the checkbox
                    if node.parent: 
                        if len(node.prev_nodes) == 1:
                            prev = list(node.prev_nodes)[0]
                            if isinstance(prev, TriccNodeMoreInfo) and prev.parent.name == node.name:
                                prev.parent = node
                            
          
                        # managing more info on NotAvaialbee
                        parent_empty = TriccOperation(TriccOperator.ISNULL, [node.parent])
                        node.relevance  = and_join([node.parent.relevance, parent_empty])
                        node.required = parent_empty
                        node.constraint = parent_empty
                        node.constraint_message = "Cannot be selected with a value entered above"
                        # update the check box parent : create loop error
                        node.parent.required = None  # "${{{0}}}=''".format(node.name)
                    else:
                        logger.warning("not available node {} does't have a single parent".format(node.get_name()))               
                elif isinstance(node.relevance, TriccOperation):
                    relevance_reference = list(node.relevance.get_references())
                    for r in relevance_reference:
                        if issubclass(r.__class__, (TriccNodeDisplayCalculateBase )):
                            add_used_calculate(node, r, calculates, used_calculates, processed_nodes)
                
            if last_version and hasattr(node, 'relevance'):
                if isinstance(node, TriccNodeInputModel):
                    version_relevance =  TriccOperation(
                            TriccOperator.ISNULL,
                            [last_version]
                        )
                elif last_version.relevance:
                        version_relevance = not_clean(
                                last_version.relevance
                            )
                elif last_version.activity.relevance:
                    version_relevance = not_clean(
                            last_version.activity.relevance,
                    )
                else:
                    version_relevance = None
                
                if version_relevance:
                    if getattr(node, 'relevance', None):
                        node.relevance = and_join(
                            [
                                version_relevance,
                                node.relevance
                            ])
                        
                    elif hasattr(node, 'relevance'):
                        node.relevance = version_relevance

            #if hasattr(node, 'next_nodes'):
                #node.next_nodes=reorder_node_list(node.next_nodes, node.group)
            process_reference(
                node, 
                processed_nodes=processed_nodes, 
                calculates=calculates,
                used_calculates=used_calculates, 
                replace_reference=True, 
                warn = warn, 
                codesystems= kwargs.get('codesystems', None)
            )
            if isinstance(node, (TriccNodeMainStart, TriccNodeActivityStart)):
                process_reference(
                    node.activity,
                    processed_nodes=processed_nodes, 
                    calculates=calculates,
                    used_calculates=used_calculates, 
                    replace_reference=True, 
                    warn = warn, 
                    codesystems= kwargs.get('codesystems', None)
                )

            return True
    # not ready to process or already processed

    return False
      


def get_max_named_version(calculates,name):
    max = 0
    if name  in calculates:
        for  node in calculates[name].values():
            if node.version > max:
                max = node.version
    return max

def get_count_node(node):
    count_id = generate_id(f"count{node.id}")
    count_name = "cnt_"+count_id
    return TriccNodeCount(
        id = count_id,
        group = node.group,
        activity = node.activity,
        label = "count: "+node.get_name(),
        name = count_name,
        path_len=node.path_len
    )
    
### Function that inject a wait after path that will wait for the nodes
def get_activity_wait(prev_nodes, nodes_to_wait, next_nodes, replaced_node = None, edge_only = False, activity = None):

    if issubclass(nodes_to_wait.__class__,TriccBaseModel):
        nodes_to_wait = [nodes_to_wait]
    if issubclass(prev_nodes.__class__,TriccBaseModel):
        prev_nodes = set([prev_nodes])
    elif isinstance(prev_nodes, list):
        prev_nodes = set(prev_nodes)
        
    iterator = iter(prev_nodes)
    prev_node = next(iterator)
    path = prev_node if len(prev_nodes) == 1 else get_bridge_path(prev_nodes, activity)
 
    activity = activity or prev_node.activity
    calc_node = TriccNodeWait(
            id = generate_id(f"ar{''.join([x.id for x in nodes_to_wait])}{activity.id}"),
            reference = nodes_to_wait,
            activity = activity,
            group = activity,
            path = path
        )

    #start the wait and the next_nodes from the prev_nodes
    #add the wait as dependency of the next_nodes

        # add edge between rhombus and node

    set_prev_next_node(path,calc_node, edge_only=edge_only, activity=activity )
    for next_node in next_nodes:
            #if prev != replaced_node and next_node != replaced_node :
            #    set_prev_next_node(prev,next_node,replaced_node)
                #if first:
                #first = False 
        set_prev_next_node(calc_node,next_node, edge_only=edge_only,activity=activity)
         
        
    return calc_node
    
def get_bridge_path(prev_nodes, node=None,edge_only=False):
    iterator = iter(prev_nodes)
    p_p_node = next(iterator)    
    if node is None:
        node = p_p_node
    calc_id  = generate_id(f"br{''.join([x.id for x in prev_nodes])}{node.id}")
    calc_name = "path_"+calc_id
    data = {
        'id': calc_id,
        'group':  node.group,
        'activity': node.activity,
        'label': "path: " + ( node.get_name()),
        'name': calc_name,
        'path_len': node.path_len + 1 * (node == p_p_node)
    }
    
    if len(prev_nodes)>1 and sum([0 if issubclass(n.__class__, (TriccNodeDisplayCalculateBase, TriccNodeRhombus)) else 1 for n in prev_nodes])>0 :
        calc= TriccNodeDisplayBridge( **data)
    else:
        calc =  TriccNodeBridge( **data)
    return calc
    
def inject_bridge_path(node, nodes):

    prev_nodes = [nodes[n.source] for n in list(filter(lambda x: (x.target == node.id or x.target == node) and x.source in list(nodes.keys()), node.activity.edges))] 
    if prev_nodes:
        calc = get_bridge_path(prev_nodes, node,edge_only=True)

        for e in node.activity.edges:
            if e.target == node.id:
                # if e.source in node.activity.nodes and len(node.activity.nodes[e.source].next_nodes):
                #     set_prev_next_node(node.activity[e.source], node, edge_only=True, replaced_node=node)
                # else:
                    e.target = calc.id
   
        # add edge between bridge and node
        set_prev_next_node(calc,node,edge_only=True, activity=node.activity)
        node.path_len += 1
        return calc


def inject_node_before(before, node, activity):
    before.group = activity
    before.activity = activity
    activity.nodes[before.id] = before
    nodes = activity.nodes
    prev_nodes = node.prev_nodes.union(set(nodes[n.source] for n in list(filter(lambda x: (x.target == node.id or x.target == node) and x.source in nodes, node.activity.edges))))
    edge_processed = False
    before.path_len = node.path_len
    for e in node.activity.edges:
        if e.target == node.id:
            e.target = before.id
    for p in prev_nodes:   
        prev_processed = len(node.next_nodes) > 0
        if node in p.next_nodes:
            p.next_nodes.remove(node)
            p.next_nodes.append(before)

    # add edge between bridge and node
    set_prev_next_node(before,node,edge_only=not edge_processed, activity=node.activity)
    node.path_len += 1

    
    
def generate_calculates(node,calculates, used_calculates,processed_nodes, process):
    list_calc = []
    count_node = None
    ## add select calcualte
    if issubclass(node.__class__, TriccNodeCalculateBase):
        if isinstance(node, TriccNodeRhombus):
            if (
                (node.expression_reference is None or isinstance(node.expression_reference, TriccOperation))
                and isinstance(node.reference, list)
                and len(node.reference)==1
                and issubclass(node.reference[0].__class__, TriccNodeSelect)
            ):

                count_node = get_count_node(node)
                list_calc.append(count_node)
                set_prev_next_node(node.reference[0],count_node)
                node.path_len+=1
                
                if isinstance(node.expression_reference, TriccOperation):
                    node.expression_reference.replace_node(node.reference, count_node)
                node.reference[0] =  count_node
            # elif isinstance(node.reference, TriccOperation):
            #     references = node.reference.get_references()
            #     if len(references) == 1 and issubclass(node.reference[0].__class__, TriccNodeSelect):
            #         count_node = get_count_node(node)
            #         list_calc.append(count_node)
            #         set_prev_next_node(references[0],count_node)
            #         node.path_len+=1
            #         node.reference.replace_node(references[0], count_node)
            if count_node:
                processed_nodes.add(count_node)
                add_calculate(calculates, count_node)
                add_used_calculate(
                    node, 
                    count_node, 
                    calculates=calculates, 
                    used_calculates=used_calculates,
                    processed_nodes=processed_nodes
                )
                
            
    # if a prev node is a calculate then it must be added in used_calc
    for prev in node.prev_nodes:
        add_used_calculate(
            node, 
            prev, 
            calculates=calculates, 
            used_calculates=used_calculates,
            processed_nodes=processed_nodes
        )
    #if the node have a save 
    if hasattr(node, 'save') and node.save is not None and node.save != '':
        # get fragments type.name.icdcode
        calculate_name=node.save   
        if node.name != calculate_name:
            calc_id = generate_id(f"autosave{node.id}")
            if issubclass(node.__class__, TriccNodeSelect) or isinstance(node, TriccNodeSelectNotAvailable):
                expression = get_count_terms_details( node,  processed_nodes, True, False, process)
            else:
                expression = get_node_expression(node,processed_nodes,True,True)
            calc_node = TriccNodeCalculate(
                name=calculate_name,
                id = calc_id,
                group = node.group,
                #version=get_next_version(calculate_name, processed_nodes, node.version+2),
                activity = node.activity,
                label =  "save: " +node.get_name(),
                path_len=node.path_len+ 1,
                last=True,
                expression=expression
            )
            node.activity.calculates.append(calc_node)
            last_version = set_last_version_false(calc_node, processed_nodes)
            if last_version:
                calc_node.expression = merge_expression(calc_node.expression, last_version)
            processed_nodes.add(calc_node)
            logger.debug("generate_save_calculate:{}:{} as {}".format(calc_node.tricc_type, node.name if hasattr(node,'name') else node.id, calculate_name))
            
            list_calc.append(calc_node)
            #add_save_calculate(calc_node, calculates, used_calculates,processed_nodes)
            for calc in list_calc:
                node.activity.nodes[calc.id] = calc
                add_calculate(calculates, calc)
    return list_calc



def add_calculate(calculates, calc_node):
    if issubclass(calc_node.__class__, TriccNodeDisplayCalculateBase):
        if calc_node.name not in calculates:
            calculates[calc_node.name]= {}
        calculates[calc_node.name][calc_node.id] = calc_node

def get_option_code_from_label(node, option_label):
    if hasattr(node, 'options'):
        for i in node.options:
            if node.options[i].label.strip() == option_label.strip():
                return node.options[i].name
        logger.critical(f"option with label {option_label} not found in {node.get_name()}")
    else:
        logger.critical(f"node {node.get_name()} has no options")


def process_reference(node, processed_nodes, calculates, used_calculates=None,  replace_reference=False,warn=False, codesystems=None):
    if getattr(node, 'expression_reference', None):
        modified_expression = process_operation_reference(
            node.expression_reference, 
            node, 
            processed_nodes=processed_nodes,
            calculates=calculates, 
            used_calculates=used_calculates, 
            replace_reference=replace_reference,
            warn=warn, 
            codesystems=codesystems
        )
        if modified_expression is False:
            return False
        elif modified_expression and replace_reference:
            node.reference = list(modified_expression.get_references())
            node.expression_reference = modified_expression
    elif getattr(node, 'reference', None):
        reference = node.reference
        if isinstance(reference, list):
            if isinstance(node, TriccNodeWait):
                reference = [TriccOperation(TriccOperator.ISTRUE,[n]) for n in reference]
            if len(node.reference) == 1 :
                operation = reference[0]
            else:
                operation = and_join(
                        reference
                    )
            modified_expression = process_operation_reference(
                operation, 
                node,
                processed_nodes=processed_nodes,
                calculates=calculates, 
                used_calculates=used_calculates, 
                replace_reference=replace_reference,
                warn=warn, 
                codesystems=codesystems
            )
            if modified_expression is False:
                return False
            elif modified_expression:
                node.reference = list(modified_expression.get_references())
                if not isinstance(node, TriccNodeWait):
                    node.expression_reference = modified_expression
        elif isinstance(node.reference, (TriccOperation, TriccReference)):
            modified_expression = process_operation_reference(
                node.reference, 
                node, 
                processed_nodes=processed_nodes,
                calculates=calculates, 
                used_calculates=used_calculates, 
                replace_reference=replace_reference,
                warn=warn, 
                codesystems=codesystems
            )
            if modified_expression is False:
                return False
            elif modified_expression and replace_reference:
                node.reference = list(modified_expression.get_references())
                node.expression_reference = modified_expression

    if isinstance(getattr(node, 'relevance', None), (TriccOperation, TriccReference)):
        modified_expression = process_operation_reference(
            node.relevance, 
            node, 
            processed_nodes=processed_nodes,
            calculates=calculates, 
            used_calculates=used_calculates, 
            replace_reference=replace_reference,
            warn=warn, 
            codesystems=codesystems
        )
        if modified_expression is False:
            return False
        elif modified_expression and replace_reference:
            node.relevance = modified_expression
    
    if isinstance(getattr(node, 'default', None), (TriccOperation, TriccReference)):
        modified_expression = process_operation_reference(
            node.default, 
            node, 
            processed_nodes=processed_nodes,
            calculates=calculates, 
            used_calculates=used_calculates, 
            replace_reference=replace_reference,
            warn=warn, 
            codesystems=codesystems
        )        
        if modified_expression is False:
            return False
        elif modified_expression and replace_reference:
            node.relevance = modified_expression
        
    if isinstance(getattr(node, 'expression', None), (TriccOperation, TriccReference)):
        modified_expression = process_operation_reference(
            node.expression, 
            node, 
            processed_nodes=processed_nodes,
            calculates=calculates, 
            used_calculates=used_calculates, 
            replace_reference=replace_reference,
            warn=warn, 
            codesystems=codesystems
        )
        if modified_expression is False:
            return False
        elif modified_expression and replace_reference:
            node.expression = modified_expression
            
    if isinstance(getattr(node, 'applicability', None), (TriccOperation, TriccReference)):
        modified_expression = process_operation_reference(
            node.applicability, 
            node, 
            processed_nodes=processed_nodes,
            calculates=calculates, 
            used_calculates=used_calculates, 
            replace_reference=replace_reference,
            warn=warn, 
            codesystems=codesystems
        )
        if modified_expression is False:
            return False
        elif modified_expression and replace_reference:
            node.applicability = modified_expression
    return True

def process_operation_reference(operation, node, processed_nodes, calculates, used_calculates=None,  replace_reference=False,warn=False, codesystems=None):
    modified_operation = None
    node_reference = []
    reference = []
    option_label = None
    ref_list = [r.value for r in operation.get_references() if isinstance(r, TriccReference)]
    real_ref_list = [r for r in operation.get_references() if issubclass(r.__class__, TriccNodeBaseModel)]
    for ref in ref_list:
        if ref.endswith(']'):
            terms = ref[:-1].split('[')
            option_label = terms[1]
            ref = terms[0]
        else:
            option_label = None
        node_in_act = [n for n in node.activity.nodes.values() if n.name == ref and n != node]    
        if node_in_act:
            if any(n not in processed_nodes for n in node_in_act):
                return False
            else:
                last_found = node_in_act[0]
        else:
            last_found = get_last_version(name=ref, processed_nodes=processed_nodes)
        if last_found is None:    
            if codesystems:
                concept =  lookup_codesystems_code(codesystems, ref)
                if not concept:
                    logger.critical(f"reference {ref} not found in the project for{str(node)} ")
                    exit(1)
                else:
                    if warn:
                        logger.debug(f"reference {ref}::{concept.display} not yet processed {node.get_name()}")
                
            elif warn:
                logger.debug(f"reference {ref} not found for a calculate {node.get_name()}")
            return False
        else:
            node_reference.append(last_found)
            reference.append(TriccReference(ref))
            if replace_reference:
                if not issubclass(last_found.__class__, (TriccNodeDisplayModel, TriccNodeDisplayCalculateBase, TriccNodeInput)):
                    last_found = get_node_expression(last_found, processed_nodes, is_prev=True)
                if isinstance(operation, (TriccOperation)):
                    if modified_operation is None:
                        modified_operation = operation.copy(keep_node=True)
                    modified_operation.replace_node(TriccReference(ref), last_found)
                elif operation == TriccReference(ref):
                    modified_operation = last_found
            if option_label:
                # Resolve human-readable label
                option_code = get_option_code_from_label(last_found, option_label)
                if option_code:
                    modified_operation = replace_code_reference(operation, old=f"{ref}[{option_label}]", new=option_code )
                else:
                    if warn:
                        logger.warning(f"Could not resolve label '{option_label}' for reference {ref}")
                    return False
            if hasattr(last_found, 'path_len'):
                path_len = last_found.path_len  
            elif isinstance(last_found, TriccOperation):
                path_len =  max(getattr(n, 'path_len', 0) for n in last_found.get_references())
            else:
                path_len = 0
            node.path_len = max(node.path_len, path_len)
    for ref in real_ref_list:
        if is_prev_processed(ref, node, processed_nodes=processed_nodes, local=False) is False:
            return False
    
    if used_calculates is not None:
        for ref_nodes in node_reference:
            if issubclass(ref_nodes.__class__, TriccNodeCalculateBase):
                add_used_calculate(node, ref_nodes, calculates, used_calculates, processed_nodes=processed_nodes)
    return modified_operation

def replace_code_reference(expression, old, new):
    if isinstance(expression, str):
        return expression_reference.replace(old, f"'{new}'")
    if isinstance(expression, TriccOperation):
        expression.replace_node(TriccReference(old), TriccStatic(new))
        return expression
#add_used_calculate(node, calc_node, calculates, used_calculates, processed_nodes)

def add_used_calculate(node, prev_node, calculates, used_calculates, processed_nodes):
    if issubclass(prev_node.__class__, TriccNodeDisplayCalculateBase):
        if prev_node in processed_nodes:
            # if not a verison, index will equal -1
            if prev_node.name not in calculates :
                logger.debug("node {} refered before being processed".format(node.get_name()))
                return False
            max_version = prev_node#get_max_version(calculates[node_clean_name])
            if prev_node.name not in used_calculates:
                used_calculates[prev_node.name] = {}
            #save the max version only once
            if max_version.id not in used_calculates[prev_node.name]:
                used_calculates[prev_node.name][max_version.id] = max_version
        else:
            logger.debug("process_calculate_version_requirement: failed for {0} , prev Node {1} ".format(node.get_name(), prev_node.get_name()))

        
def get_select_not_available_options(node,group,label):
    return {0:TriccNodeSelectOption(
                id = generate_id(f"notavaialble{node.id}"),
                name="1",
                label=label,
                select = node,
                group = group,
                list_name = node.list_name
            )}
        
def get_select_yes_no_options(node, group):
    yes = TriccNodeSelectOption(
                id = generate_id(f'yes{node.id}'),
                name=f"{TRICC_TRUE_VALUE}",
                label="Yes",
                select = node,
                group = group,
                list_name = node.list_name
            )
    no = TriccNodeSelectOption(
                id = generate_id(f'no{node.id}'),
                name=f"{TRICC_FALSE_VALUE}",
                label="No",
                select = node,
                group = group,
                list_name =  node.list_name
            )
    return {0:yes, 1:no }

# walkthough all node in an iterative way, the same node might be parsed 2 times 
# therefore to avoid double processing the nodes variable saves the node already processed
# there 2 strategies : process it the first time or the last time (wait that all the previuous node are processed)

def walktrhough_tricc_node_processed_stached(node, callback, processed_nodes, stashed_nodes, path_len, recursive=False, warn = False,
                                             node_path = [], process=None, **kwargs):
    ended_activity = False
    # logger.debug("walkthrough::{}::{}".format(callback.__name__, node.get_name()))
    
    path_len = max(node.activity.path_len, *[0,*[getattr(n,'path_len',0) + 1 for n in node.activity.prev_nodes]]) + 1
    if hasattr(node, 'prev_nodes'):
        path_len = max(path_len, *[0,*[getattr(n,'path_len',0)+ 1 for n in node.prev_nodes]])
    if hasattr(node, 'get_references'):
        references = node.get_references()
        if references:
            path_len = max(path_len, *[0,*[getattr(n,'path_len',0) + 1 for n in references]])
    node.path_len = max(node.path_len, path_len)
    prev_process = process[0] if process else None
    if isinstance(node, TriccNodeActivity) and getattr(node.root, 'process', None):
        if process is None:
            process = [node.root.process]
        else:
            process[0] = node.root.process
    if (
        callback(
            node, 
            processed_nodes=processed_nodes,
            stashed_nodes=stashed_nodes,
            warn = warn,
            node_path=node_path,
            process=process,
            **kwargs
        )
    ):
        node_path.append(node)
        # node processing succeed 
        if not isinstance(node, TriccNodeActivity) and node not in processed_nodes:
            processed_nodes.add(node)
            if warn:
                logger.debug("{}::{}: processed ({})".format(callback.__name__, node.get_name(), len(processed_nodes)))
        if isinstance(node, (TriccNodeEnd, TriccNodeActivityEnd)) and node.activity not in processed_nodes:
            end_nodes = node.activity.get_end_nodes()
            if all([e in processed_nodes for e in end_nodes]):
                processed_nodes.add(node.activity)
                ended_activity = True
                if warn:
                    logger.debug("{}::{}: processed ({})".format(callback.__name__, node.activity.get_name(), len(processed_nodes)))
        elif node in stashed_nodes:
            stashed_nodes.remove(node)
            # logger.debug("{}::{}: unstashed ({})".format(callback.__name__, node.get_name(), len(stashed_nodes)))
        # put the stached node from that group first
        # if has next, walkthrough them (support options)
        # if len(stashed_nodes)>1:
        if isinstance(node, (TriccNodeActivityStart, TriccNodeMainStart)):
            if recursive:
                for gp in node.activity.groups.values():
                    walktrhough_tricc_node_processed_stached(
                        gp, 
                        callback,
                        processed_nodes=processed_nodes, 
                        stashed_nodes=stashed_nodes, 
                        path_len=path_len,
                        recursive=recursive,
                        warn = warn,
                        node_path = node_path.copy(),
                        **kwargs
                    )
                for c in node.activity.calculates:
                    if len(c.prev_nodes)== 0:
                        walktrhough_tricc_node_processed_stached(
                            c,
                            callback,
                            processed_nodes=processed_nodes, 
                            stashed_nodes=stashed_nodes, 
                            path_len=path_len,
                            recursive=recursive,
                            warn = warn,
                            node_path = node_path.copy(),
                            **kwargs
                        )            
            else:
                stashed_nodes += [c for c in node.activity.calculates if len(c.prev_nodes)== 0] 
                stashed_nodes += node.activity.groups.values()
        elif issubclass(node.__class__, TriccNodeSelect):
            for option in node.options.values():
                option.path_len = max(path_len,  option.path_len)
                callback(option, processed_nodes=processed_nodes, stashed_nodes=stashed_nodes, warn = warn, node_path=node_path,**kwargs)    
                if option not in processed_nodes:
                    processed_nodes.add(option)
                    if warn:
                        logger.debug(
                            "{}::{}: processed ({})".format(callback.__name__, option.get_name(), len(processed_nodes)))
                walkthrough_tricc_option(node, callback, processed_nodes, stashed_nodes, path_len + 1, recursive,
                                         warn = warn,node_path = node_path, **kwargs)
        if isinstance(node, TriccNodeActivity):
            if node.root not in processed_nodes:
                if node.root is not None:
                    node.root.path_len = max(path_len,  node.root.path_len)
                    if recursive:
                        walktrhough_tricc_node_processed_stached(node.root, callback, processed_nodes, stashed_nodes, path_len,
                                                            recursive, warn = warn,node_path = node_path.copy(),**kwargs)
                    #     for gp in node.groups:
                    #         walktrhough_tricc_node_processed_stached(gp, callback, processed_nodes, stashed_nodes, path_len,
                    #                                          recursive, warn = warn,**kwargs)
                    #     if node.calculates:
                    #         for c in node.calculates:
                    #             walktrhough_tricc_node_processed_stached(c, callback, processed_nodes, stashed_nodes, path_len,
                    #                                          recursive, warn = warn,**kwargs)
                    elif node.root not in stashed_nodes:
                        #stashed_nodes.insert(0,node.root)
                        stashed_nodes.insert_at_top(node.root)
                        # if node.calculates:
                        #     stashed_nodes += node.calculates
                        # for gp in node.groups:
                        #     stashed_nodes.add(gp)
                        # #    stashed_nodes.insert(0,gp)
                    return
            elif ended_activity:
                for next_node in node.next_nodes:
                    if next_node not in stashed_nodes:
                        #stashed_nodes.insert(0,next_node)
                        if recursive:
                            walktrhough_tricc_node_processed_stached(next_node, callback, processed_nodes, stashed_nodes, path_len,
                                                            recursive, warn = warn,node_path = node_path.copy(),**kwargs)
                        else:
                            stashed_nodes.insert_at_top(next_node)
 
        
        elif hasattr(node, 'next_nodes') and len(node.next_nodes) > 0 and not isinstance(node, TriccNodeActivity):
            if recursive:
                walkthrough_tricc_next_nodes(node, callback, processed_nodes, stashed_nodes, path_len + 1, recursive,
                                             warn = warn,node_path = node_path,**kwargs)
            else:
                for nn in node.next_nodes:
                    if nn not in stashed_nodes:
                        stashed_nodes.insert_at_top(nn)
        if not recursive:
            reorder_node_list(stashed_nodes, node.group, processed_nodes)
 
        
                
    else:
        if prev_process and process and prev_process != process[0]:
            process[0] = prev_process
        if node not in processed_nodes and node not in stashed_nodes:
            if node not in stashed_nodes:
                stashed_nodes.insert_at_bottom(node)
                if warn:
                    logger.debug("{}::{}: stashed({})".format(callback.__name__, node.get_name(), len(stashed_nodes)))


def walkthrough_tricc_next_nodes(node, callback, processed_nodes, stashed_nodes, path_len, recursive, warn = False, node_path = [], **kwargs):
    
    if not recursive:
        for next_node in node.next_nodes:
            if next_node not in stashed_nodes:
                stashed_nodes.insert_at_top(next_node)
    else:
        list_next = set(node.next_nodes)
        for next_node in list_next:
            if not isinstance(node, (TriccNodeActivityEnd, TriccNodeEnd)):
                if next_node not in processed_nodes:
                    walktrhough_tricc_node_processed_stached(next_node, callback, processed_nodes, stashed_nodes,
                                                        path_len + 1,recursive, warn = warn,node_path = node_path.copy(), **kwargs)
            else:
                logger.critical(
                    "{}::end node of {} has a next node".format(callback.__name__, node.activity.get_name()))
                exit(1)


def walkthrough_tricc_option(node, callback, processed_nodes, stashed_nodes, path_len, recursive, warn = False,node_path = [], **kwargs):
    if not recursive:
        for option in node.options.values():
            if hasattr(option, 'next_nodes') and len(option.next_nodes) > 0:
                for next_node in option.next_nodes:
                    if next_node not in stashed_nodes:
                        stashed_nodes.insert_at_top(next_node)
                        #stashed_nodes.insert(0,next_node)
    else:
        list_option = []
        while not all(elem in list_option for elem in list(node.options.values())):
            for option in node.options.values():
                if option not in list_option:
                    list_option.append(option)
                    # then walk the options   
                    if hasattr(option, 'next_nodes') and len(option.next_nodes) > 0:
                        list_next = set(option.next_nodes)
                        for next_node in list_next:
                            if next_node not in processed_nodes:
                                walktrhough_tricc_node_processed_stached(next_node, callback, processed_nodes,
                                                                        stashed_nodes, path_len + 1, recursive,
                                                                        warn = warn,
                                                                        node_path = node_path.copy(), **kwargs)

def get_next_version(name, processed_nodes, version=0, min=100):
    return max(version, min,*[(getattr(n,'version',None) or getattr(n,'instance',None) or 0) for n in get_versions(name, processed_nodes)])+1


def get_data_for_log(node):
    return "{}:{}|{} {}:{}".format(
        node.group.get_name() if node.group is not None else node.activity.get_name(),
        node.group.instance if node.group is not None else node.activity.instance ,
        node.__class__,
        node.get_name(),
        node.instance)

def stashed_node_func(node, callback, recursive=False, **kwargs):
    processed_nodes = kwargs.pop('processed_nodes', OrderedSet())
    stashed_nodes = kwargs.pop('stashed_nodes', OrderedSet())
    process = kwargs.pop('process', ['main'])
    path_len = 0
    
    walktrhough_tricc_node_processed_stached(
        node,
        callback,
        processed_nodes,
        stashed_nodes,
        path_len,
        recursive,
        process=process,
        **kwargs)
    # callback( node, **kwargs)
    ## MANAGE STASHED NODES
    prev_stashed_nodes = stashed_nodes.copy()
    loop_count = 0
    len_prev_processed_nodes = 0
    while len(stashed_nodes) > 0:
        loop_count = check_stashed_loop(stashed_nodes, prev_stashed_nodes, processed_nodes, len_prev_processed_nodes,
                                        loop_count)
        prev_stashed_nodes = stashed_nodes.copy()
        len_prev_processed_nodes = len(processed_nodes)
        if len(stashed_nodes) > 0:
            s_node = stashed_nodes.pop()
            # remove duplicates
            if s_node in stashed_nodes:
                stashed_nodes.remove(s_node)
            if kwargs.get('warn', True):         
                logger.debug("{}:: {}: unstashed for processing ({})".format(callback.__name__, s_node.__class__, 
                                                                        get_data_for_log(s_node),
                                                                        len(stashed_nodes)))
            warn = loop_count >=  (9 * len(stashed_nodes   )+1)
            walktrhough_tricc_node_processed_stached(
                s_node,
                callback,
                processed_nodes,
                stashed_nodes,
                path_len,
                recursive,
                warn=warn,
                process=process,
                **kwargs)


# check if the all the prev nodes are processed
def is_ready_to_process(in_node, processed_nodes, strict=True, local=False):
    if isinstance(in_node, TriccNodeSelectOption):
        node = in_node.select
    elif (
        isinstance(in_node, (TriccNodeActivityStart, TriccNodeMainStart))    ):
        # check before
        return True
    else:
        node = in_node
    if hasattr(node, 'prev_nodes'):
        # ensure the  previous node of the select are processed, not the option prev nodes
        for prev_node in node.prev_nodes:
            if is_prev_processed(prev_node, node, processed_nodes, local) is False:
                return False
    return True
    
def is_prev_processed(prev_node, node, processed_nodes, local):
    if hasattr(prev_node, 'select'):
        return  is_prev_processed(prev_node.select, node, processed_nodes, local)
    if prev_node not in processed_nodes and (not local):
        if isinstance(prev_node, TriccNodeExclusive):
            iterator = iter(prev_node.prev_nodes)
            p_n_node = next(iterator)
            logger.debug("is_ready_to_process:failed:via_excl: {} - {} > {} {}:{}".format(
                get_data_for_log(p_n_node),
                prev_node.get_name(),
                node.__class__, node.get_name(), node.instance))

        else:
            logger.debug("is_ready_to_process:failed: {} -> {} {}:{}".format(
                get_data_for_log(prev_node),
                node.__class__, node.get_name(), node.instance))

        logger.debug("prev node node {}:{} for node {} not in processed".format(prev_node.__class__,
                                                                                prev_node.get_name(),
                                                                                node.get_name()))
        return False
    return True



def print_trace(node, prev_node, processed_nodes, stashed_nodes, history = []):
    
    if node != prev_node:
        if node in processed_nodes:
            logger.warning("print trace :: node {}  was the last not processed ({})".format(
                    get_data_for_log(prev_node), node.id, ">".join(history)))
            #processed_nodes.add(prev_node)
            return False
        elif node in history:
            logger.critical("print trace :: CYCLE node {} found in history ({})".format(
                get_data_for_log(prev_node), ">".join(history)))
            exit(1)
        elif node in stashed_nodes:
            #            logger.debug("print trace :: node {}::{} in stashed".format(node.__class__,node.get_name()))
            return False
            # else:
        # logger.debug("print trace :: node {} not processed/stashed".format(node.get_name()))     
    return True


def reverse_walkthrough(in_node, next_node, callback, processed_nodes, stashed_nodes, history = []):
    # transform dead-end nodes
    if next_node == in_node and next_node not in stashed_nodes:
        # workaround fir loop
        return False
    

    if isinstance(in_node, TriccNodeSelectOption):
        node = in_node.select
    elif isinstance(in_node, TriccNodeActivityStart):
        node = in_node.activity
    else:
        node = in_node
    if callback(node, next_node, processed_nodes=processed_nodes, stashed_nodes=stashed_nodes):
        history.append(node)
        if isinstance(in_node, TriccNodeActivity):
            prev_nodes = set(in_node.get_end_nodes())
            for prev in prev_nodes:
                reverse_walkthrough(prev, next_node, callback, processed_nodes=processed_nodes, stashed_nodes=stashed_nodes, history=history)
        if hasattr(node, 'prev_nodes'):
            if node.prev_nodes:
                for prev in node.prev_nodes:
                    reverse_walkthrough(prev, node, callback, processed_nodes=processed_nodes, stashed_nodes=stashed_nodes, history=history)
            elif node in node.activity.calculates:
                reverse_walkthrough(prev, node.activity.root, callback, processed_nodes=processed_nodes, stashed_nodes=stashed_nodes, history=history)

        if issubclass(node.__class__, TriccRhombusMixIn):
            if isinstance(node.reference, list):
                for ref in node.reference:
                    reverse_walkthrough(ref, node, callback, processed_nodes=processed_nodes, stashed_nodes=stashed_nodes, history= history)




def get_prev_node_by_name(processed_nodes, name, node):
    # look for the node in the same activity   
    last_calc = get_last_version(
                    name,
                    processed_nodes
                )
    if last_calc:
        return last_calc
                
    filtered = list(
        filter(lambda p_node: 
            hasattr(p_node,'name') 
            and p_node.name == name 
            and p_node.instance == node.instance 
            and p_node.path_len <= node.path_len, processed_nodes
        ))
    if len(filtered) == 0:
        filtered = list(filter(lambda p_node: hasattr(p_node, 'name') and p_node.name == name , processed_nodes))
    if len(filtered) > 0:
        return sorted(filtered, key=lambda x: x.path_len, reverse=False)[0]

MIN_LOOP_COUNT = 10

def check_stashed_loop(stashed_nodes, prev_stashed_nodes, processed_nodes, len_prev_processed_nodes, loop_count):
    loop_out = {}
    
    if len(stashed_nodes) == len(prev_stashed_nodes):
        # to avoid checking the details 
        if loop_count<=0:
            if loop_count < -MIN_LOOP_COUNT:
                loop_count = MIN_LOOP_COUNT+1
            else:
                loop_count -= 1
        if loop_count > MIN_LOOP_COUNT:
            if set(stashed_nodes) == set(prev_stashed_nodes) and len(processed_nodes) == len_prev_processed_nodes:
                loop_count += 1
                if loop_count > max(MIN_LOOP_COUNT, 11 * len(prev_stashed_nodes) + 1):
                    logger.critical("Stashed node list was unchanged: loop likely or unresolved dependence")
                    waited, looped =  get_all_dependant(stashed_nodes, stashed_nodes, processed_nodes)               
                    logger.debug(f"{len(looped)} nodes waiting stashed nodes")
                    logger.info("unresolved reference")
                    for es_node in [n for n in stashed_nodes if isinstance(n, TriccReference)]:
                        logger.info("Stashed node {}:{}|{} {}".format(
                            es_node.activity.get_name() if hasattr(es_node,'activity') else '' ,
                            es_node.activity.instance if hasattr(es_node,'activity') else '',
                            es_node.__class__, 
                            es_node.get_name()))
                    for es_node in [node for node_list in looped.values() for node in node_list if isinstance(node, TriccReference)]:
                        logger.info("looped node {}:{}|{} {}".format(
                            es_node.activity.get_name() if hasattr(es_node,'activity') else '' ,
                            es_node.activity.instance if hasattr(es_node,'activity') else '',
                            es_node.__class__, 
                            es_node.get_name()))
                    for es_node in [node for node_list in waited.values() for node in node_list if isinstance(node, TriccReference)]:
                        logger.info("waited node {}:{}|{} {}".format(
                            es_node.activity.get_name() if hasattr(es_node,'activity') else '' ,
                            es_node.activity.instance if hasattr(es_node,'activity') else '',
                            es_node.__class__, 
                            es_node.get_name()))
                    logger.info("looped nodes")
                    for dep_list in looped:
                        for d in looped[dep_list]:
                            if str(d) in looped:
                                logger.critical("[{}] depends on [{}]".format(
                                    dep_list, str(d)
                                    ))
                            else:
                                logger.error("[{}] depends on [{}]".format(
                                    dep_list, str(d)
                                    ))
                        if dep_list in waited:
                            for d in waited[dep_list]:
                                logger.warning("[{}] depends on [{}]".format(
                                    dep_list, str(d)
                                    ))
                    logger.info("waited nodes")
                    for dep_list in waited:
                        if dep_list not in looped:
                            for d in waited[dep_list]:
                                logger.warning("[{}] depends on [{}]".format(
                                    dep_list, d.get_name()
                                    ))
                            
                    if len(stashed_nodes) == len(prev_stashed_nodes):
                        exit(1)
            else:
                loop_count = 0
    else:
        loop_count = 0
    return loop_count

def add_to_tree(tree, n, d):
    n_str = str(n)
    if n_str not in tree:
        tree[n_str] = []
    if d not in tree[n_str]:
        tree[n_str].append(d)
    return tree

        
def get_all_dependant(loop, stashed_nodes, processed_nodes, depth=0, waited=None , looped=None, path = None):
    if path is None:
        path =[] 
    if looped is None:
        looped = {}
    if waited is None:
        waited = {}
    all_dependant = OrderedSet()
    for n in loop:
        cur_path = path.copy()
        cur_path.append(n)
        dependant = OrderedSet()
        i=0
        #logger.critical(f"{i}: {n.__class__}::{n.get_name()}::{getattr(n,'instance','')}::{process_reference(n, processed_nodes, [])}")
        i += 1
        if hasattr(n, 'prev_nodes') and n.prev_nodes:
            dependant =  dependant | n.prev_nodes
        if hasattr(n, 'get_references'):
            dependant =  dependant | (n.get_references() or OrderedSet())
        if not isinstance(dependant, list):
            pass
        for d in dependant:
            if d in path:
                logger.warning(f"loop {str(d)} already in path {'::'.join(map(str, path))}  ")
            if isinstance(d, TriccNodeSelectOption):
                d = d.select
            
            if isinstance(d, TriccReference):
                if not any(n.name == d.value for n in processed_nodes):
                    if not any(n.name == d.value for n in stashed_nodes):
                        waited = add_to_tree(waited, n, d)
                    else :
                        looped = add_to_tree(looped, n, d)
            
            elif d not in processed_nodes:
                if d in stashed_nodes:
                    looped = add_to_tree(looped, n, d)
                else :
                    waited = add_to_tree(waited, n, d)
            all_dependant = all_dependant.union(dependant)
    if depth < MAX_DRILL:
        waited, looped =  get_all_dependant(all_dependant, stashed_nodes, processed_nodes, depth+1, waited , looped, path=cur_path)
        
    return waited, looped


MAX_DRILL = 3

def get_last_end_node(processed_nodes, process=None):
    end_name = 'tricc_end_'
    if process:
        end_name += process
    return get_last_version(end_name, processed_nodes)

# Set the source next node to target and clean  next nodes of replace node
def set_prev_next_node(source_node, target_node, replaced_node=None, edge_only = False, activity=None):
    activity = activity or source_node.activity
    source_id, source_node = get_node_from_id(activity, source_node, edge_only)
    target_id, target_node = get_node_from_id(activity, target_node, edge_only)
    # if it is end node, attached it to the activity/page
    if not edge_only:
        set_prev_node(source_node, target_node, replaced_node, edge_only)
        set_next_node(source_node, target_node, replaced_node, edge_only)
         
    if activity and not any([(e.source == source_id) and ( e.target == target_id) for e in activity.edges]):
        label = "continue" if issubclass(source_node.__class__, TriccNodeSelect) else None
        activity.edges.append(TriccEdge(id = generate_id(), source = source_id, target = target_id, value = label))

def remove_prev_next(prev_node, next_node, activity=None):
    activity = activity or prev_node.activity
    if hasattr(prev_node, 'next_nodes') and next_node in prev_node.next_nodes:
        prev_node.next_nodes.remove(next_node)
    if hasattr(next_node, 'prev_nodes') and prev_node in next_node.prev_nodes:
        next_node.prev_nodes.remove(prev_node)
    
    for e in list(activity.edges):
        if (e.target == getattr(next_node, 'id', next_node) and e.source == getattr(prev_node, 'id', prev_node)):
            activity.edges.remove(e)
    
    
    
def set_next_node(source_node, target_node, replaced_node=None, edge_only = False, activity=None):
    activity = activity or source_node.activity
    replace_target = None
    if not edge_only:  
        if replaced_node is not None and hasattr(source_node, 'path') and replaced_node == source_node.path:
            source_node.path = target_node
        elif replaced_node is not None and hasattr(source_node, 'next_nodes') and replaced_node in source_node.next_nodes:
            replace_target = True
            source_node.next_nodes.remove(replaced_node)
            if hasattr(replaced_node, 'prev_nodes') and source_node in replaced_node.prev_nodes:
                replaced_node.prev_nodes.remove(source_node)
        #if replaced_node is not None and hasattr(target_node, 'next_nodes') and replaced_node in target_node.next_nodes:
        #    target_node.next_nodes.remove(replaced_node)
        if target_node not in source_node.next_nodes:
            source_node.next_nodes.add(target_node)
        # if rhombus in next_node of prev node and next node as ref
        if replaced_node is not None:
            rhombus_list = list(filter(lambda x: issubclass(x.__class__, TriccRhombusMixIn), source_node.next_nodes))
            for rhm in rhombus_list:
                if isinstance(rhm.reference, list):
                    if replaced_node in rhm.reference:
                        rhm.reference.remove(replaced_node)
                        rhm.reference.append(target_node)
    if target_node.id not in activity.nodes:
        activity.nodes[target_node.id] = target_node
    if replaced_node and replaced_node in replaced_node.activity.calculates:
        replaced_node.activity.calculates.remove(replaced_node)
    if replaced_node and replace_target:
        if replaced_node.id in replaced_node.activity.nodes:
            del replaced_node.activity.nodes[replaced_node.id]
        next_edges = set([ 
                    e for e in replaced_node.activity.edges if (e.target == replaced_node.id or e.target == replaced_node)
        ] + [ 
                    e for e in activity.edges if (e.target == replaced_node.id or e.target == replaced_node)
        ])
        if len(next_edges)==0:
            for e  in next_edges:
                e.target = target_node.id

            

# Set the target_node prev node to source and clean prev nodes of replace_node
def set_prev_node(source_node, target_node, replaced_node=None, edge_only = False, activity=None):
    activity = activity or source_node.activity
    replace_source = False
    # update the prev node of the target not if not an end node
    # update directly the prev node of the target
    if replaced_node is not None and hasattr(target_node, 'path') and replaced_node == target_node.path:
        target_node.path = source_node
    if replaced_node is not None and hasattr(target_node, 'prev_nodes') and replaced_node in target_node.prev_nodes:
        replace_source = True
        target_node.prev_nodes.remove(replaced_node)
        if hasattr(replaced_node, 'next_nodes') and source_node in replaced_node.next_nodes:
            replaced_node.next_nodes.remove(source_node)
    #if replaced_node is not None and hasattr(source_node, 'prev_nodes') and replaced_node in source_node.prev_nodes:
    #    source_node.prev_nodes.remove(replaced_node)
    if source_node not in target_node.prev_nodes:
        target_node.prev_nodes.add(source_node)
    if source_node.id not in activity.nodes:
        activity.nodes[source_node.id] = source_node
    if replaced_node and replace_source:
        if replaced_node.id in replaced_node.activity.nodes:
                del replaced_node.activity.nodes[replaced_node.id]
        next_edges = set([ 
                    e for e in replaced_node.activity.edges if (e.source == replaced_node.id or e.source == replaced_node)
        ] + [ 
                    e for e in activity.edges if (e.source == replaced_node.id or e.source == replaced_node)
        ])
        if len(next_edges)==0:
            for e  in next_edges:
                e.target = target_node.id
 

def replace_node(old, new, page = None):
    if page is None:
        page = old.activity
    logger.debug("replacing node {} with node {} from page {}".format(old.get_name(), new.get_name(), page.get_name()))
    # list_node used to avoid updating a list in the loop
    list_nodes = []
    for prev_node in old.prev_nodes:
        list_nodes.append(prev_node)
    for prev_node in list_nodes:
        set_prev_next_node(prev_node, new, old)
    old.prev_nodes = set()
    list_nodes = []
    for next_node in old.next_nodes:
        list_nodes.append(next_node)
    for next_node in list_nodes:
        set_prev_next_node(new, next_node, old)
    old.next_nodes = set()
    if old in page.nodes:
        del page.nodes[old.id]
    page.nodes[new.id] = new

    for edge in page.edges:
        if edge.source == old.id:
            edge.source = new.id
        if edge.target == old.id:
            edge.target = new.id

def replace_prev_next_node(prev_node, next_node, old_node, force = False):
    replace_prev_node(prev_node, next_node, old_node)
    replace_next_node(prev_node, next_node, old_node)

def replace_prev_node(prev_node, next_node, old_node, force = False):
    #create a copy pf the list
    list_nodes = list(next_node.prev_nodes)
    # replace in case old node is found
    for p_n_node in list_nodes:
        if p_n_node == old_node or force:
            set_prev_next_node(prev_node, next_node, old_node)
     
    
def replace_next_node(prev_node,next_node,old_node):
    list_nodes = list(prev_node.next_nodes)
    for n_p_node in list_nodes:
        if n_p_node == old_node :
            set_prev_next_node(prev_node, next_node, old_node)


# Priority constants
SAME_GROUP_PRIORITY = 7000
PARENT_GROUP_PRIORITY = 6000
ACTIVE_ACTIVITY_PRIORITY = 5000
NON_START_ACTIVITY_PRIORITY = 4000
ACTIVE_ACTIVITY_LOWER_PRIORITY = 3000
RHOMBUS_PRIORITY = 1000
DEFAULT_PRIORITY = 2000

def reorder_node_list(node_list, group, processed_nodes):
    # Cache active activities for O(1) lookup
    active_activities = {n.activity for n in processed_nodes}

    def get_priority(node):
        # Cache attributes to avoid repeated getattr calls
        priority = int(getattr(node, "priority", 0) or 0)
        node_group = getattr(node, "group", None)
        activity = getattr(node, "activity", None)

        # Check for same group
        if group is not None and node_group and node_group.id == group.id:
            priority += SAME_GROUP_PRIORITY
        # Check for parent group
        elif hasattr(group, "group") and group.group and node_group and node_group.id == group.group.id:
            priority += PARENT_GROUP_PRIORITY
        # Check for active activities (not main)
        elif activity and isinstance(activity.root, TriccNodeActivityStart) and activity in active_activities:
            priority += ACTIVE_ACTIVITY_PRIORITY
        # Check for non main activities
        elif activity and isinstance(activity.root, TriccNodeActivityStart):
            priority += NON_START_ACTIVITY_PRIORITY
        # Check for active activities (lower priority)
        elif activity and activity in active_activities:
            priority += ACTIVE_ACTIVITY_LOWER_PRIORITY
        # Check for rhombus nodes
        elif issubclass(node.__class__, TriccRhombusMixIn):
            priority += RHOMBUS_PRIORITY
        else:
            priority += DEFAULT_PRIORITY

        return priority

    # Sort in place, highest priority first
    node_list.sort(key=get_priority, reverse=True)
    
def loop_info(loop, **kwargs):
    logger.critical("dependency details")
    for n in loop:
        i=0
        logger.critical(f"{i}: {n.__class__}::{n.get_name()}")
        i += 1


def has_loop(node, processed_nodes, stashed_nodes, warn , node_path=[], action_on_loop=loop_info,action_on_other=None, **kwargs):
    next_nodes = get_extended_next_nodes(node)
    for next_node in next_nodes:      
        if next_node in node_path:
            loop_start_key = node_path.index(next_node)
            loop = node_path[loop_start_key:]
            loop.append(node)
            loop.append(next_node)
            action_on_loop(loop, **kwargs)
            return False        
    if callable(action_on_other):
        action_on_other(next_node, **kwargs)
    return True
    
        

def get_extended_next_nodes(node):
   
    nodes =  node.next_nodes  if hasattr(node,'next_nodes') else set()
    if issubclass(node.__class__, TriccNodeSelect ):
        for o in node.options.values():
            nodes = nodes | o.next_nodes
    if isinstance(node, ( TriccNodeActivity) ):
        nodes = nodes | node.root.next_nodes
    return nodes
    

# calculate or retrieve a node expression
def get_node_expression( in_node, processed_nodes, get_overall_exp=False, is_prev=False, negate=False, process=None):
    # in case of calculate we only use the select multiple if none is not selected
    expression = None
    negate_expression = None
    node = in_node
    if isinstance(node, (TriccNodeActivityStart,TriccNodeMainStart)):
        if is_prev and get_overall_exp:
            expression = get_node_expression(
                node.activity,
                processed_nodes=processed_nodes,
                get_overall_exp=True,
                is_prev=is_prev,
                negate=negate,
                process=process
            )
            if isinstance(node, TriccNodeMainStart):
                expression =  get_applicability_expression(node.activity, processed_nodes, process, expression )
        elif isinstance(node, (TriccNodeActivityStart)):
            return TriccStatic(True)
        
    elif isinstance(node, TriccNodeWait):
        if is_prev:
            # the wait don't do any calculation with the reference it is only use to wait until the reference are valid
            return get_node_expression(
                node.path,
                processed_nodes=processed_nodes,
                get_overall_exp=get_overall_exp,
                is_prev=True,
                process=process
                )
        else:
            #it is a empty calculate
            return None
    elif isinstance(node, TriccNodeRhombus):
        # if is_prev:
        #     expression = TriccOperation(
        #         TriccOperator.ISTRUE,
        #         [node]
        #     )
        # else:
        expression = get_rhombus_terms(node, processed_nodes, process=process)  # if issubclass(node.__class__, TricNodeDisplayCalulate) else TRICC_CALC_EXPRESSION.format(get_export_name(node)) #
        negate_expression = not_clean(expression)
        if node.path is None :
            if len(node.prev_nodes) == 1:
                node.path = list(node.prev_nodes)[0]
            elif len(node.prev_nodes) > 1:
                logger.critical(f"missing path for Rhombus {node.get_name()}")
                exit(1)
        prev_exp = get_node_expression(
            node.path,
            processed_nodes=processed_nodes,
            get_overall_exp=get_overall_exp,
            is_prev=True,
            process=process)
        if prev_exp and expression:
            expression = and_join([prev_exp, expression])
            negate_expression = and_join([
                    prev_exp, 
                    negate_expression
                ])

        elif prev_exp:
            
            logger.error(f"useless rhombus {node.get_name()}")
            expression = prev_exp
            negate_expression = prev_exp
            logger.critical(f"Rhombus without expression {node.get_name()}")
    elif is_prev and issubclass(node.__class__, TriccNodeDisplayCalculateBase):
        expression = TriccOperation(TriccOperator.ISTRUE, [node])
    elif hasattr(node, 'expression_reference') and isinstance(node.expression_reference, TriccOperation):
        # if issubclass(node.__class__, TriccNodeDisplayCalculateBase):
        #     expression = TriccOperation(
        #         TriccOperator.CAST_NUMBER,
        #         [node.expression_reference])
        # else:    
        expression = node.expression_reference  
    elif is_prev and isinstance(node, TriccNodeSelectOption):
        if negate:
            negate_expression = get_selected_option_expression(node, negate)
        else:
            expression = get_selected_option_expression(node, negate)
        #TODO remove that and manage it on the "Save" part
    elif is_prev and isinstance(node, TriccNodeSelectNotAvailable):
        expression =  TriccOperation(
            TriccOperator.SELECTED,
            [
                node,
                TriccStatic(1)
            ]
        )
    elif issubclass(node.__class__, TriccNodeCalculateBase):
        if negate:
            negate_expression = get_calculation_terms(node, processed_nodes=processed_nodes, get_overall_exp=get_overall_exp, negate=True, process=process)
        else:
            expression = get_calculation_terms(node, processed_nodes=processed_nodes, get_overall_exp=get_overall_exp, process=process)
    
    elif (not is_prev or not ONE_QUESTION_AT_A_TIME) and hasattr(node, 'relevance') and isinstance(node.relevance, (TriccOperation, TriccStatic)):
        expression = node.relevance  
    elif ONE_QUESTION_AT_A_TIME and is_prev and not get_overall_exp and hasattr(node, 'required') and node.required:
        expression = get_required_node_expression(node)
 
    if expression is None:
        expression = get_prev_node_expression(node, processed_nodes=processed_nodes, get_overall_exp=get_overall_exp, process=process)
            # in_node not in processed_nodes is need for calculates that can but run after the end of the activity
    #if isinstance(node, TriccNodeActivitiy) and not prev:
        # expression = get_applicability_expression(node, processed_nodes, process, expression)
        # expression = get_prev_instance_skip_expression(node, processed_nodes, process, expression)
        # expression = get_process_skip_expression(node, processed_nodes, process, expression)
    if negate:
        if negate_expression is not None:
            return negate_expression
        elif expression is not None:
            return negate_term(expression)
        else:
            logger.critical("exclusive can not negate None from {}".format(node.get_name()))
            # exit(1)
    else:
        return expression
    
def get_applicability_expression(node, processed_nodes, process, expression=None):
    if isinstance(node.applicability,(TriccStatic,TriccOperation, TriccReference)):
        if expression:
            expression = and_join([node.applicability, expression])
        else:
            expression = node.applicability
    
    return expression
    


        
        
def get_prev_instance_skip_expression(node, processed_nodes, process, expression=None):
    if node.base_instance is not None:
        activity = node
        expression_inputs = []
        past_instances = [
            n for n in processed_nodes if getattr(n.base_instance, 'id', None) == node.base_instance.id
        ]
        for past_instance in past_instances:
            add_sub_expression(
                expression_inputs, 
                get_node_expression(
                    past_instance,
                    processed_nodes=processed_nodes,
                    get_overall_exp=True,
                    is_prev=True,
                    process=process
                )
            )
        if expression and expression_inputs:
            add_sub_expression(expression_inputs, expression)
            expression = nand_join(expression, or_join(expression_inputs))
        elif expression_inputs:
            expression =  negate_term(or_join(expression_inputs))
    return expression


# end def
def get_process_skip_expression(node, processed_nodes, process, expression=None):
    
    end_expressions = []
    f_end_expression = get_end_expression(processed_nodes)
    if f_end_expression:
        end_expressions.append(f_end_expression)
    b_end_expression = get_end_expression(processed_nodes, 'pause')
    if b_end_expression:
        end_expressions.append(b_end_expression)        
    if process[0] in PROCESSES:
        for p in PROCESSES[PROCESSES.index(process[0])+1:]:
            p_end_expression = get_end_expression(processed_nodes, p)
            if p_end_expression:
                end_expressions.append(p_end_expression)
    if end_expressions:
        if expression:
            end_expressions.append(expression)
        if len(end_expressions) == 1:
            expression = end_expressions[0]
        else:
            expression = and_join(end_expressions)
    return expression
        
def get_end_expression(processed_nodes, process=None):
    end_node = get_last_end_node(processed_nodes, process)
    if end_node:
        return TriccOperation(
                    TriccOperator.ISNOTTRUE,
                    [end_node]
                )

                    


def export_proposed_diags(activity, diags=None, **kwargs):
    if diags is None:
        diags = []
    for node in activity.nodes.values():
        if isinstance(node, TriccNodeActivity):
            diags = export_proposed_diags(node, diags, **kwargs)
        if isinstance(node, TriccNodeProposedDiagnosis):
            if node.last is not False\
                and not any([diag.name  == node.name for diag in diags]):
                    diags.append(node)
    return diags
    

def get_accept_diagnostic_node(code, display, severity, priority, activity):
    node = TriccNodeAcceptDiagnostic(
        id=generate_id("pre_final." + code),
        name="pre_final." + code,
        label=display,
        list_name="acc_rej",
        activity=activity,
        group=activity,
        severity=severity,
        priority=priority
    )
    node.options = get_select_accept_reject_options(node, node.activity)
    return node

def get_diagnostic_node(code, display, severity, priority, activity):
    node = TriccNodeCalculate(
        id=generate_id("final." + code),
        name="final." + code,
        label=display,
        activity=activity,
        group=activity,
        priority=priority,
        expression_reference=or_join([
            TriccOperation(TriccOperator.ISTRUE, [TriccReference("pre_final." + code)]), 
            TriccOperation(
                TriccOperator.SELECTED,
                [TriccReference('tricc.manual.diag'), TriccStatic(code)]
            )
        ])
    )
    return node

def get_select_accept_reject_options(node, group):
    yes = TriccNodeSelectOption(
                id = generate_id(f'accept{node.id}'),
                name=f"{TRICC_TRUE_VALUE}",
                label="Accept",
                select = node,
                group = group,
                list_name = node.list_name
            )
    no = TriccNodeSelectOption(
                id = generate_id(f'reject{node.id}'),
                name=f"{TRICC_FALSE_VALUE}",
                label="Reject",
                select = node,
                group = group,
                list_name =  node.list_name
            )
    return {0:yes, 1:no }

def create_determine_diagnosis_activity(diags):
    start = TriccNodeMainStart(
        id=generate_id('start.determine-diagnosis'),
        name="start.determine-diagnosis",
        process='determine-diagnosis'
    )

    
    activity = TriccNodeActivity(
        id=generate_id('activity-determine-diagnosis'),
        name='determine-diagnosis',
        label='Diagnosis',
        root=start,
    )

    
    start.activity = activity
    start.group = activity
    diags_conf = []
    end = TriccNodeActivityEnd(
        id=generate_id("end.determine-diagnosis"),
        name="end.determine-diagnosis",
        activity=activity,
        group=activity,
    )
    activity.nodes[end.id]=end
    
    f = TriccNodeSelectMultiple(
        name="tricc.manual.diag",
        label="Add diagnosis",
        list_name='manual_diag',
        id=generate_id("tricc.manual.diag"),
        activity=activity,
        group=activity,
        required=TriccStatic(False),
        
    )
    for proposed in diags:
        d = get_accept_diagnostic_node(proposed.name, proposed.label, proposed.severity, proposed.priority, activity)
        c = get_diagnostic_node(proposed.name, proposed.label, proposed.severity, proposed.priority, activity)
        diags_conf.append(d)
        r = TriccNodeRhombus(
            path=start,
            id=generate_id(f"proposed-rhombus{proposed.id}"),
            expression_reference=TriccOperation(
                TriccOperator.ISTRUE,
                [TriccReference(proposed.name)]
            ),
            reference=[TriccReference(proposed.name)],
            activity=activity,
            priority=proposed.priority,
            group=activity)
        activity.calculates.append(r)
        activity.calculates.append(c)
        set_prev_next_node(r, d, edge_only=False)
        set_prev_next_node(d, end, edge_only=False)
        wait2 = get_activity_wait([activity.root], diags_conf, [f], edge_only=False)
        activity.nodes[d.options[0].id] = d.options[0]
        activity.nodes[d.options[1].id] = d.options[1]
        activity.nodes[d.id]=d
        activity.nodes[r.id]=r
        activity.nodes[c.id]=c
        activity.nodes[f.id]=f
        activity.nodes[wait2.id]=wait2
    # fallback

    options = [
        TriccNodeSelectOption(
            id=generate_id(d.name),
            name=d.name,
            label=d.label,
            list_name=f.list_name,
            relevance=d.activity.applicability,
            select=f
        ) for d in diags
    ]
    f.options=dict(zip(range(0, len(options)), options))
    activity.nodes[f.id]=f
    set_prev_next_node(f, end, edge_only=False)
    
    return activity
    
def get_prev_node_expression( node, processed_nodes, get_overall_exp=False, excluded_name=None, process=None):
    expression = None
    if node is None:
        pass
    # when getting the prev node, we calculate the
    if hasattr(node, 'expression_inputs') and len(node.expression_inputs) > 0:
        expression_inputs = node.expression_inputs
        expression_inputs = clean_or_list(expression_inputs)
    else:
        expression_inputs = []  
    prev_activities = {}
    for prev_node in node.prev_nodes:
        if prev_node.activity.id not in prev_activities:
            prev_activities[prev_node.activity.id]=[]
        prev_activities[prev_node.activity.id].append(prev_node)
    
    for act_id in prev_activities:
        act_expression_inputs = []
        for prev_node in prev_activities[act_id]:
            if excluded_name is None or prev_node != excluded_name or (
                    isinstance(excluded_name, str) and hasattr(prev_node, 'name') and prev_node.name != excluded_name): # or isinstance(prev_node, TriccNodeActivityEnd):
                # the rhombus should calculate only reference
                sub = get_node_expression(
                    prev_node,
                    processed_nodes=processed_nodes,
                    get_overall_exp=get_overall_exp,
                    is_prev=True,
                    process=process)
                if  isinstance(node, TriccNodeActivity) or get_overall_exp:
                    add_sub_expression(act_expression_inputs, sub )
                else:
                    add_sub_expression(expression_inputs, sub )
                
        if act_expression_inputs:
            act_sub = or_join(act_expression_inputs)
            if act_sub == TriccStatic(True): 
                 act_sub = get_node_expression(
                    prev_node.activity,
                    processed_nodes=processed_nodes,
                    get_overall_exp=True,
                    is_prev=True,
                    negate=False,
                    process=process
                )
            add_sub_expression(expression_inputs, act_sub )
            # avoid void is there is not conditions to avoid looping too much itme
    # expression_inputs = clean_or_list(
    #     [
    #         get_tricc_operation_operand(e) 
    #         if isinstance(expression, TriccOperation) 
    #         else e 
    #         for e in expression_inputs])
    
    if expression_inputs:
        expression =  or_join(
            expression_inputs
        )
        # if isinstance(node,  TriccNodeExclusive):
        #    expression =  TRICC_NEGATE.format(expression)
    # only used for activityStart 
    else:
        expression = TriccStatic(True)
    return expression

def get_activity_end_terms( node, processed_nodes, process=None):
    end_nodes = node.get_end_nodes()
    expression_inputs = []
    for end_node in end_nodes:
        add_sub_expression(
            expression_inputs,
            get_node_expression(
                end_node,
                processed_nodes=processed_nodes,
                get_overall_exp=False,
                is_prev=True,
                process=process))

    return  or_join(expression_inputs)

def get_count_terms( node, processed_nodes, get_overall_exp, negate=False, process=None):
    terms = []
    
    for prev_node in node.prev_nodes:
        term = get_count_terms_details( prev_node, processed_nodes, get_overall_exp, negate, process)
        if term:
            terms.append(term)
    if len(terms) == 1:
        return TriccOperation(
            TriccOperator.CAST_NUMBER,
            [terms[0]]
        )
    elif len(terms) > 0:
        return TriccOperation(
            TriccOperator.PLUS,
            [
                TriccOperation(
                    TriccOperator.CAST_NUMBER,
                    [term]
                ) for term in terms
            ]
        )
        
def get_count_terms_details( prev_node, processed_nodes, get_overall_exp, negate=False, process=None):
        operation_none = TriccOperation(
            TriccOperator.SELECTED,
            [
                prev_node,
                TriccStatic('opt_none')
            ]
        )
        if isinstance(prev_node, TriccNodeSelectYesNo):
            return TriccOperation(
                TriccOperator.SELECTED,
                [
                    prev_node,
                    TriccStatic(prev_node.options[0].name)
                ]
            )
        elif issubclass(prev_node.__class__, TriccNodeSelect):
            if negate:
                return
                #terms.append(TRICC_SELECT_MULTIPLE_CALC_NONE_EXPRESSION.format(get_export_name(prev_node)))
            else:
                return TriccOperation(
                    TriccOperator.MINUS,
                    [
                        TriccOperation(
                            TriccOperator.NATIVE,
                            [
                                'count-selected',
                                prev_node
                            ]
                        ),TriccOperation(
                            TriccOperator.CAST_NUMBER,
                            [
                                operation_none
                            ]
                        )
                ])
                #terms.append(TRICC_SELECT_MULTIPLE_CALC_EXPRESSION.format(get_export_name(prev_node)))
        elif isinstance(prev_node, (TriccNodeSelectNotAvailable)):
            return TriccOperation(
                TriccOperator.SELECTED,
                [
                    prev_node,
                    TriccStatic('1')
                ]
            )
            #terms.append(TRICC_SELECTED_EXPRESSION.format(get_export_name(prev_node), '1'))
        elif isinstance(prev_node, TriccNodeSelectOption):
            return get_selected_option_expression(prev_node, negate)
        else:
            if negate:
                return TriccOperation(
                        TriccOperator.CAST_NUMBER,
                        [
                            TriccOperation(
                                TriccOperator.NATIVE,
                                [
                                    TriccOperation(
                                    TriccOperator.CAST_NUMBER,
                                    [
                                        get_node_expression(
                                            prev_node,
                                            processed_nodes=processed_nodes,
                                            get_overall_exp=True,
                                            is_prev=True,
                                            process=process)
                                    ]),
                                    TriccStatic('0')
                                ]
                            )
                        ]
                    )
                
            else:
                return TriccOperation(
                        TriccOperator.CAST_NUMBER,
                        [
                            get_node_expression(
                                prev_node,
                                processed_nodes=processed_nodes,
                                get_overall_exp=True,
                                is_prev=True,
                                process=process)
                        ]
                    )
    
        
    
def get_add_terms( node, processed_nodes, get_overall_exp=False, negate=False, process=None):
    if negate:
        logger.warning("negate not supported for Add node {}".format(node.get_name()))
    terms = []
    for prev_node in node.prev_nodes:
        if issubclass(prev_node, TriccNodeNumber) or isinstance(node, TriccNodeCount):
            terms.append(
                TriccOperation(
                    TriccOperator.COALESCE,
                    [
                        prev_node,
                        TriccStatic(0)
                    ]
                )
            )
        else:
            terms.append(
                TriccOperation(
                    TriccOperator.CAST_NUMBER,
                    [
                        get_node_expression(
                            prev_node,
                            processed_nodes=processed_nodes,
                            get_overall_exp=True,
                            is_prev=True, 
                            process=process)
                    ]
                )
            )
    if len(terms) > 0:
        operation = terms[0]
        if len(terms) > 1:
            for term in terms[1:]:
                operation = TriccOperation(
                    TriccOperator.ADD,
                    [
                        operation,
                        term
                    ]
                )
        return operation
    
def get_rhombus_terms( node, processed_nodes, get_overall_exp=False, negate=False, process=None):
    expression = None
    left_term = None
    operator = None
    if node.reference is not None:
        if isinstance(node.reference, set):
            node.reference = list(node.reference)
        # calcualte the expression only for select muzltiple and fake calculate
        if  issubclass(node.reference.__class__, (list,OrderedSet)):
            if node.expression_reference is None and len(node.reference) == 1:
                ref = node.reference[0]
                if issubclass(ref.__class__, TriccNodeBaseModel):
                    if isinstance(ref, TriccNodeActivity):
                        expression = get_activity_end_terms(ref, processed_nodes, process=process)
                    elif issubclass(ref.__class__, TriccNodeFakeCalculateBase):
                        expression = get_node_expression(
                            ref,
                            processed_nodes=processed_nodes,
                            get_overall_exp=True,
                            is_prev=True,
                            process=process
                        )
                    else:
                        expression = ref
                elif issubclass(ref.__class__, TriccReference):
                    expression = ref
                else:
                    logger.critical('reference {0} was not found in the previous nodes of node {1}'.format(node.reference,
                                                                                                        node.get_name()))
                    exit(1)
            elif node.expression_reference is not None and node.expression_reference != '':
                if isinstance(node.expression_reference, TriccOperation):
                    return node.expression_reference
                elif isinstance(node.expression_reference, str):
                    expression = node.expression_reference.format(*get_list_names(node.reference))
                else:
                    logger.critical('expression_reference {0} unsuported type {1}'.format(node.expression_reference, node.expression_reference.__class__.__name__))
                    exit(1)

            else:
                logger.warning("missing expression for node {}".format(node.get_name()))
        else:
            logger.critical('reference {0} is not a list {1}'.format(node.reference, node.get_name()))
            exit(1)
    else:
        logger.critical('reference empty for Rhombis {}'.format( node.get_name()))
        exit(1)

    if expression is not None:
        if isinstance(expression, (TriccOperation, TriccStatic)):
            return expression
        elif issubclass(expression.__class__ , TriccNodeCalculateBase):
            return TriccOperation(
                TriccOperator.CAST_NUMBER,
                [
                    get_node_expression(
                        expression,
                        processed_nodes=processed_nodes,
                        get_overall_exp=True,
                        is_prev=True,
                        process=process
                    )
                ])
        elif issubclass(expression.__class__ , (TriccOperation)  ):
            return expression
        elif issubclass(expression.__class__ , (TriccNodeDisplayModel, TriccReference)):
            return TriccOperation(
                TriccOperator.ISTRUE,
                [
                    expression                
                ]
            )
        else:
            if left_term is not None and re.search(" (+)|(-)|(or)|(and) ", expression):
                expression = "({0}){1}".format(expression, left_term)
            else:
                expression = "{0}{1}".format(expression, left_term)
    else:
        logger.critical("Rhombus reference was not found for node {}, reference {}".format(
            node.get_name(),
            node.reference
        ))
        exit(1)

    return expression
# function that generate the calculation terms return by calculate node
# @param node calculate node to assess
# @param processed_nodes list of node already processed, importnat because only processed node could be use
# @param get_overall_exp used when this funciton is called in the evaluation of another calculate
# @param negate use to retriece the negation of a calculation
def get_calculation_terms( node, processed_nodes, get_overall_exp=False, negate=False, process=None):
    # returns something directly only if the negate is managed
    expression = None
    if isinstance(node, TriccNodeAdd):
        return get_add_terms(node, False, negate, process=process)
    elif isinstance(node, TriccNodeCount):
        return get_count_terms(node, False, negate, process=process)
    elif isinstance(node, TriccNodeRhombus):
        return get_rhombus_terms(
            node,
            processed_nodes=processed_nodes,
            get_overall_exp=False,
            negate=negate,
            process=process
        )
    elif isinstance(node, ( TriccNodeWait)):
        # just use to force order of question
        expression = None
    # in case of calulate expression evaluation, we need to get the relevance of the activity 
    # because calculate are not the the activity group
    elif isinstance(node, (TriccNodeActivityStart)) and get_overall_exp:
        expression =  get_prev_node_expression(node.activity, processed_nodes=processed_nodes, get_overall_exp=get_overall_exp, negate=negate, process=process)
    elif isinstance(node, (TriccNodeActivityStart, TriccNodeActivityEnd)):
        # the group have the relevance for the activity, not needed to replicate it
        expression = None #return get_prev_node_expression(node.activity, processed_nodes, get_overall_exp=False, excluded_name=None)
    elif isinstance(node, TriccNodeExclusive):
        if len(node.prev_nodes) == 1:
            iterator = iter(node.prev_nodes)
            node_to_negate = next(iterator)
            if isinstance(node_to_negate, TriccNodeExclusive):
                logger.critical("2 exclusives cannot be on a row")
                exit(1)
            elif issubclass(node_to_negate.__class__, TriccNodeCalculateBase):
                return get_node_expression(
                    node_to_negate,
                    processed_nodes=processed_nodes,
                    get_overall_exp=True,
                    is_prev=True,
                    negate=True,
                    process=process
                    )
            elif isinstance(node_to_negate, TriccNodeActivity):
                return get_node_expression(
                    node_to_negate,
                    processed_nodes=processed_nodes,
                    get_overall_exp=True,
                    is_prev=True,
                    negate=True,
                    process=process
                )
            else:
                logger.critical(f"exclusive node {node.get_name()}\
                    does not depend of a calculate but on\
                        {node_to_negate.__class__}::{node_to_negate.get_name()}")

        else:
            logger.critical("exclusive node {} has no ou too much parent".format(node.get_name()))
    
    if isinstance(node.expression_reference, (TriccOperation, TriccStatic)):
        expression = node.expression_reference
    elif node.reference is not None and node.expression_reference is not None :
        expression = get_prev_node_expression(node, processed_nodes=processed_nodes, get_overall_exp=get_overall_exp, process=process)
        ref_expression = node.expression_reference.format(*[get_export_name(ref) for ref in node.reference])
        if expression is not None and expression != '':
            expression =  and_join([expression,ref_expression])
        else:
            expression = ref_expression
    elif expression is None:
        expression =  get_prev_node_expression(node, processed_nodes=processed_nodes, get_overall_exp=get_overall_exp, process=process)
    
    # manage the generic negation
    if negate:
        
        return negate_term(expression)
    else:
        return expression
    
# Function that add element to array is not None or ''
def add_sub_expression(array, sub):
    if isinstance(sub, (TriccOperation, TriccStatic)):
        not_sub = negate_term(sub)
        if not_sub in array:
            # avoid having 2 conditions that are complete opposites
            array.remove(not_sub)
            array.append(TriccStatic(True))
        else:
            array.append(sub)
    else:
        pass
    # elif sub is None:
    #     array.append(TriccStatic(True))
        
 

    # function that negate terms
# @param expression to negate
def negate_term(expression):            
    
    return not_clean(expression)




# if the node is "required" then we can take the fact that it has value for the next elements
def get_required_node_expression(node):
    return TriccOperation(
            operator=TriccOperator.EXISTS,
            reference=[
                node
            ]
    )


# Get a selected option
def get_selected_option_expression(option_node, negate):
    
    selected = TriccOperation(
        TriccOperator.SELECTED,
        [
            option_node.select,
            TriccStatic(option_node.name)
        ]
    )
    
    if negate:
        return TriccOperation(
            operator=TriccOperator.AND,
            resource=[
                TriccOperation(
                    operator=TriccOperator.NOT,
                    resource=[
                        selected
                    ]
                ),TriccOperation(
                    operator=TriccOperator.NATIVE,
                    resource=[
                        'count-selected',
                        option_node.select
                    ]
                )
        ])
    
    else:
        return selected


   



