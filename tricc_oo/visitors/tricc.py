import re

from tricc_oo.converters.utils import *
from tricc_oo.models import *
from tricc_oo.visitors.tricc import *


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
    for prev in prev_nodes:
        set_prev_next_node(prev, calc, activity=node.activity, edge_only=edge_only )
    
def inject_bridge_path(node, nodes):

    prev_nodes = [nodes[n.source] for n in list(filter(lambda x: (x.target == node.id or x.target == node) and x.source in nodes ,node.activity.edges ))] 
    calc = get_bridge_path(prev_nodes, node,edge_only=True)

    for e in node.activity.edges:
        if e.target == node.id:
            e.target = calc.id
   
    # add edge between bridge and node
    set_prev_next_node(calc,node,edge_only=True, activity=node.activity)
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
                processed_nodes.add(count_node)
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
            ref_pattern=r'(\$\{[^\}]+\})'
            lookup = re.findall(ref_pattern, node.reference)
            if lookup and len(lookup)>0:
                ref_list = [x[2:-1] for x in lookup]
                expression_reference = re.sub(ref_pattern,r"${{{}}}", node.reference )
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
                    set_prev_next_node(last_found, node)
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



# walkthough all node in an iterative way, the same node might be parsed 2 times 
# therefore to avoid double processing the nodes variable saves the node already processed
# there 2 strategies : process it the first time or the last time (wait that all the previuous node are processed)

def walktrhough_tricc_node_processed_stached(node, callback, processed_nodes, stashed_nodes, path_len, recursive=True, warn = False,
                                             node_path = [], **kwargs):
    # logger.debug("walkthrough::{}::{}".format(callback.__name__, node.get_name()))
    if hasattr(node, 'prev_nodes') and len(node.prev_nodes) > 0:
        path_len = max(path_len, *[n.path_len + 1 for n in node.prev_nodes], len(processed_nodes)+1)
    node.path_len = max(node.path_len, path_len)
    if (callback(node, processed_nodes=processed_nodes, stashed_nodes=stashed_nodes, warn = warn, node_path=node_path, **kwargs)):
        node_path.append(node)
        # node processing succeed 
        if node not in processed_nodes:
            processed_nodes.add(node)
            logger.debug("{}::{}: processed ({})".format(callback.__name__, node.get_name(), len(processed_nodes)))
        if node in stashed_nodes:
            stashed_nodes.remove(node)
            # logger.debug("{}::{}: unstashed ({})".format(callback.__name__, node.get_name(), len(stashed_nodes)))
        # put the stached node from that group first
        # if has next, walkthrough them (support options)
        # if len(stashed_nodes)>1:
        if not recursive:
            reorder_node_list(stashed_nodes, node.group)
        if isinstance(node, (TriccNodeActivityStart, TriccNodeMainStart)):
            if recursive:
                for gp in node.activity.groups:
                    walktrhough_tricc_node_processed_stached(gp, callback, processed_nodes, stashed_nodes, path_len,
                                                        recursive, warn = warn, node_path = node_path.copy(), **kwargs)
                for c in node.activity.calculates:
                    walktrhough_tricc_node_processed_stached(c, callback, processed_nodes, stashed_nodes, path_len,
                                                    recursive, warn = warn,node_path = node_path.copy(),**kwargs)
            else:
                stashed_nodes += node.activity.calculates 
                stashed_nodes += node.activity.groups
        if isinstance(node, TriccNodeActivity):
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
                    stashed_nodes.insert_at_bottom(node.root)
                    # if node.calculates:
                    #     stashed_nodes += node.calculates
                    # for gp in node.groups:
                    #     stashed_nodes.add(gp)
                    # #    stashed_nodes.insert(0,gp)
                return
        elif isinstance(node, TriccNodeActivityEnd):
            for next_node in node.activity.next_nodes:
                if next_node not in stashed_nodes:
                    #stashed_nodes.insert(0,next_node)
                    if recursive:
                        walktrhough_tricc_node_processed_stached(next_node, callback, processed_nodes, stashed_nodes, path_len,
                                                         recursive, warn = warn,node_path = node_path.copy(),**kwargs)
                    else:
                        stashed_nodes.insert_at_bottom(next_node)
        elif issubclass(node.__class__, TriccNodeSelect):
            for option in node.options.values():
                option.path_len = max(path_len,  option.path_len)
                callback(option, processed_nodes=processed_nodes, stashed_nodes=stashed_nodes, warn = warn, node_path=node_path,**kwargs)    
                if option not in processed_nodes:
                    processed_nodes.add(option)
                    logger.debug(
                        "{}::{}: processed ({})".format(callback.__name__, option.get_name(), len(processed_nodes)))
                walkthrough_tricc_option(node, callback, processed_nodes, stashed_nodes, path_len + 1, recursive,
                                         warn = warn,node_path = node_path, **kwargs)
        if hasattr(node, 'next_nodes') and len(node.next_nodes) > 0:
            walkthrough_tricc_next_nodes(node, callback, processed_nodes, stashed_nodes, path_len + 1, recursive,
                                             warn = warn,node_path = node_path,**kwargs)
    else:
        if node not in processed_nodes and node not in stashed_nodes:
            if node not in stashed_nodes:
                stashed_nodes.insert_at_bottom(node)
                logger.debug("{}::{}: stashed({})".format(callback.__name__, node.get_name(), len(stashed_nodes)))


def walkthrough_tricc_next_nodes(node, callback, processed_nodes, stashed_nodes, path_len, recursive, warn = False, node_path = [], **kwargs):
    if not recursive:
        for next_node in node.next_nodes:
            if next_node not in stashed_nodes:
                stashed_nodes.insert_at_bottom(next_node)
    else:
        list_next = set(node.next_nodes)
        for next_node in list_next:
            if not isinstance(node, (TriccNodeActivityEnd, TriccNodeEnd)):
                if next_node not in processed_nodes:
                    walktrhough_tricc_node_processed_stached(next_node, callback, processed_nodes, stashed_nodes,
                                                        path_len + 1,recursive, warn = warn,node_path = node_path.copy(), **kwargs)
            else:
                logger.error(
                    "{}::end node of {} has a next node".format(callback.__name__, node.activity.get_name()))
                exit()


def walkthrough_tricc_option(node, callback, processed_nodes, stashed_nodes, path_len, recursive, warn = False,node_path = [], **kwargs):
    if not recursive:
        for option in node.options.values():
            if hasattr(option, 'next_nodes') and len(option.next_nodes) > 0:
                for next_node in option.next_nodes:
                    if next_node not in stashed_nodes:
                        stashed_nodes.insert_at_bottom(next_node)
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
        node.group.instance if node.group is not None else node.activityinstance ,
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
            logger.debug("{}:: {}: unstashed for processing ({})".format(callback.__name__, s_node.__class__, 
                                                                        get_data_for_log(s_node),
                                                                        len(stashed_nodes)))
            warn = loop_count ==  (10 * len(stashed_nodes   )-1)
            walktrhough_tricc_node_processed_stached(s_node, callback, processed_nodes, stashed_nodes, path_len,
                                                     recursive, warn= warn, **kwargs)


# check if the all the prev nodes are processed
def is_ready_to_process(in_node, processed_nodes, strict=True, local = False):
    if isinstance(in_node, TriccNodeSelectOption):
        node = in_node.select
    elif isinstance(in_node, TriccNodeActivityStart):
        if local:
            # an activitiy start iss always processable locally
            return True
        node = in_node.activity
    else:
        node = in_node
    if hasattr(node, 'prev_nodes'):
        # ensure the  previous node of the select are processed, not the option prev nodes
        for prev_node in node.prev_nodes:
            if isinstance(prev_node, TriccNodeActivity):
                if not local:
                    # other activity dont affect local evaluation
                    activity_end_nodes = prev_node.get_end_nodes()
                    if len(activity_end_nodes) == 0:
                        
                        logger.error("is_ready_to_process:failed: endless activity {0} before {0}".format(prev_node.get_name(),
                                                                                                    node.get_name()))
                        return False
                    for end_node in activity_end_nodes:
                        if end_node not in processed_nodes:
                            logger.debug("is_ready_to_process:failed:via_end: {} - {} > {} {}:{}".format(
                                get_data_for_log(prev_node),
                                end_node.get_name(),
                                node.__class__, node.get_name(), node.instance))
                            return False
            elif prev_node not in processed_nodes and (not local or prev_node.activity == node.activity):
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
        if strict:
            return is_rhombus_ready_to_process(node, processed_nodes, local)
        else:
            return True
    else:
        return True


def print_trace(node, prev_node, processed_nodes, stashed_nodes, history = []):
    
    if node != prev_node:
        if node in processed_nodes:
            logger.warning("print trace :: node {}  was the last not processed ({})".format(
                    get_data_for_log(prev_node), node.id, ">".join(history)))
            processed_nodes.add(prev_node)
            return False
        elif node in history:
            logger.error("print trace :: CYCLE node {} found in history ({})".format(
                get_data_for_log(prev_node), ">".join(history)))
            exit()
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
    if callback(node, next_node, processed_nodes, stashed_nodes):
        history.append(node)
        if isinstance(in_node, TriccNodeActivity):
            prev_nodes = set(in_node.get_end_nodes())
            for prev in prev_nodes:
                reverse_walkthrough(prev, next_node, callback, processed_nodes, stashed_nodes, history)
        if hasattr(node, 'prev_nodes'):
            if node.prev_nodes:
                for prev in node.prev_nodes:
                    reverse_walkthrough(prev, node, callback, processed_nodes, stashed_nodes, history)
            elif node in node.activity.calculates:
                reverse_walkthrough(prev, node.activity.root, callback, processed_nodes, stashed_nodes, history)

        if issubclass(node.__class__, TriccRhombusMixIn):
            if isinstance(node.reference, list):
                for ref in node.reference:
                    reverse_walkthrough(ref, node, callback, processed_nodes, stashed_nodes, history)


def is_rhombus_ready_to_process(node, processed_nodes, local = False):
    if issubclass(node.__class__, TriccRhombusMixIn):
        if isinstance(node.reference, str):
            logger.debug(f"Node {node.__class__}::{node.get_name()} as still a reference to string: {node.reference}")
            return False  # calculate not yet processed
        else:
            references = node.get_references() or []
            for ref in references:
                if issubclass(ref.__class__, TriccNodeBaseModel) and ref not in processed_nodes and (not local or ref.activity == node.activity):
                    logger.debug(f"Node {node.__class__}::{node.get_name()} as one of its reference {ref.__class__}::{ref.get_name()} not processed")
                    return False
                elif issubclass(ref.__class__, str):
                    logger.debug(f"Node {node.__class__}::{node.get_name()} as one of its reference as string: {ref}")
    return True


def get_prev_node_by_name(processed_nodes, name, node):
    filtered = list(filter(lambda p_node: hasattr(p_node,'name') and p_node.name == name and p_node.instance == node.instance and p_node.path_len <= node.path_len, processed_nodes))
    if len(filtered) == 0:
        filtered = list(filter(lambda p_node: hasattr(p_node, 'name') and p_node.name == name, processed_nodes))
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
        if loop_count>MIN_LOOP_COUNT:
            if set(stashed_nodes) == set(prev_stashed_nodes) and len(processed_nodes) == len_prev_processed_nodes:
                loop_count += 1
                if loop_count > max(MIN_LOOP_COUNT, 10 * len(prev_stashed_nodes) + 1):
                    logger.error("Stashed node list was unchanged: loop likely or a cyclic redundancy")
                    waited, looped =  get_all_dependant(stashed_nodes, stashed_nodes, processed_nodes)               
                    logger.debug(f"{len(looped)} nodes waiting stashed nodes")
                    logger.debug(f"{len(waited)} nodes waited but not in stashed nodes")
                    for es_node in cur_stashed_nodes:
                        
                        logger.error("Stashed node {}:{}|{} {}:{}".format(
                                                                    es_node.group.get_name() if es_node.group is not None else es_node.activity.get_name() ,
                                                                    es_node.group.instance if es_node.group is not None else es_node.activityinstance ,
                                                                    es_node.__class__, 
                                                                    es_node.get_name(), es_node.instance))
                        #reverse_walkthrough(es_node, es_node, print_trace, processed_nodes, stashed_nodes)
                    if len(stashed_nodes) == len(prev_stashed_nodes):
                        exit()
        #else:
        #    loop_count += 1
    else:
        loop_count = 0
    return loop_count

        
def get_all_dependant(loop, stashed_nodes, processed_nodes, depth=0, waited=[] , looped=[]):
    
    logger.error("LOOP detected")
    for n in loop:
        dependant = set()
        i=0
        logger.error(f"{i}: {n.__class__}::{n.get_name()}")
        i += 1
        if hasattr(n, 'prev_nodes') and n.prev_nodes:
            dependant =  dependant | n.prev_nodes
        if hasattr(n, 'get_references'):
            dependant =  dependant | (n.get_references() or set())
        if not isinstance(dependant, list):
            pass
        for d in dependant:
            if isinstance(d, TriccNodeSelectOption):
                d = d.select
            if d not in waited and d not in looped:
                if d  not in processed_nodes:
                    if d not in stashed_nodes:
                        waited.append(d)
                    else :
                        looped.append(d)
    if depth < MAX_DRILL:
        return get_all_dependant(waited, stashed_nodes, processed_nodes, depth+1, waited , looped)

    return waited, looped


MAX_DRILL = 1

# Set the source next node to target and clean  next nodes of replace node
def set_prev_next_node(source_node, target_node, replaced_node=None, edge_only = False, activity=None):
    activity = activity or source_node.activity
    source_id, source_node = get_node_from_id(activity, source_node, edge_only)
    target_id, target_node = get_node_from_id(activity, target_node, edge_only)
    # if it is end node, attached it to the activity/page
    if not edge_only:
        set_prev_node(source_node, target_node, replaced_node, edge_only)
        set_next_node(source_node, target_node, replaced_node, edge_only)
         
    if not any([(e.source == source_id) and ( e.target == target_id) for e in activity.edges]):
        activity.edges.append(TriccEdge(id = generate_id(), source = source_id, target = target_id))


    
    
def set_next_node(source_node, target_node, replaced_node=None, edge_only = False, activity=None):
    activity = activity or source_node.activity
    if not edge_only:  
        if replaced_node is not None and hasattr(source_node, 'path') and replaced_node == source_node.path:
            source_node.path = target_node
        if replaced_node is not None and hasattr(source_node, 'next_nodes') and replaced_node in source_node.next_nodes:
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
    next_edges = [ e for e in activity.edges if replaced_node and (e.target == replaced_node.id or e.target == replaced_node)]
    if len(next_edges)==0:
        for e  in next_edges:
            e.target = target_node.id

# Set the target_node prev node to source and clean prev nodes of replace_node
def set_prev_node(source_node, target_node, replaced_node=None, edge_only = False, activity=None):
    activity = activity or source_node.activity
    # update the prev node of the target not if not an end node
    # update directly the prev node of the target
    if replaced_node is not None and hasattr(target_node, 'path') and replaced_node == target_node.path:
        target_node.path = source_node
    if replaced_node is not None and hasattr(target_node, 'prev_nodes') and replaced_node in target_node.prev_nodes:
        target_node.prev_nodes.remove(replaced_node)
        if hasattr(replaced_node, 'next_nodes') and source_node in replaced_node.next_nodes:
            replaced_node.next_nodes.remove(source_node)
    #if replaced_node is not None and hasattr(source_node, 'prev_nodes') and replaced_node in source_node.prev_nodes:
    #    source_node.prev_nodes.remove(replaced_node)
    if source_node not in target_node.prev_nodes:
        target_node.prev_nodes.add(source_node)
        

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
    
#FIXME should work with OrderedSet
def reorder_node_list(list_node, group):
    if len(list_node)>1:
        list_out = []
        list_out_group = []
        list_out_other = []
        
        
        for l_node in list_node:
            group_id = l_node.group.id if hasattr(l_node, 'group') and l_node.group is not None else None
            if group is not None and group.id == group_id:
                list_out.append(l_node)
            elif hasattr(group, 'group') and group.group is not None and group.group.id == group_id:
                list_out_group.append(l_node)
            else:
                list_out_other.append(l_node)

        list_node = []
        if len(list_out)>0:
            list_node.extend(list_out)
        if len(list_out_group)>0:
            list_node.extend(list_out_group)
        if len(list_out_other)>0:
            list_node.extend(list_out_other)
            
        logger.debug("reorder list init len: {}, group : {} group.group: {} other: {}".format(len(list_node), len(list_out), len(list_out_group), len(list_out_other)))

def loop_info(loop, **kwargs):
    logger.error("LOOP detected")
    for n in loop:
        i=0
        logger.error(f"{i}: {n.__class__}::{n.get_name()}")
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
    