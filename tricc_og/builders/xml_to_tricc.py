import logging
from networkx import MultiDiGraph, union
from tricc_og.builders.drawio_type_map import TYPE_MAP

from tricc_og.builders.utils import remove_html, clean_str, generate_id
from tricc_og.models.base import (
    TriccMixinRef,
    TriccActivity,
    TriccTask,
    FlowType,
    TriccBaseModel,
)
from tricc_og.models.tricc import TriccNodeType
from tricc_og.parsers.xml import (
    get_edges_list,
    get_mxcell,
    get_mxcell_parent_list,
    get_tricc_type_list,
)

from tricc_og.visitors.tricc_project import add_flow


TRICC_YES_LABEL = ["yes", "oui"]
TRICC_NO_LABEL = ["no", "non"]
TRICC_FOLOW_LABEL = ["folow", "suivre"]
NO_LABEL = "NO_LABEL"
TRICC_LIST_NAME = "list_{0}"


logger = logging.getLogger("default")


def create_activity(project, diagram, media_path):
    drawio_id = diagram.attrib.get("id")
    # root = create_root_node(diagram)
    name = diagram.attrib.get("name")
    form_id = diagram.attrib.get("name", None)
    abs_activity = TriccActivity(
        code=clean_str(name), system=project.code, label=name, attributes={}
    )
    nodes, graph = get_nodes(diagram, abs_activity)
    if nodes:
        activity = TriccActivity(
            instantiate=abs_activity,
            code=get_drawio_name(diagram),
            system=project.code,
            label=name,
            attributes={"form_id": form_id, "id": drawio_id},
            elements=nodes,
            graph=graph,
        )

        get_edges(diagram, activity)
        project.graph = union(project.graph, activity.graph)
    else:
        logger.warning(f"no processable element found in {name}")


def get_nodes(diagram, activity):
    graph = MultiDiGraph()
    for tricc_type in TYPE_MAP:
        list = get_tricc_type_list(diagram, TYPE_MAP[tricc_type]["objects"], tricc_type)
        add_tricc_base_node(
            graph,
            tricc_type,
            list,
            activity,
            attributes=TYPE_MAP[tricc_type]["attributes"],
            mandatory_attributes=TYPE_MAP[tricc_type]["mandatory_attributes"],
        )

        if (
            "has_options" in TYPE_MAP[tricc_type]
            and TYPE_MAP[tricc_type]["has_options"]
        ):
            for elm in list:
                drawio_id = elm.attrib.get("id")
                node = get_node_by_attibute(nodes, "id", drawio_id)
                if node:
                    options = get_select_options(diagram, node, nodes)
                    for i in options:
                        nodes.add(options[i])
                        add_flow(
                            graph,
                            activity,
                            node,
                            options[i],
                            label=i,
                            flow_type=FlowType("OPTION"),
                        )
                else:
                    logger.error(f"node with id {drawio_id} not found")
    return nodes, graph


def get_node_by_attibute(nodes, attribute_name, attribute_value):
    filtered = list(
        filter(lambda n: n.attributes[attribute_name] == attribute_value, nodes)
    )
    if filtered:
        return filtered[0]


# converter XML item to object


def set_additional_attributes(node, elm, attribute_names):
    if not isinstance(attribute_names, list):
        attribute_names = [attribute_names]
    for attributename in attribute_names:
        attribute = elm.attrib.get(attributename)
        if attribute is not None:
            # input expression can add a condition to either
            # relevance (display) or calculate expression
            if attributename == "expression_inputs":
                attribute = [attribute]
            elif attributename == "instance":
                attribute = int(attribute)
            else:
                attribute
            if hasattr(node, attributename):
                setattr(node, attributename, attribute)
            else:
                node.attributes[attributename] = attribute


def get_select_options(diagram, select_node, nodes):
    options = {}
    i = 0
    list = get_mxcell_parent_list(
        diagram, select_node.attributes["id"], TriccNodeType.select_option
    )
    options_name_list = []
    for elm in list:
        name = get_drawio_name(elm)
        if name in options_name_list and not name.endswith("_"):
            logger.error(
                "Select question {0} have twice the option name {1}".format(
                    select_node.get_name(), name
                )
            )
        else:
            options_name_list.append(name)
        drawio_id = elm.attrib.get("id")
        option = TriccBaseModel(
            code=name,
            system=select_node.get_name(),
            type_scv=TriccMixinRef(
                system="tricc_type", code=str(TriccNodeType.select_option)
            ),
            label=elm.attrib.get("label"),
            attributes={
                "id": drawio_id,
            },
        )
        set_additional_attributes(option, elm, ["save"])
        options[i] = option
        i += 1
    return options


def get_drawio_name(elm):
    name = elm.attrib.get("name", "")
    if not name or name.endswith("_"):
        name += elm.attrib.get("id")
    return clean_str(name)


def add_tricc_base_node(
    graph, type_code, list, group, attributes=[], mandatory_attributes=[]
):
    for elm in list:
        drawio_id = elm.attrib.get("id")
        parent = elm.attrib.get("parent")
        node = TriccBaseModel(
            code=get_drawio_name(elm),
            type_scv=TriccMixinRef(system="tricc_type", code=str(type_code)),
            system=group.system if group else "drawio",
            context=group,
            attributes={"parent": parent, "id": drawio_id},
        )

        set_mandatory_attribute(node, elm, mandatory_attributes)
        set_additional_attributes(node, elm, attributes)
        graph.add_node(node.__resp__(), data=node)


def set_mandatory_attribute(node, elm, mandatory_attributes):
    value = None
    for attributes in mandatory_attributes:
        attribute_value = elm.attrib.get(attributes)
        if attribute_value is None:
            if elm.attrib.get("label") is not None:
                display_name = elm.attrib.get("label")
            elif elm.attrib.get("name") is not None:
                display_name = elm.attrib.get("name")
            else:
                display_name = elm.attrib.get("id")
            logger.error(
                "the attribute {} is mandatory but not found in {}".format(
                    attributes, display_name
                )
            )
            if mandatory_attributes == "source":
                if elm.attrib.get("target") is not None:
                    logger.error(f"the attribute target is {elm.attrib.get('target')}")
            elif mandatory_attributes == "target":
                if elm.attrib.get("source") is not None:
                    logger.error(f"the attribute target is {elm.attrib.get('source')}")
            exit()
        if attributes == "link":
            value = clean_link(attribute_value)
        elif attributes in ("parent", "id", "source", "target"):
            value = attribute_value
        elif value is not None:
            value = remove_html(value.strip())
            if hasattr(node, attributes):
                setattr(node, attributes, value)
            else:
                node.attributes[attributes] = value


def clean_link(link):
    # link have the format "data:page/id,DiagramID"
    link_parts = link.split(",")
    if link_parts[0] == "data:page/id" and len(link_parts) == 2:
        return link_parts[1]


# TODO support group
# TODO support contained including images


def get_media(elm, activity):
    style = elm.attrib.get("style")
    # IMAGE
    if style is not None and "image=data:image/" in style:
        image_attrib = style.split("image=data:image/")
        if image_attrib is not None and len(image_attrib) == 2:
            image_parts = image_attrib[1].split(",")
            if len(image_parts) == 2:
                payload = image_parts[1][:-1].encode("ascii")
                image_name = generate_id(name=payload)
                parent = elm.attrib.get("parent")
                return TriccBaseModel(
                    code=image_name,
                    system=activity.system,
                    type_scv=TriccMixinRef(
                        system="data:image", code=str(image_parts[0])
                    ),
                    context=activity,
                    attributes={
                        "parent": parent,
                        "id": elm.attrib.get("id"),
                        "data": payload,
                    },
                )


def get_edges(diagram, activity):
    list = get_edges_list(diagram)
    for elm in list:
        source_id = elm.attrib.get("source")
        source = get_node_by_attibute(activity.elements, "id", source_id)
        target_id = elm.attrib.get("target")
        target = get_node_by_attibute(activity.elements, "id", target_id)
        value = elm.attrib.get("value")
        if value is not None:
            value = remove_html(value)
        if target and source:
            add_flow(activity.graph, activity, source, target, value)
        elif target:
            if elm is not None:
                elm = get_mxcell(diagram, source_id)
                source = get_message(elm, activity)
                if not source:
                    source = get_media(elm, activity)
                if source:
                    activity.elements.add(source)
                    add_flow(activity.graph, activity, source, target, value)
                else:
                    logger.error(f"unreconized source id {source_id}: {elm}")
                    exit(-1)
        else:
            elm = get_mxcell(diagram, target_id)
            logger.error(f"unreconized target id {target_id}: {elm}")
            exit(-1)


def get_message(elm, activity):
    tricc_type = elm.attrib.get("odk_type")
    if tricc_type is not None:
        if tricc_type.endswith("-message"):
            tricc_type = type[:-8]
            return TriccBaseModel(
                code=get_drawio_name(elm),
                system=activity.system,
                label=elm.attrib.get("label"),
                type_scv=TriccMixinRef(system="tricc_type", code=str(tricc_type)),
                context=activity,
                attributes={
                    "parent": elm.attrib.get("parent"),
                    "id": elm.attrib.get("id"),
                },
            )
