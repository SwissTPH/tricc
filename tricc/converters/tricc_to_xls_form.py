
from tricc.models import *



def generate_xls_form_condition(node):
    # generate condition
    if issubclass( node.__class__, TriccNodeInputModel):
        # we don't overright if define in the diagram
        if node.constraint is None:
            if isinstance(node, TriccNodeSelectMultiple):
                node.constraint = '.=\'opt_none\' or not(selected(.,\'opt_none\'))'
                # TODO gettext
                node.constraint_message = '**None** cannot be selected together with choice.'
        elif node.odk_type in (TriccNodeType.integer, TriccNodeType.decimal):
            constraints = []
            constraints_message = []
            if node.min is not None:
                    constraints.append('.>=' + node.min)
                    constraints_message = "the minimun value is {0}.".format(node.min)
            if node.max is not None:
                    constraints.append('.>=' + node.max)
                    constraints_message = "the minimun value is {0}.".format(node.min)
            if len(constraints)>0:
                node.constraint = ' and '.join(constraints)
                node.constraint_message = ' '.join(constraints_message)

def generate_xls_form_relevance(node):
    # if has prev, create condition
    if hasattr(node, 'relevance') and (node.relevance is None or len(node.expression_inputs)>1 ):
        node.relevance = get_node_expressions(node)
        

def generate_xls_form_calculate(node):
    expressions= []
    if hasattr(node, 'expression') and (node.expression is None or len(node.expression_inputs)>1 ):
        if node.odk_type == TriccNodeType.calculate:
            input_expression = get_node_expressions(node)
            if input_expression is not None:
                add_sub_expression(expressions, "({})".format(input_expression))
        elif issubclass(node.__class__, TriccNodeCalculateBase):
            add_sub_expression(expressions, get_calculation_terms(node))
        if len(expressions)>0:
            node.expression = "number({0})".format( ' and '.join(expressions) )

    
def get_required_node_expression(node):
    return "coalesce(${{{0}}},'') != ''".format(node.name)

def get_selected_option_expression(option_node):
    return 'selected(${{{0}}}, "{1}")'.format(option_node.select.name,option_node.name )

def get_calculate_expressions(node):
    return '${{{0}}} = 1'.format(node.name)

def get_node_expressions(node):
    expression = None
    if hasattr(node,'prev_nodes') and len(node.prev_nodes)>0\
        and hasattr(node, 'expression_inputs'):
        # generate only if relevance is not set in the diagramm 
        for prev_node in node.prev_nodes:
        #   - IF OPTION, then use selected()
        #   - if calculate : ${name} == 1
        #   - for the rest, if required, check for empty value if not required, copy relevance
            add_sub_expression(node.expression_inputs,get_node_expression(prev_node))
        if len(node.expression_inputs)>0:
            expression =  ' or '.join(node.expression_inputs)
            if node.odk_type ==  TriccExtendedNodeType.exclusive:
                expression =  'not(' + expression  + ')'
            
        return expression

def get_node_expression(node):
    if node.odk_type == TriccExtendedNodeType.select_option:
       return get_selected_option_expression(node)
    elif issubclass(node.__class__, TriccNodeCalculateBase):
        return get_calculate_expressions(node)
    else:
        if hasattr(node,'required') and node.required == True:
            return get_required_node_expression(node)
        elif hasattr(node, 'relevance') and node.relevance is not None  :
            return node.relevance
        else:
            # get the expression form the parent (will be useful for the links)
            if node.odk_type not in (TriccExtendedNodeType.start, TriccExtendedNodeType.activity_start):
                return get_node_expressions(node)


def add_sub_expression(array, sub):
    if sub is not None and sub not in array:
        array.append(sub)

def get_calculation_terms(node):
    if isinstance(node, TriccNodeAdd):
        return get_add_terms(node)
    elif isinstance(node, TriccNodeCount):
        return get_count_terms(node)
    elif isinstance(node, TriccNodeRhombus):
        return get_rhumbus_terms(node)
    
    
def process_rhumbus_expression(label, operation):
    if operation in label:
        terms = label.split(operation)
        if len(terms) == 2:
            if operation == '==':
                operation = operation[1]
            #TODO check if number
            return  operation + terms[1].replace('?','').strip()
        
def get_rhumbus_terms(node):
    
    if node.label is not None:
        for operation in ['=','>','<', '>=', '<=', '==']:
            left_term =  process_rhumbus_expression(node.label, operation)
            if left_term is not None:
                return "number(${{{0}}}{1})=1".format(node.reference,left_term)
    return "number(${{{}}})=1".format(node.reference.strip())
         
        
def get_add_terms(node): 
    terms = []
    for prev_node in node.prev_nodes:
        if issubclass(prev_node, TriccNodeNumber) or isinstance(node, TriccNodeCount):
            terms.append("coalesce(${{{0}}},0)".format(prev_node.name))
        else:
            terms.append("number({0})".format(get_node_expression(prev_node)))
    if len(terms)>0:
        return  ' + '.join(terms)
            
def get_count_terms(node): 
    terms = []
    for prev_node in node.prev_nodes:
        terms.append("number({0})".format(get_node_expression(prev_node)))
    if len(terms)>0:
        return  ' + '.join(terms)


