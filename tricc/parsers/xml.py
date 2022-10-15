from typing import List

import lxml.etree as etree


def read_drawio(filepath):

    root = etree.parse(filepath)
    # import xml.etree.cElementTree as ET
    #with open(filepath) as f:
        #add a fake root so etree can work
        #it = itertools.chain('<root>', f, '</root>')
        #etree = ET.fromstringlist(it)
        #get all the pages
    diagram_list = root.findall('//diagram')


    
    return diagram_list



def get_container_media(diagram, container_id):
    # get the edge 
    return diagram.find(".//object[@odk_type='container_hint_media' and @id='{0}']".format(container_id))
    #get the image node 

def get_odk_type(diagram, node_type, odk_type):
    return diagram.find('.//{0}[@odk_type="{1}"]'.format(node_type, odk_type))


def get_odk_type_list(diagram, node_type, odk_type=None, parent_id = None):
   
    parent_suffix = "[@parent='{}']".format(parent_id)  if parent_id is not None else ''
    if isinstance(odk_type, list):
        result = []
        for type_ in odk_type:
            result +=  get_odk_type_list(diagram, node_type, type_, parent_id)
        return list(set(result))
    if isinstance(node_type, list):
        result = []
        for type_ in node_type:
            result +=  get_odk_type_list(diagram, type_, odk_type, parent_id)
        return list(set(result))
    elif  odk_type is None:
        return list(diagram.findall('.//{0}[@odk_type]{1}'.format(node_type, parent_suffix)))
    else:
        return list(diagram.findall('.//{0}[@odk_type="{1}"]{2}'.format(node_type, odk_type, parent_suffix)))
    
def get_mxcell_parent_list(diagram, select_id, odk_type =None, attrib = None):
    #get the mxcels
    if odk_type is None:
        if attrib is not None:
            return diagram.findall(".//mxCell[@parent='{0}']/..[@{1}]".format(select_id, attrib))
        else:
            return diagram.findall(".//mxCell[@parent='{0}']".format(select_id))
    elif isinstance(odk_type, List):
        result = []
        for type in odk_type:
            result +=  get_mxcell_parent_list(diagram, select_id, type)
        return result
    else:
        return diagram.findall(".//mxCell[@parent='{0}']/..[@odk_type='{1}']".format(select_id, odk_type))

def get_mxcell(diagram, id):
    return diagram.find(".//*[@id='{0}']".format(id))

def get_edges_list(diagram):
    #return list(diagram.findall('.//mxCell[@edge][@source][@target]'))
    # to ensure source and target one can use this xpath above but better trigger a pydantic error if source/target are missing
    return list(set( diagram.findall('.//mxCell[@edge][@source]') + diagram.findall('.//mxCell[@edge][@target]')))  


def get_select_option_image(diagram, select_option_id):
    # get the edge 
    edge=diagram.find(".//mxCell[@edge and @target='{0}']".format(select_option_id))
    #get the image node 
    if edge is not None and edge.attrib.get('source') is not None:
        return diagram.find(".//mxCell[@id='{0}' and not(@odk_type) and not(@edge)]".format(edge.attrib.get('source')))
    
