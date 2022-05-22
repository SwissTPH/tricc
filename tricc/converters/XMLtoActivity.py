

from tricc.models import *
from tricc.serializers.xml import  get_edges_list, get_mxcell_parent_list, get_odk_type,  get_odk_type_list
import warnings
import logging
logger = logging.getLogger(__name__)

def create_activity(diagram_key, diagram):
    
    root = create_root_node(diagram)
    if root is not None:
        edges = get_edges(diagram)
        nodes = get_nodes(diagram)
        
        name = diagram.attrib.get('name')
        id=diagram.attrib.get('id')
        activity = TriccNodeActivity(
            root=root,
            name=id,
            id=id,       
            label=name,
        )
        if nodes and len(nodes)>0:
            activity.nodes = nodes
        if edges and len(edges)>0:
            activity.edges = edges
            activity.edges_copy = edges.copy()
    else:
        logger.debug("root not found for page {0}".format(name))
            
        
    return activity


def get_nodes(diagram):
    nodes = {}
    add_note_nodes(nodes, diagram)  
    add_calculate_nodes(nodes, diagram)
    add_select_nodes(nodes, diagram)
    add_input_nodes(nodes, diagram)
    add_link_nodes(nodes, diagram)
    #add_loose_link_nodes(nodes, diagram)
    add_contained_resources(diagram, nodes)
    add_pages(diagram, nodes)
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
            setattr(node, attributename, attribute)        

def add_note_nodes(nodes, diagram):
    list = get_odk_type_list(diagram, 'UserObject', TriccNodeType.note)
    add_tricc_nodes(nodes, TriccNodeNote, list, ['relevance'])
    list = get_odk_type_list(diagram, 'object', TriccNodeType.note)
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
def get_select_options(diagram, select_id):
    options = {}
    i = 0
    list = get_mxcell_parent_list(diagram, select_id, TriccExtendedNodeType.select_option)
    options_name_list = []
    for elm in list:
        name = elm.attrib.get('name')
        if name in options_name_list:
            logger.error("Select quesiton {0} have twice the option name {1}"\
                .format(select_id,name))
        else:
            options_name_list.append(name)
        option = TriccNodeSelectOption(
            id = elm.attrib.get('id'),
            label = elm.attrib.get('label'),
            name = name
        )
        set_additional_attributes(['save'], elm, option)
        options[i]=option
        i += 1
    return options
        
    
def add_tricc_select_nodes(diagram, nodes, type, list, attributes):
    for elm in list:
        id = elm.attrib.get('id')
        parent= elm.attrib.get('parent')
        options = get_select_options(diagram, id)
        if options is not None and len(options)>0 :
            node = type(
                id = id,
                parent= parent,
                label = elm.attrib.get('label'),
                name = elm.attrib.get('name'),
                required=True,
                options = options
            )
            set_additional_attributes(attributes, elm, node)
            nodes[id]=node
        else:
            warnings.warn("Select_multiple {0} without option".format(elm.attrib.get('label')))
      



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
            attribute_value = clean_link(attribute_value)
        if attribute_value is not None:
            param[attributes]=attribute_value
    return param

def clean_link(link):
    # link have the format "data:page/id,DiagramID"
    link_parts = link.split(',')
    if link_parts[0] == 'data:page/id' and len(link_parts)==2:
        return link_parts[1]
    
        
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
                image = get_contained_image(diagram, id)
                if hint_message:
                    nodes[main_id].hint=hint_message
                if help_message:
                    nodes[main_id].help=help_message
                if image:
                    nodes[main_id].image=image                        
        
        

def get_contained_image(diagram, id):
    pass

def get_contained_main_node(diagram, id):
    list = get_mxcell_parent_list(diagram, id, media_nodes)
    if isinstance(list, List) and len(list)>0:
        #use only the first one
        return list[0]
        
def get_contained_message(diagram, id,type):
    list = get_mxcell_parent_list(diagram, id, type)
    if isinstance(list, List) and len(list)>0:
        #use only the first one
        return list[0].attrib.get('label')


def get_edges( diagram):
    edges = []
    list = get_edges_list(diagram)
    for elm in list:
        id = elm.attrib.get('id')
        edge = TriccEdge(
            id = id,
            source = elm.attrib.get('source'),
            target = elm.attrib.get('target'),
            parent= elm.attrib.get('parent')
        )
        set_additional_attributes(['label'], elm, edge)
        edges.append(edge)
    return edges
        
def add_pages(diagram, nodes):
    pass
