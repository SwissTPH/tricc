#from lxml import etree
import itertools
from typing import List
import lxml.etree as etree
import html2text
import pandas as pd
 


def read_drawio(filepath):
    # dict of pages
    diagrams={}
    xml_element_tree = None
    # full list of object
    objects = None
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


def get_odk_type_list(diagram, node_type, odk_type):
    return list(diagram.findall('.//{0}[@odk_type="{1}"]'.format(node_type, odk_type)))

def get_mxcell_parent_list(diagram, select_id, odk_type):
    #get the mxcels
    if isinstance(odk_type, List):
        result = []
        for type in odk_type:
            result +=  get_mxcell_parent_list(diagram, select_id, type)
        return result
    else:
        return diagram.findall(".//mxCell[@parent='{0}']/..[@odk_type='{1}']".format(select_id, odk_type))


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
    
