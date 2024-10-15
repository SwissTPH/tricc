import logging
import re

from tricc_og.builders.utils import clean_name, remove_html
from tricc_og.models.lang import SingletonLangClass
from tricc_og.visitors.tricc_project import is_ready_to_process
from tricc_og.models.base import (
    TriccActivity,
    TriccOperation,
    TriccOperator,
    TriccStatic,
    TriccSCV,
    TriccBaseModel
    )
from tricc_og.models.paterns import TriccPaterns
from tricc_og.strategies.export.base_export_strategy import BaseExportStrategy
logger = logging.getLogger("default")

langs = SingletonLangClass()

TRICC_SELECT_MULTIPLE_CALC_EXPRESSION = (
    "count-selected(${{{0}}}) - number(selected(${{{0}}},'opt_none'))"
)
TRICC_SELECT_MULTIPLE_CALC_NONE_EXPRESSION = "selected(${{{0}}},'opt_none')"
TRICC_CALC_EXPRESSION = "${{{0}}}>0"
TRICC_CALC_NOT_EXPRESSION = "${{{0}}}=0"
TRICC_EMPTY_EXPRESSION = "coalesce(${{{0}}},'') != ''"
TRICC_SELECTED_EXPRESSION = 'selected(${{{0}}}, "{1}")'
TRICC_SELECTED_NEGATE_EXPRESSION = (
    'count-selected(${{{0}}})>0 and not(selected(${{{0}}}, "{1}"))'
)
TRICC_REF_EXPRESSION = "${{{0}}}"
TRICC_NEGATE = "not({})"
TRICC_NUMBER = "number({})"
TRICC_AND_EXPRESSION = "{0} and {1}"
VERSION_SEPARATOR = "_Vv_"
INSTANCE_SEPARATOR = "_Ii_"
NODE_ID = '7636'

def start_group(
    strategy, cur_group, groups, df_survey, df_calculate, relevance=False, **kargs
):
    name = cur_group.scv()
    if name in groups:
        groups[name] += 1
        name = name + INSTANCE_SEPARATOR + str(groups[name])

    else:
        groups[name] = 0
    relevance = None
    if hasattr(cur_group, "expression") and cur_group.expression:
        relevance = strategy.get_tricc_operation_expression(cur_group.expression)

    ## group
    values = []
    for column in SURVEY_MAP:
        if column == "type":
            values.append("begin group")
        elif column == "name":
            values.append(name)
        elif column == "appearance":
            values.append("field-list")
        elif column == "relevance":
            values.append(relevance)
        else:
            values.append(get_xfrom_trad(cur_group, column, SURVEY_MAP))
    df_survey.loc[len(df_survey)] = values


def end_group(cur_group, groups, df_survey, **kargs):

    values = []
    for column in SURVEY_MAP:
        if column == "type":
            values.append("end group")
        elif column == "relevance":
            values.append("")
        elif column in ("name"):
            value = get_attr_if_exists(cur_group, column, SURVEY_MAP)

            if get_export_name(cur_group) in groups:
                value = value + "_" + str(groups[get_export_name(cur_group)])
            values.append(value)
        else:
            values.append(get_xfrom_trad(cur_group, column, SURVEY_MAP))
    df_survey.loc[len(df_survey)] = values

    # waltk thought the node,
    # if node has group, open the group (and parent group)
    # check process the next_node with the same group first, then process the other

    # if node has another group (not current) close the group
    # if node is an activity close  the group

    # during tricc object building/ or par of the stategy
    # static calculte node with same name:
    # follow same approach as the dynamic
    # if reference not in used_saves
    #   , then create calculate node reference_1 # and save is used_saves 'reference' : 1
    # else create calculate node reference_(used_saves['reference']+1) # and update used_saves['reference'] += 1
    # once done, walkthrough again and remame  reference_(used_saves['reference']) to reference and create the other save


ODK_TRICC_TYPE_MAP = {
    TriccPaterns.activity_start: "calculate",
    TriccPaterns.process_start: "calculate",
    TriccPaterns.link_throw: "",  # should not be implemenbed
    TriccPaterns.link_catch: "",
    TriccPaterns.logic: "calculate",
    TriccPaterns.exclusive: "calculate",
    TriccPaterns.inclusive: "calculate",
    TriccPaterns.wait: "calculate",
    TriccPaterns.output: "calculate",
    TriccPaterns.escalated_end: "escalated_end",
    TriccPaterns.activity_end: "activity_end",
    TriccPaterns.calculate: "calculate",
    TriccPaterns.count: "count",
    TriccPaterns.add: "add",
    TriccPaterns.operation: "",
    TriccPaterns.note: "note",
    TriccPaterns.container_hint_media: "",
    TriccPaterns.hint: "hint",
    TriccPaterns.help: "help",
    TriccPaterns.select_multiple: "select_multiple",
    TriccPaterns.select_one: "select_one",
    TriccPaterns.select_yesno: "select_one",
    TriccPaterns.decimal: "decimal",
    TriccPaterns.integer: "integer",
    TriccPaterns.text: "text",
    TriccPaterns.date: "date",
    TriccPaterns.select_option: "",
    TriccPaterns.not_available: "",
    TriccPaterns.quantity: "",
}

GROUP_TRICC_TYPE = [TriccPaterns.process_start]

SURVEY_MAP = {
    "type": ODK_TRICC_TYPE_MAP,
    "name": "name",
    **langs.get_trads_map("label"),
    **langs.get_trads_map("hint"),
    **langs.get_trads_map("help"),
    "default": "default",
    "appearance": "appearance",
    "constraint": "constraint",
    **langs.get_trads_map("constraint_message"),
    "relevance": "relevance",
    "disabled": "disabled",
    "required": "required",
    **langs.get_trads_map("required_message"),
    "read only": "read only",
    "calculation": "expression",
    "repeat_count": "repeat_count",
    "media::image": "image",
}

OPERATOR_MAP = {
    "EQUAL" : '='
}

CHOICE_MAP = {"list_name": "list_name", "value": "name", **langs.get_trads_map("label")}


TRAD_MAP = ["label", "constraint_message", "required_message", "hint", "help"]



def get_xfrom_trad(node, column, maping, clean_html=False):
    arr = column.split("::")
    column = arr[0]
    trad = arr[1] if len(arr) == 2 else None
    value = get_attr_if_exists(node, column, maping)
    if clean_html and isinstance(value, str):
        value = remove_html(value)
    if column in TRAD_MAP:
        value = langs.get_trads(value, trad=trad)

    return value


def get_attr_if_exists(node, column, map_array):
    if column in map_array:
        mapping = map_array[column]
        if isinstance(mapping, Dict) and node.tricc_type in map_array[column]:
            tricc_type = map_array[column][node.tricc_type]
            if tricc_type[:6] == "select":
                return tricc_type + " " + node.list_name
            else:
                return tricc_type
        elif hasattr(node, map_array[column]):
            value = getattr(node, map_array[column])
            if column == "name":
                if issubclass(value.__class__, (TriccBaseModel)):
                    return get_export_name(value)
                else:
                    return get_export_name(node)
            elif value is not None:
                return str(value) if not isinstance(value, dict) else value
            else:
                return ""
        else:
            return ""
    elif hasattr(node, column) and getattr(node, column) is not None:
        value = getattr(node, column)
        return str(value) if not isinstance(value, dict) else value
    else:
        return ""


def generate_xls_form_export(
    G,
    node,
    processed_nodes,
    stashed_nodes,
    df_survey,
    df_choice,
    df_calculate,
    cur_group,
    **kargs,
):
    # check that all prev nodes were processed
    if is_ready_to_process(G, node, processed_nodes):
        if node not in processed_nodes:
            logger.debug("printing node {}".format(node.get_name()))
            # clean stashed node when processed
            if node in stashed_nodes:
                stashed_nodes.remove(node)
                logger.debug("generate_xls_form_export: unstashing processed node{} ".format(node.get_name()))
            if isinstance(node, TriccNodeSelectOption):
                values = []
                for column in CHOICE_MAP:
                    values.append(get_xfrom_trad(node, column, CHOICE_MAP, True ))
                # add only if not existing
                if len(df_choice[(df_choice['list_name'] == node.list_name) & (df_choice['value'] == node.name)])  == 0:
                    df_choice.loc[len(df_choice)] = values
            elif node.tricc_type in ODK_TRICC_TYPE_MAP and ODK_TRICC_TYPE_MAP[node.tricc_type] is not None:
                if ODK_TRICC_TYPE_MAP[node.tricc_type] =='calculate':
                    values = []
                    for column in SURVEY_MAP:
                        if column == 'default' and issubclass(node.__class__, TriccNodeDisplayCalculateBase):
                            values.append(0)
                        else:
                            values.append(get_xfrom_trad(node, column, SURVEY_MAP ))
                    if len(df_calculate[df_calculate.name == get_export_name(node)])==0:
                        df_calculate.loc[len(df_calculate)] = values
                    else:
                        logger.error("name {} found twice".format(node.name))
                    
                elif  ODK_TRICC_TYPE_MAP[node.tricc_type] !='':
                    values = []
                    for column in SURVEY_MAP:
                        values.append(get_xfrom_trad(node,column,SURVEY_MAP))
                    df_survey.loc[len(df_survey)] = values
                else:
                    logger.warning("node {} have an unmapped type {}".format(node.get_name(),node.tricc_type))
            else:
                logger.warning("node {} have an unsupported type {}".format(node.get_name(),node.tricc_type))
            #continue walk °
            return True
    return False
    
    


def get_diagnostic_line(node):
    label = langs.get_trads(node.label, force_dict=True)
    empty = langs.get_trads("", force_dict=True)
    return [
        "select_one yes_no",
        "cond_" + get_export_name(node),
        *list(label.values()),
        *list(empty.values()),  # hint
        *list(empty.values()),  # help
        "",  # default
        "",  #'appearance', clean_name
        "",  #'constraint',
        *list(empty.values()),  #'constraint_message'
        TRICC_CALC_EXPRESSION.format(get_export_name(node)),  #'relevance'
        "",  #'disabled'
        "1",  #'required'
        *list(empty.values()),  #'required message'
        "",  #'read only'
        "",  #'expression'
        "",  #'repeat_count'
        "",  #'image'
    ]


def get_diagnostic_start_group_line():
    label = langs.get_trads("List of diagnostics", force_dict=True)
    empty = langs.get_trads("", force_dict=True)
    return [
        "begin group",
        "l_diag_list25",
        *list(label.values()),
        *list(empty.values()),  # hint
        *list(empty.values()),  # help
        "",  # default
        "field-list",  #'appearance',
        "",  #'constraint',
        *list(empty.values()),  #'constraint_message'
        "",  #'relevance'
        "",  #'disabled'
        "",  #'required'
        *list(empty.values()),  #'required message'
        "",  #'read only'
        "",  #'expression'
        "",  #'repeat_count'
        "",  #'image'
    ]


def get_diagnostic_add_line(diags, df_choice):
    for diag in diags:
        df_choice.loc[len(df_choice)] = [
            "tricc_diag_add",
            get_export_name(diag),
            *list(langs.get_trads(diag.label, True).values()),
        ]
    label = langs.get_trads("Add a missing diagnostic", force_dict=True)
    empty = langs.get_trads("", force_dict=True)
    return [
        "select_multiple tricc_diag_add",
        "new_diag",
        *list(label.values()),
        *list(empty.values()),  # hint
        *list(empty.values()),  # help
        "",  # default
        "minimal",  #'appearance',
        "",  #'constraint',
        *list(empty.values()),  #'constraint_message',
        "",  #'relevance'
        "",  #'disabled'
        "",  #'required'
        *list(empty.values()),  #'required message'
        "",  #'read only'
        "",  #'expression'
        "",  #'repeat_count'
        "",  #'image'
    ]


def get_diagnostic_none_line(diags):
    relevance = ""
    for diag in diags:
        relevance += TRICC_CALC_EXPRESSION.format(get_export_name(diag)) + " or "
    label = langs.get_trads(
        "Aucun diagnostic trouvé par l'outil mais cela ne veut pas dire que le patient est en bonne santé",
        force_dict=True,
    )
    empty = langs.get_trads("", force_dict=True)
    return [
        "note",
        "l_diag_none25",
        *list(label.values()),
        *list(empty.values()),
        *list(empty.values()),
        "",  # default
        "",  #'appearance',
        "",  #'constraint',
        *list(empty.values()),
        negate_term(relevance[:-4]),  #'relevance'
        "",  #'disabled'
        "",  #'required'
        *list(empty.values()),
        "",  #'read only'
        "",  #'expression'
        "",  #'repeat_count'
        "",  #'image'  TRICC_NEGATE
    ]


def get_diagnostic_stop_group_line():
    label = langs.get_trads("", force_dict=True)
    return [
        "end group",
        "l_diag_list25",
        *list(label.values()),
        *list(label.values()),
        *list(label.values()),  # help
        "",  # default
        "",  #'appearance',
        "",  #'constraint',
        *list(label.values()),
        "",  #'relevance'
        "",  #'disabled'
        "",  #'required'
        *list(label.values()),
        "",  #'read only'
        "",  #'expression'
        "",  #'repeat_count'
        "",  #'image'
    ]


# if the node is "required" then we can take the fact that it has value for the next elements
def get_required_node_expression(node):
    return TRICC_EMPTY_EXPRESSION.format(get_export_name(node))


# Get a selected option
def get_selected_option_expression(option_node, negate):
    if negate:
        return TRICC_SELECTED_NEGATE_EXPRESSION.format(
            get_export_name(option_node.select), get_export_name(option_node)
        )
    else:
        return TRICC_SELECTED_EXPRESSION.format(
            get_export_name(option_node.select), get_export_name(option_node)
        )


# Function that add element to array is not None or ''
def add_sub_expression(array, sub):
    if sub is not None and sub not in array and sub != "":
        not_sub = negate_term(sub)
        if not_sub in array:
            # avoid having 2 conditions that are complete opposites
            array.remove(not_sub)
            array.append("true()")
        else:
            array.append(sub)
    elif sub is None:
        array.append("true()")


# function that make multipat  and
# @param argv list of expression to join with and
def and_join(argv):
    argv = add_bracket_to_list_elm(argv)
    if len(argv) == 0:
        return ""
    elif len(argv) == 1:
        raise ValueError("cannot have an and with only one operande")
    elif len(argv) == 2:
        return simple_and_join(argv[0], argv[1])
    else:
        return " and ".join(argv)


# function that make a 2 part and
# @param left part
# @param right part
def simple_and_join(left, right):
    expression = None

    # no term is considered as True
    left_issue = left is None or left == ""
    right_issue = right is None or right == ""
    left_neg = left == False or left == 0 or left == "0" or left == "false()"
    right_neg = right == False or right == 0 or right == "0" or right == "false()"
    if issubclass(left.__class__, (TriccSCV, TriccBaseModel)):
        left = get_export_name(left)
    if issubclass(right.__class__, (TriccSCV, TriccBaseModel)):
        right = get_export_name(right)

    if left_issue and right_issue:
        logger.error("and with both terms empty")
    elif left_neg or right_neg:
        return "false()"
    elif left_issue:
        logger.debug("and with empty left term")
        return right
    elif left == "1" or left == 1 or left == "true()":
        return right
    elif right_issue:
        logger.debug("and with empty right term")
        return left
    elif right == "1" or right == 1 or right == "true()":
        return left
    else:
        return f"{left} and {right}"


def or_join(list_or, elm_and=None):
    cleaned_list = clean_list_or(list_or, elm_and)
    if len(cleaned_list) == 1:
        return cleaned_list[0]
    if len(cleaned_list) > 1:
        return "(" + " or ".join(cleaned_list) + ")"


# function that make a 2 part NAND
# @param left part
# @param right part
def nand_join(left, right):
    # no term is considered as True
    left_issue = left is None or left == ""
    right_issue = right is None or right == ""
    left_neg = left == False or left == 0 or left == "0" or left == "false()"
    right_neg = right == False or right == 0 or right == "0" or right == "false()"
    if issubclass(left.__class__, (TriccSCV, TriccBaseModel)):
        left = get_export_name(left)
    if issubclass(right.__class__, (TriccSCV, TriccBaseModel)):
        right = get_export_name(right)
    if left_issue and right_issue:
        logger.error("and with both terms empty")
    elif left_issue:
        logger.debug("and with empty left term")
        return negate_term(right)
    elif left == "1" or left == 1 or left == "true()":
        return negate_term(right)
    elif right_issue:
        logger.debug("and with empty right term")
        return "false()"
    elif right == "1" or right == 1 or left_neg or right == "true()":
        return "false()"
    elif right_neg:
        return left
    else:
        return and_join([left, negate_term(right)])


# function that negate terms
# @param expression to negate
def negate_term(expression):
    if expression is None or expression == "":
        return "false()"
    elif expression == "false()":
        return "true()"
    elif expression == "true()":
        return "false()"

    elif is_single_fct("not", expression):
        return expression[4:-1]
    else:
        return TRICC_NEGATE.format((expression))


def safe_to_bool_logic(expression):
    if (
        " or " in expression
        or " and " in expression
        and not has_overall_brace(expression)
    ):
        return f"({expression})"
    return expression


def has_overall_brace(expression):
    expression = expression.strip()
    if not expression[0] == "(":
        return False
    if not expression[-1] == ")":
        return False
    count_braces = 1
    # ensure that the start brace don't close before the end
    for c in expression[1:-1]:
        if c == "(":
            count_braces += 1
        if c == ")":
            count_braces -= 1
        if count_braces == 0:
            return False
    return True


def is_single_fct(name, expression):
    if len(expression) > (len(name) + 2):
        return False
    if not expression.startswith(f"{name}("):
        return False
    elif not expression.endswith(f")"):
        return False
    count = 0
    for char in expression[4:-1]:
        if char == "(":
            count += 1
        elif char == ")":
            count += 1
        if count < 0:
            return False
    return True


# TODO need to be move in in strategy and generate TriccOpperation instead
# function that parse expression for rhombus
# @param list_or
# @param and elm use upst
def process_rhumbus_expression(label, operation):
    if operation in label:
        terms = label.split(operation)
        if len(terms) == 2:
            if operation == "==":
                operation = operation[0]
            # TODO check if number
            return operation + terms[1].replace("?", "").strip()


# function that generate remove unsure condition
# @param list_or
# @param and elm use upstream
def clean_list_or(list_or, elm_and=None):
    if len(list_or) == 0:
        return []
    if "false()" in list_or:
        list_or.remove("false()")
    if "1" in list_or or 1 in list_or or "true()" in list_or:
        list_or = ["true()"]
        return list_or
    if elm_and is not None:
        if negate_term(elm_and) in list_or:
            # we remove x and not X
            list_or.remove(negate_term(elm_and))
        if elm_and in list_or:
            # we remove  x and x
            list_or.remove(elm_and)
    for exp_prev in list_or:
        if negate_term(exp_prev) in list_or:
            # if there is x and not(X) in an OR list them the list is always true
            list_or = ["true()"]
        if elm_and is not None:
            if negate_term(elm_and) in list_or:
                # we remove x and not X
                list_or.remove(negate_term(elm_and))
            else:
                if (
                    re.search(exp_prev, " and ") in list_or
                    and exp_prev.replace("and ", "and not") in list_or
                ):
                    right = exp_prev.split(" and ")[0]
                    list_or.remove(exp_prev)
                    list_or.remove(exp_prev.replace("and ", "and not"))
                    list_or.append(right)

                if negate_term(exp_prev) == elm_and or exp_prev == elm_and:
                    list_or.remove(exp_prev)

    return add_bracket_to_list_elm(list_or)


def add_bracket_to_list_elm(list_terms):
    cleaned = []
    for elm in list_terms:
        cleaned.append(safe_to_bool_logic(elm))
    return cleaned


def get_export_name(node):
    if isinstance(node, (str, TriccSCV)):
        return clean_name(str(node))
    return clean_name(node.scv())


def get_list_names(list):
    names = []
    for elm in list:
        if issubclass(elm.__class__, (TriccSCV, TriccBaseModel)):
            names.append(get_export_name(elm))
        elif isinstance(elm, str):
            names.append(elm)
    return names

def convert_basic(node):
    name = clean_name(node.scv())
    label = node.label
    odk_type = node.type_scv.code
    return (name, label, odk_type)

def convert_note(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    df_survey.loc[len(df_survey)] = convert_generic(
        G, node, processed_nodes, strategy, df_survey,
        df_choices, **kwargs
    )
# Create helper to generate relevance from path in graph 
# for Activity end the relevance will be the expression if there is no expression 


def convert_calculate(G, node, processed_nodes, out_strategy, df_survey, **kwargs):
    name, label, odk_type = convert_basic(node)
    data_condition = convert_expression(node.expression, node.context, G, node, processed_nodes, out_strategy, **kwargs )

    df_survey.loc[len(df_survey)] = [
        odk_type,
        name,
        label,
        '',  # hint
        '',  # help
        '',  # default
        '',  # 'appearance', clean_name
        '',  # 'constraint', 
        '',  # 'constraint_message'
        '',  # 'relevance'
        '',  # 'disabled'
        '',  # 'required'
        '',  # 'required message'
        '',  # 'read only'
        data_condition,  # 'expression'
        '',  # 'repeat_count'
        ''  # 'image'  
    ]

def convert(
    G,
    node,
    processed_nodes,
    df_survey,
    df_choices,
    stashed_nodes,
    out_strategy,
    **kwargs
):
    if is_ready_to_process(G, node, processed_nodes, stashed_nodes):
        if NODE_ID in node.scv():
                pass
        if node.type_scv and node.type_scv.system + \
            '.'+node.type_scv.code in TRICC_BUILDERS:
            builder=node.type_scv.system +'.'+node.type_scv.code
            TRICC_BUILDERS[builder](G, node, processed_nodes, out_strategy, df_survey=df_survey, df_choices=df_choices)
            return True
        elif not node.type_scv:
            logger.error(f"{node.scv()}: missing type")
            exit()
        else:
            logger.error(f"{node.scv()}: no converter for {node.type_scv}")
            exit()

def get_value(processed_nodes, ref, strategy):

    if isinstance(ref, (TriccSCV)):
        svc = processed_nodes.get_latest_matching_str(
            ref.value.split('::')[0]
        )
        if svc == None :
            pass
        return strategy.get_tricc_operation_operand(svc)
    else:
        return strategy.get_tricc_operation_operand(ref)
#Move to base export strategy?   
def convert_expression(expression, activity, G, node, processed_nodes, out_strategy, **kwargs ):
    if isinstance(activity, TriccActivity) :
        activity_expression = get_relevance(
            G, activity, processed_nodes, out_strategy, **kwargs
        )
    else:
        activity_expression = None
    references = [
        convert_expression(
            exp,
            None,
            G,
            node, 
            processed_nodes, 
            out_strategy,
            **kwargs
        ) if isinstance(
                exp, 
                TriccOperation
        ) else get_value(processed_nodes, exp, out_strategy) for exp in expression.reference
    ]
    expression = out_strategy.OPERATOR_EXPORT[expression.operator](out_strategy, references)
    if activity_expression:
        return out_strategy.OPERATOR_EXPORT[TriccOperator.AND](out_strategy, [activity_expression, expression])
    else:
        return expression
    #  or f'{OPERATOR_MAP[operator]}' if not isinstance(exp, TriccStatic) else exp.value
    
#def get_latest_instance(expression, G, node, processed_nodes, **kwargs):
#    if isinstance(expression, TriccSCV):
#        return get_latest_matching_str(f"{expression.value}::")
#    else:
#        return str(exp)

def get_relevance(G, node, processed_nodes, strategy, **kwargs):
    expressions = [
        convert_expression(
            data['condition'],
            data['activity'],
            G,
            node,
            processed_nodes,
            strategy,
            **kwargs) for u, v, data in G.in_edges(node.scv(), data=True) if 'condition' in data
        ]
    
    applicability_condition = convert_expression(
                node.applicability,
                None,
                G,
                node,
                processed_nodes,
                strategy,
                **kwargs
        ) if node.applicability else None
    in_condition = or_join(expressions, elm_and=applicability_condition)
    if applicability_condition and in_condition:
        return and_join([applicability_condition, in_condition])
    elif in_condition:
        return in_condition
    elif applicability_condition:
        return applicability_condition

 
def convert_generic(
    G, node, processed_nodes, strategy, df_survey,
    df_choices, **kwargs
):
    name, label, odk_type = convert_basic(node)
    data_condition = get_relevance(
        G, node, processed_nodes, strategy, **kwargs
    )
    return [
        odk_type,
        name,
        label,
        '',  # hint
        '',  # help
        '',  # default
        '',  # 'appearance', clean_name
        '',  # 'constraint', 
        '',  # 'constraint_message'
        data_condition,  # 'relevance'
        '',  # 'disabled'
        '',  # 'required'
        '',  # 'required message'
        '',  # 'read only'
        '',  # 'expression'
        '',  # 'repeat_count'
        ''  # 'image'  
    ]
    

def convert_select_multiple(G, node, processed_nodes, strategy, df_survey,
        df_choices, **kwargs):
    survey_row = convert_generic(
        G, node, processed_nodes, strategy, df_survey,
        df_choices, **kwargs
    )
    list_name = add_options(node, df_choices)
    survey_row[0] = f"select_multiple list_{list_name}"
    df_survey.loc[len(df_survey)] = survey_row


def add_options(node, df_choices):
    list_name = node.attributes.get(
        'option_list_name',
        clean_name(node.scv(with_instance=False))
    )
    list_name_exists = len(df_choices[df_choices['list_name'] == list_name])
    if list_name_exists:
        return list_name
    options = [
        att for k, att in node.attributes.items() if k.startswith('options_') 
    ]
    for o in options:
        df_choices.loc[len(df_choices)] = [
            list_name,  # "list_name"
            o.code,  # "name"
            o.label,  # "label"
        ]

    return list_name

def add_yes_no_options(df_choices):
    list_name = 'yes_no'
    if len(df_choices[df_choices['list_name'] == list_name])> 0:
        for o in [(1, 'Yes'), (-1, 'No')]:
            df_choices.loc[len(df_choices)] = [
                list_name,  # "list_name"
                o[0],  # "name"
                o[1],  # "label"
            ]
    return list_name

def convert_select_one(G, node, processed_nodes, strategy, df_survey,
        df_choices, **kwargs):
    survey_row = convert_generic(
        G, node, processed_nodes, strategy, df_survey,
        df_choices, **kwargs
    )
    list_name = add_options(node, df_choices)
    survey_row[0] = f"select_multiple list_{list_name}"
    df_survey.loc[len(df_survey)] = survey_row


def convert_select_yesno(G, node, processed_nodes, strategy, df_survey,
        df_choices, **kwargs):
    survey_row = convert_generic(
        G, node, processed_nodes, strategy, df_survey,
        df_choices, **kwargs
    )
    list_name = add_yes_no_options(df_choices)
    survey_row[0] = f"select_multiple list_{list_name}"
    df_survey.loc[len(df_survey)] = survey_row



def convert_select_option(G, node, processed_nodes, strategy, df_choices, **kwargs):
    add_options(node, df_choices)


def convert_decimal(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    df_survey.loc[len(df_survey)] = convert_generic(
        G, node, processed_nodes, strategy, df_survey,
        df_choices, **kwargs
    )


def convert_integer(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    df_survey.loc[len(df_survey)] = convert_generic(
        G, node, processed_nodes, strategy, df_survey,
        df_choices, **kwargs
    )


def convert_text(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    df_survey.loc[len(df_survey)] = convert_generic(
        G, node, processed_nodes, strategy, df_survey,
        df_choices, **kwargs
    )


def convert_date(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    df_survey.loc[len(df_survey)] = convert_generic(
        G, node, processed_nodes, strategy, df_survey,
        df_choices, **kwargs
    )


def convert_rhombus(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass

def convert_goto(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass

def convert_start(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass

def convert_activity_start(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass

def convert_link_in(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass


def convert_link_out(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass


def convert_count(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass

def convert_add(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass

def convert_container_hint_media(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass

def convert_activity(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass


def convert_help_message(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass


def convert_hint_message(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass


def convert_not(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass


def convert_end(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass


def convert_activity_end(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass


def convert_edge(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass


def convert_page(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass


def convert_not_available(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass


def convert_quantity(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass


def convert_bridge(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass


def convert_wait(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass


def convert_operation(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass

def convert_context(G, node, processed_nodes, strategy, df_survey, df_choices, **kwargs):
    pass


TRICC_BUILDERS = {
    'tricc_type.note': convert_note,
    'tricc_type.calculate': convert_calculate,
    'tricc_type.output': convert_calculate,
    'tricc_type.select_multiple': convert_select_multiple,
    'tricc_type.select_one': convert_select_one,
    'tricc_type.select_yesno': convert_select_yesno,
    'tricc_type.select_option': convert_select_option,
    'tricc_type.decimal': convert_decimal,
    'tricc_type.integer': convert_integer,
    'tricc_type.text': convert_text,
    'tricc_type.date': convert_date,
    'tricc_type.rhombus': convert_rhombus,  # fetch data
    'tricc_type.goto': convert_goto,  #: start the linked activity within the target activity
    'tricc_type.start': convert_start,  #: main start of the algo
    'tricc_type.activity_start': convert_activity_start,  #: start of an activity (link in)
    'tricc_type.link_in': convert_link_in,
    'tricc_type.link_out': convert_link_out,
    'tricc_type.count': convert_count,  #: count the number of valid input
    'tricc_type.add': convert_add,  # add counts
    'tricc_type.container_hint_media': convert_container_hint_media,  # DEPRECATED
    'tricc_type.activity': convert_activity,
    'tricc_type.help': convert_help_message,
    'tricc_type.hint': convert_hint_message,
    'tricc_type.exclusive': convert_not,
    'tricc_type.end': convert_end,
    'tricc_type.activity_end': convert_activity_end,
    'tricc_type.edge': convert_edge,
    'tricc_type.page': convert_page,
    'tricc_type.not_available': convert_not_available,
    'tricc_type.quantity': convert_quantity,
    'tricc_type.bridge': convert_bridge,
    'tricc_type.wait': convert_wait,
    'tricc_type.operation': convert_operation,
    'tricc_type.context': convert_context,
}