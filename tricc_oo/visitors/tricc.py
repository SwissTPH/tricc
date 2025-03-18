import re
import logging

from tricc_oo.converters.utils import *
from tricc_oo.models import *
from tricc_oo.visitors.tricc import *
from tricc_oo.converters.datadictionnary import lookup_codesystems_code

logger = logging.getLogger("default")

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
    return [n for n in iterable if ((name == 'tricc_end' and isinstance(n, TriccNodeEnd)) or  n.name == name) and not isinstance(n, TriccNodeSelectOption)]


def get_last_version(name, processed_nodes,  _list=None):
    max_version = None
    if isinstance(_list, dict):
        _list = _list[name].values() if name in _list else []
    if _list is None:
        _list = get_versions(name, processed_nodes)
    if _list:
        for  sim_node in _list:
            # get the max version while not taking a node that have a next node before next calc
            if ((max_version is None 
                or  max_version.activity.path_len < sim_node.activity.path_len
                or  max_version.path_len < sim_node.path_len 
                or max_version.path_len == sim_node.path_len and hash(max_version.id) < hash(sim_node.id)
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
def get_node_expressions(node, processed_nodes):
    is_calculate = issubclass(node.__class__, TriccNodeCalculateBase)
    expression = None
    # in case of recursive call processed_nodes will be None
    if processed_nodes is None or is_ready_to_process(node, processed_nodes=processed_nodes):
        expression = get_node_expression(node, processed_nodes=processed_nodes, is_calculate=is_calculate)
        
    if is_calculate:
        if expression  and (not isinstance(expression, str) or expression != '') and  expression is not True  :
            num_expression = TriccOperation(
                TriccOperator.CAST_NUMBER,
                [expression]
            )
        elif expression is True or (not expression and is_calculate):
            expression = TriccStatic(1)                
        else:
            expression = ''
    if (
        issubclass(node.__class__, TriccNodeCalculateBase) 
        and not isinstance(expression, (TriccStatic, TriccReference, TriccOperation)) 
        and str(expression) != '' 
        and not isinstance(node, (TriccNodeWait, TriccNodeActivityEnd, TriccNodeActivityStart, TriccNodeEnd))
    ):
        logger.warning("Calculate {0} returning no calculations".format(node.get_name()))
        expression = TriccStatic(True)
    return expression


def process_calculate(node,processed_nodes, stashed_nodes, calculates, used_calculates, warn = False, **kwargs ):
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
            last_version = get_last_version(node.name, processed_nodes) if issubclass(node.__class__, (TriccNodeDisplayModel)) and not isinstance(node, TriccNodeSelectOption)  else  None
            if last_version:
                # 0-100 for manually specified instance.  100-200 for auto instance 
                node.version = last_version.version + 1
                last_version.last = False
                node.path_len = max(node.path_len, last_version.path_len + 1)
                # FIXME this is for XLS form where only calculate are evaluated for a activity that is not triggered
                if issubclass(node.__class__, (TriccNodeCalculateBase, TriccNodeNote)):
                    node.last = True
                else:
                    node.last = False
                    # versions = get_versions(node.name, processed_nodes)
                    # if the last version is already a coalesce no need to take all lat version
                    # if len(versions)>1:
                    #     if issubclass(last_version.__class__, TriccNodeCalculateBase):
                    #         versions = [last_version]
                    #     else:
                    #         logger.warning(f"several version of {node.get_name()} without a coalesce wrap")
                    calc = TriccNodeCalculate(
                        id=generate_id(),
                        name=node.name,
                        path_len=node.path_len+1,
                        version=last_version.version + 2,
                        expression=TriccOperation(
                            TriccOperator.COALESCE,
                            [node, last_version, TriccStatic('')]
                        ),
                        last=True,
                        activity=node.activity,
                        group=node.group
                        )
                    node.activity.nodes[calc.id]=calc
                    node.activity.calculates.append(calc)
                    if issubclass(node.__class__, TriccNodeInputModel):
                        node.expression = TriccOperation(
                            TriccOperator.COALESCE,
                            [
                                '$this',
                                last_version
                            ]
                        )
                
                
        # if has prev, create condition
            if hasattr(node, 'relevance') and (node.relevance is None or isinstance(node.relevance, TriccOperation)):
                node.relevance = get_node_expressions(node, processed_nodes=processed_nodes)
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
                
                generate_calculates(node,calculates, used_calculates,processed_nodes=processed_nodes)
            if last_version:
                if isinstance(node, TriccNodeInputModel):
                    version_relevance =  TriccOperation(
                            TriccOperator.ISNULL,
                            [last_version]
                        )
                elif last_version.relevance:
                    if last_version.activity.relevance:
                        version_relevance = TriccOperation(
                                TriccOperator.NOT,
                                [
                                    TriccOperation(
                                        TriccOperator.AND,
                                        [
                                            last_version.relevance,
                                            last_version.activity.relevance
                                        ]
                                    )
                                ]
                            )
                    else:
                        version_relevance = TriccOperation(
                                TriccOperator.NOT,
                                [

                                    last_version.relevance,

                                ]
                            )
                elif last_version.activity.relevance:
                    version_relevance = TriccOperation(
                        TriccOperator.NOT,
                        [

                            last_version.activity.relevance,

                        ]
                    )
                else:
                    version_relevance = None
                
                if version_relevance:
                    if getattr(node, 'relevance', None):
                        node.relevance = TriccOperation(
                            TriccOperator.AND,
                            [
                                version_relevance,
                                node.relevance
                            ]
                        )
                    elif hasattr(node, 'relevance'):
                        node.relevance = version_relevance
            
            if (
                issubclass(node.__class__, (TriccNodeDisplayCalculateBase )) and node.name is not None
            ):
                node_name = node.name if not isinstance(node, TriccNodeEnd) else 'tricc_end'
                # generate the calc node version by looking in the processed calculate
                # TODO the calculates should not be required with the latest version of get_last_version
                last_calc = get_last_version(
                    node_name,
                    [p for p in processed_nodes if issubclass(p.__class__, (TriccNodeCalculateBase, TriccNodeDisplayCalculateBase))]
                )
                
                # add calculate is added after the version collection so it is 0 in case there is no calc found_                add_calculate(calculates,node)  
                # merge is there is unused version ->
                # current node not yet in the list so 1 item is enough
                node_to_delete = None
                if last_calc is not None:
                    node.path_len = max(node.path_len, last_calc.path_len + 1 )
                    node.version = last_calc.version + 1
                        #logger.debug("set last to false for node {}  and add its link it to next one".format(last_used_calc.get_name()))
                    if node.prev_nodes:    
                        set_prev_next_node(last_calc,node)
                    elif isinstance(node.expression_reference, TriccOperation):
                        if  isinstance(node, ( TriccNodeAdd, TriccNodeCount)):
                            node.expression_reference = TriccOperation(
                                TriccOperator.PLUS,
                                [last_calc, node.expression_reference]
                            )
                        else:
                            node.expression_reference = TriccOperation(
                                TriccOperator.OR,
                                [TriccOperation(TriccOperator.ISTRUE, [last_calc]), node.expression_reference]
                            )
                    else:
                        logger.error(f"not able to find how to prev calc should contribute to {node.get_name()}")
                    last_calc.last = False
                    #update_calc_version(calculates,node_name)
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
      
def update_calc_version(calculates,name):
    if name in calculates and len(calculates[name])>1:
        ordered_list = sorted(list(calculates[name].values()), key=lambda x:x.path_len)
        i = 1
        len_max=len(calculates[name])
        for elm in ordered_list:
            elm.version=i
            elm.last= (i == len_max)
            i+=1
        

def get_max_named_version(calculates,name):
    max = 0
    if name  in calculates:
        for  node in calculates[name].values():
            if node.version > max:
                max = node.version
    return max

def get_count_node(node):
    count_id = generate_id()
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
            id = "ar_"+generate_id(),
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
    calc_id  = generate_id()
    calc_name = "path_"+calc_id
    data = {
        'id': calc_id,
        'group':  node.group,
        'activity': node.activity,
        'label': "path: " + ( node.get_name()),
        'name': calc_name,
        'path_len': node.path_len + 1 * (node == p_p_node)
    }
    
    if sum([0 if issubclass(n.__class__, (TriccNodeDisplayCalculateBase, TriccNodeRhombus)) else 1 for n in prev_nodes])>0 : #and len(node.prev_nodes)>1:
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

    
    
def generate_calculates(node,calculates, used_calculates,processed_nodes):
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
        if not isinstance(node, TriccNodeSelectYesNo) and  issubclass(node.__class__, (TriccNodeSelect)):
            calc_node = get_count_node(node)
            calc_node.path_len += 1
            calc_node.name=calculate_name
            calc_node.label =  "save select: " +node.get_name()        
        else:
            calc_id = generate_id()
            calc_node = TriccNodeCalculate(
                name=calculate_name,
                id = calc_id,
                group = node.group,
                activity = node.activity,
                label =  "save: " +node.get_name(),
                path_len=node.path_len+ 1
            )
        logger.debug("generate_save_calculate:{}:{} as {}".format(calc_node.tricc_type, node.name if hasattr(node,'name') else node.id, calculate_name))
        if isinstance(node, TriccNodeSelectYesNo):
            yesNode =  node.options[0]
            set_prev_next_node(yesNode,calc_node)
        else:
            set_prev_next_node(node,calc_node)
        list_calc.append(calc_node)
        #add_save_calculate(calc_node, calculates, used_calculates,processed_nodes)
        for calc in list_calc:
            node.activity.nodes[calc.id] = calc
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
        if isinstance(node.reference, list):
            if len(node.reference) == 1 :
                operation = node.reference[0]
            else:
                operation = TriccOperation(
                        TriccOperator.AND,
                        node.reference
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
                    logger.critical(f"reference {ref} not found in the project")
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
            
                
            node.path_len = max(node.path_len, last_found.path_len)
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
                id = generate_id(),
                name="1",
                label=label,
                select = node,
                group = group,
                list_name = node.list_name
            )}
        
def get_select_yes_no_options(node, group):
    yes = TriccNodeSelectOption(
                id = generate_id(),
                name="1",
                label="Yes",
                select = node,
                group = group,
                list_name = node.list_name
            )
    no = TriccNodeSelectOption(
                id = generate_id(),
                name="-1",
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
                                             node_path = [], **kwargs):
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
    if (callback(node, processed_nodes=processed_nodes, stashed_nodes=stashed_nodes, warn = warn, node_path=node_path, **kwargs)):
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
        if not recursive:
            reorder_node_list(stashed_nodes, node.group, processed_nodes)
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
                stashed_nodes += node.activity.calculates 
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
        
                
    else:
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


def get_data_for_log(node):
    return "{}:{}|{} {}:{}".format(
        node.group.get_name() if node.group is not None else node.activity.get_name(),
        node.group.instance if node.group is not None else node.activity.instance ,
        node.__class__,
        node.get_name(),
        node.instance)

def stashed_node_func(node, callback, recursive=False, **kwargs):
    processed_nodes = kwargs.get('processed_nodes', set())
    stashed_nodes = kwargs.get('stashed_nodes', OrderedSet())
    path_len = 0
    walktrhough_tricc_node_processed_stached(node, callback, processed_nodes, stashed_nodes, path_len, recursive,
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
            walktrhough_tricc_node_processed_stached(s_node, callback, processed_nodes, stashed_nodes, path_len,
                                                     recursive, warn= warn, **kwargs)


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
                    logger.info("looped nodes")
                    for es_node in looped:
                        logger.info("Stashed node {}:{}|{} {}".format(
                            es_node.activity.get_name() if hasattr(es_node,'activity') else '' ,
                            es_node.activity.instance if hasattr(es_node,'activity') else '',
                            es_node.__class__, 
                            es_node.get_name()))
                        #reverse_walkthrough(es_node, es_node, print_trace, processed_nodes, stashed_nodes)
                    logger.info("waited nodes")
                    for es_node in waited:
                        logger.info("Stashed node {}:{}|{} {}".format(
                            es_node.activity.get_name() if hasattr(es_node,'activity') else '' ,
                            es_node.activity.instance if hasattr(es_node,'activity') else '',
                            es_node.__class__, 
                            es_node.get_name()))
                    if len(stashed_nodes) == len(prev_stashed_nodes):
                        exit(-1)
            else:
                loop_count = 0
    else:
        loop_count = 0
    return loop_count

        
def get_all_dependant(loop, stashed_nodes, processed_nodes, depth=0, waited=[] , looped=[]):
    for n in loop:
        dependant = OrderedSet()
        i=0
        logger.critical(f"{i}: {n.__class__}::{n.get_name()}::{getattr(n,'instance','')}::{process_reference(n, processed_nodes, [])}")
        i += 1
        if hasattr(n, 'prev_nodes') and n.prev_nodes:
            dependant =  dependant | n.prev_nodes
        if hasattr(n, 'get_references'):
            dependant =  dependant | (n.get_references() or OrderedSet())
        if not isinstance(dependant, list):
            pass
        for d in dependant:
            if isinstance(d, TriccNodeSelectOption):
                d = d.select
            if d not in waited and d not in looped:
                if isinstance(d, TriccReference):
                    if not any(n.name == d.value for n in processed_nodes):
                        if not any(n.name == d.value for n in stashed_nodes):
                            waited.append(d)
                        else :
                            looped.append(d)
                
                elif d  not in processed_nodes:
                    
                    if d not in stashed_nodes:
                        waited.append(d)
                    else :
                        looped.append(d)
    if depth < MAX_DRILL:
        return get_all_dependant(waited, stashed_nodes, processed_nodes, depth+1, waited , looped)

    return waited, looped


MAX_DRILL = 1

def get_last_end_node(processed_nodes, process=None):
    end_name = 'tricc_end'
    if process:
        end_name += f"_{process}"
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
    
def reorder_node_list(list_node, group, processed_nodes):
    active_activities = set(n.activity for n in processed_nodes)
    
    # Define a lambda to assign numeric priorities
    def filter_logic(l_node):
        
        if (
            isinstance(l_node, TriccNodeWait)
            and any(isinstance(rn, TriccNodeActivity) and any(sn.activity == rn for sn in list_node) for rn in l_node.reference)
        ):
            return 7
        elif group is not None and hasattr(l_node, 'group') and l_node.group and l_node.group.id == group.id:
            return 0  # Highest priority: Same group
        elif issubclass(l_node.__class__, TriccRhombusMixIn) :
            return 6
        elif hasattr(group, 'group') and group.group and l_node.group and l_node.group.id == group.group.id:
            return 1  # Second priority: Parent group
        elif not isinstance(l_node.activity.root, TriccNodeActivityStart) and l_node.activity in active_activities:
            return 2  # Third priority: Active activities
        elif not isinstance(l_node.activity.root, TriccNodeActivityStart):
            return 3  # Third priority: Active activities
        elif l_node.activity in active_activities:
            return 4  # Third priority: Active activities
 

        else:
            return 5  # Lowest priority: Others
    
    # Sort list_node in place using filter_logic as the key
    list_node.sort(key=filter_logic, reverse=False)
    return None
    
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
def get_node_expression( in_node, processed_nodes, is_calculate=False, is_prev=False, negate=False):
    # in case of calculate we only use the select multiple if none is not selected
    expression = None
    negate_expression = None
    node = in_node
    if isinstance(node, (TriccNodeActivityStart,TriccNodeMainStart, TriccNodeActivityEnd, TriccNodeEnd)):
        if is_prev and is_calculate:
            expression = get_node_expression(node.activity, processed_nodes=processed_nodes, is_calculate=is_calculate, is_prev=is_prev, negate=negate )
        elif  isinstance(node, (TriccNodeActivityStart)):
            return None
        
    elif isinstance(node, TriccNodeWait):
        if is_prev:
            # the wait don't do any calculation with the reference it is only use to wait until the reference are valid
            return get_node_expression(node.path, processed_nodes=processed_nodes, is_calculate=is_calculate, is_prev=True)
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
        expression = get_rhombus_terms(node, processed_nodes)  # if issubclass(node.__class__, TricNodeDisplayCalulate) else TRICC_CALC_EXPRESSION.format(get_export_name(node)) #
        negate_expression = TriccOperation(TriccOperator.NOT,[expression])
        if node.path is None :
            if len(node.prev_nodes) == 1:
                node.path = list(node.prev_nodes)[0]
            elif len(node.prev_nodes) > 1:
                logger.critical(f"missing path for Rhombus {node.get_name()}")
                exit(1)
        prev_exp = get_node_expression(node.path, processed_nodes=processed_nodes, is_calculate=is_calculate, is_prev=True)
        if prev_exp and expression:
            expression = TriccOperation(
                TriccOperator.AND,
                [prev_exp, expression]
            )
            negate_expression = TriccOperation(
                TriccOperator.AND,
                [
                    prev_exp, 
                    negate_expression
                ]
            )
        elif prev_exp:
            
            logger.error(f"useless rhombus {node.get_name()}")
            expression = prev_exp
            negate_expression = prev_exp
            logger.critical(f"Rhombus without expression {node.get_name()}")
    elif hasattr(node, 'expression_reference') and isinstance(node.expression_reference, TriccOperation):
        # if issubclass(node.__class__, TriccNodeDisplayCalculateBase):
        #     expression = TriccOperation(
        #         TriccOperator.CAST_NUMBER,
        #         [node.expression_reference])
        # else:    
        expression = node.expression_reference
    elif not is_prev and hasattr(node, 'relevance') and isinstance(node.relevance, TriccOperation):
        expression = node.relevance  
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
    elif is_prev and issubclass(node.__class__, TriccNodeDisplayCalculateBase):
        expression = TriccOperation(TriccOperator.ISTRUE, [node])
    elif issubclass(node.__class__, TriccNodeCalculateBase):
        if negate:
            negate_expression = get_calculation_terms(node, processed_nodes=processed_nodes, is_calculate=is_calculate, negate=True)
        else:
            expression = get_calculation_terms(node, processed_nodes=processed_nodes, is_calculate=is_calculate)
    elif is_prev and not is_calculate and hasattr(node, 'required') and node.required:
        expression = get_required_node_expression(node)
    if expression is None:
        expression = get_prev_node_expression(node, processed_nodes=processed_nodes, is_calculate=is_calculate)
            # in_node not in processed_nodes is need for calculates that can but run after the end of the activity

    
    if isinstance(node, TriccNodeActivity):
        
        
        if node.base_instance is not None and not is_prev:
            activity = node
            expression_inputs = []
            past_instances = [
                n for n in processed_nodes if getattr(n.base_instance, 'id', None) == node.base_instance.id
            ]
            for past_instance in past_instances:
                add_sub_expression(expression_inputs, get_node_expression(past_instance, processed_nodes=processed_nodes, is_calculate=False, is_prev=True))
            if expression and expression_inputs:
    
                add_sub_expression(expression_inputs, expression)
                expression = nand_join(expression, or_join(expression_inputs))
            elif expression_inputs:
                expression =  negate_term(or_join(expression_inputs))
        if not is_prev:
            end_node = get_last_end_node(processed_nodes)
            if end_node:
                end_operation = TriccOperation(
                    TriccOperator.NOT, 
                    [
                        TriccOperation(
                            TriccOperator.ISTRUE,
                            [end_node]
                        )
                    ]
                )
                if  expression:
                    expression = TriccOperation(
                        TriccOperator.AND, [
                                end_operation,
                                expression
                        ]
                    )
                else:
                    expression = end_operation

            elif node.root.relevance:
                expression = and_join([expression, node.root.relevance])
              
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
    
def export_proposed_diags(activity, diags=None, **kwargs):
    if diags is None:
        diags = []
    for node in activity.nodes.values():
        if isinstance(node, TriccNodeActivity):
            diags = export_proposed_diags(node, diags, **kwargs)
        if isinstance(node, TriccNodeProposedDiagnosis):
            if node.last\
                and not any([diag.name  == node.name for diag in diags]):
                    diags.append(node)
    return diags
    

def get_accept_diagnostic_node(code, display, severity, activity):
    node = TriccNodeAcceptDiagnostic(
        id=generate_id(),
        name="pre_final." + code,
        label=display,
        list_name="acc_rej",
        activity=activity,
        group=activity,
        severity=severity
    )
    node.options = get_select_accept_reject_options(node, node.activity)
    return node

def get_diagnostic_node(code, display, severity, activity):
    node = TriccNodeAcceptDiagnostic(
        id=generate_id(),
        name="final." + code,
        label=display,
        list_name="acc_rej",
        activity=activity,
        group=activity,
        severity=severity
    )
    node.options = get_select_accept_reject_options(node, node.activity)
    return node

def get_select_accept_reject_options(node, group):
    yes = TriccNodeSelectOption(
                id = generate_id(),
                name="1",
                label="Accept",
                select = node,
                group = group,
                list_name = node.list_name
            )
    no = TriccNodeSelectOption(
                id = generate_id(),
                name="-1",
                label="Reject",
                select = node,
                group = group,
                list_name =  node.list_name
            )
    return {0:yes, 1:no }

def create_determine_diagnosis_activity(diags):
    start = TriccNodeActivityStart(
        id=generate_id(),
        name="start.determine-diagnosis"
    )

    
    activity = TriccNodeActivity(
        id=generate_id(),
        name='determine-diagnosis',
        label='Diagnosis',
        root=start,
    )

    
    start.activity = activity
    start.group = activity
    diags_conf = []
    r_diags_conf = []
    end = TriccNodeActivityEnd(
        id=generate_id(),
        name="end.determine-diagnosis",
        activity=activity,
        group=activity,
    )
    activity.nodes[end.id]=end
    for proposed in diags:
        d = get_diagnostic_node(proposed.name, proposed.label, proposed.severity, activity)
        diags_conf.append(d)
        r = TriccNodeRhombus(
            id=generate_id(),
            expression_reference=TriccOperation(
                TriccOperator.ISTRUE,
                [TriccReference(proposed.name)]
            ),
            reference=[TriccReference(proposed.name)],
            activity=activity,
            group=activity        )
        r_diags_conf.append(r)
        set_prev_next_node(start, r, edge_only=False)
        set_prev_next_node(r, d, edge_only=False)
        set_prev_next_node(d, end, edge_only=False)
        activity.nodes[d.options[0].id] = d.options[0]
        activity.nodes[d.options[1].id] = d.options[1]
        activity.nodes[d.id]=d
        activity.nodes[r.id]=r
    # fallback
    f = TriccNodeSelectMultiple(
        name="tricc.manual.diag",
        label="Add a diagnostic",
        list_name='manual_diag',
        id=generate_id("tricc.manual.diag"),
        activity=activity,
        group=activity,
        required=TriccStatic(False),
        
    )
    options = [
        TriccNodeSelectOption(
            id=generate_id(d.name),
            name=d.name,
            label=d.label,
            list_name=f.list_name,
            select=f
        ) for d in diags
    ]
    f.options=dict(zip(range(0, len(options)), options))
    wait2 = get_activity_wait([activity.root], diags_conf, [f], edge_only=False)
    activity.nodes[wait2.id]=wait2
    activity.nodes[f.id]=f

    
    return activity
    
def get_prev_node_expression( node, processed_nodes, is_calculate=False, excluded_name=None):
    expression = None
    if node is None:
        pass
    # when getting the prev node, we calculate the
    if hasattr(node, 'expression_inputs') and len(node.expression_inputs) > 0:
        expression_inputs = node.expression_inputs
        expression_inputs = clean_list_or(expression_inputs)
    else:
        expression_inputs = []        
    for prev_node in node.prev_nodes:
        if excluded_name is None or prev_node != excluded_name or (
                isinstance(excluded_name, str) and hasattr(prev_node, 'name') and prev_node.name != excluded_name): # or isinstance(prev_node, TriccNodeActivityEnd):
            # the rhombus should calculate only reference
            add_sub_expression(expression_inputs, get_node_expression(prev_node, processed_nodes=processed_nodes, is_calculate=is_calculate, is_prev=True))
            # avoid void is there is not conditions to avoid looping too much itme
    expression_inputs = clean_list_or(
        [
            get_tricc_operation_operand(e) 
            if isinstance(expression, TriccOperation) 
            else e 
            for e in expression_inputs])
    
    expression = None
    if len(expression_inputs) == 1:
        expression = expression_inputs[0]
    
    elif expression_inputs:
        expression = TriccOperation(
            TriccOperator.OR,
            expression_inputs
        )
        # if isinstance(node,  TriccNodeExclusive):
        #    expression =  TRICC_NEGATE.format(expression)
    # only used for activityStart 
    
    return expression

def get_activity_end_terms( node, processed_nodes):
    end_nodes = node.get_end_nodes()
    expression_inputs = []
    for end_node in end_nodes:
        add_sub_expression(expression_inputs,
                        get_node_expression(end_node, processed_nodes=processed_nodes, is_calculate=False, is_prev=True))

    return  or_join(expression_inputs)

def get_count_terms( node, processed_nodes, is_calculate, negate=False):
    terms = []
    for prev_node in node.prev_nodes:
        operation_none = TriccOperation(
            TriccOperator.SELECTED,
            [
                prev_node,
                TriccStatic('opt_none')
            ]
        )
        if isinstance(prev_node, TriccNodeSelectMultiple):
            if negate:
                terms.append()
                #terms.append(TRICC_SELECT_MULTIPLE_CALC_NONE_EXPRESSION.format(get_export_name(prev_node)))
            else:
                terms.append(TriccOperation(
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
                ]))
                #terms.append(TRICC_SELECT_MULTIPLE_CALC_EXPRESSION.format(get_export_name(prev_node)))
        elif isinstance(prev_node, (TriccNodeSelectYesNo, TriccNodeSelectNotAvailable)):
            terms.append(TriccOperation(
                TriccOperator.SELECTED,
                [
                    prev_node,
                    TriccStatic('1')
                ]
            ))
            #terms.append(TRICC_SELECTED_EXPRESSION.format(get_export_name(prev_node), '1'))
        elif isinstance(prev_node, TriccNodeSelectOption):
            terms.append(get_selected_option_expression(prev_node, negate))
        else:
            if negate:
                terms.append(
                    TriccOperation(
                        TriccOperator.CAST_NUMBER,
                        [
                            TriccOperation(
                                TriccOperator.NATIVE,
                                [
                                    TriccOperation(
                                    TriccOperator.CAST_NUMBER,
                                    [
                                        get_node_expression(prev_node, processed_nodes=processed_nodes, is_calculate=False, is_prev=True)
                                    ]),
                                    TriccStatic('0')
                                ]
                            )
                        ]
                    )
                )
            else:
                terms.append(
                    TriccOperation(
                        TriccOperator.CAST_NUMBER,
                        [
                            get_node_expression(prev_node, processed_nodes=processed_nodes, is_calculate=False, is_prev=True)
                        ]
                    ))
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
        
    
def get_add_terms( node, processed_nodes, is_calculate=False, negate=False):
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
                        TriccStatic("''")
                    ]
                )
            )
        else:
            terms.append(
                TriccOperation(
                    TriccOperator.CAST_NUMBER,
                    [
                        get_node_expression(prev_node, processed_nodes=processed_nodes, is_calculate=False, is_prev=True)
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
    
def get_rhombus_terms( node, processed_nodes, is_calculate=False, negate=False):
    expression = None
    left_term = None
    operator = None
    if node.reference is not None:
        if isinstance(node.reference, set):
            node.reference = list(node.reference)
        # calcualte the expression only for select muzltiple and fake calculate
        if  issubclass(node.reference.__class__, list):
            if node.expression_reference is None and len(node.reference) == 1:
                ref = node.reference[0]
                if issubclass(ref.__class__, TriccNodeBaseModel):
                    if isinstance(ref, TriccNodeActivity):
                        expression = get_activity_end_terms(ref, processed_nodes)
                    elif issubclass(ref.__class__, TriccNodeFakeCalculateBase):
                        expression = get_node_expression(ref, processed_nodes=processed_nodes, is_calculate=True, is_prev=True)
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
                else:
                    expression = node.expression_reference.format(*get_list_names(node.reference))
            else:
                logger.warning("missing expression for node {}".format(node.get_name()))
        else:
            logger.critical('reference {0} is not a list {1}'.format(node.reference, node.get_name()))
            exit(1)
    else:
        logger.critical('reference empty for Rhombis {}'.format( node.get_name()))
        exit(1)

    if expression is not None:
        if isinstance(expression, TriccOperation):
            return expression
        elif issubclass(expression.__class__ , TriccNodeCalculateBase):
            return TriccOperation(
                TriccOperator.CAST_NUMBER,
                [
                    get_node_expression(expression, processed_nodes=processed_nodes, is_calculate=True, is_prev=True)
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
            if left_term is not None and re.search(" (\+)|(\-)|(or)|(and) ", expression):
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
# @param is_calculate used when this funciton is called in the evaluation of another calculate
# @param negate use to retriece the negation of a calculation
def get_calculation_terms( node, processed_nodes, is_calculate=False, negate=False):
    # returns something directly only if the negate is managed
    expression = None
    if isinstance(node, TriccNodeAdd):
        return get_add_terms(node, False, negate)
    elif isinstance(node, TriccNodeCount):
        return get_count_terms(node, False, negate)
    elif isinstance(node, TriccNodeRhombus):
        return get_rhombus_terms(node, processed_nodes=processed_nodes, is_calculate=False, negate=negate)
    elif isinstance(node, ( TriccNodeWait)):
        # just use to force order of question
        expression = None
    # in case of calulate expression evaluation, we need to get the relevance of the activity 
    # because calculate are not the the activity group
    elif isinstance(node, (TriccNodeActivityStart)) and is_calculate:
        expression =  get_prev_node_expression(node.activity, processed_nodes=processed_nodes, is_calculate=is_calculate, negate=negate)
    elif isinstance(node, (TriccNodeActivityStart, TriccNodeActivityEnd)):
        # the group have the relevance for the activity, not needed to replicate it
        expression = None #return get_prev_node_expression(node.activity, processed_nodes, is_calculate=False, excluded_name=None)
    elif isinstance(node, TriccNodeExclusive):
        if len(node.prev_nodes) == 1:
            iterator = iter(node.prev_nodes)
            node_to_negate = next(iterator)
            if isinstance(node_to_negate, TriccNodeExclusive):
                logger.critical("2 exclusives cannot be on a row")
                exit(1)
            elif issubclass(node_to_negate.__class__, TriccNodeCalculateBase):
                return get_node_expression(node_to_negate, processed_nodes=processed_nodes, is_prev=True, negate=True)
            elif isinstance(node_to_negate, TriccNodeActivity):
                return get_node_expression(node_to_negate, processed_nodes=processed_nodes, is_calculate=False, is_prev=True,
                                        negate=True)
            else:
                logger.critical(f"exclusive node {node.get_name()}\
                    does not depend of a calculate but on\
                        {node_to_negate.__class__}::{node_to_negate.get_name()}")

        else:
            logger.critical("exclusive node {} has no ou too much parent".format(node.get_name()))
    
    if isinstance(node.expression_reference, (TriccOperation, TriccStatic)):
        expression = node.expression_reference
    elif node.reference is not None and node.expression_reference is not None :
        expression = get_prev_node_expression(node, processed_nodes=processed_nodes, is_calculate=is_calculate)
        ref_expression = node.expression_reference.format(*[get_export_name(ref) for ref in node.reference])
        if expression is not None and expression != '':
            expression =  and_join([expression,ref_expression])
        else:
            expression = ref_expression
    elif expression is None:
        expression =  get_prev_node_expression(node, processed_nodes=processed_nodes, is_calculate=is_calculate)
    
    # manage the generic negation
    if negate:
        
        return negate_term(expression)
    else:
        return expression
    
# Function that add element to array is not None or ''
def add_sub_expression(array, sub):
    if isinstance(sub, TriccOperation) or  sub:
        not_sub = negate_term(sub)
        if not_sub in array:
            # avoid having 2 conditions that are complete opposites
            array.remove(not_sub)
            array.append(TriccStatic(True))
        else:
            array.append(sub)
    # elif sub is None:
    #     array.append(TriccStatic(True))
        
       
# function that generate remove unsure condition
# @param list_or
# @param and elm use upstream
def clean_list_or(list_or, elm_and=None):
    if len(list_or) == 0:
        return []
    if 'false()' in list_or:
        list_or.remove('false()')
    if TriccStatic(False) in list_or:
        ist_or.remove(TriccStatic(False))
    if (
        '1' in list_or 
        or 1 in list_or 
        or TriccStatic(True) in list_or 
        or True in list_or 
        or 'True' in list_or
    ):
        list_or = [TriccStatic(True)]
        return list_or
    if elm_and is not None:
            if negate_term(elm_and) in list_or:
                # we remove x and not X
                list_or.remove(negate_term(elm_and))
            if elm_and in list_or:
                # we remove  x and x
                list_or.remove(elm_and)
    
    if elm_and is not None:
        if str(negate_term(elm_and)) in [str(s) for s in list_or]:
            # we remove x and not X
            list_or.remove(negate_term(elm_and))
    for exp_prev in list_or:
        if negate_term(exp_prev) in list_or:
            # if there is x and not(X) in an OR list them the list is always true
            list_or = [TriccStatic(True)]
        else:
                # if (
                #     re.search(exp_prev, ' and ') in list_or
                #     and exp_prev.replace('and ', 'and not') in list_or
                # ):
                #     right = exp_prev.split(' and ')[0]
                #     list_or.remove(exp_prev)
                #     list_or.remove(exp_prev.replace('and ', 'and not'))
                #     list_or.append(right)

                if  str(negate_term(exp_prev)) == str(elm_and) or str(exp_prev) == (elm_and):
                    list_or.remove(exp_prev)
   
    return sorted(list_or, key=str)

    # function that negate terms
# @param expression to negate
def negate_term(expression):            
    if expression is None or isinstance(expression, str) and expression == '':
        return TriccStatic(False)
    elif isinstance(expression, TriccStatic) and expression == TriccStatic(False):
        return TriccStatic(True)
    elif isinstance(expression, TriccStatic) and expression == TriccStatic(True):
        return TriccStatic(False)
    else:
        if isinstance(expression, TriccOperation) or issubclass(expression.__class__, TriccNodeDisplayCalculateBase):
            return TriccOperation(
                operator=TriccOperator.NOT,
                reference=[expression]
            )
        if issubclass(expression.__class__, TriccNodeDisplayModel):
            return TriccOperation(
                operator=TriccOperator.NOT,
                reference=[TriccOperation(
                    operator=TriccOperator.EXISTS,
                    reference=[expression]
                )]
            )
        else:
            return TRICC_NEGATE.format((expression))
        
# function that make multipat  and
# @param argv list of expression to join with and
def and_join(argv):
    #argv=add_bracket_to_list_elm(argv)
    if len(argv) == 0:
        return ''
    elif len(argv) == 1:
        return argv[0]
    elif len(argv) == 2:
        return simple_and_join(argv[0], argv[1])
    else:
        return  TriccOperation(
            TriccOperator.AND,
            argv
        )

# function that make a 2 part and
# @param left part
# @param right part
def simple_and_join(left, right):
    expression = None
    # no term is considered as True
    left_issue = left is None or left == ''
    right_issue = right is None or right == ''
    left_neg = left is False or left == 0 or left == '0' or left == TriccStatic(False) or left is True
    right_neg = right is False or right == 0 or right == '0' or right == TriccStatic(False) or right is False
    if issubclass(left.__class__, TriccNodeBaseModel):
        left = get_export_name(left)
    if issubclass(right.__class__, TriccNodeBaseModel):
        right = get_export_name(right)    
    
    if left_issue and right_issue:
        logger.critical("and with both terms empty")
    elif left_neg or right_neg:
        return 'false()'
    elif left_issue:
        logger.debug('and with empty left term')
        return  right
    elif left == '1' or left == 1 or left == TriccStatic(True) or left is True:
        return  right
    elif right_issue:
        logger.debug('and with empty right term')
        return  left
    elif right == '1' or right == 1 or right == TriccStatic(True) or right is True:
        return  left
    else:
        return  TriccOperation(
            TriccOperator.AND,
            [left, right]
        )

def or_join(list_or, elm_and=None):
    cleaned_list  = clean_list_or(list_or, elm_and)
    if len(cleaned_list) == 1:
        return cleaned_list[0]
    if len(cleaned_list)>1: 
        return TriccOperation(
            TriccOperator.OR,
            cleaned_list
        )
    
    
    
# function that make a 2 part NAND
# @param left part
# @param right part
def nand_join(left, right):
    # no term is considered as True
    left_issue = left is None or left == ''
    right_issue = right is None or right == ''
    left_neg = left == False or left == 0 or left == '0' or left == TriccStatic(False)
    right_neg = right == False or right == 0 or right == '0' or right == TriccStatic(False)
    if issubclass(left.__class__, TriccNodeBaseModel):
        left = get_export_name(left)
    if issubclass(right.__class__, TriccNodeBaseModel):
        right = get_export_name(right) 
    if left_issue and right_issue:
        logger.critical("and with both terms empty")
    elif left_issue:
        logger.debug('and with empty left term')
        return  negate_term(right)
    elif left == '1' or left == 1 or left == TriccStatic(True):
        return  negate_term(right)
    elif right_issue :
        logger.debug('and with empty right term')
        return  TriccStatic(False)
    elif right == '1' or right == 1 or left_neg or right == TriccStatic(True):
        return  TriccStatic(False)
    elif right_neg:
        return left
    else:
        return  and_join([left, negate_term(right)])



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


   



