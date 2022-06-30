#FIXME, romhbus should not be a next node of the previous but a next node of the ref
# and then nodes before the rombus should be "linked" node after the rombhus but in a way that 
# won't impact the relevance/calcualteg

import os
from uuid import uuid4
import html2text
from tricc.converters.utils import clean_name
from tricc.models import *
from tricc.parsers.xml import  get_edges_list, get_mxcell, get_mxcell_parent_list, get_odk_type,  get_odk_type_list
import logging
import base64

from tricc.services.utils import set_prev_node

NO_LABEL = "NO_LABEL"

logger = logging.getLogger("default")

def create_activity(diagram):
    
    root = create_root_node(diagram)
    name = diagram.attrib.get('name')
    id = diagram.attrib.get('id')
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
            activity.edges_copy = edges.copy()
        for edge in edges:
            if edge.source not in nodes and edge.target in nodes:
                node_used = enrich_node(diagram, edge, nodes[edge.target])
                if node_used is not None:
                    edges.remove(edge)

        # link back the activity
        activity.root.activity = activity
        return activity
    else:
        logger.warning("root not found for page {0}".format(name))
            
        
   

# the soup.text strips off the html formatting also
def remove_html(string):
    text = html2text.html2text(string) # retrive pure text from html
    text = text.strip('\n') # get rid of empty lines at the end (and beginning)
    text = text.split('\n') # split string into a list at new lines
    text = '\n'.join([i.strip(' ') for i in text if i]) # in each element in that list strip empty space (at the end of line) 
    # and delete empty lines
    return text

def get_nodes(diagram, group):
    nodes = {}
    add_note_nodes(nodes, diagram, group)  
    add_calculate_nodes(nodes, diagram, group)
    add_select_nodes(nodes, diagram, group)
    add_input_nodes(nodes, diagram, group)
    add_link_nodes(nodes, diagram, group)
    get_hybride_node(nodes, diagram, group)
    return nodes


    
    
def create_root_node(diagram):
    elm = get_odk_type(diagram, 'object', TriccExtendedNodeType.start)
    if elm is not None:
        return  TriccNodeMainStart(
            id = elm.attrib.get('id'),
            parent= elm.attrib.get('parent'),
            name = diagram.attrib.get('name'),
        )
    elm = get_odk_type(diagram, 'object', TriccExtendedNodeType.activity_start)
    if elm is not None:
        return  TriccNodeActivityStart(
            id = elm.attrib.get('id'),
            parent= elm.attrib.get('parent'),
            name = diagram.attrib.get('name')
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
    add_tricc_nodes(nodes, TriccNodeCalculate, list, group, ['save','expression'])
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
    add_tricc_nodes(nodes, TriccNodeGoTo, list, group,[],['link'])
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
        if name in options_name_list:
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



def add_save_calculate(node, calculates, used_calculates,processed_nodes, stashed_nodes ):
     # used_calculates dict[name, Dict[id, node]]
     # processed_nodes Dict[id, node]
     # calculates  dict[name, Dict[id, node]]
    if hasattr(node,'prev_nodes') and is_ready_to_process(node, processed_nodes) and node.id not in processed_nodes:
        if not process_calculate_version_requirement(node, calculates, used_calculates,processed_nodes):
            # missing save stashed it for later
            logger.warning("add_save_calculate:stashed:{}".format(node.get_name()))
            stashed_nodes[node.id] = node
            return False
        generate_save_calculate(node, calculates)
        if isinstance(node, (TriccNodeCount, TriccNodeAdd, TriccNodeCalculate )) and node.name is not None:
            # generate the calc node version by looking in the processed calculate
            if node.name in calculates:
                if node.id in calculates[node.name]:
                    node.version = get_max_used_version(calculates,node.name) + 1
                # check if the calculate is used, if not merge it with the previous versions
                from_version = get_max_used_version(used_calculates, node.name)
                if len(calculates[node.name])>1:
                    merge_calculate(node, calculates[node.name], from_version)

                if from_version > 0:
                    update_last_calculate_name(calculates[node.name], from_version-1 )
            else:
                calculates[node.name]= {}
            calculates[node.name][node.id]=node
        processed_nodes[node.id] = node
        group_next_nodes(node)
        return True
    else:
        return False


def get_max_used_version(used_calculates,name):
    max = 0
    if name  in used_calculates:
        for id, node in used_calculates[name].items():
            if node.version > max:
                max = node.version
    return max

def update_last_calculate_name(calculates, version ):
    for id, node in calculates.items():
        if node.version == version:
            node.name += VERSION_SEPARATOR + str(version)
    
def generate_save_calculate(node, calculates):
    if hasattr(node, 'save') and node.save is not None:
        logger.debug("generate_save_calculate:{}".format(node.name if hasattr(node,'name') else node.id))
        # get fragments type.name.icdcode
        save_fragments=node.save.split('.')
        if len(save_fragments)>1:
            calculate_name = "{0}.{1}".format(save_fragments[0], save_fragments[1])
        else:
            calculate_name = "{0}.{1}".format(save_fragments[0], node.name)
        calc_node = TriccNodeCalculate(
            name=calculate_name,
            id = generate_id(),
            group = node.group
        )
        calc_node.prev_nodes.append(node)
        node.next_nodes.append(calc_node)
        if calculate_name not in calculates:
            calculates[calculate_name] = {}
        calculates[calculate_name][calc_node.id]=calc_node
        #add_save_calculate(calc_node, calculates, used_calculates,processed_nodes)
        
def generate_id():
    return str(uuid4())


def get_max_version(dict):
    max_version = None
    for id, sim_node in dict.items():
        if max_version is None or  max_version.version < sim_node.version :
            max_version = sim_node
    return max_version

# check if the all the prev nodes are processed
def is_ready_to_process(node, processed_nodes):
    if isinstance(node, TriccNodeSelectOption):
            node = node.select
    if hasattr(node, 'prev_nodes'):
        # ensure the the previous node of the select are processed, not the option prev nodes
        for prev_node in node.prev_nodes:
            if isinstance(prev_node,TriccNodeActivity):
                if len(prev_node.end_prev_nodes)==0 and len(prev_node.activity_end_prev_nodes)==0:
                    return False
                for end_node in prev_node.end_prev_nodes:
                    if end_node.id not in processed_nodes:
                        return False
                for activity_end_node in prev_node.activity_end_prev_nodes:
                    if activity_end_node.id not in processed_nodes:
                        return False
            elif prev_node.id not in processed_nodes:
                return False
        return True
    else:
        return True
        
VERSION_SEPARATOR = '_v_'       
def process_calculate_version_requirement(node, calculates,used_calculates,processed_nodes):
    if isinstance(node, TriccNodeRhombus):
        logger.debug("process_calculate_version_requirement:{} ".format(node.name if hasattr(node,'name') else node.id))
        last_found = None
        for key, p_node in processed_nodes.items():
            if hasattr(p_node,'name') and p_node.name == node.reference:
                # issue is that it can be further in another path
                last_found = p_node
        if node.reference in calculates and len(calculates[node.reference])>0 :
                # issue is that it can be further in another path
                last_found = get_max_version(calculates[node.reference])
        if last_found is not None:
            if node is not last_found.next_nodes:
                last_found.next_nodes.append(node)
            if last_found is not node.prev_nodes:
                node.prev_nodes.append(last_found)
        else:
            return False
        return True
            
    for prev_node in node.prev_nodes:
        if prev_node.id in processed_nodes:
            if isinstance(prev_node, (TriccNodeCount, TriccNodeAdd, TriccNodeCalculate )):
                logger.debug("process_calculate_version_requirement:{}".format(node.name if hasattr(node,'name') else node.id))
                # if not a verison, index will equal -1
                index = prev_node.name.rfind(VERSION_SEPARATOR)
                #remove the leading part with version 
                node_clean_name = prev_node.name[:index] if index > 0 else prev_node.name
                if node_clean_name not in used_calculates:
                    node_clean_name =prev_node.name
                if node_clean_name not in calculates :
                    logger.warning("node {} refered before being processed".format(node.label if node.label is not None else node.name))
                max_version = get_max_version(calculates[node_clean_name])
                if node_clean_name not in used_calculates:
                    used_calculates[node_clean_name] = {}
                #save the max version only once
                if max_version.id not in used_calculates[node_clean_name]:
                    used_calculates[node_clean_name][max_version.id] = max_version
    # update the used_calculates         
    return True

def merge_calculate(node, calculates, from_version):
    #calcualtes list[ node] 
    version = node.version
    node_to_delete = []
    for id, calc_node in calculates.items():
        # merge only if same name, version >= fromm version but < node version    
        if  node.odk_type == calc_node.odk_type :
            cur_version = calc_node.version
            if cur_version >= from_version and  cur_version<version:
                logger.debug("merge_calculate:{} ".format(node.name if hasattr(node,'name') else node.id))
                node.next_nodes += calc_node.next_nodes
                node.prev_nodes += calc_node.prev_nodes
                
                # unlink the merged node in its next nodes

                for next_node in calc_node.next_nodes:
                    if hasattr(next_node,'prev_nodes'):
                        if calc_node in next_node.prev_nodes:
                            next_node.prev_nodes.remove(calc_node)
                        set_prev_node(node, next_node)
                # unlink the merged node in its prev nodes
                for prev_node in calc_node.prev_nodes:
                    if hasattr(prev_node, 'next_nodes'):
                        if calc_node in prev_node.next_nodes:
                            prev_node.next_nodes.remove(calc_node)
                        prev_node.next_nodes.append(node)
                node_to_delete.append(id)
        else:
            logger.error("two different type of calculate node share the same name {}".format(node.name))
    for node_id in node_to_delete:
        del calculates[node_id]

def enrich_node(diagram, edge, node):
    if edge.target == node.id:
        # get node and process type
        type, message = get_message(diagram, edge.source)
        if type is not None and type not in (TriccExtendedNodeType.start, TriccExtendedNodeType.activity_start):   
            if hasattr(node, type):
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
            group =  group
        )
        if type == TriccNodeSelectNotAvailable:
            node.options =   {0:TriccNodeSelectOption(
                id = generate_id(),
                name="1",
                label=label,
                select = node,
                group = group
            )}
        elif type == TriccNodeSelectYesNo:
            node.options =   {0:TriccNodeSelectOption(
                id = generate_id(),
                name="1",
                label=_("Yes"),
                select = None,
                group = group
            ), 1:TriccNodeSelectOption(
                id = generate_id(),
                name="-1",
                label=_("No"),
                select = None,
                group = group
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
            group =  group
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
            **set_mandatory_attribute(elm, mandatory_attributes)
        )
        set_additional_attributes(attributes, elm, node)
        nodes[id]=node
    
def set_mandatory_attribute(elm, mandatory_attributes):
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
            logger.error("the attibute {} is mandatory but not found in {}".format(attributes, display_name))
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
            **set_mandatory_attribute(elm, ['source' , 'parent', 'target'])
        )
        set_additional_attributes(['label'], elm, edge)
        edges.append(edge)
    return edges
        
def group_next_nodes(node):
    if hasattr(node, 'next_nodes') and len(node.next_nodes)>1:
        new_order = [ len(node.next_nodes) for i in node.next_nodes]
        curent_place = 0
        # fist the one from the same group
        order_group_hierachy_nodes(node, new_order, curent_place, node.group)
        if curent_place > 0:
            node.next_nodes =  [node.next_nodes[i] for i in new_order]
           
        # then loop over the parent group
def order_group_hierachy_nodes(node, new_order, curent_place, group):
    if group is not None:
        order_group_nodes(node.next_nodes, new_order, curent_place, node.group)
        if group is not group.group:
            order_group_hierachy_nodes(node, new_order, curent_place, group.group)
    

    
def order_group_nodes(nodes, new_order, curent_place, group):
    for i in range(len(nodes)):
        next_node = nodes[i]
        #if same group give the first place available
        if next_node.group == group:
            new_order[i] = curent_place
            curent_place += 1