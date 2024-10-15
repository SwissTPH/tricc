import logging
import networkx as nx
import re
from networkx.exception import NetworkXNoCycle, NetworkXNoPath, NetworkXError
from tricc_og.models.operators import TriccOperator
from tricc_og.models.base import to_scv_str

logger = logging.getLogger("default")

from tricc_og.builders.utils import remove_html, clean_str, generate_id
from tricc_og.models.base import (
    TriccMixinRef,
    TriccTask,
    TriccActivity,
    TriccContext,
    FlowType,
    TriccBaseModel,
    TriccOperation,
    TriccStatic,
    TriccSCV,
)
from tricc_og.models.tricc import TriccNodeType
from tricc_og.visitors.tricc_project import (
    get_element,
    get_elements,
    add_flow,
)

QUESTION_SYSTEM = "questions"
DIAGNOSE_SYSTEM = "diagnose"
ACTIVITY_END_SYSTEM = "ActivityEnd"
STAGE_SYSTEM = "step"
MANDATORY_STAGE = [
    "registration_step",
    "patient_data",
    "first_look_assessment_step",
    "complaint_category",
]



def import_mc_nodes(json_node, system, project, js_fullorder, start):
    if json_node["type"] == "QuestionsSequence":
        node = to_activity(json_node, system, project.graph)
        node.attributes['expended'] = False
    else:
        tricc_type = get_mc_tricc_type(json_node)
        node = to_node(
            json_node=json_node,
            tricc_type=tricc_type,
            system=system,
            project=project,
            graph=project.graph,
            js_fullorder=js_fullorder,
        )

    return node


def import_mc_flow_from_diagram(js_diagram, system, graph, start):
    context = TriccContext(label="basic questions", code="main", system=system)
    dandling = add_flow_from_instances(graph, js_diagram["instances"].values(), context)

    for n in dandling:
        add_flow(graph, context, start.scv(), n.scv())

def reference_to_code(node, reference):
    return [
        o.code for k, o in node.attributes.items() 
        if k.startswith('options_') and str(o.reference) == reference
    ][0]


def code_to_reference(node, code):
    return [
        o.reference for k, o in node.attributes.items() 
        if k.startswith('options_') and str(o.code) == code
    ][0]


def import_mc_flow_to_diagnose(json_node, system, project, start):
    diag = to_activity(json_node, system, project.graph, generate_end=False)
    diag.attributes['expended'] = False
    project.graph.add_node(diag.scv(), data=diag)
    diag.graph.add_node(diag.scv(), data=diag)
    diag = import_qs_inner_flow(json_node, system, project)
    if json_node["complaint_category"]:
        cc = get_element(
            project.graph, QUESTION_SYSTEM, str(json_node["complaint_category"])
        )
        condition = TriccOperation(TriccOperator.EQUAL)
        condition.append(TriccSCV(cc.scv(with_instance=False)))
        condition.append(TriccStatic(reference_to_code(cc, '1')))
        add_flow(project.graph, None, cc.scv(), diag.scv(), condition=condition)
    else:
        add_flow(project.graph, None, start.scv(), diag.scv())
    


def add_flow_from_instances(graph, instances, activity, white_list=None):
    dandling = set()
    for instance in instances:
        _to = get_element(graph, QUESTION_SYSTEM, instance["id"], white_list=white_list)
        _to_activity_end = None
        if isinstance(_to, TriccActivity) and _to == activity:
            _to_activity_end = get_element(graph, ACTIVITY_END_SYSTEM, instance["id"], white_list=white_list)

        _to = _to_activity_end if _to_activity_end else _to
        if no_forced_link(graph, _to):
            # if activity is a real activity then we add the edges on the activity level
            # else we add it on the main graph
            if instance["conditions"]:
                add_flow_from_condition(
                    graph, instance["conditions"], _to, activity, white_list=white_list
                )
            # add edge if no other edges
            else:
                dandling.add(_to)
    return dandling


def no_forced_link(graph, node):
    return not any(
        [
            "triage" in e[0] and ("conditions" not in e[2] or not e[2]["conditions"])
            for e in graph.in_edges(node.scv(), data=True)
        ]
    )


def get_node_list_from_instance(graph, instances, white_list=None):
    node_list = []
    for instance in instances:
        node = get_element(
            graph, QUESTION_SYSTEM, instance["id"], white_list=white_list
        )
        node_list.append((node.scv(), {"data": node}))
    return node_list


def add_flow_from_condition(
    graph, conditions, _to, activity, white_list=None, flow_type="SEQUENCE"
):
    for cond in conditions:
        _from = get_element(
            graph, QUESTION_SYSTEM, cond["node_id"], white_list=white_list
        )
        # if the node start fron the activity (start) but NOT inside the that activity
        _from_activity_end = None
        #if isinstance(_from, TriccActivity) and _from != activity:
        #    _from_activity_end = to_scv_str(ACTIVITY_END_SYSTEM, _from.code, _from.version, _from.instance)
        condition = None
        if not _from or "answer_id" not in cond:
            logger.error(f"node {cond['node_id']} not found")
        elif "answer_id" in cond:
            condition = TriccOperation(
                TriccOperator.EQUAL,
                ## Seems like with the else statement it has an infinite loop? why? FIXME
                [TriccSCV(_from.get_name()), TriccStatic(cond["answer_id"])] if not _from_activity_end else
                    [TriccSCV(_from_activity_end), TriccStatic(cond["answer_id"])]
            )
        add_flow(
            activity.graph if hasattr(activity, "graph") else graph,
            activity,
            _from_activity_end if _from_activity_end != None else _from, 
            _to,
            label=None,
            condition=condition,
            flow_type=flow_type,
        )


def import_qs_inner_flow(json_node, QUESTION_SYSTEM, project):
    start = project.graph.nodes[
        to_scv_str(
            QUESTION_SYSTEM,
            json_node['id'],
        )
    ]["data"]

    # get node from main graph
    i_nodes = get_node_list_from_instance(project.graph, json_node["instances"].values()) 
    # add node to internal graph
    start.graph.add_nodes_from(i_nodes)
    # create expression for output for QS
    if "conditions" in json_node:
        if json_node["value_format"] != "Boolean":
            logger.error(f"value_format {json_node['value_format']} is not supported")
            exit(-1)
        output = start.attributes['output']
        output.expression = add_expression_from_condition(start.graph, json_node['conditions'])
        # add flow to output
        add_flow_from_condition(
            start.graph,
            json_node["conditions"],
            output.scv(),
            start,
            flow_type="ASSOCIATION",
        )
    dangling = add_flow_from_instances(
        start.graph,
        json_node["instances"].values(),
        start,
    )
    # attached the node that no "in" edges inside the QS
    # we assume they are the first node inside the QS 
    for n in dangling:
        add_flow(start.graph, start, start.scv(), n.scv())
    return start


def add_expression_from_condition(graph, conditions):
    expression_or = TriccOperation(TriccOperator.OR)
    expression = None
    for condition in conditions:
        expression = TriccOperation(TriccOperator.EQUAL)
        ref = get_elements(
            graph, QUESTION_SYSTEM, condition['node_id']
        )[-1]
        val = str(ref.attributes[f'options_{condition["answer_id"]}'].reference)
        if isinstance(ref, TriccActivity):
            ref_output = ref.attributes.get('output', None)
            if ref_output:
                ref = ref_output
        ref = TriccSCV(ref.scv())
        expression.append(ref)
        expression.append(val)
        if len(conditions) > 1:
            expression_or.append(expression)
    return expression_or if len(conditions) > 1 else expression


def get_start_node(project):
    start = TriccBaseModel(
        code="triage",
        system="cpg-common-processes",
        label="Start",
        type_scv=TriccMixinRef(system="tricc_type", code=str(TriccNodeType.start)),
    )
    project.graph.add_node(start.scv(), data=start)
    project.graph_process_start["main"] = [start]
    return start


def to_activity(json_node, system, graph, generate_end=True):
    node = TriccActivity(
        code=get_mc_name(json_node["id"]),
        system=system,
        label=json_node["label"][list(json_node["label"].keys())[0]],
        type_scv=TriccMixinRef(system="tricc_type", code=str(TriccNodeType.activity)),
    )
    graph.add_node(node.scv(), data=node)
    get_options(json_node, node, str(TriccNodeType.activity), system)
    generate_cut_off_exp(json_node, node)
    if generate_end:
        end = TriccBaseModel(
            code=get_mc_name(json_node["id"]),
            system=ACTIVITY_END_SYSTEM,
            label=json_node["label"][list(json_node["label"].keys())[0]],
            type_scv=TriccMixinRef(system="tricc_type", code="output"),
        )
        node.attributes['output'] = end
        node.graph.add_node(end.scv(), data=end)
        node.graph.add_node(node.scv(), data=node)
    return node


def get_mc_tricc_type(json_node):
    tricc_type = json_node.get("type", None)
    if tricc_type == "Question":
        if json_node["value_format"] == "Integer":
            tricc_type = TriccNodeType.integer
        elif json_node["value_format"] == "String":
            tricc_type = TriccNodeType.text
        elif json_node["value_format"] == "Date":
            tricc_type = TriccNodeType.date
        elif json_node["value_format"] == "Float":
            tricc_type = TriccNodeType.decimal
        elif "formula" in json_node and (
            "anwers" not in json_node or not json_node["anwers"]
        ):
            tricc_type = TriccNodeType.calculate
        else:
            tricc_type = TriccNodeType.select_one
    return tricc_type


def to_node(json_node, tricc_type, system, project, graph, js_fullorder):
    node = TriccBaseModel(
        code=get_mc_name(json_node["id"]),
        system=system,
        label=json_node["label"][list(json_node["label"].keys())[0]],
        type_scv=TriccMixinRef(system="tricc_type", code=str(tricc_type)),
    )
    generate_cut_off_exp(json_node, node)
    set_additional_attributes(
        node,
        json_node,
        ["is_mandatory", "type", "id", "description", "formula"],
    )
    context_code = get_context_from_fullorder(json_node["id"], js_fullorder)
    if not context_code:
        if "category" in json_node and json_node["category"]:
            context_code = json_node["category"]
        
    if context_code:
        node.context = project.get_context(STAGE_SYSTEM, context_code)
        get_options(json_node, node, tricc_type, system)
        graph.add_node(node.scv(), data=node)
    else:
        pass
    return node


def get_options(json_node, select_node, tricc_type, system):
    if "answers" in json_node and json_node["answers"]:
        i = 0
        for key, elm in json_node["answers"].items():
            label = elm['label']['en'] if isinstance(elm['label'], dict) else elm['label']
            option = TriccBaseModel(
                code=key,
                system=select_node.system,
                type_scv=TriccMixinRef(
                    system="tricc_type", code=str(TriccNodeType.select_option)
                ),
                label=label,
                reference=elm['reference']
            )
            set_additional_attributes(
                option,
                json_node,
                ["id", "type", "reference", "cut_off_start", "cut_off_end"],
            )
            select_node.attributes[f"options_{key}"] = option
            i += 1

def set_additional_attributes(node, json_node, attribute_names):
    if not isinstance(attribute_names, list):
        attribute_names = [attribute_names]
    for attributename in attribute_names:
        if attributename in json_node:
            if attributename == "is_mandatory":
                node.attributes["required"] = "1"
            if attributename == "description":
                node.attributes["help"] = json_node[attributename]
            elif json_node[attributename]:
                node.attributes[attributename] = json_node[attributename]


def get_mc_name(name):
    return f"{name}"


def get_context_from_fullorder(js_id, js_fullorder):
    return walkthrough_fullorder(
        js_fullorder,
        lambda data, context, value: context if str(data) == str(value) else None,
        value=js_id,
    )


def get_registration_nodes():
    js_nodes = {}
    js_nodes["first_name"] = {
        "id": "first_name",
        "label": {"en": "First Name", "fr": "Prénom"},
        "type": "Question",
        "category": "patient_data",
        "value_format": "String",
    }
    js_nodes["last_name"] = {
        "id": "last_name",
        "label": {"en": "Last Name", "fr": "Nom de famille"},
        "type": "Question",
        "category": "patient_data",
        "value_format": "String",
    }
    js_nodes["birth_date"] = {
        "id": "birth_date",
        "label": {"en": "Date of birth", "fr": "Date de naissance"},
        "type": "Question",
        "category": "patient_data",
        "value_format": "Date",
    }
    return js_nodes

def get_age_nodes():
    js_nodes = {}    
    js_nodes["age_day"] = {
        "id": "age_day",
        "label": {"en": "Age in days", "fr": "Age en jours"},
        "type": "Question",
        "category": "basic_demographic",
        "value_format": "Float",
        "formula":"ToDay"
    }
    js_nodes["age_month"] = {
        "id": "age_month",
        "label": {"en": "Age in Months", "fr": "age en mois"},
        "type": "Question",
        "category": "basic_demographic",
        "value_format": "Float",
        "formula":"ToMonth"
    }
    return js_nodes


def all_simple_paths(graph, start, end, cutoff=5, max_len=5):
    # return nx.all_simple_paths(graph,start,end,cutoff=5)
    paths = []
    current_path = ()
    get_simple_paths(graph, start, end, paths, current_path, cutoff, max_len)
    return paths


def get_simple_paths(graph, start, end, paths, current_path, cutoff, max_len=None):
    # get the egdes
    if max_len and len(paths) > max_len:
        return
    current_path = current_path + (start,)
    if any(e[1] == end for e in graph.out_edges(start)):
        current_path = current_path + (end,)
        paths.append(current_path)
    elif cutoff > 0:
        map(
            lambda n: get_simple_paths(graph, n, end, paths, current_path, cutoff - 1),
            graph.out_edges(start),
        )


def walkthrough_fullorder(js_fullorder, callback=None, **kwargs):
    # section name
    for context in js_fullorder:
        if isinstance(js_fullorder[context], dict):
            # for dict of id at level 1, each dict the titel as section and list of id as section value
            for sub in js_fullorder[context]:
                if isinstance(js_fullorder[context][sub], list):
                    for sub_sub in js_fullorder[context][sub]:
                        res = callback(sub_sub, context=f"{context}.{sub}", **kwargs)
                        if res:
                            return res
                else:
                    logger.error("unexpected format")
        elif isinstance(js_fullorder[context], list):
            # for list of dict of id at level 1, each dict having title and data
            for sub in js_fullorder[context]:
                if isinstance(sub, dict):
                    if "data" in sub:
                        for sub_sub in sub["data"]:
                            res = callback(
                                sub_sub, context=f"{context}.{sub['title']}", **kwargs
                            )
                            if res:
                                return res

                    else:
                        logger.error("unexpected format")
                # for list of id at level 1
                elif isinstance(sub, (str, int)):
                    res = callback(sub, context=context, **kwargs)
                    if res:
                        return res

        else:
            logger.error("unexpected format")


def fullorder_to_order(js_fullorder):
    order = []
    walkthrough_fullorder(
        js_fullorder, lambda data, context, order: order.append(str(data)), order=order
    )
    return order


### TODO tranlate it for

def add_age_calculation(json_node, dob):
    if json_node["formula"] == "ToMonth":
        op = TriccOperation(TriccOperator.AGE_MONTH)
        op.append(TriccSCV(dob.scv()))
    elif json_node["formula"] == "ToDay":
        op = TriccOperation(TriccOperator.AGE_DAY)
        op.append(TriccSCV(dob.scv()))
    else:
        logger.error("basic_demographic unrelated to age not supported")
        exit(-1)
    return op

def add_background_calculation_options(json_node, age_day, age_month, dob):
    # in a previous functions basic_demographic node should be identified (How to keep the old id ?) use a filter ? 
    #   toDay -> age_data
    #   toMonth -> age_month
    #   toYear -> age year
    # if not found must be created
    # here retrieve thos 3 nodes and replace all other ToMonth/toDay/toYear reference with the equivalent node
    op = None
    if json_node["category"] in (
        "basic_demographic"
    ) and 'formula' in json_node:
        op = add_age_calculation(json_node, dob)    
    else:
        op = TriccOperation(TriccOperator.IFS)
        for a in json_node["answers"].values():
            if "operator" in a:
                ref = get_formula_ref(json_node, age_day, age_month)
                if ref:  # Manage slices
                    op.append(get_answer_operation(ref, a))
                    # op.append(TriccStatic(str(a['id'])))
                elif "reference_table_x_id" in json_node:  # manage ZScore
                    x_node = None
                    y_node = None
                    z_node = None
                    # run the code only if there is data in the setup fields, case condition
                    opa_c = TriccOperation("exists")
                    if (
                        json_node["reference_table_x_id"] is not None
                        and json_node["reference_table_x_id"] != ""
                    ):
                        x_node = to_scv_str(
                            QUESTION_SYSTEM, json_node["reference_table_x_id"]
                        )
                        opa_c.append(x_node)
                    if (
                        json_node["reference_table_y_id"] is not None
                        and json_node["reference_table_y_id"] != ""
                    ):
                        y_node = to_scv_str(
                            QUESTION_SYSTEM, json_node["reference_table_y_id"]
                        )
                        opa_c.append(y_node)
                    if (
                        json_node["reference_table_z_id"] is not None
                        and json_node["reference_table_z_id"] != ""
                    ):
                        z_node = to_scv_str(
                            QUESTION_SYSTEM, json_node["reference_table_z_id"]
                        )
                        opa_c.append(z_node)

                    op.append(opa_c)
                    opa_v = None
                    if x_node and z_node:
                        opa_v = TriccOperation("izscore")
                        opa_v.append(TriccSCV(x_node))
                        opa_v.append(TriccSCV(z_node))
                    elif x_node and y_node:
                        opa_v = TriccOperation("zscore")
                        opa_v.append(TriccSCV(x_node))
                        opa_v.append(TriccSCV(y_node))
                    if opa_v:
                        op.append(opa_v)
                else:
                    raise NotImplementedError(
                        "opertaion not implemented, only slice and tables are"
                    )
                    exit(-1)
    return op


def get_formula_ref(json_node, node_age_day, node_age_month):
    if "formula" in json_node:
        if json_node["formula"] == "ToMonth" and node_age_month:
            return node_age_month.scv()
        elif json_node["formula"] == "ToDay" and node_age_day:
            return node_age_day.scv()
        elif json_node["formula"][0] == "[" and json_node["formula"][-1] == "]":
            return to_scv_str(QUESTION_SYSTEM, json_node["formula"][1:-1])
        else:
            logger.error(f"ref {json_node['formula']} not supported or not yet known")
            exit(-1)


def get_answer_operation(ref, a):
    opa = None
    val = a["value"].split(",")
    opa = TriccOperation(a["operator"])
    opa.append(TriccSCV(ref))
    expected_values = 1 + int(a["operator"] == "between")
    if len(val) != expected_values:
        raise ValueError(
            f"value for operator {a['operator']} in {a.id} needs {expected_values} values but {a['value']} found"
        )
    for v in val:
        opa.append(v)
    return opa


def generate_cut_off_exp(js_node, node):
    exp = []
    if "cut_off_start" in js_node or "cut_off_end" in js_node:
        if "cut_off_start" in js_node and js_node["cut_off_start"] is not None:
            cs = TriccOperation(TriccOperator.MORE_OR_EQUAL)
            cs.append(TriccSCV(to_scv_str(QUESTION_SYSTEM, "age_day")))
            cs.append(TriccStatic(js_node["cut_off_start"]))
            exp.append(cs)

        if "cut_off_end" in js_node and js_node["cut_off_end"] is not None:
            ce = TriccOperation(TriccOperator.LESS)
            ce.append(TriccSCV(to_scv_str(QUESTION_SYSTEM, "age_day")))
            ce.append(TriccStatic(js_node["cut_off_end"]))
            exp.append(ce)
    if exp:
        node.applicability = (
            TriccOperation(TriccOperator.OR, exp) if len(exp) > 1 else exp[0]
        )
