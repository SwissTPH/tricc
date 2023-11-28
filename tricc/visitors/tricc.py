import re

from tricc.converters.utils import *
from tricc.models.tricc import *



def merge_node(from_node,to_node):
    if from_node.activity != to_node.activity:
        logger.error("Cannot merge nodes from different activities")
    elif issubclass(from_node.__class__, TriccNodeCalculateBase) and issubclass(to_node.__class__, TriccNodeCalculateBase):
        for e in to_node.activity.edges:
            if e.target == from_node.id:
                e.target = to_node.id
    else:
        logger.error("Cannot merge not calculate nodes ")
    

def get_max_version(dict):
    max_version = None
    for id, sim_node in dict.items():
        if max_version is None or  max_version.version < sim_node.version :
            max_version = sim_node
    return max_version

def get_last_version(dict, name):
    max_version = None
    if name in dict:
        for  sim_node in dict[name].values():
            if max_version is None or  max_version.path_len < sim_node.path_len :
                max_version = sim_node
    return max_version




def process_calculate(node,processed_nodes, stashed_nodes, calculates, used_calculates, warn = False, **kwargs ):
     # used_calculates dict[name, Dict[id, node]]
     # processed_nodes Dict[id, node]
     # calculates  dict[name, Dict[id, node]]
    if node not in processed_nodes:
        # generate condition
        if is_ready_to_process(node, processed_nodes,False) and process_reference(node, calculates,used_calculates,processed_nodes,warn = warn):
            if is_rhombus_ready_to_process(node,processed_nodes):
                generate_calculates(node,calculates, used_calculates,processed_nodes)
                if issubclass(node.__class__, (TriccNodeDisplayCalculateBase )) and node.name is not None:
                    # generate the calc node version by looking in the processed calculate
                    last_calc = get_last_version(calculates, node.name)
                    # get max version used 
                    #last_used_version =  get_max_named_version(used_calculates, node.name)
                    last_used_calc = get_last_version(used_calculates, node.name)
                    # add calculate is added after the version collection so it is 0 in case there is no calc found
                    add_calculate(calculates,node)  
                    # merge is there is unused version ->
                    # current node not yet in the list so 1 item is enough
                    if last_calc is not None:
                        if last_used_calc is None or last_calc.path_len > last_used_calc.path_len:
                            node.version = last_calc.version + 1
                            node_to_delete = merge_calculate(node, calculates[node.name],last_used_calc)
                            if node_to_delete is not None:  
                                for d_node in node_to_delete:               
                                    del calculates[d_node.name][d_node.id]
                                    
                                    if d_node.name in used_calculates:
                                        if d_node.id in used_calculates[d_node.name]:
                                            logger.error("node {} used but deleted".format(d_node.get_name()))
                                    if d_node.id in d_node.activity.nodes:
                                        # mostly for end nodes
                                        if isinstance(d_node,(TriccNodeEnd,TriccNodeActivityEnd)):
                                            del d_node.activity.nodes[d_node.id]
                                    if  d_node  in stashed_nodes:
                                        logger.error("node {} not porcessed but deleted".format(d_node.get_name()))
                        # chaining the calculate, this is needed each time there is a last used version       
                        if last_used_calc is not None :
                            logger.debug("set last to false for node {}  and add its link it to next one".format(last_used_calc.get_name()))
                            set_prev_next_node(last_used_calc,node)
                            last_used_calc.last = False
                        update_calc_version(calculates,node.name)
                #if hasattr(node, 'next_nodes'):
                    #node.next_nodes=reorder_node_list(node.next_nodes, node.group)
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
def get_activity_wait(prev_nodes, nodes_to_wait, next_nodes, replaced_node = None):
    
    if not isinstance(nodes_to_wait, list):
        nodes_to_wait = [nodes_to_wait]
    path = prev_nodes[0] if len(prev_nodes) == 1 else get_bridge_path(prev_nodes)
    activity = prev_nodes[0].activity
    calc_node = TriccNodeWait(
            id = "ar_"+generate_id(),
            reference = nodes_to_wait,
            activity = activity,
            group = activity,
            path = path
        )


    #start the wait and the next_nodes from the prev_nodes
    #add the wait as dependency of the next_nodes
    for prev in prev_nodes:
        first = True
        # add edge between rhombus and node
        set_prev_next_node(prev,calc_node)
        for next_node in next_nodes:
            if prev != replaced_node and next_node != replaced_node :
                set_prev_next_node(prev,next_node,replaced_node)
            if first:
                first = False 
                set_prev_next_node(calc_node,next_node)
    
    return calc_node
    
def get_bridge_path(prev_nodes, node=None):
    if node is None:
        node = prev_nodes[0]
    calc_id  = generate_id()
    calc_name = "path_"+calc_id
    data = {
        'id': calc_id,
        'group':  node.group,
        'activity': node.activity,
        'label': "path: " + ( node.get_name()),
        'name': calc_name,
        'path_len': node.path_len + 1 * (node == prev_nodes[0])
    }
    if sum([0 if issubclass(n.__class__, (TriccNodeDisplayCalculateBase, TriccNodeRhombus)) else 1 for n in prev_nodes])>0 : #and len(node.prev_nodes)>1:
        calc= TriccNodeDisplayBridge( **data)
    else:
        calc =  TriccNodeBridge( **data)
    
def inject_bridge_path(node, nodes):

    prev_nodes = [nodes[n.source] for n in list(filter(lambda x: (x.target == node.id or x.target == node) and x.source in nodes ,node.activity.edges ))] 
    calc = get_bridge_path(prev_nodes, node)

    for e in node.activity.edges:
        if e.target == node.id:
            e.target = calc.id
   
    # add edge between bridge and node
    node.activity.edges.append(TriccEdge(
        id = generate_id(),
        source = calc.id,
        target = node.id
    ))
    node.path_len += 1
    return calc
    
def generate_calculates(node,calculates, used_calculates,processed_nodes):
    list_calc = []
    ## add select calcualte
    if issubclass(node.__class__, TriccNodeCalculateBase):
        if isinstance(node, TriccNodeRhombus):
            if node.expression_reference is None and len(node.reference)==1 and issubclass(node.reference[0].__class__, TriccNodeSelect):
                count_node = get_count_node(node)
                list_calc.append(count_node)
                set_prev_next_node(node.reference[0],count_node)
                node.path_len+=1
                node.reference[0] =  count_node
                processed_nodes.append(count_node)
                add_calculate(calculates, count_node)
                add_used_calculate(node, count_node, calculates, used_calculates, processed_nodes)
            
    # if a prev node is a calculate then it must be added in used_calc
    for prev in node.prev_nodes:
        add_used_calculate(node, prev, calculates, used_calculates, processed_nodes)
    #if the node have a save 
    if hasattr(node, 'save') and node.save is not None and node.save != '':
        # get fragments type.name.icdcode
        save_fragments=node.save.split('.')
        if len(save_fragments)>1:
            calculate_name = "{0}.{1}".format(save_fragments[0], save_fragments[1])
        else:
            calculate_name = "{0}.{1}".format(save_fragments[0], node.name)
            
        

    
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
    return list_calc



def add_calculate(calculates, calc_node):
    if issubclass(calc_node.__class__, TriccNodeDisplayCalculateBase):
        if calc_node.name not in calculates:
            calculates[calc_node.name]= {}
        calculates[calc_node.name][calc_node.id] = calc_node

def process_reference(node,  calculates ,used_calculates,processed_nodes, warn = False ):
    #global last_unfound_ref
    reference = []
    expression_reference = None
    if issubclass(node.__class__, TriccRhombusMixIn):
        if isinstance(node.reference, str) :
            logger.debug("process_reference:{}: {} ".format(node.get_name(), node.reference))
            ref_regex=r'(\$\{[^\}]+\})'
            lookup = re.findall(ref_regex, node.reference)
            if lookup and len(lookup)>0:
                ref_list = [x[2:-1] for x in lookup]
                expression_reference = re.sub(ref_regex,r"${{{}}}", node.reference )
            else:
                ref_list= [node.reference]
            for ref in ref_list:
                ref = ref.strip()
                last_found = get_prev_node_by_name(processed_nodes, ref, node)
                # ref is still a string here
                if last_found is None  or issubclass(last_found.__class__, TriccNodeCalculateBase):
                    if ref in calculates and len(calculates[ref])>0 :
                        # issue is that it can be further in another path
                        last_found = get_last_version(calculates, ref)
                if last_found is None:
                    if warn:
                        logger.warning("reference {} not found for a calculate {}".format(ref, node.get_name()))
                    else:
                        logger.debug("reference {} not found for a calculate {}".format(ref, node.get_name()))
                    #if last_unfound_ref == node:
                    #    logger.warning("reference not found for a calculate twice in a row {}".format(node.get_name()))
                    #last_unfound_ref = node
                    return False
                else:
                    reference.append(last_found) 
                    last_found.next_nodes.append(node)
                    node.path_len = max(node.path_len,last_found.path_len )
            for ref in reference:
                add_used_calculate(node, ref, calculates, used_calculates, processed_nodes)
            node.reference = reference
            node.expression_reference = expression_reference
        elif isinstance(node.reference,list):
            for ref in node.reference:
                #add_calculate(calculates,ref )
                add_used_calculate(ref, node,calculates, used_calculates, processed_nodes)
        elif node.reference is None:
            logger.error("process_calculate_version_requirement:reference is None for {0} ".format(node.get_name()))
            exit()             
            
    return True


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

def merge_calculate(node, calculates, last_used_calc):
    #calcualtes list[ node]
    node_to_delete = []
    for calc_node in calculates.values():
        # merge only if same name, version >= fromm version but < node version   and we don't merge the end node from differentes instance 
        if  calc_node!=node and node.tricc_type == calc_node.tricc_type:
            # if there is a calculate and a count, merge on the count
            remaining = node
            to_remove = calc_node
            if not(isinstance(remaining,(TriccNodeActivityEnd, TriccNodeActivityStart))) or remaining.instance == to_remove.instance:
                if (last_used_calc is None or to_remove.path_len > last_used_calc.path_len )and  to_remove.path_len<=remaining.path_len:
                    logger.debug("merge_calculate:{} ".format(remaining.name if hasattr(remaining,'name') else remaining.id))
                    # unlink the merged node in its next nodes
                    # list node is used to not update to_remove.next_nodes in a loop not porcessed but deleted
                    list_nodes = []
                    for next_node in to_remove.next_nodes:
                        list_nodes.append(next_node)
                    for next_node in list_nodes:
                        set_prev_next_node(remaining, next_node, to_remove )
                    # unlink the merged node in its prev nodes
                    # list node is used to not update to_remove.prev_nodes in a loop
                    list_nodes = []
                    for prev_node in to_remove.prev_nodes:
                        list_nodes.append(prev_node)
                    for prev_node in list_nodes:
                        set_prev_next_node(prev_node, remaining, to_remove )                 
                    node_to_delete.append(to_remove)
            else:
                logger.info("activity {} instance {} and {} might be merged (end node mergables)".format(remaining.activity.get_name(), remaining.activity.instance, to_remove.activity.instance))
        elif node.tricc_type != calc_node.tricc_type:
            logger.warning("two different type of calculate node share the same name {}::{}::{}".format(node.name,node.tricc_type, calc_node.tricc_type))
    return node_to_delete
    
    

        
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
                list_name =  node.list_name
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