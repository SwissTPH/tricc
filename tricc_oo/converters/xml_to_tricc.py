import base64
import os
import re
from curses.ascii import isalnum, isalpha, isdigit

from numpy import isnan

from tricc_oo.converters.utils import clean_name, remove_html
from tricc_oo.converters.cql_to_operation import transform_cql_to_operation
from tricc_oo.models.tricc import *
from tricc_oo.models.base import TriccNodeType, OPERATION_LIST
from tricc_oo.models.ocl import get_data_type
from tricc_oo.converters.drawio_type_map import TYPE_MAP
from tricc_oo.parsers.xml import (
    get_edges_list,
    get_mxcell,
    get_elm,
    get_mxcell_parent_list,
    get_tricc_type,
    get_tricc_type_list,
)
import hashlib
from tricc_oo.visitors.tricc import *
from tricc_oo.converters.datadictionnary import add_concept

TRICC_YES_LABEL = ["yes", "oui"]
TRICC_NO_LABEL = ["no", "non"]
TRICC_FOLLOW_LABEL = ["follow", "suivre", "continue"]
NO_LABEL = "NO_LABEL"
TRICC_LIST_NAME = "list_{0}"
import logging

logger = logging.getLogger("default")



def get_all_nodes(diagram, activity, nodes):
    for tricc_type in TYPE_MAP:
        if TYPE_MAP[tricc_type]["model"]:
            list = get_tricc_type_list(diagram, TYPE_MAP[tricc_type]["objects"], tricc_type)
            add_tricc_base_node(
                diagram,
                nodes,
                TYPE_MAP[tricc_type]["model"],
                list,
                activity,
                attributes=TYPE_MAP[tricc_type]["attributes"],
                mandatory_attributes=TYPE_MAP[tricc_type]["mandatory_attributes"],
                has_options=TYPE_MAP[tricc_type].get('has_options', None)
            )

    return nodes

def create_activity(diagram, media_path, project):

    external_id = diagram.attrib.get("id")
    id = get_id( external_id,  diagram.attrib.get("id"))
    root = create_root_node(diagram)
    name = diagram.attrib.get("name")
    form_id = diagram.attrib.get("name", None)
    if root is not None:
        activity = TriccNodeActivity(
            root=root,
            name=get_rand_name(f"a{id}"),
            id=id,
            external_id=external_id,
            label=name,
            form_id=form_id,
        )
        # activity definition is never instanciated
        if isinstance(root, TriccNodeActivityStart):
            activity.instance = 0
        # add the group on the root node
        root.group = activity
        activity.group = activity
        edges = get_edges(diagram)
        if edges and len(edges) > 0:
            activity.edges = edges
        nodes = get_nodes(diagram, activity)
        for n in nodes.values():
            
            if (
                issubclass(n.__class__, (TriccNodeDisplayModel, TriccNodeDisplayCalculateBase)) 
                and not isinstance(n, (TriccRhombusMixIn, TriccNodeRhombus, TriccNodeDisplayBridge))
                and not n.name.startswith('label_')
            ):
                system = n.name.split('.')[0] if '.' in n.name else 'tricc'
                if isinstance(n, TriccNodeSelectOption) and isinstance(n.select, TriccNodeSelectNotAvailable):
                    add_concept(project.code_systems, system, n.select.name, n.label, {"datatype": 'Boolean'})
                elif not isinstance(n, TriccNodeSelectNotAvailable):
                    add_concept(project.code_systems, system, n.name, n.label, {"datatype": get_data_type(n.tricc_type)})
                if getattr(n,'save', None):
                    system = n.save.split('.')[0] if '.' in n.save else 'tricc'
                    add_concept(project.code_systems, system, n.save, n.label, {"datatype": get_data_type(n.tricc_type)})
            
        groups = get_groups(diagram, nodes, activity)
        if groups and len(groups) > 0:
            activity.groups = groups
        if nodes and len(nodes) > 0:
            activity.nodes = nodes

        images = process_edges(diagram, media_path, activity, nodes)
        # link back the activity
        activity.root.activity = activity
        manage_dangling_calculate(activity)
        
        if activity is not None:
            if activity.root is not None:
                project.pages[activity.id] = activity
                if activity.root.tricc_type == TriccNodeType.start:
                    if "main" not in project.start_pages and (
                        activity.root.process == "main" or activity.root.process is None
                    ):
                        project.start_pages["main"] = activity
                    elif activity.root.process is not None:
                        if activity.root.process not in project.start_pages:
                            project.start_pages[activity.root.process] = []
                        project.start_pages[activity.root.process].append(activity)
                    else:
                        logger.warning(
                            "Page {0} has a start node but there is already a start node in page  {1}".format(
                                activity.label, start_page.label
                            )
                        )
        if images:
            project.images += images
        for node in list(filter(lambda p_node: isinstance(p_node, TriccNodeSelectNotAvailable),list(activity.nodes.values()))):
            prev_node = None
            prev_edges = list(filter(lambda p_e: p_e.target == node.id,list(activity.edges))) 
            if len(prev_edges):
                prev_node = [n for n in activity.nodes.values() if n.id in [p_e.source for p_e in prev_edges]]
                if prev_node:
                    node.parent = prev_node[0]
            if not  node.parent :    
                logger.critical(f"unable to find the parent of the NotApplicable node {node.get_name()}")
                exit(1)


  
    else:
        return None, None
        logger.warning("root not found for page {0}".format(name))


def manage_dangling_calculate(activity):
    dangling = {}
    for node in activity.nodes.values():
        prev_nodes = [
            activity.nodes[n.source]
            for n in list(
                filter(
                    lambda x: (x.target == node.id or x.target == node)
                    and (
                        x.source in activity.nodes
                        or x.source in activity.nodes.values()
                    ),
                    activity.edges,
                )
            )
        ]
        if len(prev_nodes) == 0 and issubclass(node.__class__, TriccNodeCalculateBase):
            dangling[node.id] = node
    if len(dangling) > 0:
        activity.calculates += list(dangling.values())
        # wait = get_activity_wait([activity.root], [activity.root], dangling.values(), edge_only=True)
        # activity.nodes.update(dangling)


def process_edges(diagram, media_path, activity, nodes):
    end_found = False
    images = []
    for edge in activity.edges:
        # enrich nodes
        if edge.target not in nodes:
            activity.unused_edges.append(edge)
        elif edge.source not in nodes and edge.target in nodes:
            enriched, image = enrich_node(diagram, media_path, edge, nodes[edge.target], activity)
            if enriched is None:
                activity.unused_edges.append(edge)
            if image is not None:
                images.append({"file_path": enriched, "image_content": image})

        elif isinstance(nodes[edge.target], (TriccNodeActivityEnd, TriccNodeEnd)):
            end_found = True
        if (
            edge.target in nodes
            and issubclass(nodes[edge.target].__class__, TriccRhombusMixIn)
            and edge.source != nodes[edge.target].path.id
        ):
            edge.target = nodes[edge.target].path.id
        # modify edge for selectyesNo
        if edge.source in nodes and isinstance(
            nodes[edge.source], TriccNodeSelectYesNo
        ):
            process_yesno_edge(edge, nodes)

        # create calculate based on edges label
        elif edge.value is not None:
            label = edge.value.strip()
            processed = False
            calc = None
            if (
                isinstance(nodes[edge.source], TriccNodeRhombus)
                and label.lower() in TRICC_FOLLOW_LABEL
            ):
                edge.source = nodes[edge.source].path.id
                processed = True
            elif label.lower() in (TRICC_YES_LABEL) or label == "":
                # do nothinbg for yes
                processed = True
            elif re.search(r"^\-?[0-9]+([.,][0-9]+)?$", edge.value.strip()):
                calc = process_factor_edge(edge, nodes)
            elif label.lower() in TRICC_NO_LABEL:
                calc = process_exclusive_edge(edge, nodes)
            elif  any(reserved in label.lower() for reserved in ([str(o) for o in list(TriccOperator)] + list(OPERATION_LIST.keys()) + ['$this'])):
                # manage comment
                calc = process_condition_edge(edge, nodes)
            else:
                logger.warning(f"unsupported edge label {label} in {diagram.attrib.get('name', diagram.attrib['id'])}")
            if calc is not None:
                processed = True
                nodes[calc.id] = calc
                # add edge between calc and
                set_prev_next_node(calc, nodes[edge.target], edge_only=True)
                edge.target = calc.id
            if not processed:
                logger.warning(
                    "Edge between {0} and {1} with label '{2}' could not be interpreted: {3}".format(
                        nodes[edge.source].get_name(),
                        nodes[edge.target].get_name(),
                        edge.value.strip(),
                        "not management found",
                    )
                )
    if not end_found:
        fake_end = TriccNodeActivityEnd(id=generate_id(), activity=activity, group=activity)
        last_nodes = [
            n for n in list(activity.nodes.values())
            if (
                issubclass(
                    n.__class__, 
                    (
                        TriccNodeInputModel, 
                        TriccNodeText, 
                        TriccNodeNote,
                    )
                ) and (
                    not any([n.id == e.source for e in activity.edges])
                )
            )
        ]
        if last_nodes:
            for n in last_nodes:
                set_prev_next_node(n, fake_end, edge_only=True)
            activity.nodes[fake_end.id] = fake_end
        # take all last nodes
        else:
            logger.warning(f"Activity {activity.label} have no end, calculated might be included in the end definition")
            last_nodes = [
                n for n in list(activity.nodes.values())
                if (
                        not any([n.id == e.source for e in activity.edges])
                )
            ]
            if last_nodes:
                for n in last_nodes:
                    set_prev_next_node(n, fake_end, edge_only=True)
                activity.nodes[fake_end.id] = fake_end
            else:
                logger.critical(f"cannot guess end for {activity.get_name()}")
                exit(1)
    
    return images

def get_id(elm_id, activity_id):
   return  str(elm_id) if len(elm_id)>8 else str(activity_id) + str(elm_id)

def _get_name(name, id, act_id):
    if (
        name is not None
        and (name.endswith(("_", ".")))
    ):
        return name + get_id(id, act_id)
    return name
   

def get_nodes(diagram, activity):
    nodes = {activity.root.id: activity.root}
    get_all_nodes(diagram, activity, nodes)
    new_nodes = {}
    node_to_remove = []
    activity_end_node = None
    end_node = None
    for node in nodes.values():
        # clean name
        if (
            hasattr(node, "name")
        ):
            node.name = _get_name(node.name, node.id, activity.id)
        if issubclass(node.__class__, TriccRhombusMixIn) and node.path is None:
            # generate rhombuse path
            calc = inject_bridge_path(node, {**nodes, **new_nodes})
            if calc:
                node.path = calc
                new_nodes[calc.id] = calc
            else:
                node.path = activity.root
            # add the edge between trhombus and its path
        elif isinstance(node, TriccNodeGoTo):
            # find if the node has next nodes, if yes, add a bridge + Rhoimbus
            path = inject_bridge_path(node, {**nodes, **new_nodes})
            if path:
                new_nodes[path.id] = path
            else:
                logger.critical(f"goto without in edges {node.get_name()}")
            # action after the activity
            next_nodes_id = [e.target for e in activity.edges if e.source == node.id]
            if len(next_nodes_id) > 0:

                calc = get_activity_wait(
                    path, [node], next_nodes_id, node, edge_only=True
                )
                new_nodes[calc.id] = calc
                for goto_next_node in next_nodes_id:
                    remove_prev_next(node, goto_next_node, activity) 
        elif isinstance(node, TriccNodeActivityEnd):
            if not activity_end_node:
                activity_end_node = node
            else:
                merge_node(node, activity_end_node)
                node_to_remove.append(node.id)
        # add activity relevance to calculate
        elif (
            issubclass(node.__class__, TriccNodeDisplayCalculateBase) 
            and not getattr(node, 'relevance', None)
            and node.activity.root.relevance
        ):
            node.applicability = node.activity.root.relevance
            

    nodes.update(new_nodes)

    for key in node_to_remove:
        del nodes[key]
    edge_list = activity.edges.copy()
    for edge in edge_list:
        if edge.source in node_to_remove or edge.target in node_to_remove:
            activity.edges.remove(edge)

    return nodes


def create_root_node(diagram):
    node = None
    elm = get_tricc_type(diagram, "object", TriccNodeType.start)
    if elm is None:
        elm = get_tricc_type(diagram, "UserObject", TriccNodeType.start)
    if elm is not None:
        external_id = elm.attrib.get("id")
        id = get_id( external_id,  diagram.attrib.get("id"))
        node = TriccNodeMainStart(
            id=id,
            external_id=external_id,
            parent=elm.attrib.get("parent"),
            name="ms" + id,
            label=elm.attrib.get("label"),
            form_id=elm.attrib.get("form_id"),
            relevance=elm.attrib.get("relevance"),
            process=elm.attrib.get("process") or 'main',
        )
    else:
        elm = get_tricc_type(diagram, "object", TriccNodeType.activity_start)
        if elm is None:
            elm = get_tricc_type(diagram, "UserObject", TriccNodeType.activity_start)
        if elm is not None:
            external_id = elm.attrib.get("id")
            id = get_id( external_id,  diagram.attrib.get("id"))
            node = TriccNodeActivityStart(
                id=id,
                external_id=external_id,
                #parent=elm.attrib.get("parent"),
                name="ma" + id,
                label=diagram.attrib.get("name"),
                relevance=elm.attrib.get("relevance"),
                instance=int(
                    elm.attrib.get("instance")
                    if elm.attrib.get("instance") is not None
                    else 1
                ),
            )
    load_expressions(node)
    return node


# converter XML item to object


def set_additional_attributes(attribute_names, elm, node):
    if not isinstance(attribute_names, list):
        attribute_names = [attribute_names]
    for attributename in attribute_names:
        attribute = elm.attrib.get(attributename)
        if attribute is not None:
            # input expression can add a condition to either relevance (display) or calculate expression
            if attributename == "expression_inputs":
                attribute = [attribute]
            elif attributename == "instance":
                attribute = int(attribute)
            else:
                attribute
            setattr(node, attributename, attribute)




def get_select_options(diagram, select_node, nodes):
    options = {}
    i = 0
    list = get_mxcell_parent_list(diagram, select_node.external_id, TriccNodeType.select_option)
    options_name_list = []
    for elm in list:
        name = elm.attrib.get("name")
        if name in options_name_list and not name.endswith("_"):
            logger.critical(
                "Select question {0} have twice the option name {1}".format(
                    select_node.get_name(), name
                )
            )
        else:
            options_name_list.append(name)
        
        external_id = elm.attrib.get("id")
        id = get_id(external_id, diagram.attrib.get('id'))  
        option = TriccNodeSelectOption(
            id=id,
            label=elm.attrib.get("label"),
            name=name,
            select=select_node,
            list_name=select_node.list_name,
            activity=select_node.activity,
            group=select_node.group,
            )
        set_additional_attributes(["save", "relevance"], elm, option)
        load_expressions(option)
        options[i] = option
        nodes[id] = option
        i += 1
    if len(list) == 0:
        logger.critical("select {} does not have any option".format(select_node.label))
    else:
        return options

    ##TBR START


def get_max_version(dict):
    max_version = None
    for id, sim_node in dict.items():
        if max_version is None or max_version.version < sim_node.version:
            max_version = sim_node
    return max_version


def update_calc_version(calculates, name):
    if name in calculates and len(calculates[name]) > 1:
        ordered_list = sorted(list(calculates[name].values()), key=lambda x: x.path_len)
        i = 1
        len_max = len(calculates[name])
        for elm in ordered_list:
            elm.version = i
            elm.last = (i == len_max)
            i += 1


def get_max_named_version(calculates, name):
    max = 0
    if name in calculates:
        for node in calculates[name].values():
            if node.version > max:
                max = node.version
    return max



def inject_bridge_path(node, nodes):
    calc_id = generate_id()
    calc_name = "path_" + calc_id
    data = {
        "id": calc_id,
        "group": node.group,
        "activity": node.activity,
        "label": "path: " + node.get_name(),
        "name": calc_name,
        "path_len": node.path_len,
    }
    prev_nodes = [
        nodes[n.source]
        for n in list(
            filter(
                lambda x: (x.target == node.id or x.target == node)
                and x.source in nodes,
                node.activity.edges,
            )
        )
    ]
    if (
        sum(
            [
                (
                    0
                    if issubclass(
                        n.__class__, (TriccNodeDisplayCalculateBase, TriccNodeRhombus)
                    )
                    else 1
                )
                for n in prev_nodes
            ]
        )
        > 0
    ):  # and len(node.prev_nodes)>1:
        calc = TriccNodeDisplayBridge(**data)
    else:
        calc = TriccNodeBridge(**data)

    for e in node.activity.edges:
        if e.target == node.id:
            if e.source in node.activity.nodes and len(node.activity.nodes[e.source].next_nodes):
                set_prev_next_node(node.activity[e.source], node, edge_only=False, replaced_node=node)
            else:
                e.target = calc.id

    # add edge between bridge and node
    set_prev_next_node(calc, node, edge_only=True)

    node.path_len += 1
    return calc


def enrich_node(diagram, media_path, edge, node, activity, help_before=False):
    if edge.target == node.id:
        # get node and process type
        type, message = get_message(diagram, edge.source_external_id)
        if type is not None:
            if type == 'help':
                help = TriccNodeMoreInfo(
                    id=generate_id(),
                    name=f"{node.name}.more_info",
                    label=message,
                    parent=node,
                    required=None,
                )
                #node.help = message
                if help_before:
                    inject_node_before(help, node, activity)
                else:
                    set_prev_next_node(node, help, edge_only=True, activity=activity)
                    activity.nodes[help.id] = help
                return help, None

            if type in (TriccNodeType.start, TriccNodeType.activity_start):
                return True
            elif hasattr(node, type):
                if message is not None:
                    setattr(node, type, message)
                    return True, None
            else:
                logger.warning(
                    "A attribute box of type {0} and value {1} is attached to an object not compatible {2}".format(
                        type, message, node.get_name()
                    )
                )
                return False, None
        else:
            image, payload = get_image(diagram, media_path, edge.source_external_id)
            if image is not None:
                if hasattr(node, "image"):
                    node.image = image
                    return image, payload
                else:
                    logger.warning("image not supported for {} ".format(node.get_name()))
                    return None, None
            else:
                logger.warning(f"edge from an unsuported node {edge.source_external_id}")
                
            return None, None


get_style_dict = lambda style: dict(item.split('=', 1) for item in style.split(';') if '=' in item)


def severity_from_color(color):  
    if color == '#fff2cc':
        return 'moderate'
    elif color == '#f8cecc':
        return 'severe'
    else:
        return 'light'
    


def add_tricc_base_node(
    diagram, nodes, type, list, group, attributes=[], mandatory_attributes=[], has_options=None
):
    for elm in list:
        external_id = elm.attrib.get("id")
        id = get_id( external_id,  diagram.attrib.get("id"))
        parent = elm.attrib.get("parent")    
        node = type(
            external_id=external_id,
            id=id,
            #parent=parent,
            group=group,
            activity=group,
            **set_mandatory_attribute(elm, mandatory_attributes, diagram),
        )
        if has_options:
            node.options = get_select_options(diagram, node, nodes)
            for o in node.options:
                nodes[node.options[o].id] = node.options[o]
        elif type == TriccNodeSelectNotAvailable:
            node.options = get_select_not_available_options(node, group, node.label)
            node.label = NO_LABEL
            nodes[node.options[0].id] = node.options[0]
        elif type == TriccNodeSelectYesNo:
            node.list_name = "yes_no"
            node.options = get_select_yes_no_options(node, group)
            nodes[node.options[0].id] = node.options[0]
            nodes[node.options[1].id] = node.options[1]
        elif type == TriccNodeProposedDiagnosis and getattr(node, 'severity', '') == None:
            mxcell = get_mxcell(diagram, external_id)
            styles = get_style_dict(mxcell.attrib.get('style',''))
            if 'fillColor' in styles and styles['fillColor'] != 'none':
                node.severity = severity_from_color(styles['fillColor'])
            
    
                
        set_additional_attributes(attributes, elm, node)
        load_expressions(node)
        nodes[id] = node


def load_expressions(node):
    if getattr(node, 'expression', None):
        node.expression = parse_expression('', node.expression)
    if getattr(node, 'relevance', None):
        node.relevance = parse_expression('', node.relevance)
    if getattr(node, 'default', None):
        node.default = parse_expression('', node.default)
    if getattr(node, 'reference', None):
        if isinstance(node, TriccNodeRhombus):
            node.label = remove_html(node.label)
            node.expression_reference = parse_expression(node.label, node.reference)
        else:
            node.expression_reference = parse_expression('', node.reference)
            
        node.reference = node.expression_reference.get_references()
    
        
        

def parse_expression(label=None, expression=None):
    if expression:
        ref_pattern = r'(\$\{[^\}]+\})'
            # only if simple ref
        if not re.search(ref_pattern, expression):
            operation = transform_cql_to_operation(expression, label)
            if isinstance(operation, TriccReference):
                if label:
                    if label[0] == '[' and label[-1] == ']':
                        operation = TriccOperation(
                            operator=TriccOperator.SELECTED,
                            reference=[
                                operation,
                                TriccReference(operation.value + label)
                            ]
                        )
                    else:
                        for operator in OPERATION_LIST:
                            if operator in label:
                                if operator == '==':
                                    operator = '='
                                terms = label.split(operator)
                                operation = transform_cql_to_operation(
                                    f"{expression} {operator} {terms[1].replace('?', '').strip()}",
                                    label
                                )
                                break
                # implied is true
                if isinstance(operation, TriccReference):
                     operation = TriccOperation(
                            operator=TriccOperator.ISTRUE,
                            reference=[
                                operation,
                            ]
                        )
                    
            else:
                pass

        else:
            operation = transform_cql_to_operation(
                expression.replace('${', '"').replace('}', '"'),
                label
            )
        
    if operation is None:
        logger.warning(f"unable to parse: {expression} ")
        return expression
    return operation
        

def set_mandatory_attribute(elm, mandatory_attributes, diagram=None):
    param = {}
    diagram_id = diagram.attrib.get('id')
    for attributes in mandatory_attributes:
        if attributes == 'name':
            name = elm.attrib.get("name")
            id = elm.attrib.get("id")
            attribute_value = _get_name(name, id, diagram_id)
        elif attributes == 'list_name':
            name = elm.attrib.get("name")
            id = elm.attrib.get("id")
            attribute_value = TRICC_LIST_NAME.format(clean_str(_get_name(name, id, diagram_id), replace_dots= True))
        else:   
            attribute_value = elm.attrib.get(attributes)
        if attribute_value is None:
            if elm.attrib.get("label") is not None:
                display_name = elm.attrib.get("label")
            elif elm.attrib.get("name") is not None:
                display_name = elm.attrib.get("name")
            else:
                display_name = elm.attrib.get("id")
                 
            if attributes == "source":
                if elm.attrib.get("target") is not None:
                    logger.critical(
                        "the attibute target is {}".format(elm.attrib.get("target"))
                    )
            elif attributes == "target":
                if elm.attrib.get("source") is not None:
                    logger.critical(
                        "the attibute target is {}".format(elm.attrib.get("source"))
                    )
            
            logger.critical(
                "the attibute {} is mandatory but not found in {} within group {}".format(
                    attributes, display_name, diagram.attrib.get('name') if diagram is not None else ""
                )
            )
            exit(1)
        if attributes == "link":
            param[attributes] = clean_link(attribute_value)
        elif attributes in ("parent", "id", "source", "target"):
            param[attributes] = attribute_value
        elif attribute_value is not None:
            param[attributes] = remove_html(attribute_value.strip())
    return param


def clean_link(link):
    # link have the format "data:page/id,DiagramID"
    link_parts = link.split(",")
    if link_parts[0] == "data:page/id" and len(link_parts) == 2:
        return link_parts[1]


def get_groups(diagram, nodes, parent_group):
    groups = {}
    list = get_tricc_type_list(diagram, "object", TriccNodeType.page)
    for elm in list:
        add_group(elm, diagram, nodes, groups, parent_group)
    return groups


def add_group(elm, diagram, nodes, groups, parent_group):
    external_id = elm.attrib.get("id")
    id = get_id(external_id, diagram.attrib.get("id"))
    if id not in groups:
        group = TriccGroup(
            name=elm.attrib.get("name"),
            label=elm.attrib.get("label"),
            id=id,
            external_id=external_id,
            group=parent_group,
        )
        # get elememt witn parent = id and tricc_type defiend
        list_child = get_tricc_type_list(
            diagram, ["object", "UserObject"], tricc_type=None, parent_id=id
        )
        add_group_to_child(group, diagram, list_child, nodes, groups, parent_group)
        if group is not None:
            groups[group.id] = group
        return group


def add_group_to_child(group, diagram, list_child, nodes, groups, parent_group):
    for child_elm in list_child:
        if child_elm.attrib.get("tricc_type") == TriccNodeType.container_hint_media:
            list_sub_child = get_tricc_type_list(
                diagram,
                ["object", "UserObject"],
                tricc_type=None,
                parent_id=child_elm.attrib.get("id"),
            )
            add_group_to_child(
                group, diagram, list_sub_child, nodes, groups, parent_group
            )
        elif child_elm.attrib.get("tricc_type") == TriccNodeType.page:
            child_group_id = child_elm.attrib.get("id")
            if not child_group_id in groups:
                child_group = add_group(child_elm, diagram, nodes, groups, group)
            else:
                child_group = groups[child_group_id]
            child_group.group = group
        else:
            child_id = child_elm.attrib.get("id")
            if child_id is not None and child_id in nodes:
                nodes[child_id].group = group


def get_image(diagram, path, id):
    elm = get_mxcell(diagram, id)
    if elm is not None:
        style = elm.attrib.get("style")
        file_name, payload = add_image_from_style(style, path)
        if file_name is not None:
            return file_name, payload
    return None, None


def add_image_from_style(style, path):
    image_attrib = None
    if style is not None and "image=data:image/" in style:
        image_attrib = style.split("image=data:image/")
    if image_attrib is not None and len(image_attrib)== 2:
        image_parts = image_attrib[1].split(",")
        if len(image_parts) == 2:
            payload = image_parts[1][:-1]
            image_name = hashlib.md5(payload.encode('utf-8')).hexdigest()
            path = os.path.join(path, "images")
            file_name = os.path.join(path, image_name + "." + image_parts[0])
            if not (
                os.path.isdir(path)
            ):  # check if it exists, because if it does, error will be raised
                # (later change to make folder complaint to CHT)
                os.makedirs(path, exist_ok=True)
            with open(file_name, "wb") as fh:
                fh.write(base64.decodebytes(payload.encode("ascii")))
                image_path = os.path.basename(file_name)
                return image_path, payload
    return None, None


def get_contained_main_node(diagram, id):
    list = get_mxcell_parent_list(diagram, id, media_nodes)
    if isinstance(list, List) and len(list) > 0:
        # use only the first one
        return list[0]


def get_message(diagram, id):
    elm = get_elm(diagram, id)
    if elm is not None:
        type = elm.attrib.get("odk_type")
        if type is not None:
            if type.endswith("-message"):
                type = type[:-8]
            return type, elm.attrib.get("label")
        # use only the first one
    return None, None


def get_edges(diagram):
    edges = []
    list = get_edges_list(diagram)
    for elm in list:
        external_id = elm.attrib.get("id")
        id = get_id(external_id, diagram.attrib.get("id"))
        edge = TriccEdge(
            id=id,
            **set_mandatory_attribute(
                elm, ["source", "parent", "target"], diagram
            ),
        )
        edge.source_external_id = edge.source
        edge.target_external_id = edge.target
        edge.source = get_id(edge.source,  diagram.attrib.get("id"))
        edge.target = get_id(edge.target,  diagram.attrib.get("id"))
        set_additional_attributes(["value"], elm, edge)
        if edge.value is not None:
            edge.value = remove_html(edge.value)
        edges.append(edge)
    return edges


## Process edges


def process_factor_edge(edge, nodes):
    factor = edge.value.strip()
    if factor != 1:
        return TriccNodeCalculate(
            id=edge.id,
            expression_reference=TriccOperation(TriccOperator.MULTIPLIED, [nodes[edge.source],TriccStatic(factor)]),
            reference=[nodes[edge.source]],
            activity=nodes[edge.source].activity,
            group=nodes[edge.source].group,
            label="factor {}".format(factor),
        )
    return None


def process_condition_edge(edge, nodes):
    label = edge.value.strip()
    node = nodes[edge.source]
    node_ref = f'"{nodes[edge.source].name}"'
    if '$this' in label:
        operation = parse_expression('', expression=label.replace('$this', node_ref ))
    else:
        operation = parse_expression(label, expression=node_ref)
    if operation and isinstance(operation, TriccOperation):
        # insert rhombus
        return TriccNodeRhombus(
            id=edge.id,
            expression_reference=operation,
            reference=operation.get_references(),
            path=nodes[edge.source],
            activity=nodes[edge.source].activity,
            group=nodes[edge.source].group,
            label=label
        )



        

def process_exclusive_edge(edge, nodes):
    error = None
    if issubclass(nodes[edge.source].__class__, TriccNodeCalculateBase):
        # insert Negate
        if not isinstance(nodes[edge.target], TriccNodeExclusive) or not isinstance(
            nodes[edge.source], TriccNodeExclusive
        ):
            return TriccNodeExclusive(
                id=edge.id,
                activity=nodes[edge.target].activity,
                group=nodes[edge.target].group,
            )
        else:
            error = "No after or before a exclusice/negate node"
    else:
        error = "label not after a yesno nor a calculate"
    if error is not None:
        logger.warning(
            "Edge between {0} and {1} with label '{2}' could not be interpreted: {3}".format(
                nodes[edge.source].get_name(),
                nodes[edge.target].get_name(),
                edge.value.strip(),
                error,
            )
        )
    return None


def process_yesno_edge(edge, nodes):
    if edge.value is None:
        logger.critical(
            "yesNo {} node with labelless edges".format(nodes[edge.source].get_name())
        )
        exit(1)
    label = edge.value.strip().lower()
    yes_option = None
    no_option = None
    for option in nodes[edge.source].options.values():
        if option.name == "1":
            yes_option = option
        else:
            no_option = option
    if label.lower() in TRICC_FOLLOW_LABEL:
        pass
    elif label.lower() in TRICC_YES_LABEL:
        edge.source = yes_option.id
    elif label.lower() in TRICC_NO_LABEL:
        edge.source = no_option.id
    else:
        logger.warning(
            "edge {0} is coming from select {1}".format(
                edge.id, nodes[edge.source].get_name()
            )
        )
