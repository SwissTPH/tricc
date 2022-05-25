

import os
from uuid import uuid4
import html2text
from tricc.models import *
from tricc.parsers.xml import  get_edges_list, get_mxcell_parent_list, get_odk_type,  get_odk_type_list
import logging
import base64

from tricc.services.utils import set_prev_node



logger = logging.getLogger(__name__)

def create_activity(diagram):
    
    root = create_root_node(diagram)
    name = diagram.attrib.get('name')
    id = diagram.attrib.get('id')
    if root is not None:
        edges = get_edges(diagram)
        nodes = get_nodes(diagram)
        groups  = get_groups(diagram, nodes)

        activity = TriccNodeActivity(
            root=root,
            name=id,
            id=id,       
            label=name,
        )
        if groups and len(groups)>0:
            activity.groups = groups        
        if nodes and len(nodes)>0:
            activity.nodes = nodes
        if edges and len(edges)>0:
            activity.edges = edges
            activity.edges_copy = edges.copy()
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

def get_nodes(diagram):
    nodes = {}
    add_note_nodes(nodes, diagram)  
    add_calculate_nodes(nodes, diagram)
    add_select_nodes(nodes, diagram)
    add_input_nodes(nodes, diagram)
    add_link_nodes(nodes, diagram)
    add_contained_resources(diagram, nodes)
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

def add_note_nodes(nodes, diagram):
    list = get_odk_type_list(diagram, ['UserObject','object'], TriccNodeType.note)
    add_tricc_nodes(nodes, TriccNodeNote, list, ['relevance'])
    

def add_select_nodes(nodes, diagram):
    list = get_odk_type_list(diagram, 'UserObject', TriccNodeType.select_one)
    add_tricc_select_nodes(diagram, nodes, TriccNodeSelectOne, list, ['required','save','filter','constraint','constraint_message'])
    #list = get_odk_type_list(diagram, 'UserObject', TriccExtendedNodeType.select_yesno)
    #add_tricc_nodes(nodes, TriccNodeSelectYesNo, list, ['constraint','save','constraint_message','required'])
    list = get_odk_type_list(diagram, 'UserObject', TriccNodeType.select_multiple)
    add_tricc_select_nodes(diagram, nodes, TriccNodeSelectMultiple, list, ['required','save','filter','constraint','constraint_message'])

def add_input_nodes(nodes, diagram):
    list = get_odk_type_list(diagram, 'object', TriccNodeType.decimal)
    add_tricc_nodes(nodes, TriccNodeDecimal, list, ['min','max', 'constraint','save','constraint_message','required'])
    list = get_odk_type_list(diagram, 'object', TriccNodeType.integer)
    add_tricc_nodes(nodes, TriccNodeInteger, list, ['min','max', 'constraint','save','constraint_message','required'])
    list = get_odk_type_list(diagram, 'object', TriccNodeType.text)
    add_tricc_nodes(nodes, TriccNodeText, list, ['constraint','save','constraint_message','required'])

def add_calculate_nodes(nodes, diagram):
    list = get_odk_type_list(diagram, 'object', TriccNodeType.calculate)
    add_tricc_nodes(nodes, TriccNodeCalculate, list, ['save','expression'])
    list = get_odk_type_list(diagram, 'object', TriccExtendedNodeType.add)
    add_tricc_nodes(nodes, TriccNodeAdd, list, ['save','expression'])
    list = get_odk_type_list(diagram, 'object', TriccExtendedNodeType.count)
    add_tricc_nodes(nodes, TriccNodeCount, list, ['save','expression'])
    list = get_odk_type_list(diagram, 'UserObject', TriccExtendedNodeType.rhombus)
    add_tricc_nodes(nodes, TriccNodeRhombus, list, ['save','expression'])
    list = get_odk_type_list(diagram, 'object', TriccExtendedNodeType.exclusive)
    add_tricc_base_node(nodes, TriccNodeExclusive, list)
    

    
def add_link_nodes(nodes, diagram):
    list = get_odk_type_list(diagram, 'object', TriccExtendedNodeType.link_out)
    add_tricc_nodes(nodes, TriccNodeLinkOut, list, [], ['reference'])
    list = get_odk_type_list(diagram, 'object', TriccExtendedNodeType.link_in)
    add_tricc_nodes(nodes, TriccNodeLinkIn, list)
    list = get_odk_type_list(diagram, 'object', TriccExtendedNodeType.goto)
    add_tricc_nodes(nodes, TriccNodeGoTo, list,[],['link'])
    list = get_odk_type_list(diagram, 'object', TriccExtendedNodeType.activity_end)
    add_tricc_base_node(nodes, TriccNodeActivityEnd, list)
    list = get_odk_type_list(diagram, 'object', TriccExtendedNodeType.end)
    add_tricc_base_node(nodes, TriccNodeEnd, list)
    
    
def get_select_options(diagram, select_node):
    options = {}
    i = 0
    list = get_mxcell_parent_list(diagram, select_node.id, TriccExtendedNodeType.select_option)
    options_name_list = []
    for elm in list:
        name = elm.attrib.get('name')
        if name in options_name_list:
            logger.error("Select quesiton {0} have twice the option name {1}"\
                .format(select_node.label ,name))
        else:
            options_name_list.append(name)
        option = TriccNodeSelectOption(
            id = elm.attrib.get('id'),
            label = elm.attrib.get('label'),
            name = name,
            select = select_node
        )
        get_select_option_image(option)
        set_additional_attributes(['save'], elm, option)
        options[i]=option
        i += 1
    if len(list)== 0:
        logger.error("select {} does not have any option".format(select_node.label))
    else:
        return options



def add_save_calculate(node, calculates, used_calculates,processed_nodes ):
     # used_calculates dict[name, Dict[id, node]]
     # processed_nodes Dict[id, node]
     # calculates  dict[name, Dict[id, node]]
    logger.debug("{}:save the calculate".format(node.label if hasattr(node,'label') else node.id))
    if is_ready_to_process(node, processed_nodes):
        process_calculate_version_requirement(node, calculates, used_calculates,processed_nodes)
        generate_save_calculate(node, calculates, used_calculates,processed_nodes)
        if issubclass(node.__class__, TriccNodeCalculateBase) and node.name is not None:
            # generate the calc node version by looking in the processed calculate
            if node.name in calculates:
                if node.id in calculates[node.name]:
                    node.version = get_max_used_version(calculates,node.name) + 1
                # check if the calculate is used, if not merge it with the previous versions
                from_version = get_max_used_version(used_calculates, node.name)
                merge_calculate(node, calculates[node.name], from_version)
            else:
                calculates[node.name]= {}
            calculates[node.name][node.id]=node
        processed_nodes[node.id] = node

def get_max_used_version(used_calculates,name):
    max = 0
    if name  in used_calculates:
        for id, node in used_calculates[name].items():
            if node.version > max:
                max = node.version
    return max




def generate_save_calculate(node, calculates, used_calculates,processed_nodes):
    if hasattr(node, 'save') and node.save is not None:
        # get fragments type.name.icdcode
        save_fragments=node.save.split('.')
        if len(save_fragments)>1:
            calculate_name = "{0}_{1}".format(save_fragments[0], save_fragments[1])
        else:
            calculate_name = "{0}_{1}".format(save_fragments[0], node.name)
        calc_node = TriccNodeCalculate(
            name=calculate_name,
            id = generate_id()
        )
        calc_node.prev_nodes.append(node)
        node.next_nodes.append(calc_node)
        if calculate_name not in calculates:
            calculates[calculate_name] = {}
        calculates[calculate_name][calc_node.id]=calc_node
        add_save_calculate(calc_node, calculates, used_calculates,processed_nodes)
        
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
    if hasattr(node, 'prev_nodes'):
        prev_nodes_processed = True
        for prev_node in node.prev_nodes:
            if prev_node.id not in processed_nodes:
                prev_nodes_processed = False
        return prev_nodes_processed
    else:
        return False
        
            
def process_calculate_version_requirement(node, calculates,used_calculates,processed_nodes):
    prev_nodes_processed = True
    for prev_node in node.prev_nodes:
        if prev_node.id in processed_nodes:
            # reference the used calculate
            if issubclass(prev_node.__class__, TriccNodeCalculateBase):
                if prev_node.name not in calculates:
                    logger.warning("node {} refered before being processed".format(node.label if node.label is not None else node.name))
                max_version = get_max_version(calculates[prev_node.name])
                if prev_node.name not in used_calculates:
                    used_calculates[prev_node.name] = {}
                #save the max version only once
                if max_version.id not in used_calculates[prev_node.name]:
                    used_calculates[prev_node.name][max_version.id] = max_version
    # update the used_calculates         
    return prev_nodes_processed



def merge_calculate(node, calculates, from_version):
    #calcualtes list[ node] 
    version = node.version
    node_to_delete = []
    for id, calc_node in calculates.items():
        cur_version = calc_node.version
        
        # merge only if same name, version >= fromm version but < node version
        if cur_version >= from_version and  cur_version<version :
            if node.odk_type == calc_node.odk_type and (not hasattr(node, 'reference') or node.reference == calc_node.reference):
                node.next_nodes += calc_node.next_nodes
                node.prev_nodes += calc_node.prev_nodes
                node.expression_inputs += calc_node.expression_inputs
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



def get_select_option_image(option):
    # TODO , get edge that has a target to the option (mxcelL ?)
    # get the image from source
    # save image and add the link to the option.image
    pass
    
def add_tricc_select_nodes(diagram, nodes, type, list, attributes):
    for elm in list:
        id = elm.attrib.get('id')
        parent= elm.attrib.get('parent')
        node = type(
            id = id,
            parent= parent,
            label = elm.attrib.get('label'),
            name = elm.attrib.get('name'),
            required=True,
        )
        node.options = get_select_options(diagram, node)
        set_additional_attributes(attributes, elm, node)
        nodes[id]=node
        


def add_tricc_nodes(nodes, type, list, attributes = [], mandatory_attributes = []):
        mandatory_attributes +=  ['label','name']
        add_tricc_base_node(nodes, type, list, attributes, mandatory_attributes)
            
            
def add_tricc_base_node(nodes, type, list, attributes = [], mandatory_attributes = []):   
    for elm in list:
        id = elm.attrib.get('id')
        parent= elm.attrib.get('parent')
        node = type(
            id = id,
            parent= parent,
            **set_mandatory_attribute(elm, mandatory_attributes)
        )
        set_additional_attributes(attributes, elm, node)
        nodes[id]=node
    
def set_mandatory_attribute(elm, mandatory_attributes):
    param = {}
    for attributes in mandatory_attributes:
        attribute_value = elm.attrib.get(attributes)
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
    
def get_groups(diagram, nodes):
    groups = {}
    list=get_odk_type_list(diagram, 'object', TriccExtendedNodeType.page )
    for elm in list:
        group = add_group(elm, diagram, nodes, groups)
    return groups

        
def add_group(elm, diagram, nodes, groups):
    id = elm.attrib.get('id')
    if id not in groups:
        group = TriccGroup(
            name = elm.attrib.get('name'),
            label = elm.attrib.get('label'),
            id = id
        )
        # get elememt witn parent = id and odk_type defiend
        list_child = get_odk_type_list(diagram, ['object','UserObject'], odk_type=None, parent_id = id)
        add_group_to_child(group, diagram,list_child, nodes, groups)
        if group is not None:
            groups[group.id] = group
        return group
        
def add_group_to_child(group, diagram,list_child, nodes, groups):
    for child_elm in list_child:
        if child_elm.attrib.get('odk_type') == TriccExtendedNodeType.container_hint_media:
            list_sub_child = get_odk_type_list(diagram, ['object','UserObject'], odk_type=None, parent_id = id )
            add_group_to_child(group, diagram,list_sub_child, nodes, groups)
        elif child_elm.attrib.get('odk_type') == TriccExtendedNodeType.page:
            child_group_id = child_elm.attrib.get('id')
            if not child_group_id  in groups:
                child_group = add_group(child_elm, diagram, nodes, groups)
            else:
                child_group = groups[child_group_id]
            child_group.group = group
        else:
            child_id=child_elm.attrib.get('id')
            if child_id is not None and child_id in nodes:
                if issubclass(nodes[child_id].__class__, TriccNodeDiplayModel):
                    nodes[child_id].group = group
                
                
        

        
def add_contained_resources(diagram, nodes):
    list=get_odk_type_list(diagram, 'object', TriccExtendedNodeType.container_hint_media)
    for elm in list:
        id = elm.attrib.get('id')
        main_node = get_contained_main_node(diagram, id)
        if main_node is not None:
            main_id = main_node.attrib.get('id')
            if main_id in nodes:
                hint_message = get_contained_message(diagram, id,TriccExtendedNodeType.hint)
                help_message = get_contained_message(diagram, id,TriccExtendedNodeType.help)
                image = get_contained_image(diagram, id )
                if hint_message:
                    nodes[main_id].hint=hint_message
                if help_message:
                    nodes[main_id].help=help_message
                if image:
                    nodes[main_id].image=image                        
        
        

def get_contained_image(diagram, container_id ):

    list = get_mxcell_parent_list(diagram, container_id, None)
    for elm in list:
        style=elm.attrib.get('style')
        file_name = add_image_from_style(style, container_id)
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
        
def get_contained_message(diagram, id,type):
    list = get_mxcell_parent_list(diagram, id, type)
    if isinstance(list, List) and len(list)>0:
        #use only the first one
        return remove_html(list[0].attrib.get('label'))


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
        