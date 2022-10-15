
import re
from gettext import gettext as _  # plurals: , ngettext as __

from tricc.converters.utils import OPERATION_LIST, clean_str
from tricc.models import *

#from babel import _

TRICC_SELECT_MULTIPLE_CALC_EXPRESSION = "count-selected(${{{0}}}) - number(selected(${{{0}}},'opt_none'))"
TRICC_SELECT_MULTIPLE_CALC_NONE_EXPRESSION = "selected(${{{0}}},'opt_none')"
TRICC_CALC_EXPRESSION = "${{{0}}}>0"
TRICC_EMPTY_EXPRESSION = "coalesce(${{{0}}},'') != ''"
TRICC_SELECTED_EXPRESSION = 'selected(${{{0}}}, "{1}")'
TRICC_REF_EXPRESSION = "${{{0}}}"
TRICC_NEGATE = "not({})"
TRICC_NUMBER = "number({})"
TRICC_NAND_EXPRESSION = '(({0}) and not({1}))'
TRICC_AND_EXPRESSION = '(({0}) and ({1}))'
VERSION_SEPARATOR = '_v_'
INSTANCE_SEPARATOR = "I_{0}_{1}"


import logging

logger = logging.getLogger("default")

def generate_xls_form_condition(node, processed_nodes, stashed_nodes, **kwargs):
    node.name = get_printed_name(node)
    if is_ready_to_process(node, processed_nodes, stashed_nodes,strict  =False):
        if node not in processed_nodes:
            if hasattr(node, 'name') and node.name is not None:
                node.name = clean_str(node.name)
            if isinstance(node, TriccNodeRhombus) and isinstance(node.reference, str):
                    logger.warning("node {} still using the reference string".format(node.get_name()))
                    
            if issubclass( node.__class__, TriccNodeInputModel):
                # we don't overright if define in the diagram
                if node.constraint is None:
                    if isinstance(node, TriccNodeSelectMultiple):
                        node.constraint = '.=\'opt_none\' or not(selected(.,\'opt_none\'))'
                        node.constraint_message = _('**None** cannot be selected together with choice.')
                elif node.odk_type in (TriccNodeType.integer, TriccNodeType.decimal):
                    constraints = []
                    constraints_message = []
                    if node.min is not None:
                            constraints.append('.>=' + node.min)
                            constraints_message.append( _("The minimun value is {0}.").format(node.min))
                    if node.max is not None:
                            constraints.append('.>=' + node.max)
                            constraints_message.append( _("The maximum value is {0}.").format(node.max))
                    if len(constraints)>0:   
                        node.constraint = ' and '.join(constraints)
                        node.constraint_message = ' '.join(constraints_message)
            #continue walk 
            return True
    return False

def generate_xls_form_relevance(node, processed_nodes, stashed_nodes, **kwargs):
    if is_ready_to_process(node, processed_nodes, stashed_nodes):
        if node not in processed_nodes:
            logger.debug('Processing relevance for node {0}'.format(node.get_name()))
            # if has prev, create condition
            if hasattr(node, 'relevance') and node.relevance is None :  
                node.relevance = get_node_expressions(node, processed_nodes)
                # manage not Available
                if isinstance(node, TriccNodeSelectNotAvailable):
                    #update the checkbox
                    if len(node.prev_nodes)==1:
                        parent_node = node.prev_nodes[0]
                        parent_empty = "${{{0}}}=''".format(parent_node.name)
                        if node.relevance is not None: 
                            TRICC_AND_EXPRESSION.format(node.relevance, parent_empty)
                        else:
                            node.relevance =  parent_empty
                        node.required = parent_empty
                        node.constraint = parent_empty
                        node.constraint_message = _("Cannot be selected with a value entered above")
                        #update the check box parent : create loop error
                        parent_node.required = None #"${{{0}}}=''".format(node.name)
                    else:
                        logger.warning("not available node {} does't have a single parent".format(node.get_name()))

            return True
    return False


def generate_xls_form_calculate(node, processed_nodes, stashed_nodes, **kwargs):
    if is_ready_to_process(node, processed_nodes, stashed_nodes):
        if node not in processed_nodes :
            logger.debug("generation of calculate for node {}".format(node.get_name()))
            if hasattr(node, 'expression') and (node.expression is None ):
                node.expression = get_node_expressions(node, processed_nodes)
                #continue walk 
            return True
    return False

#if the node is "required" then we can take the fact that it has value for the next elements
def get_required_node_expression(node):
    return TRICC_EMPTY_EXPRESSION.format(node.name)

# Get a selected option
def get_selected_option_expression(option_node):
    return TRICC_SELECTED_EXPRESSION.format(option_node.select.name,option_node.name )


# Function that add element to array is not None or ''
def add_sub_expression(array, sub):
    if sub is not None and sub not in array and sub != '':
        not_sub = TRICC_NEGATE.format(sub)
        if not_sub in array:
            # avoid having 2 conditions that are complete opposites
            array.remove(not_sub)
        else:
            array.append(sub)


# main function to retrieve the expression from the tree
# node is the node to calculate
# processed_nodes are the list of processed nodes

def get_node_expressions(node, processed_nodes):
    is_calculate =issubclass(node.__class__, TriccNodeCalculateBase)
    expression = None
    # in case of recursive call processed_nodes will be None
    if processed_nodes is None or is_ready_to_process(node, processed_nodes):
        expression = get_node_expression(node, processed_nodes, is_calculate)
    if is_calculate:
        if expression is not None and expression != '':
            expression = TRICC_NUMBER.format(expression)
        else:
            expression = ''
    if issubclass(node.__class__, TriccNodeCalculateBase) and expression == '':
        logger.warning("Calculate {0} returning no calcualtions".format(node.get_name()))
        expression = '1'
    return expression




def get_prev_node_expression(node, processed_nodes, is_calculate = False, excluded_name = None):
    expression = None
    
    #when getting the prev node, we calculate the  
    if hasattr(node, 'expression_inputs') and len(node.expression_inputs)>0:
        expression_inputs = node.expression_inputs
        clean_list_or(expression_inputs)
    else:
        expression_inputs = []
    for  prev_node in node.prev_nodes:

        if excluded_name is None or prev_node != excluded_name or  ( isinstance(excluded_name, str) and hasattr(prev_node,'name') and  prev_node.name != excluded_name):
            # the rumbus should calcualte only reference
            add_sub_expression(expression_inputs, get_node_expression(prev_node, processed_nodes, is_calculate, True))
            # avoid void is there is not conditions to avoid looping too much itme
    if len(expression_inputs)>0:
        clean_list_or(expression_inputs)
        expression =  ' or '.join(expression_inputs)
        expression_inputs = None
        #if isinstance(node,  TriccNodeExclusive):
        #    expression =  TRICC_NEGATE.format(expression)
    # only used for activityStart 
    if isinstance(node, TriccNodeActivity) and node.base_instance is not None:
        activity = node
        expression_inputs = []
        # relevance of the previous instance must be false to display this activity
        add_sub_expression(expression_inputs, get_node_expression(activity.base_instance, processed_nodes, False, True))
        for instance_nb, past_instance in activity.base_instance.instances.items():
            if int(past_instance.path_len) < int(activity.path_len):
                add_sub_expression(expression_inputs, get_node_expression(past_instance, processed_nodes, False, True))
        #clean_list_or(expression_inputs)
        expression_activity =  ' or '.join(expression_inputs)
        if expression_activity is not None and expression_activity != '':
            expression = TRICC_NAND_EXPRESSION.format(expression,expression_activity)         
    return expression

#calculate or retrieve a node expression
def get_node_expression(in_node,processed_nodes, is_calculate = False, is_prev = False, negate = False ):
    # in case of calculate we only use the select multiple if none is not selected
    expression = None
    negate_expression = None
    node = in_node
    if is_prev and isinstance(node, TriccNodeSelectOption):
       expression = get_selected_option_expression(node)
    elif is_prev  and isinstance(node, TriccNodeRhombus):
        right = get_node_expression(node.path,processed_nodes, is_calculate, is_prev  )
        if right != '1':
            expression = TRICC_AND_EXPRESSION.format(right, TRICC_CALC_EXPRESSION.format(node.name))
            negate_expression = TRICC_NAND_EXPRESSION.format(right, TRICC_CALC_EXPRESSION.format(node.name))
        else:
            expression = TRICC_CALC_EXPRESSION.format(node.name)
    elif is_prev  and issubclass(node.__class__, TriccNodeDisplayCalculateBase):
        expression = TRICC_CALC_EXPRESSION.format(node.name)
    elif issubclass(node.__class__, TriccNodeCalculateBase):
        if negate:
            negate_expression =  get_calculation_terms(node, processed_nodes, is_calculate, negate = True )
        else:
            expression =  get_calculation_terms(node, processed_nodes , is_calculate)
    elif is_prev  and hasattr(node,'required') and node.required == True:
        expression = get_required_node_expression(node) 
    elif is_prev and isinstance(node, TriccNodeActivity) and node.base_instance is not None:
        expression= get_activity_end_terms(node, processed_nodes)
    elif is_prev  and   hasattr(node, 'relevance') and node.relevance is not None and node.relevance != '':
            expression = node.relevance
    if expression is None:
        expression= get_prev_node_expression(node,processed_nodes,is_calculate)
    if negate:
        if negate_expression is not None:
            return negate_expression
        elif expression is not None:
            return TRICC_NEGATE.format(expression)
        else:
            logger.error("exclusive can not negate None from {}".format(node.get_name()))
            #exit()
    else:
        return expression

def get_activity_end_terms(node, processed_nodes):
    end_nodes = node.get_end_nodes()
    expression_inputs = []
    for end_node in end_nodes:
        add_sub_expression(expression_inputs, get_node_expression(end_node,processed_nodes, is_calculate = False, is_prev = True))
    expression_inputs = clean_list_or(expression_inputs)
    return ' or '.join(expression_inputs)


def get_calculation_terms(node, processed_nodes, is_calculate = False, negate = False):
    if isinstance(node, TriccNodeAdd):
        return get_add_terms(node,  False, negate)
    elif isinstance(node, TriccNodeCount):
        return get_count_terms(node, False, negate)
    elif isinstance(node, TriccNodeRhombus):
        return get_rhumbus_terms(node, processed_nodes, False, negate)
    elif isinstance(node, TriccNodeActivityStart):
        return get_prev_node_expression(node.activity, processed_nodes, is_calculate = False, excluded_name = None)
    elif isinstance(node, TriccNodeExclusive):
        if len(node.prev_nodes) == 1:
            if isinstance(node.prev_nodes[0], TriccNodeExclusive):
                logger.error("2 exclusives cannot be on a row")
                exit()
            elif issubclass(node.prev_nodes[0].__class__, TriccNodeCalculateBase):
                return get_node_expression(node.prev_nodes[0], processed_nodes, is_prev = True, negate=True) 
            elif isinstance(node.prev_nodes[0],TriccNodeActivity):
                return get_node_expression(node.prev_nodes[0], processed_nodes, is_calculate = False, is_prev=True, negate=True)
            else:
                logger.error("exclusive node {} does not depend of a calculate but on {}::{}".format(node.get_name(), node.prev_nodes[0].__class__,node.prev_nodes[0].get_name() ))
        else:
            logger.error("exclusive node {} has no ou too much parent".format(node.get_name()))
    elif negate:
        return TRICC_NEGATE.format(get_prev_node_expression(node,processed_nodes,is_calculate))
    else:
        return get_prev_node_expression(node, processed_nodes, is_calculate )
    
    
def process_rhumbus_expression(label, operation):
    if operation in label:
        terms = label.split(operation)
        if len(terms) == 2:
            if operation == '==':
                operation = operation[0]
            #TODO check if number
            return  operation + terms[1].replace('?','').strip()

def get_rhumbus_terms(node, processed_nodes, is_calculate= False, negate = False):
    expression = None
    left_term = None
    # calcualte the expression only for select muzltiple and fake calculate
    if  node.reference is not None and issubclass(node.reference.__class__, list):
            if node.expression_reference is None and len(node.reference) == 1:
                if node.label is not None:
                    for operation in OPERATION_LIST:
                        left_term =  process_rhumbus_expression( node.label, operation)
                        if left_term is not None:
                            break
                if left_term is None:
                    left_term = '>0'
                ref = node.reference[0]
                if issubclass(ref.__class__, TriccNodeBaseModel):
                    if isinstance(ref, TriccNodeActivity):
                        expression = get_activity_end_terms(ref, processed_nodes)
                    elif issubclass(ref.__class__, TriccNodeFakeCalculateBase):
                        expression = get_node_expression(ref, processed_nodes, is_calculate = True, is_prev = True)
                    else:
                        expression = TRICC_REF_EXPRESSION.format(ref.name)
                else: 
                    #expression = TRICC_REF_EXPRES
                    # SION.format(node.reference)
                    #expression = "${{{}}}".format(node.reference)
                    logger.error('reference {0} was not found in the previous nodes of node {1}'.format(node.reference, node.get_name()))
                    exit()
            elif node.expression_reference is not None and node.expression_reference != '':
                left_term=''
                expression = node.expression_reference.format(*get_list_names(node.reference))
            else:
                logger.warning("missing epression for node {}".format(node.get_name()))
    else:
        logger.error('reference {0} is not a list {1}'.format(node.reference, node.get_name()))
        exit()        

    if expression is not None :
       
        if  left_term is not None and re.search(" (\+)|(\-)|(or)|(and) ", expression):
            expression =  "({0}){1}".format(expression,left_term)
        else:
            expression =  "{0}{1}".format(expression,left_term)
    else:
        logger.error("Rhombus reference was not found for node {}, reference {}".format(
            node.get_name(),
            node.reference
        ))
        exit()
   
    return expression


def clean_list_or(list_or, elm_and = None):
    if 'false()' in list_or:
            list_or.remove('false()')
    if elm_and is not None:
        if TRICC_NEGATE.format(elm_and) in  list_or:
            # we remove x and not X
            list_or.remove(TRICC_NEGATE.format(elm_and))
        elif  elm_and in  list_or:
            # we remove  x and x
            list_or.remove(elm_and)
        else:
            for exp_prev in list_or:
                if re.search(exp_prev, ' and ') and exp_prev.replace('and ','and not' ) in list_or  :
                    right = exp_prev.split(' and ')[0]
                    list_or.remove(exp_prev)
                    list_or.remove(exp_prev.replace('and ','and not' ))
                    list_or.append(right)
                    
                if TRICC_NEGATE.format(exp_prev) == elm_and or exp_prev == elm_and :
                    list_or.remove(exp_prev)
                if TRICC_NEGATE.format(exp_prev) in list_or :
                    # if there is x and not(X) in an OR list them the list is always true
                    list_or = []
    return list_or
                
def get_printed_name(node):
    if issubclass(node.__class__, TriccNodeDiplayModel):
        node.gen_name()
        if not isinstance(node, TriccNodeSelectOption)\
            and not issubclass(node.__class__, TriccNodeDisplayCalculateBase)\
            and INSTANCE_SEPARATOR.format(node.instance,node.name) != node.name:
            return INSTANCE_SEPARATOR.format(node.instance, node.name)
    elif issubclass(node.__class__, TriccNodeCalculateBase):
        node.gen_name()
        if node.last == False\
                    and VERSION_SEPARATOR not in node.name:
        
            return node.name + VERSION_SEPARATOR + str(node.version)  
    return node.name
                
    
def get_add_terms(node, processed_nodes, is_calculate = False, negate = False): 
    if negate:
        logger.warning("negate not supported for Add node {}".format(node.get_name()))
    terms = []
    for prev_node in node.prev_nodes:
        if issubclass(prev_node, TriccNodeNumber) or isinstance(node, TriccNodeCount):
            terms.append("coalesce(${{{0}}},0)".format(prev_node.name))
        else:
            terms.append("number({0})".format(get_node_expression(prev_node, processed_nodes, is_calculate = False, is_prev = True)))
    if len(terms)>0:
        return  ' + '.join(terms)
            
def get_count_terms(node, processed_nodes, is_calculate, negate = False): 
    terms = []
    for prev_node in node.prev_nodes:
        if isinstance(prev_node, TriccNodeSelectMultiple):
            if negate:
                terms.append(TRICC_SELECT_MULTIPLE_CALC_NONE_EXPRESSION.format(prev_node.name))
            else:
                terms.append(TRICC_SELECT_MULTIPLE_CALC_EXPRESSION.format(prev_node.name))
        elif isinstance(prev_node, (TriccNodeSelectYesNo, TriccNodeSelectNotAvailable)):
            terms.append(TRICC_SELECTED_EXPRESSION.format(prev_node.name,'1'))
        elif isinstance(prev_node, TriccNodeSelectOption):
            terms.append(get_selected_option_expression(prev_node))
        else:
            if negate:
                terms.append("number(number({0})=0)".format(get_node_expression(prev_node, processed_nodes, is_calculate = False, is_prev = True)))
            else:
                terms.append("number({0})".format(get_node_expression(prev_node, processed_nodes, is_calculate= False, is_prev =  True)))
    if len(terms)>0:
        return  ' + '.join(terms)


def get_list_names(list):
    names = []
    for elm in list:
        if issubclass(elm.__class__, TriccNodeBaseModel):
            names.append(elm.name)
        elif isinstance(elm, str):
            names.append(elm)
    return names