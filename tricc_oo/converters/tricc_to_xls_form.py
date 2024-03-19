from operator import attrgetter
import re

from tricc_oo.converters.utils import OPERATION_LIST, clean_str,clean_name
from tricc_oo.models import *

# from babel import _

TRICC_SELECT_MULTIPLE_CALC_EXPRESSION = "count-selected(${{{0}}}) - number(selected(${{{0}}},'opt_none'))"
TRICC_SELECT_MULTIPLE_CALC_NONE_EXPRESSION = "selected(${{{0}}},'opt_none')"
TRICC_CALC_EXPRESSION = "${{{0}}}>0"
TRICC_CALC_NOT_EXPRESSION = "${{{0}}}=0"
TRICC_EMPTY_EXPRESSION = "coalesce(${{{0}}},'') != ''"
TRICC_SELECTED_EXPRESSION = 'selected(${{{0}}}, "{1}")'
TRICC_REF_EXPRESSION = "${{{0}}}"
TRICC_NEGATE = "not({})"
TRICC_NUMBER = "number({})"
TRICC_NAND_EXPRESSION = '({0}) and not({1})'
TRICC_AND_EXPRESSION = '({0}) and ({1})'
VERSION_SEPARATOR = '_Vv_'
INSTANCE_SEPARATOR = "_Ii_"

import logging

logger = logging.getLogger("default")

# gettext language dict {'code':gettext}


# if the node is "required" then we can take the fact that it has value for the next elements
def get_required_node_expression(node):
    return TRICC_EMPTY_EXPRESSION.format(get_export_name(node))


# Get a selected option
def get_selected_option_expression(option_node):
    return TRICC_SELECTED_EXPRESSION.format(get_export_name(option_node.select), get_export_name(option_node))


# Function that add element to array is not None or ''
def add_sub_expression(array, sub):
    if sub is not None and sub not in array and sub != '':
        not_sub = negate_term(sub)
        if not_sub in array:
            # avoid having 2 conditions that are complete opposites
            array.remove(not_sub)
            array.append('true()')
        else:
            array.append(sub)
    elif sub is None:
        array.append('true()')
    


# function that make multipat  and
# @param argv list of expression to join with and
def and_join(argv):
    if len(argv) == 0:
        return ''
    elif len(argv) == 1:
        raise ValueError("cannot have an and with only one operande")
    elif len(argv) == 2:
        return simple_and_join(argv[0], argv[1])
    else:
        return '('+') and ('.join(argv)+')'

# function that make a 2 part and
# @param left part
# @param right part
def simple_and_join(left, right):
    expression = None

    # no term is considered as True
    left_issue = left is None or left == ''
    right_issue = right is None or right == ''
    left_neg = left == False or left ==0 or left =='0' or left =='false()'
    right_neg = right == False or right ==0 or right =='0' or right =='false()'
    if issubclass(left.__class__, TriccNodeBaseModel):
        left = get_export_name(left)
    if issubclass(right.__class__, TriccNodeBaseModel):
        right = get_export_name(right)    
    
    if left_issue and right_issue:
        logger.error("and with both terms empty")
    elif left_neg or right_neg:
        return 'false()'
    elif left_issue:
        logger.debug('and with empty left term')
        return  right
    elif left == '1' or left == 1 or left == 'true()':
        return  right
    elif right_issue:
        logger.debug('and with empty right term')
        return  left
    elif right == '1' or right == 1 or right == 'true()':
        return  left
    else:
        return     TRICC_AND_EXPRESSION.format((left), (right))

def or_join(list_or, elm_and=None):
    cleaned_list  = clean_list_or(list_or, elm_and)
    if len(cleaned_list)>0:
        return ' or '.join(cleaned_list)
    
    
# function that make a 2 part NAND
# @param left part
# @param right part
def nand_join(left, right):
    # no term is considered as True
    left_issue = left is None or left == ''
    right_issue = right is None or right == ''
    left_neg = left == False or left ==0 or left =='0' or left =='false()'
    right_neg = right == False or right ==0 or right =='0' or right =='false()'
    if issubclass(left.__class__, TriccNodeBaseModel):
        left = get_export_name(left)
    if issubclass(right.__class__, TriccNodeBaseModel):
        right = get_export_name(right) 
    if left_issue and right_issue:
        logger.error("and with both terms empty")
    elif left_issue:
        logger.debug('and with empty left term')
        return  negate_term(right)
    elif left == '1' or left == 1 or left == 'true()':
        return  negate_term(right)
    elif right_issue :
        logger.debug('and with empty right term')
        return  'false()'
    elif right == '1' or right == 1 or left_neg or right == 'true()':
        return  'false()'
    elif right_neg:
        return left
    else:
        return  TRICC_AND_EXPRESSION.format(left, negate_term(right))

# function that negate terms
# @param expression to negate
def negate_term(expression):
    if expression is None or expression == '':
        return 'false()'
    elif expression == 'false()':
        return 'true()'
    elif expression == 'true()':
        return 'false()'
 
    elif is_single_fct('not', expression):
        return expression[4:-1]
    else:
        return TRICC_NEGATE.format((expression))
    
def is_single_fct(name,expression):
    if len(expression)>len(name)+2:
        return False
    if not expression.startswith(f"{name}("):
        return False
    elif not expression.endswith(f")"):
        return False
    count = 0
    for char in expression[4:-1]:
        if char == '(':
            count += 1
        elif char == ')':
            count += 1
        if count < 0:
            return False
    return True

#TODO need to be move in in strategy and generate TriccOpperation instead
# function that parse expression for rhombus
# @param list_or
# @param and elm use upst
def process_rhumbus_expression(label, operation):
    if operation in label:
        terms = label.split(operation)
        if len(terms) == 2:
            if operation == '==':
                operation = operation[0]
            # TODO check if number
            return operation + terms[1].replace('?', '').strip()
        
# function that generate remove unsure condition
# @param list_or
# @param and elm use upstream
def clean_list_or(list_or, elm_and=None):
    if len(list_or) == 0:
        return []
    if 'false()' in list_or:
        list_or.remove('false()')
    if '1' in list_or or 1 in list_or or 'true()' in list_or:
        list_or = ['true()']
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
            list_or = ['true()']
        if elm_and is not None:
            if negate_term(elm_and) in list_or:
                # we remove x and not X
                list_or.remove(negate_term(elm_and))
            else:
                    if re.search(exp_prev, ' and ')  in list_or and exp_prev.replace('and ', 'and not') in list_or:
                        right = exp_prev.split(' and ')[0]
                        list_or.remove(exp_prev)
                        list_or.remove(exp_prev.replace('and ', 'and not'))
                        list_or.append(right)

                    if negate_term(exp_prev) == elm_and or exp_prev == elm_and:
                        list_or.remove(exp_prev)

    return list_or

def get_export_name(node):
    if isinstance(node, str):
        return clean_name("id_" + node) 
    if node.export_name is None:
        node.export_name = clean_name(node.name)
        if node.name is None:
            node.export_name= clean_name("id_" + node.id)
        elif not ( INSTANCE_SEPARATOR  in node.name or  VERSION_SEPARATOR in node.name):
            if issubclass(node.__class__, TriccNodeCalculateBase):
                node.gen_name()
                if node.last == False:
                    node.export_name = clean_name(node.name + VERSION_SEPARATOR + str(node.path_len))
                else:
                    node.export_name = clean_name(node.name)
            elif issubclass(node.__class__, (TriccNodeDisplayModel)):
                node.gen_name()
                if not isinstance(node, TriccNodeSelectOption) and node.activity.instance!=1:
                    node.export_name = clean_name(node.name +  INSTANCE_SEPARATOR + str(node.instance))
            #elif isinstance(node, TriccNodeActivityEnd):
            #    node.export_name =  clean_name(node.name +  INSTANCE_SEPARATOR + str(node.instance))
            elif isinstance(node,  TriccNodeActivityStart):
                node.export_name =  clean_name(node.name +  INSTANCE_SEPARATOR + str(node.instance))
    return (node.export_name )






def get_list_names(list):
    names = []
    for elm in list:
        if issubclass(elm.__class__, TriccNodeBaseModel):
            names.append(get_export_name(elm))
        elif isinstance(elm, str):
            names.append(elm)
    return names
