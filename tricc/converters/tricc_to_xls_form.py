
import logging
from tricc.converters.utils import   clean_str
from tricc.converters.xml_to_tricc import is_ready_to_process
from tricc.models import *
from tricc.serializers.xls_form import CHOICE_MAP, ODK_TRICC_TYPE_MAP
from gettext import gettext as _ # plurals: , ngettext as __
#from babel import _

TRICC_SELECT_MULTIPLE_CALC_EXPRESSION = "count-selected(${{{0}}}) - number(selected(${{{0}}},'opt_none'))"
TRICC_SELECT_MULTIPLE_CALC_NONE_EXPRESSION = "selected(${{{0}}},'opt_none')"
TRICC_CALC_EXPRESSION = "${{{0}}}='1'"
TRICC_EMPTY_EXPRESSION = "coalesce(${{{0}}},'') != ''"
TRICC_SELECTED_EXPRESSION = 'selected(${{{0}}}, "{1}")'
TRICC_REF_EXPRESSION = "${{{0}}}"
TRICC_NEGATE = "not({})"
TRICC_NUMBER = "number({})"
TRICC_NAND_EXPRESSION = '({0}) and not({1})'

logger = logging.getLogger('default')

def generate_xls_form_condition(node, processed_nodes, **kwargs):
    if is_ready_to_process(node, processed_nodes) and node.id not in processed_nodes:
        logger.debug('Processing condition for node {0}'.format(node.get_name()))
        # generate condition
        if hasattr(node, 'name') and node.name is not None:
            node.name = clean_str(node.name)
        if hasattr(node, 'reference'):
            if isinstance(node.reference,str):
                node.reference = clean_str(node.reference)
                logger.warning("node  {} still usign the reference string".format(node.get_name()))
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
        processed_nodes[node.id]=node
        return True
    else:
        return False

def generate_xls_form_relevance(node, processed_nodes, **kwargs):
    if is_ready_to_process(node, processed_nodes) and node.id not in processed_nodes:
        logger.debug('Processing relevance for node {0}'.format(node.get_name()))
        # if has prev, create condition
        if hasattr(node, 'relevance') and node.relevance is None:  
            node.relevance = get_node_expressions(node, processed_nodes)
            # manage not Available
            if isinstance(node, TriccNodeSelectNotAvailable):
                #update the checkbox
                if len(node.prev_nodes)==1:
                    parent_node = node.prev_nodes[0]
                    parent_empty = "${{{0}}}=''".format(parent_node.name)
                    if node.relevance is not None: 
                        node.relevance += " and " + parent_empty
                    else:
                        node.relevance =  parent_empty
                    node.required = parent_empty
                    node.constraint = parent_empty
                    node.constraint_message = _("Cannot be selected with a value entered above")
                    #update the check box parent : create loop error
                    parent_node.required = None #"${{{0}}}=''".format(node.name)
                else:
                    logger.warning("not available node {} does't have a single parent".format(node.get_name()))
                
                
        processed_nodes[node.id]=node
        #continue walk
        return True
    else:
        return False


def generate_xls_form_calculate(node, processed_nodes, **kwargs):
    if is_ready_to_process(node, processed_nodes) and node.id not in processed_nodes :
        logger.debug("generation of calculate for node {}".format(node.get_name()))
        if hasattr(node, 'expression') and (node.expression is None ):
            if issubclass(node.__class__, TriccNodeCalculateBase):
                node.expression = get_node_expressions(node, processed_nodes, is_calculate = True)
               #continue walk 
        processed_nodes[node.id]=node
        return True
    else:
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
        not_sub = 'not({})'.format(sub)
        if not_sub in array:
            # avoid having 2 conditions that are complete opposites
            array.remove(not_sub)
        else:
            array.append(sub)


# main function to retrieve the expression from the tree
# node is the node to calculate
# processed_nodes are the list of processed nodes

def get_node_expressions(node, processed_nodes, is_calculate = False):
    expression = None
    # in case of recursive call processed_nodes will be None
    if hasattr(node,'prev_nodes') and (processed_nodes is None or is_ready_to_process(node, processed_nodes)):
        # for the calculate we 
        if not issubclass(node.__class__, TriccNodeCalculate):
            expression = get_node_expression(node, processed_nodes, is_calculate, processed_nodes)
        #fall back on required or on relevance if nothin found
        if expression is None:
                is_calculate = issubclass(node.__class__, TriccNodeCalculate)
                expression = get_prev_node_expression(node,processed_nodes)
    if is_calculate:
        if expression is not None and expression != '':
            expression = TRICC_NUMBER.format(expression)
        else:
            expression = ''
    return expression




def get_prev_node_expression(node, processed_nodes, excluded_name = None):
    expression = None
    #when getting the prev node, we calculate the  
    
    if hasattr(node, 'expression_inputs') and len(node.expression_inputs)>0:
        expression_inputs = node.expression_inputs
    else:
        expression_inputs = []

    for  prev_node in node.prev_nodes:
        if excluded_name is None or  hasattr(prev_node,'name') and prev_node.name != excluded_name:
            #we have to calculate all but the real calculate
            is_calculate = issubclass(node.__class__, TriccNodeCalculate) 
            add_sub_expression(expression_inputs, get_node_expression(prev_node, processed_nodes, is_calculate, True))
        # avoid void is there is not conditions to avoid looping too much itme
    if len(expression_inputs)>0:
        expression =  ' or '.join(expression_inputs)
        expression_inputs = None
        if isinstance(node,  TriccNodeExclusive):
            expression =  TRICC_NEGATE.format(expression)
    if isinstance(node, TriccNodeActivity) and node.base_instance is not None:
        activity = node
        expression_inputs = []
        add_sub_expression(expression_inputs, get_node_expression(activity.base_instance, processed_nodes, is_calculate, True))
        for instance_nb, past_instance in activity.base_instance.instances.items():
            if int(instance_nb) < int(activity.instance):
                add_sub_expression(expression_inputs, get_node_expression(past_instance, processed_nodes, is_calculate, True))
        expression_activity =  ' or '.join(expression_inputs)
        expression = TRICC_NAND_EXPRESSION.format(expression,expression_activity)         
    return expression

def get_node_expression(node,processed_nodes, is_calculate = False, is_prev = False, negate = False ):
    # in case of calculate we only use the select multiple if none is not selected
    expression = None
    negate_expression = None
    if is_calculate and isinstance(node, (TriccNodeSelectMultiple, TriccNodeSelectOne )):
        expression = TRICC_SELECT_MULTIPLE_CALC_EXPRESSION.format(node.name)
    elif is_calculate and isinstance(node, (TriccNodeSelectYesNo,TriccNodeSelectNotAvailable)):
        expression = TRICC_CALC_EXPRESSION.format(node.name)
    elif is_calculate  and  isinstance(node, TriccNodeActivityStart):
            expression = node.activity.relevance
    elif is_prev  and issubclass(node.__class__, TriccNodeDisplayCalculateBase):
        expression = '${{{0}}} = 1'.format(node.name)
    elif issubclass(node.__class__, TriccNodeCalculateBase):
        if negate:
            negate_expression =  get_calculation_terms(node, processed_nodes, negate = True )
        else:
            expression =  get_calculation_terms(node, processed_nodes )
    elif is_prev  and hasattr(node,'required') and node.required == True:
        expression = get_required_node_expression(node) 
    elif is_prev and isinstance(node, TriccNodeActivity) and node.base_instance is not None:
        expression = get_prev_node_expression(node, processed_nodes, excluded_name = "instances")
    elif is_prev  and   hasattr(node, 'relevance') and node.relevance is not None:
            expression = node.relevance
    elif isinstance(node, TriccNodeSelectOption):
       expression = get_selected_option_expression(node)


    if negate:
        if negate_expression is not None:
            return negate_expression
        elif expression is not None:
            return TRICC_NEGATE.format(expression)
        else:
            logger.error("exclusive can not negate None from {}".format(node.get_name()))
    else:
        return expression

    def get_activity_expression(activity):
        # for each activity before
        for instance_nb, past_instance in activity.base_instance.instances.items():
            if int(instance_nb) < int(activity.instance):
                
        # create an exclusive node
                exclusif = TriccNodeExclusive(
                    id = generate_id(),
                    group= activity,
                    name = 'exclude_activity_'   
                )
            # link excluisive node between activity before
                set_prev_next_node(past_instance, exclusif)
                set_prev_next_node(exclusif, activity)
    #same for main
        exclusif = TriccNodeExclusive(
                    id = generate_id(),
                    group= activity.base_instance,
                    name = 'exclude_activity_'   
            )
        activity.base_instance.nodes[exclusif.id]=exclusif
            # link excluisive node between activity before
        set_prev_next_node(activity.base_instance, exclusif)
        set_prev_next_node(exclusif, activity)


def get_calculation_terms(node, processed_nodes, is_calculate = False, negate = False):
    if isinstance(node, TriccNodeAdd):
        return get_add_terms(node, is_calculate, negate)
    elif isinstance(node, TriccNodeCount):
        return get_count_terms(node, is_calculate, negate)
    elif isinstance(node, TriccNodeRhombus):
        return get_rhumbus_terms(node, processed_nodes, is_calculate, negate)
    elif isinstance(node, TriccNodeExclusive):
        if len(node.prev_nodes) == 1:
            if issubclass(node.prev_nodes[0].__class__, TriccNodeDisplayCalculateBase):
                return get_node_expression(node.prev_nodes[0], processed_nodes, negate=True) 
            elif issubclass(node.prev_nodes[0].__class__, (TriccNodeFakeCalculateBase, TriccNodeSelect)):
                return  get_node_expression(node.prev_nodes[0], processed_nodes, is_calculate = True, negate=True)
            elif isinstance(node.prev_nodes[0],TriccNodeActivity):
                return get_node_expression(node.prev_nodes[0], processed_nodes, negate=True, is_prev=True)
            else:
                logger.error("exclusive node {} does not depend of a calculate".format(node.get_name()))
        else:
            logger.error("exclusive node {} has no ou too much parent".format(node.get_name()))
    elif negate:
        return TRICC_NEGATE.format(get_prev_node_expression(node,processed_nodes))
    else:
        return get_prev_node_expression(node )
    
    
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
    if node.label is not None:
        for operation in [ '>=', '<=', '==','=','>','<']:
            left_term =  process_rhumbus_expression(node.label, operation)
            if left_term is not None:
                break
    if left_term is None:
        left_term = '>0'
    # calcualte the expression only for select muzltiple and fake calculate
    if  node.reference is not None and issubclass(node.reference.__class__, TriccBaseModel):
        if issubclass(node.reference.__class__, TriccNodeFakeCalculateBase) or isinstance(node.reference, TriccNodeSelectMultiple):
            expression = get_node_expression(node.reference, processed_nodes, is_calculate = True, is_prev = True)
        else:
            expression = TRICC_REF_EXPRESSION.format(node.reference.name)
    else: 
        #expression = TRICC_REF_EXPRESSION.format(node.reference)
        #expression = "${{{}}}".format(node.reference)
        logger.error('reference {0} was not found in the previous nodes of node {1}'.format(node.reference, node.get_name()))
        exit()
    expression_prev = get_prev_node_expression(node,processed_nodes, node.reference )
    if expression is not None:
        expression =  "({0}){1}".format(expression,left_term)
    else:
        expression =  "({0}){1}".format(node.reference,left_term)
    if negate:
        expression = TRICC_NEGATE.format(expression)
    if expression_prev is not None:
        expression = "({} and ({}))".format(expression, expression_prev)
    return expression



        
   
def get_add_terms(node, processed_nodes, is_calculate = False, negate = False): 
    if negate:
        logger.warning("negate not supported for Add node {}".format(node.get_name()))
    terms = []
    for prev_node in node.prev_nodes:
        if issubclass(prev_node, TriccNodeNumber) or isinstance(node, TriccNodeCount):
            terms.append("coalesce(${{{0}}},0)".format(prev_node.name))
        else:
            terms.append("number({0})".format(get_node_expression(prev_node, processed_nodes, is_calculate, True)))
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
        else:
            if negate:
                terms.append("number(number({0})=0)".format(get_node_expression(prev_node, processed_nodes, is_calculate, True)))
            else:
                terms.append("number({0})".format(get_node_expression(prev_node, processed_nodes, is_calculate, True)))
    if len(terms)>0:
        return  ' + '.join(terms)


