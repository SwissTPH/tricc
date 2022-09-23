#FIXME, romhbus should not be a next node of the previous but a next node of the ref
# and then nodes before the rombus should be "linked" node after the rombhus but in a way that 
# won't impact the relevance/calcualteg

import os
import html2text
from tricc.converters.utils import clean_name
from gettext import gettext as _
from tricc.models import *
from tricc.parsers.xml import  get_edges_list, get_mxcell, get_mxcell_parent_list, get_odk_type,  get_odk_type_list

import base64

TRICC_YES_LABEL = ['yes', "oui"]
TRICC_NO_LABEL = ['no', "non"]
TRICC_FOLOW_LABEL = ['folow', "suivre"]
NO_LABEL = "NO_LABEL"
TRICC_LIST_NAME = 'list_{0}'
import logging
logger = logging.getLogger("default")

def create_activity(diagram):
    id = diagram.attrib.get('id')    
    root = create_root_node(diagram)
    name = diagram.attrib.get('name')

    if root is not None:
        activity = TriccNodeActivity(
            root=root,
            name=id,
            id=id,       
            label=name
        )
        # add the group on the root node
        root.group = activity
        activity.group = activity
        edges = get_edges(diagram)
        nodes = get_nodes(diagram, activity)
        groups  = get_groups(diagram, nodes, activity)
        if groups and len(groups)>0:
            activity.groups = groups        
        if nodes and len(nodes)>0:
            activity.nodes = nodes
            
        if edges and len(edges)>0:
            activity.edges = edges
        process_edges(diagram, activity, nodes)

        # link back the activity
        activity.root.activity = activity
        return activity
    else:
        logger.warning("root not found for page {0}".format(name))
            
def process_edges(diagram, activity, nodes):
    for edge in activity.edges:
        # enrich nodes
        if edge.target not in nodes :
            activity.unused_edges.append(edge)
        elif edge.source not in nodes and edge.target in nodes:
            node_used = enrich_node(diagram, edge, nodes[edge.target])
            if node_used is None:
                activity.unused_edges.append(edge)
        # modify edge for selectyesNo
        if edge.source in nodes and isinstance(nodes[edge.source], TriccNodeSelectYesNo):
            if edge.value is None:
                logger.error("yesNo {} node with labelless edges".format(nodes[edge.source].get_name()))
                exit()
            label  = edge.value.strip().lower()
            yes_option = None
            no_option = None
            for option in nodes[edge.source].options.values():
                if option.name == '1':
                    yes_option = option
                else:
                    no_option = option
            if label in TRICC_FOLOW_LABEL:
                pass
            elif label in TRICC_YES_LABEL:
                edge.source = yes_option.id
            elif label in TRICC_NO_LABEL:
                edge.source = no_option.id
            else:
                logger.warning("edge {0} is coming from select {1}".format(edge.id, nodes[edge.source].get_name()))
        # create calculate based on edges label
        elif edge.value is not None:
            calc = None
            error = None
            # manage comment
            label  = edge.value.strip()
            for op in [ '>=', '<=', '==','=','>','<']:
                if op in label:
                    # insert rhombus
                    calc = TriccNodeRhombus(
                        id = generate_id(),
                        reference = [nodes[edge.source]],
                        activity = nodes[edge.source].activity,
                        group = nodes[edge.source].group,
                        label= label
                    )
                    break
            if calc is None:
                if label.lower() in TRICC_FOLOW_LABEL:
                    pass
                elif label.lower() in TRICC_YES_LABEL:
                    if  not isinstance(nodes[edge.source], TriccNodeRhombus):
                        error = "Yes not after a rhombus"
                elif label.lower() in TRICC_NO_LABEL:
                    # insert Negate
                    if not isinstance(nodes[edge.source], TriccNodeExclusive) and not isinstance(nodes[edge.target], TriccNodeExclusive):
                        calc = TriccNodeExclusive(
                            id = generate_id(),
                            activity = nodes[edge.target].activity,
                            group = nodes[edge.target].group                    
                        )
                    else:
                        error = "No after or before a exclusice/negate node"
                else:        
                    error = "label don't match with test, no "
            if calc is not None:
                nodes[calc.id] = calc
                # add edge between calc and 
                activity.edges.append(TriccEdge(
                    id = generate_id(),
                    source = calc.id,
                    target = edge.target
                ))
                edge.target = calc.id
            elif error is not None:
                logger.warning("Edge between {0} and {1} with label '{2}' could not be interpreted: {3}".format(
                    nodes[edge.source].get_name(),
                    nodes[edge.target].get_name(),
                    label,
                    error
                ))
    
                         
   

# the soup.text strips off the html formatting also
def remove_html(string):
    text = html2text.html2text(string) # retrive pure text from html
    text = text.strip('\n') # get rid of empty lines at the end (and beginning)
    text = text.split('\n') # split string into a list at new lines
    text = '\n'.join([i.strip(' ') for i in text if i]) # in each element in that list strip empty space (at the end of line) 
    # and delete empty lines
    return text

def get_nodes(diagram, activity):
    nodes = {}
    add_note_nodes(nodes, diagram, activity)  
    add_calculate_nodes(nodes, diagram, activity)
    add_select_nodes(nodes, diagram, activity)
    add_input_nodes(nodes, diagram, activity)
    add_link_nodes(nodes, diagram, activity)
    get_hybride_node(nodes, diagram, activity)
    for node in nodes.values():
        # clean name
        if hasattr(node, 'name') and node.name is not None and node.name.endswith('_'):
            node.name = node.name + node.id
    return nodes


    
    
def create_root_node(diagram):
    elm = get_odk_type(diagram, 'object', TriccExtendedNodeType.start)
    if elm is not None:
        return  TriccNodeMainStart(
            id = elm.attrib.get('id'),
            parent= elm.attrib.get('parent'),
            name = 'ms'+diagram.attrib.get('id'),
            label = elm.attrib.get('label')
        )
    elm = get_odk_type(diagram, 'object', TriccExtendedNodeType.activity_start)
    if elm is not None:
        return  TriccNodeActivityStart(
            id = elm.attrib.get('id'),
            parent= elm.attrib.get('parent'),
            name = 'ma'+diagram.attrib.get('id'),
            label = diagram.attrib.get('name')
        )



# converter XML item to object 



def set_additional_attributes(attribute_names, elm, node):
    if not isinstance(attribute_names, list):
        attribute_names = [attribute_names]
    for attributename in attribute_names:
        attribute =  elm.attrib.get(attributename)
        if attribute is not None:
            # input expression can add a condition to either relevance (display) or calculate expression
            attribute = [attribute] if attributename == 'expression_inputs' else attribute
            setattr(node, attributename, attribute)        

def add_note_nodes(nodes, diagram, group):
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccNodeType.note)
    add_tricc_nodes(nodes, TriccNodeNote, list, group, ['relevance'])
    

def add_select_nodes(nodes, diagram, group=None):
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccNodeType.select_one)
    add_tricc_select_nodes(diagram, nodes, TriccNodeSelectOne, list, group, ['required','save','filter','constraint','constraint_message'])
    #list = get_odk_type_list(diagram, 'UserObject', TriccExtendedNodeType.select_yesno)
    #add_tricc_nodes(nodes, TriccNodeSelectYesNo, list, ['constraint','save','constraint_message','required'])
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccNodeType.select_multiple)
    add_tricc_select_nodes(diagram, nodes, TriccNodeSelectMultiple, list, group, ['required','save','filter','constraint','constraint_message'])

def add_input_nodes(nodes, diagram, group= None):
    list = get_odk_type_list(diagram, ['object','UserObject'], TriccNodeType.decimal)
    add_tricc_nodes(nodes, TriccNodeDecimal, list, group, ['min','max', 'constraint','save','constraint_message','required'])
    list = get_odk_type_list(diagram, ['object','UserObject'], TriccNodeType.integer)
    add_tricc_nodes(nodes, TriccNodeInteger, list, group, ['min','max', 'constraint','save','constraint_message','required'])
    list = get_odk_type_list(diagram, ['object','UserObject'], TriccNodeType.text)
    add_tricc_nodes(nodes, TriccNodeText, list, group, ['constraint','save','constraint_message','required'])

def add_calculate_nodes(nodes, diagram, group=None):
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccNodeType.calculate)
    add_tricc_nodes(nodes, TriccNodeCalculate, list, group, ['save','expression','help', 'hint'])
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccExtendedNodeType.add)
    add_tricc_nodes(nodes, TriccNodeAdd, list, group, ['save','expression'])
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccExtendedNodeType.count)
    add_tricc_nodes(nodes, TriccNodeCount, list, group, ['save','expression'])
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccExtendedNodeType.rhombus)
    add_tricc_nodes(nodes, TriccNodeRhombus, list, group, ['save','expression'],['reference'])
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccExtendedNodeType.exclusive)
    add_tricc_base_node(nodes, TriccNodeExclusive, list, group)
 
def get_hybride_node(nodes, diagram, group=None):
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccExtendedNodeType.not_available)
    add_tricc_hybrid_select_nodes(nodes, TriccNodeSelectNotAvailable, list, group, [])
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccExtendedNodeType.select_yesno)
    add_tricc_hybrid_select_nodes(nodes, TriccNodeSelectYesNo, list, group, ['required','save','filter','constraint','constraint_message'])
    #to do generate option
   
def add_link_nodes(nodes, diagram, group=None):
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccExtendedNodeType.link_out)
    add_tricc_nodes(nodes, TriccNodeLinkOut, list, group, [], ['reference'])
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccExtendedNodeType.link_in)
    add_tricc_nodes(nodes, TriccNodeLinkIn, list, group)
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccExtendedNodeType.goto)
    add_tricc_nodes(nodes, TriccNodeGoTo, list, group,['instance'],['link'])
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccExtendedNodeType.activity_end)
    add_tricc_base_node(nodes, TriccNodeActivityEnd, list, group)
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccExtendedNodeType.end)
    add_tricc_base_node(nodes, TriccNodeEnd, list, group)

 
    
def get_select_options(diagram, select_node, nodes):
    options = {}
    i = 0
    list = get_mxcell_parent_list(diagram, select_node.id, TriccExtendedNodeType.select_option)
    options_name_list = []
    for elm in list:
        name = elm.attrib.get('name')
        if name in options_name_list and not name.endswith('_'):
            logger.error("Select question {0} have twice the option name {1}"\
                .format(select_node.get_name() ,name))
        else:
            options_name_list.append(name)
        id=elm.attrib.get('id')
        option = TriccNodeSelectOption(
            id = id,
            label = elm.attrib.get('label'),
            name = name,
            select = select_node,
            list_name = select_node.list_name,
            group = select_node.group
        )
        set_additional_attributes(['save'], elm, option)
        options[i]=option
        nodes[id]=option
        i += 1
    if len(list)== 0:
        logger.error("select {} does not have any option".format(select_node.label))
    else:
        return options



def process_calculate(node,processed_nodes, stashed_nodes, calculates, used_calculates,  **kwargs ):
     # used_calculates dict[name, Dict[id, node]]
     # processed_nodes Dict[id, node]
     # calculates  dict[name, Dict[id, node]]
    if node not in processed_nodes:
                    # generate condition

        if is_ready_to_process(node, processed_nodes, stashed_nodes, False,False) and process_calculate_version_requirement(node, calculates, used_calculates,processed_nodes):
            if is_rhombus_ready_to_process(node,processed_nodes):
                generate_calculates(node,calculates, used_calculates,processed_nodes)
                if issubclass(node.__class__, (TriccNodeDisplayCalculateBase )) and node.name is not None:
                    # generate the calc node version by looking in the processed calculate
                    add_calculate(calculates,node)                    # get max version existing

                    #update_calc_version(calculates,node.name)
                    last_version = get_max_named_version(calculates,node.name)
                    # get max version used 
                    last_used_version = get_max_named_version(used_calculates, node.name)
                    # merge is there is unused version ->
                    # current node not yet in the list so 1 item is enough
                    node.version = last_version + 1
                    if last_version > last_used_version:

                    #if last_version > 0:
                        
                        node_to_delete = merge_calculate(node, calculates[node.name], last_used_version)
                        if node_to_delete is not None:
                            for d_node in node_to_delete:
                                del calculates[d_node.name][d_node.id]
                                node_clean_name = get_calculate_cleaned_name(d_node.name)
                                if node_clean_name in used_calculates:
                                    if d_node.id in used_calculates[node_clean_name]:
                                        logger.error("node {} used but deleted".format(d_node.get_name()))
                        #                del used_calculates[node.name][node.id]
                                if d_node.id in d_node.activity.nodes:
                                    # mostly for end nodes
                                    del d_node.activity.nodes[d_node.id]
                                if  d_node  in stashed_nodes:
                                    logger.error("node {} not porcessed but deleted".format(d_node.get_name()))
                        #            stashed_nodes.remove(node)
                        if last_used_version > 0 :
                            # chaining the calculate, only one way FIXME it can create issue
                            last_used_calc = list(filter(lambda x: x.version == last_used_version , used_calculates[node.name].values))[0]
                            if last_used_calc is not None:
                                set_prev_next_node(last_used_calc,node)
                                last_used_calc.name += VERSION_SEPARATOR + str(last_used_calc.version)
                            else:
                                logger.error("process_calculate_calculate: last used calc not found for {}".format(node.get_name()))
                                exit(-2)
                    
                    else:
                        node.version = 0
                
                if hasattr(node, 'next_nodes'):
                    node.next_nodes=reorder_node_list(node.next_nodes, node.group)
                # it seems that the "next nodes" don't take newly created node
                #if calc_node is not None:
                #    processed_nodes[calc_node.id]=calc_node
                #    if calc_node.name not in calculates:
                #        calculates[calc_node.name]= {}
                #    calculates[calc_node.name][calc_node.id]=calc_node
                return True
        # not ready to process or already processed

    return False

def update_calc_version(calculates,name):
    if len(calculates[name])>1:
        ordered_list = sorted(list(calculates[name].values()), key=lambda x:x.path_len)
        i = 1
        for elm in ordered_list:
            elm.version=i
            i+=1
        

def get_max_named_version(calculates,name):
    max = 0
    if name  in calculates:
        for id, node in calculates[name].items():
            if node.version > max:
                max = node.version
    return max
        
    
def generate_calculates(node,calculates, used_calculates,processed_nodes):
    list_calc = []
    ## add select calcualte
    if issubclass(node.__class__, TriccNodeCalculateBase):
        if  isinstance(node,TriccNodeRhombus):
            if len(node.reference)==1 and issubclass(node.reference[0].__class__, TriccNodeSelect):
                count_id = generate_id()
                count_name = "cnt_"+count_id
                count_node = TriccNodeCount(
                    id = count_id,
                    group = node.group,
                    activity = node.activity,
                    label = "ref: "+node.get_name(),
                    name = count_name,
                    path_len=node.path_len
                )
                list_calc.append(count_node)
                
                set_prev_next_node(node.reference[0],count_node)
                node.path_len+=1
                node.reference[0] =  count_node
                processed_nodes.append(count_node)
                add_calculate(calculates, count_node)
                add_used_calculate(node, count_node, calculates, used_calculates, processed_nodes)
            else:
                pass
            # generate rhombuse path 
            calc_id  = generate_id()
            calc_name = "path_"+calc_id
            calc_node = TriccNodeCalculate(
                        id =calc_id,
                        group = node.group,
                        activity = node.activity,
                        label = "path " + node.get_name(),
                        name = calc_name,
                        path_len = node.path_len
                    )
            node.path = calc_node
            list_nodes=[]
            for prev in node.prev_nodes:
                list_nodes.append(prev)
            for prev in list_nodes:
                set_prev_next_node(prev,calc_node, node)
            set_prev_next_node(calc_node, node)
            node.path_len +=1
            list_calc.append(calc_node)
            processed_nodes.append(calc_node)
            add_calculate(calculates, calc_node)
    for prev in node.prev_nodes:
        add_used_calculate(node, prev, calculates, used_calculates, processed_nodes)

            
                

    if hasattr(node, 'save') and node.save is not None and node.save != '':
        count_node = None
        
        if issubclass(node.__class__, TriccNodeSelect):
            count_id = generate_id()
            count_name = "cnt_"+count_id
            count_node = TriccNodeCount(
                id = count_id,
                group = node.group,
                activity = node.activity,
                label = "count SM: " +node.get_name(),
                path_len=node.path_len+1,
                name=count_name
            )
            add_calculate(calculates, count_node)
            list_calc.append(count_node)
            set_prev_next_node(node,count_node)
            processed_nodes.append(count_node)
            
        # get fragments type.name.icdcode
        save_fragments=node.save.split('.')
        if len(save_fragments)>1:
            calculate_name = "{0}.{1}".format(save_fragments[0], save_fragments[1])
        else:
            calculate_name = "{0}.{1}".format(save_fragments[0], node.name)
        logger.debug("generate_save_calculate:{} as {}".format(node.name if hasattr(node,'name') else node.id, calculate_name))
        calc_id = generate_id()
        calc_node = TriccNodeCalculate(
            name=calculate_name,
            id = calc_id,
            group = node.group,
            activity = node.activity,
            label =  "Save: " +node.get_name(),
            path_len=node.path_len+ (2 if count_node is not None else 1)
        )
        processed_nodes.append(calc_node)
        add_calculate(calculates, calc_node)       
        
        if count_node is not None:
            set_prev_next_node(count_node,calc_node)
            add_used_calculate(calc_node, count_node, calculates, used_calculates, processed_nodes)
        else:
            set_prev_next_node(node,calc_node)
        list_calc.append(calc_node)
        #add_save_calculate(calc_node, calculates, used_calculates,processed_nodes)
    return list_calc
        



def get_max_version(dict):
    max_version = None
    for id, sim_node in dict.items():
        if max_version is None or  max_version.version < sim_node.version :
            max_version = sim_node
    return max_version

last_unfound_ref = None
        
VERSION_SEPARATOR = '_v_'
#this function adds the reference if any 
def process_calculate_version_requirement(node, calculates,used_calculates,processed_nodes):
    if(process_reference(node, calculates,used_calculates,processed_nodes)):
        return False
    #if hasattr(node, 'prev_nodes'):
    #    for prev_node in node.prev_nodes:
    #        add_used_calculate(node, prev_node, calculates, used_calculates, processed_nodes)

        
    # update the used_calculates         
    return True

def add_calculate(calculates, calc_node):
    if issubclass(calc_node.__class__, TriccNodeDisplayCalculateBase):
        node_clean_name = get_calculate_cleaned_name(calc_node.name)
        if node_clean_name not in calculates:
            calculates[node_clean_name]= {}
        calculates[node_clean_name][calc_node.id] = calc_node

def process_reference(node,  calculates ,used_calculates,processed_nodes):
    #global last_unfound_ref
    reference = []
    if isinstance(node, (TriccNodeRhombus)):
        if isinstance(node.reference, str) :
            logger.debug("process_reference:{}: {} ".format(node.get_name(), node.reference))
            ref_list = node.reference.split(';')
            for ref in ref_list:
                last_found = get_prev_node_by_name(processed_nodes, ref, node)
                # ref is still a string here
                if last_found is None  or issubclass(last_found.__class__, TriccNodeCalculateBase):
                    if ref in calculates and len(calculates[ref])>0 :
                        # issue is that it can be further in another path
                        last_found = get_max_version(calculates[ref])
                if last_found is None:
                    logger.debug("reference {} not found for a calculate {}".format(ref, node.get_name()))
                    #if last_unfound_ref == node:
                    #    logger.warning("reference not found for a calculate twice in a row {}".format(node.get_name()))
                    #last_unfound_ref = node
                    return False
                else:
                    reference.append(last_found) 
                    last_found.next_nodes.append(node)
                    #set_prev_next_node(last_found, node)
                    # just to be safe even if it should be covered after
                    add_used_calculate(node, last_found, calculates, used_calculates, processed_nodes)

            node.reference = reference
        elif isinstance(node.reference,list):
            for ref in node.reference:
                add_calculate(calculates,ref )
                add_used_calculate(ref, node,calculates, used_calculates, processed_nodes)
        elif node.reference is None:
            logger.error("process_calculate_version_requirement:reference is None for {0} ".format(node.get_name()))
            exit()


def get_calculate_cleaned_name(name):
    index = name.rfind(VERSION_SEPARATOR)
     #remove the leading part with version 
    return name[:index] if index > 0 else name

#add_used_calculate(node, calc_node, calculates, used_calculates, processed_nodes)

def add_used_calculate(node, prev_node, calculates, used_calculates, processed_nodes):
    if issubclass(prev_node.__class__, TriccNodeDisplayCalculateBase):
        if prev_node in processed_nodes:
            # if not a verison, index will equal -1
            node_clean_name = get_calculate_cleaned_name(prev_node.name)
            if node_clean_name not in calculates :
                logger.debug("node {} refered before being processed".format(node.get_name()))
                return False
            max_version = get_max_version(calculates[node_clean_name])
            if node_clean_name not in used_calculates:
                used_calculates[node_clean_name] = {}
            #save the max version only once
            if max_version.id not in used_calculates[node_clean_name]:
                used_calculates[node_clean_name][max_version.id] = max_version
        else:
            logger.debug("process_calculate_version_requirement: failed for {0} , prev Node {1} ".format(node.get_name(), prev_node.get_name()))
    
    
        



def merge_calculate(node, calculates, from_version):
    #calcualtes list[ node]

    version = node.version
    node_to_delete = []
    for id, calc_node in calculates.items():
        # merge only if same name, version >= fromm version but < node version    
        if  node.odk_type == calc_node.odk_type :
            cur_version = calc_node.version
            if cur_version > from_version and  cur_version<version:
                logger.debug("merge_calculate:{} ".format(node.name if hasattr(node,'name') else node.id))
                # unlink the merged node in its next nodes
                # list node is used to not update calc_node.next_nodes in a loop
                list_nodes = []
                for next_node in calc_node.next_nodes:
                    list_nodes.append(next_node)
                for next_node in list_nodes:
                    set_prev_next_node(node, next_node, calc_node )
                # unlink the merged node in its prev nodes
                # list node is used to not update calc_node.prev_nodes in a loop
                list_nodes = []
                for prev_node in calc_node.prev_nodes:
                    list_nodes.append(prev_node)
                for prev_node in list_nodes:
                    set_prev_next_node(prev_node, node, calc_node )
                node_to_delete.append(calc_node)
        else:
            logger.error("two different type of calculate node share the same name {}".format(node.name))
    return node_to_delete
    

def enrich_node(diagram, edge, node):
    if edge.target == node.id:
        # get node and process type
        type, message = get_message(diagram, edge.source)
        if type is not None:
            if type in (TriccExtendedNodeType.start, TriccExtendedNodeType.activity_start):
                return True   
            elif hasattr(node, type):
                if message is not None:
                    setattr(node,type,message)
                    return True
            else:
                logger.warning("A attribute box of type {0} and value {1} is attached to an object not compatible {2}".format(type, message, node.get_name()))
        else:
            image = get_image(diagram, edge.source )
            if image:
                node.image=image
                return True

def add_tricc_hybrid_select_nodes(nodes, type, list, group, attributes):
    for elm in list:
        id = elm.attrib.get('id')
        label = elm.attrib.get('label')
        name = elm.attrib.get('name')
        if name is None:
            name = elm.attrib.get('id')
        node = type(
            id=id,
            parent=  elm.attrib.get('parent'),
            label = label if type != TriccNodeSelectNotAvailable else NO_LABEL,
            name = name,
            required=True,
            group =  group,
            activity = group,
            list_name = 'yes_no' if type == TriccNodeSelectYesNo else TRICC_LIST_NAME.format(id)
        )
        if type == TriccNodeSelectNotAvailable:
            node.options =   {0:TriccNodeSelectOption(
                id = generate_id(),
                name="1",
                label=label,
                select = node,
                group = group,
                list_name = node.list_name
            )}
        elif type == TriccNodeSelectYesNo:
            node.options =   {0:TriccNodeSelectOption(
                id = generate_id(),
                name="1",
                label=_("Yes"),
                select = node,
                group = group,
                list_name =  node.list_name
            ), 1:TriccNodeSelectOption(
                id = generate_id(),
                name="-1",
                label=_("No"),
                select = node,
                group = group,
                list_name =  node.list_name
            )}
            
        set_additional_attributes(attributes, elm, node)
        nodes[id]=node
    
def add_tricc_select_nodes(diagram, nodes, type, list, group, attributes):
    for elm in list:
        id = elm.attrib.get('id')
        node = type(
            id = id,
            parent= elm.attrib.get('parent'),
            label = elm.attrib.get('label'),
            name = elm.attrib.get('name'),
            required=True,
            group =  group,
            activity = group,
            list_name = TRICC_LIST_NAME.format(id)
        )
        node.options = get_select_options(diagram, node, nodes)
        set_additional_attributes(attributes, elm, node)
        
        nodes[id]=node
        


def add_tricc_nodes(nodes, type, list, group, attributes = [], mandatory_attributes = []):
        mandatory_attributes +=  ['label','name']
        add_tricc_base_node(nodes, type, list, group, attributes, mandatory_attributes)
            
            
def add_tricc_base_node(nodes, type, list, group, attributes = [], mandatory_attributes = []):   
    for elm in list:
        id = elm.attrib.get('id')
        parent= elm.attrib.get('parent')
        node = type(
            id = id,
            parent= parent,
            group = group,
            activity = group,
            **set_mandatory_attribute(elm, mandatory_attributes, group.name)
        )
        set_additional_attributes(attributes, elm, node)
        nodes[id]=node
    
def set_mandatory_attribute(elm, mandatory_attributes, groupname = None):
    param = {}
    for attributes in mandatory_attributes:
        attribute_value = elm.attrib.get(attributes)
        if attribute_value is None:
            if elm.attrib.get('label')is not None:
                display_name = elm.attrib.get('label')
            elif elm.attrib.get('name')is not None:
                display_name = elm.attrib.get('name')
            else:
                display_name = elm.attrib.get('id')
            logger.error("the attibute {} is mandatory but not found in {} within group {}".format(attributes, display_name, groupname if groupname is not None else ''))
            exit()
        if attributes == 'link':
            param[attributes] = clean_link(attribute_value)
        elif attributes in ('parent','id', 'source', 'target'):
            param[attributes]=attribute_value
        elif attribute_value is not None:
            param[attributes]=remove_html(attribute_value)
    return param

def clean_link(link):
    # link have the format "data:page/id,DiagramID"
    link_parts = link.split(',')
    if link_parts[0] == 'data:page/id' and len(link_parts)==2:
        return link_parts[1]
    
def get_groups(diagram, nodes, parent_group):
    groups = {}
    list=get_odk_type_list(diagram, 'object', TriccExtendedNodeType.page )
    for elm in list:
        add_group(elm, diagram, nodes, groups,parent_group)
    return groups

        
def add_group(elm, diagram, nodes, groups, parent_group):
    id = elm.attrib.get('id')
    if id not in groups:
        group = TriccGroup(
            name = clean_name(elm.attrib.get('name')),
            label = elm.attrib.get('label'),
            id = id,
            group = parent_group
        )
        # get elememt witn parent = id and odk_type defiend
        list_child = get_odk_type_list(diagram, ['object','UserObject'], odk_type=None, parent_id = id)
        add_group_to_child(group, diagram,list_child, nodes, groups, parent_group)
        if group is not None:
            groups[group.id] = group
        return group
        
def add_group_to_child(group, diagram,list_child, nodes, groups, parent_group):
    for child_elm in list_child:
        if child_elm.attrib.get('odk_type') == TriccExtendedNodeType.container_hint_media:
            list_sub_child = get_odk_type_list(diagram, ['object','UserObject'], odk_type=None, parent_id =child_elm.attrib.get('id') )
            add_group_to_child(group, diagram,list_sub_child, nodes, groups, parent_group )
        elif child_elm.attrib.get('odk_type') == TriccExtendedNodeType.page:
            child_group_id = child_elm.attrib.get('id')
            if not child_group_id  in groups:
                child_group = add_group(child_elm, diagram, nodes, groups, group)
            else:
                child_group = groups[child_group_id]
            child_group.group = group
        else:
            child_id=child_elm.attrib.get('id')
            if child_id is not None and child_id in nodes:
                nodes[child_id].group = group
        

def get_image(diagram, id, image_name = None ):
    elm = get_mxcell(diagram, id)
    if elm is not None:
        style=elm.attrib.get('style')
        if image_name is None:
            image_name = id
        file_name = add_image_from_style(style, image_name)
        if file_name is not None:
            return file_name

        
def add_image_from_style(style,image_name):
    image_attrib = None
    if style is not None and 'image=data:image/' in style:
        image_attrib = style.split('image=data:image/')
    if image_attrib is not None and len(image_attrib)==2:
        image_parts = image_attrib[1].split(',')
        if len(image_parts) == 2:
            payload = image_parts[1][:-1]
            file_name = "media/"+image_name+ '.' + image_parts[0]
            if not(os.path.isdir('media')): # check if it exists, because if it does, error will be raised 
                # (later change to make folder complaint to CHT)
                os.mkdir('media')
            with open(file_name , "wb") as fh:
                fh.write(base64.decodebytes(payload.encode('ascii'))) 
                return file_name

def get_contained_main_node(diagram, id):
    list = get_mxcell_parent_list(diagram, id, media_nodes)
    if isinstance(list, List) and len(list)>0:
        #use only the first one
        return list[0]
        
def get_message(diagram, id):
    elm = get_mxcell(diagram, id)
    if elm is not None:
        type = elm.attrib.get('odk_type')
        if type is not None:
            if type.endswith("-message"):
                type = type[:-8]
            return type, elm.attrib.get('label')
        #use only the first one
    return None, None

def get_edges( diagram):
    edges = []
    list = get_edges_list(diagram)
    for elm in list:
        id = elm.attrib.get('id')
        edge = TriccEdge(
            id = id,
            **set_mandatory_attribute(elm, ['source' , 'parent', 'target'], diagram.attrib.get('name'))
        )
        set_additional_attributes(['value'], elm, edge)
        if edge.value is not None:
            edge.value = remove_html(edge.value)
        edges.append(edge)
    return edges
        
