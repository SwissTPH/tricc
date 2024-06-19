from typing import List

import lxml.etree as etree


type_name = "odk_type"


def read_drawio(filepath):
    filepath = bytes(bytearray(filepath[0], encoding="utf-8"))
    root = etree.fromstring(filepath)
    # import xml.etree.cElementTree as ET
    # with open(filepath) as f:
    # add a fake root so etree can work
    # it = itertools.chain('<root>', f, '</root>')
    # etree = ET.fromstringlist(it)
    # get all the pages
    diagram_list = root.findall(".//diagram")

    return diagram_list


def get_container_media(diagram, container_id):
    # get the edge
    return diagram.find(
        f".//object[@{type_name}='container_hint_media' and @id='{container_id}']"
    )
    # get the image node


def get_tricc_type(diagram, node_type, tricc_type):
    return diagram.find(f'.//{node_type}[@{type_name}="{str(tricc_type)}"]')


def get_tricc_type_list(diagram, node_type, tricc_type=None, parent_id=None):
    tricc_type = str(tricc_type)

    parent_suffix = f"[@parent='{parent_id}']" if parent_id is not None else ""
    if isinstance(tricc_type, list):
        result = []
        for type_ in tricc_type:
            result += get_tricc_type_list(diagram, node_type, type_, parent_id)
        return list(set(result))
    if isinstance(node_type, list):
        result = []
        for type_ in node_type:
            result += get_tricc_type_list(diagram, type_, tricc_type, parent_id)
        return list(set(result))
    elif tricc_type is None:
        return list(diagram.findall(f".//{node_type}[@{type_name}]{parent_suffix}"))
    else:
        return list(
            diagram.findall(
                f'.//{node_type}[@{type_name}="{tricc_type}"]{parent_suffix}'
            )
        )


def get_mxcell_parent_list(diagram, select_id, tricc_type=None, attrib=None):
    # get the mxcels
    if tricc_type is None:
        if attrib is not None:
            return diagram.findall(f".//mxCell[@parent='{select_id}']/..[@{attrib}]")
        else:
            return diagram.findall(f".//mxCell[@parent='{select_id}']")
    elif isinstance(tricc_type, List):
        result = []
        for type in tricc_type:
            result += get_mxcell_parent_list(diagram, select_id, type)
        return result
    else:
        return diagram.findall(
            f".//mxCell[@parent='{select_id}']/..[@{type_name}='{tricc_type}']"
        )


def get_mxcell(diagram, id):
    return diagram.find(f".//*[@id='{id}']")


def get_edges_list(diagram):
    # return list(diagram.findall('.//mxCell[@edge][@source][@target]'))
    # to ensure source and target one can use this xpath above but better trigger a pydantic error if source/target are missing
    return list(
        set(
            diagram.findall(".//mxCell[@edge][@source]")
            + diagram.findall(".//mxCell[@edge][@target]")
        )
    )


def get_select_option_image(diagram, select_option_id):
    # get the edge
    edge = diagram.find(f".//mxCell[@edge and @target='{select_option_id}']")
    # get the image node
    if edge is not None and edge.attrib.get("source") is not None:
        return diagram.find(
            f".//mxCell[@id='{edge.attrib.get('source')}' and not(@{type_name}) and not(@edge)]"
        )
