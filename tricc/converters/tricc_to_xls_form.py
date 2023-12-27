from operator import attrgetter
import re

from tricc.converters.utils import OPERATION_LIST, clean_str,clean_name
from tricc.models.tricc import *

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

def generate_xls_form_condition(node, processed_nodes, **kwargs):
    if is_ready_to_process(node, processed_nodes, strict=False):
        if node not in processed_nodes:
            if issubclass(node.__class__, TriccRhombusMixIn) and isinstance(node.reference, str):
                logger.warning("node {} still using the reference string".format(node.get_name()))
            if issubclass(node.__class__, TriccNodeInputModel):
                # we don't overright if define in the diagram
                if node.constraint is None:
                    if isinstance(node, TriccNodeSelectMultiple):
                        node.constraint = '.=\'opt_none\' or not(selected(.,\'opt_none\'))'
                        node.constraint_message = '**None** cannot be selected together with choice.'
                elif node.tricc_type in (TriccNodeType.integer, TriccNodeType.decimal):
                    constraints = []
                    constraints_min = None
                    constraints_max = None
                    if node.min is not None:
                        constraints.append('.>=' + node.min) 
                        constraints_min= "The minimun value is {0}.".format(node.min)
                    if node.max is not None:
                        constraints.append('.>=' + node.max)
                        constraints_max="The maximum value is {0}.".format(node.max)
                    if len(constraints) > 0:
                        node.constraint = ' and '.join(constraints)
                        node.constraint_message = (constraints_min + " "  + constraints_max).strip()
            # continue walk
            return True
    return False


def generate_xls_form_relevance(node, processed_nodes, stashed_nodes, **kwargs):
    if is_ready_to_process(node, processed_nodes):
        if node not in processed_nodes:
            logger.debug('Processing relevance for node {0}'.format(node.get_name()))
            # if has prev, create condition
            if hasattr(node, 'relevance') and node.relevance is None:
                node.relevance = get_node_expressions(node, processed_nodes)
                # manage not Available
                if isinstance(node, TriccNodeSelectNotAvailable):
                    # update the checkbox
                    if len(node.prev_nodes) == 1:
                        parent_node = node.prev_nodes[0]
                        parent_empty = "${{{0}}}=''".format(get_export_name(parent_node))
                        node.relevance  = and_join(node.relevance, parent_empty)

                        node.required = parent_empty
                        node.constraint = parent_empty
                        node.constraint_message = "Cannot be selected with a value entered above"
                        # update the check box parent : create loop error
                        parent_node.required = None  # "${{{0}}}=''".format(node.name)
                    else:
                        logger.warning("not available node {} does't have a single parent".format(node.get_name()))

            return True
    return False


def generate_xls_form_calculate(node, processed_nodes, stashed_nodes, **kwargs):
    if is_ready_to_process(node, processed_nodes):
        if node not in processed_nodes:
            logger.debug("generation of calculate for node {}".format(node.get_name()))
            if hasattr(node, 'expression') and (node.expression is None) and issubclass(node.__class__,TriccNodeCalculateBase):
                node.expression = get_node_expressions(node, processed_nodes)
                # continue walk
            return True
    return False


# if the node is "required" then we can take the fact that it has value for the next elements
def get_required_node_expression(node):
    return TRICC_EMPTY_EXPRESSION.format(get_export_name(node))


# Get a selected option
def get_selected_option_expression(option_node):
    return TRICC_SELECTED_EXPRESSION.format(get_export_name(option_node.select), option_node.name)


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


# main function to retrieve the expression from the tree
# node is the node to calculate
# processed_nodes are the list of processed nodes

def get_node_expressions(node, processed_nodes):
    is_calculate = issubclass(node.__class__, TriccNodeCalculateBase)
    expression = None
    # in case of recursive call processed_nodes will be None
    if processed_nodes is None or is_ready_to_process(node, processed_nodes):
        expression = get_node_expression(node, processed_nodes, is_calculate)
    if is_calculate:
        if expression is not None and expression != '':
            expression = TRICC_NUMBER.format(expression)
        else:
            expression = ''
    if issubclass(node.__class__, TriccNodeCalculateBase) and expression == '' and not isinstance(node, (TriccNodeWait, TriccNodeActivityEnd, TriccNodeActivityStart)):
        logger.warning("Calculate {0} returning no calculations".format(node.get_name()))
        expression = 'true()'
    return expression


def get_prev_node_expression(node, processed_nodes, is_calculate=False, excluded_name=None):
    expression = None
    if node is None:
        pass
    # when getting the prev node, we calculate the
    if hasattr(node, 'expression_inputs') and len(node.expression_inputs) > 0:
        expression_inputs = node.expression_inputs
        expression_inputs = clean_list_or(expression_inputs)
    else:
        expression_inputs = []
    if isinstance(node, TriccNodeBridge) and node.label=='path: signe de danger >0  ?':
        logger.debug('hre')
    for prev_node in node.prev_nodes:
        if excluded_name is None or prev_node != excluded_name or (
                isinstance(excluded_name, str) and hasattr(prev_node, 'name') and prev_node.name != excluded_name): # or isinstance(prev_node, TriccNodeActivityEnd):
            # the rhombus should calculate only reference
            add_sub_expression(expression_inputs, get_node_expression(prev_node, processed_nodes, is_calculate, True))
            # avoid void is there is not conditions to avoid looping too much itme
    expression_inputs = clean_list_or(expression_inputs)
    
    expression = or_join(expression_inputs)
    expression_inputs = None
        # if isinstance(node,  TriccNodeExclusive):
        #    expression =  TRICC_NEGATE.format(expression)
    # only used for activityStart 
    if isinstance(node, TriccNodeActivity) and node.base_instance is not None:
        activity = node
        expression_inputs = []
        #exclude base node only if the defaulf instance number is not 0
        if activity.base_instance.instance >1:
            add_sub_expression(expression_inputs, get_node_expression(activity.base_instance, processed_nodes, False, True))
        # relevance of the previous instance must be false to display this activity
        for past_instance in activity.base_instance.instances.values():
            if int(past_instance.root.path_len) < int(activity.root.path_len) and past_instance in processed_nodes:
                add_sub_expression(expression_inputs, get_node_expression(past_instance, processed_nodes, False))         
        expression_activity = or_join(expression_inputs)
        expression = nand_join(expression, expression_activity or False)
    return expression


# calculate or retrieve a node expression
def get_node_expression(in_node, processed_nodes, is_calculate=False, is_prev=False, negate=False):
    # in case of calculate we only use the select multiple if none is not selected
    expression = None
    negate_expression = None
    node = in_node
    
    if is_prev and isinstance(node, TriccNodeSelectOption):
        expression = get_selected_option_expression(node)
        #TODO remove that and manage it on the "Save" part
    elif is_prev and isinstance(in_node, TriccNodeSelectNotAvailable):
        expression =  TRICC_SELECTED_EXPRESSION.format(get_export_name(node), 'true()')
    elif is_prev and isinstance(node, TriccNodeRhombus):
        if node.path is not None: 
            left = get_node_expression(node.path, processed_nodes, is_calculate, is_prev)
        else:
            left = 'true()'
        r_ref=get_rhombus_terms(node, processed_nodes)  # if issubclass(node.__class__, TricNodeDisplayCalulate) else TRICC_CALC_EXPRESSION.format(get_export_name(node)) #
        expression = and_join(left, r_ref)
        negate_expression = nand_join(left, r_ref)        
    elif isinstance(node, TriccNodeWait):
        if is_prev:
            # the wait don't do any calculation with the reference it is only use to wait until the reference are valid
            return get_node_expression(node.path, processed_nodes, is_calculate, is_prev)
        else:
            #it is a empty calculate
            return ''
    elif is_prev and issubclass(node.__class__, TriccNodeDisplayCalculateBase):
        expression = TRICC_CALC_EXPRESSION.format(get_export_name(node))
    elif issubclass(node.__class__, TriccNodeCalculateBase):
        if negate:
            negate_expression = get_calculation_terms(node, processed_nodes, is_calculate, negate=True)
        else:
            expression = get_calculation_terms(node, processed_nodes, is_calculate)
    elif is_prev and hasattr(node, 'required') and node.required == True:
        expression = get_required_node_expression(node)

    elif is_prev and hasattr(node, 'relevance') and node.relevance is not None and node.relevance != '':
            expression = node.relevance
    if expression is None:
            expression = get_prev_node_expression(node, processed_nodes, is_calculate)
    if isinstance(node, TriccNodeActivity) and is_prev:
        end_nodes = node.get_end_nodes()
        if all([end in processed_nodes for end in end_nodes]):
            expression = and_join(expression, get_activity_end_terms(node,processed_nodes))
    if negate:
        if negate_expression is not None:
            return negate_expression
        elif expression is not None:
            return negate_term(expression)
        else:
            logger.error("exclusive can not negate None from {}".format(node.get_name()))
            # exit()
    else:
        return expression
    
def and_join(*argv):
    if len(argv) == 0:
        return ''
    elif len(argv) == 2:
        return simple_and_join(argv[0], argv[1])
    else:
        return '('+') and ('.join(argv)+')'
    
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
        return     TRICC_AND_EXPRESSION.format(left, right)

def or_join(list_or, elm_and=None):
    cleaned_list  = clean_list_or(list_or, elm_and)
    if len(cleaned_list)>0:
        return ' or '.join(cleaned_list)

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
        return  TRICC_NAND_EXPRESSION.format(left, right)

def negate_term(expression):
    if expression is None or expression == '':
        return 'false()'
    elif expression == 'false()':
        return 'true()'
    elif expression == 'true()':
        return 'false()'
    else:
        return TRICC_NEGATE.format(expression)
    
    
def get_activity_end_terms(node, processed_nodes):
    end_nodes = node.get_end_nodes()
    expression_inputs = []
    for end_node in end_nodes:
        add_sub_expression(expression_inputs,
                           get_node_expression(end_node, processed_nodes, is_calculate=False, is_prev=True))

    return  or_join(expression_inputs)

# function that generate the calculation terms return by calculate node
# @param node calculate node to assess
# @param processed_nodes list of node already processed, importnat because only processed node could be use
# @param is_calculate used when this funciton is called in the evaluation of another calculate
# @param negate use to retriece the negation of a calculation
def get_calculation_terms(node, processed_nodes, is_calculate=False, negate=False):
    # returns something directly only if the negate is managed
    expresison = None
    if isinstance(node, TriccNodeAdd):
        return get_add_terms(node, False, negate)
    elif isinstance(node, TriccNodeCount):
        return get_count_terms(node, False, negate)
    elif isinstance(node, TriccNodeRhombus):
        return get_rhombus_terms(node, processed_nodes, False, negate)
    elif isinstance(node, ( TriccNodeWait)):
        # just use to force order of question
        expression = None
    # in case of calulate expression evaluation, we need to get the relevance of the activity 
    # because calculate are not the the activity group
    elif isinstance(node, (TriccNodeActivityStart)) and is_calculate:
        expresison =  get_prev_node_expression(node.activity, processed_nodes, is_calculate)
    elif isinstance(node, (TriccNodeActivityStart, TriccNodeActivityEnd)):
        # the group have the relevance for the activity, not needed to replicate it
        expression = None#return get_prev_node_expression(node.activity, processed_nodes, is_calculate=False, excluded_name=None)
    elif isinstance(node, TriccNodeExclusive):
        if len(node.prev_nodes) == 1:
            if isinstance(node.prev_nodes[0], TriccNodeExclusive):
                logger.error("2 exclusives cannot be on a row")
                exit()
            elif issubclass(node.prev_nodes[0].__class__, TriccNodeCalculateBase):
                return get_node_expression(node.prev_nodes[0], processed_nodes, is_prev=True, negate=True)
            elif isinstance(node.prev_nodes[0], TriccNodeActivity):
                return get_node_expression(node.prev_nodes[0], processed_nodes, is_calculate=False, is_prev=True,
                                           negate=True)
            else:
                logger.error("exclusive node {} does not depend of a calculate but on {}::{}".format(node.get_name(),
                                                                                                     node.prev_nodes[
                                                                                                         0].__class__,
                                                                                                     node.prev_nodes[
                                                                                                         0].get_name()))
        else:
            logger.error("exclusive node {} has no ou too much parent".format(node.get_name()))
    
    if node.reference is not None and node.expression_reference is not None :
        expression = get_prev_node_expression(node, processed_nodes, is_calculate)
        ref_expression = node.expression_reference.format(*[get_export_name(ref) for ref in node.reference])
        if expression is not None and expression != '':
            expression =  and_join(expression,ref_expression)
        else:
            expression = ref_expression
    else:
        expression =  get_prev_node_expression(node, processed_nodes, is_calculate)
    
    # manage the generic negation
    if negate:
        
        return negate_term(expression)
    else:
        return expresison


def process_rhumbus_expression(label, operation):
    if operation in label:
        terms = label.split(operation)
        if len(terms) == 2:
            if operation == '==':
                operation = operation[0]
            # TODO check if number
            return operation + terms[1].replace('?', '').strip()


def get_rhombus_terms(node, processed_nodes, is_calculate=False, negate=False):
    expression = None
    left_term = None
    # calcualte the expression only for select muzltiple and fake calculate
    if node.reference is not None and issubclass(node.reference.__class__, list):
        if node.expression_reference is None and len(node.reference) == 1:
            if node.label is not None:
                for operation in OPERATION_LIST:
                    left_term = process_rhumbus_expression(node.label, operation)
                    if left_term is not None:
                        break
            if left_term is None:
                left_term = '>0'
            ref = node.reference[0]
            if issubclass(ref.__class__, TriccNodeBaseModel):
                if isinstance(ref, TriccNodeActivity):
                    expression = get_activity_end_terms(ref, processed_nodes)
                elif issubclass(ref.__class__, TriccNodeFakeCalculateBase):
                    expression = get_node_expression(ref, processed_nodes, is_calculate=True, is_prev=True)
                else:
                    expression = TRICC_REF_EXPRESSION.format(get_export_name(ref))
            else:
                # expression = TRICC_REF_EXPRES
                # SION.format(node.reference)
                # expression = "${{{}}}".format(node.reference)
                logger.error('reference {0} was not found in the previous nodes of node {1}'.format(node.reference,
                                                                                                    node.get_name()))
                exit()
        elif node.expression_reference is not None and node.expression_reference != '':
            left_term = ''
            expression = node.expression_reference.format(*get_list_names(node.reference))
        else:
            logger.warning("missing epression for node {}".format(node.get_name()))
    else:
        logger.error('reference {0} is not a list {1}'.format(node.reference, node.get_name()))
        exit()

    if expression is not None:

        if left_term is not None and re.search(" (\+)|(\-)|(or)|(and) ", expression):
            expression = "({0}){1}".format(expression, left_term)
        else:
            expression = "{0}{1}".format(expression, left_term)
    else:
        logger.error("Rhombus reference was not found for node {}, reference {}".format(
            node.get_name(),
            node.reference
        ))
        exit()

    return expression


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


def get_add_terms(node, processed_nodes, is_calculate=False, negate=False):
    if negate:
        logger.warning("negate not supported for Add node {}".format(node.get_name()))
    terms = []
    for prev_node in node.prev_nodes:
        if issubclass(prev_node, TriccNodeNumber) or isinstance(node, TriccNodeCount):
            terms.append("coalesce(${{{0}}},0)".format(get_export_name(prev_node)))
        else:
            terms.append(
                "number({0})".format(get_node_expression(prev_node, processed_nodes, is_calculate=False, is_prev=True)))
    if len(terms) > 0:
        return ' + '.join(terms)


def get_count_terms(node, processed_nodes, is_calculate, negate=False):
    terms = []
    for prev_node in node.prev_nodes:
        if isinstance(prev_node, TriccNodeSelectMultiple):
            if negate:
                terms.append(TRICC_SELECT_MULTIPLE_CALC_NONE_EXPRESSION.format(get_export_name(prev_node)))
            else:
                terms.append(TRICC_SELECT_MULTIPLE_CALC_EXPRESSION.format(get_export_name(prev_node)))
        elif isinstance(prev_node, (TriccNodeSelectYesNo, TriccNodeSelectNotAvailable)):
            terms.append(TRICC_SELECTED_EXPRESSION.format(get_export_name(prev_node), '1'))
        elif isinstance(prev_node, TriccNodeSelectOption):
            terms.append(get_selected_option_expression(prev_node))
        else:
            if negate:
                terms.append("number(number({0})=0)".format(
                    get_node_expression(prev_node, processed_nodes, is_calculate=False, is_prev=True)))
            else:
                terms.append("number({0})".format(
                    get_node_expression(prev_node, processed_nodes, is_calculate=False, is_prev=True)))
    if len(terms) > 0:
        return ' + '.join(terms)


def get_list_names(list):
    names = []
    for elm in list:
        if issubclass(elm.__class__, TriccNodeBaseModel):
            names.append(get_export_name(elm))
        elif isinstance(elm, str):
            names.append(elm)
    return names
