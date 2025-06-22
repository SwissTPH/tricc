from __future__ import annotations

import logging
import random
import string
from enum import Enum, auto
from typing import Dict, ForwardRef, List, Optional, Union, Set, Annotated

from pydantic import BaseModel, StringConstraints
from strenum import StrEnum

from tricc_oo.converters.utils import generate_id, get_rand_name
from tricc_oo.models.ordered_set import OrderedSet

logger = logging.getLogger("default")

Expression = Annotated[
    str,
    StringConstraints(pattern=r'^[^\\/\:]+$')
]

triccId = Annotated[
    str,
    StringConstraints(pattern=r'^[^\\/\: ]+$')
]

triccName = Annotated[
    str,
    StringConstraints(pattern=r'^[^\s]+( [^\s]+)*$')
]

b64 = Annotated[
    str,
    StringConstraints(pattern=r'^[^-A-Za-z0-9+/=]|=[^=]|={3,}$')
]


TriccEdge = ForwardRef('TriccEdge')
# data:page/id,UkO_xCL5ZjyshJO9Bexg


ACTIVITY_END_NODE_FORMAT = "aend_{}"
END_NODE_FORMAT = "end_{}"


class TriccNodeType(StrEnum):
    #replace with auto ? 
    note = 'note'
    calculate = 'calculate',
    output = 'output',
    select_multiple = 'select_multiple'
    select_one = 'select_one'
    select_yesno = 'select_one yesno'
    select_option = 'select_option'
    decimal = 'decimal'
    integer = 'integer'
    text = 'text'
    date = 'date'
    rhombus = 'rhombus'  # fetch data
    goto = 'goto'  #: start the linked activity within the target activity
    start = 'start'  #: main start of the algo
    activity_start = 'activity_start'  #: start of an activity (link in)
    link_in = 'link_in'
    link_out = 'link_out'
    count = 'count'  #: count the number of valid input
    add = 'add'  # add counts
    container_hint_media = 'container_hint_media'  # DEPRECATED
    activity = 'activity'
    help = 'help-message'
    hint = 'hint-message'
    exclusive = 'not'
    end = 'end'
    activity_end = 'activity_end'
    edge = 'edge'
    page = 'container_page'
    not_available = 'not_available'
    quantity = 'quantity'
    bridge = 'bridge'
    wait = 'wait'
    operation = 'operation'
    context = 'context'
    diagnosis = 'diagnosis'
    proposed_diagnosis = 'proposed_diagnosis'
    input = 'input'

    def __iter__(self):
        return iter(self.__members__.values())

    def __next__(self):
        return next(iter(self))



media_nodes = [
    TriccNodeType.note,
    TriccNodeType.select_multiple,
    TriccNodeType.select_one,
    TriccNodeType.decimal,
    TriccNodeType.integer,
    TriccNodeType.text,
]


class TriccBaseModel(BaseModel):
    id: triccId
    external_id: triccId = None
    tricc_type: TriccNodeType
    datatype: str = None
    instance: int = 0
    base_instance: Optional[TriccBaseModel] = None
    last: bool = None
    version: int = 1
    def get_datatype(self):
        return self.datatype or self.tricc_type
    
    def get_next_instance(self):
        if getattr(self, 'instances', None):
            return max(100, *[n.instance for n in self.instances.values()]) + 1
        if getattr(self, 'base_instance', None) and getattr(self.base_instance, 'instances', None):
            return max(100, *[n.instance for n in self.base_instance.instances.values()]) + 1
        return max(100,self.instance) + 1 
    
    def to_dict(self):
        return {key: value for key, value in vars(self).items() if not key.startswith('_')}

    def make_instance(self, nb_instance=None, **kwargs):
        if nb_instance == None:
            nb_instance = self.get_next_instance()
        instance = self.copy()
        attr_dict = self.to_dict()
        for attr, value in attr_dict.items():
            if not attr.startswith('_') and value is not None:
                try:
                    if hasattr(value, 'copy'):
                        setattr(instance, attr, value.copy())
                    else:
                        setattr(instance, attr, value)
                except Exception as e:
                    logger.warning(f"Warning: Could not copy attribute {attr}: {e}")
        
        # change the id to avoid collision of name
        instance.id = generate_id(f"{self.id}{nb_instance}")
        instance.instance = int(nb_instance)
        instance.base_instance = self
        if hasattr(self, 'instances'):
            self.instances[nb_instance] = instance
        
        
        # assign the defualt group
        # if activity is not None and self.group == activity.base_instance:
        #    instance.group = instance
        return instance

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.id == other.id
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        hash_value = hash(self.id)
        return hash_value

    def get_name(self):
        return self.id
    
    def __str__(self):
        return self.get_name()
    
    def __repr__(self):
        return f"{self.tricc_type}:{self.get_name()}({self.id})"
    
    def __init__(self, **data):
        if 'id' not in data:
            data['id'] = generate_id(str(data))
        super().__init__(**data)


class TriccEdge(TriccBaseModel):
    tricc_type: TriccNodeType = TriccNodeType.edge
    source: Union[triccId, TriccNodeBaseModel]
    source_external_id: triccId = None
    target: Union[triccId, TriccNodeBaseModel]
    target_external_id: triccId = None
    value: Optional[str]  = None



class TriccGroup(TriccBaseModel):
    tricc_type: TriccNodeType = TriccNodeType.page
    group: Optional[TriccBaseModel] = None
    name: Optional[str] = None
    export_name:Optional[str] = None
    label: Optional[Union[str, Dict[str,str]]] = None
    relevance: Optional[Union[Expression, TriccOperation]] = None
    path_len: int = 0
    prev_nodes: OrderedSet[TriccBaseModel] = OrderedSet()
    def __init__(self, **data):
        super().__init__(**data)
        if self.name is None:
            self.name = generate_id(str(data))

    def get_name(self):
        result = str(super().get_name())
        name =  getattr(self, 'name', None) 
        label =  getattr(self, 'label', None)
    
        if name:
            result = result + "::" + name
        if label:
            result = result + "::" + (
                next(iter(self.label.values())) if isinstance(self.label, Dict) else self.label
            )
        if len(name) < 50:
            return result
        else:
            return result[:50] 

FwTriccNodeBaseModel = ForwardRef('TriccNodeBaseModel')


class TriccNodeBaseModel(TriccBaseModel):
    path_len: int = 0
    group: Optional[Union[TriccGroup, FwTriccNodeBaseModel]] = None
    name: Optional[str] = None
    export_name: Optional[str] = None
    label: Optional[Union[str, Dict[str,str]]] = None
    next_nodes: OrderedSet[TriccNodeBaseModel] = OrderedSet()
    prev_nodes: OrderedSet[TriccNodeBaseModel] = OrderedSet()
    expression: Optional[Union[Expression, TriccOperation, TriccStatic]] = None  # will be generated based on the input
    expression_inputs: List[Expression] = []
    activity: Optional[FwTriccNodeBaseModel] = None
    ref_def: Optional[Union[int,str]]  = None# for medal creator

    class Config:
        use_enum_values = True  # <--
    
    def __hash__(self):
        return hash(self.id )

    # to be updated while processing because final expression will be possible to build$
    # #only the last time the script will go through the node (all prev node expression would be created    
    def get_name(self):
        result = self.__class__.__name__[9:]# str(super().get_name())
        name =  getattr(self, 'name', None) 
        label =  getattr(self, 'label', None)
    
        if name:
            result += name
        if label:
            result += "::" + (
                next(iter(self.label.values())) if isinstance(self.label, Dict) else self.label
            )
        if len(result) < 80:
            return result
        else:
            return result[:80]        
        


    def make_instance(self, instance_nb=None, activity=None):
        instance = super().make_instance(instance_nb)
        instance.group = activity
        if hasattr(self, 'activity') and activity is not None:
            instance.activity = activity
        next_nodes = OrderedSet()
        instance.next_nodes = next_nodes
        prev_nodes = OrderedSet()
        instance.prev_nodes = prev_nodes
        expression_inputs = []
        instance.expression_inputs = expression_inputs
        
        for attr in ['expression', 'relevance', 'default', 'reference', 'expression_reference']:
            if getattr(self, attr, None):
                setattr(instance, attr,  getattr(self, attr).copy())
        
        return instance

    def gen_name(self):
        if self.name is None:
            self.name = get_rand_name(self.id)
    def get_references(self):
        return OrderedSet()

class TriccStatic(BaseModel):
    value: Union[str, float, int, bool]
    def __init__(self,value):
        super().__init__(value = value)
        
    def get_datatype(self):
        if str(type(self.value)) == 'bool':
            return 'boolean'
        elif  str(self.value).isnumeric():
            return 'number'
        else:
            return str(type(self.value))
    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.value == other.value
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        hash_value = hash(self.value)
        return hash_value
    def get_name(self):
        return self.value
    
    def __str__(self):
        return str(self.value)
    
    def __repr__(self):
        return self.__class__.__name__+":"+str(type(self.value))+':' +str(self.value)

    def get_references(self):
        return OrderedSet()

class TriccReference(TriccStatic):
    value: str
    def __copy__(self):
        return type(self)(self.value)

    def copy(self):
        return self.__copy__()

    def get_references(self):
        return OrderedSet([self])


class TriccOperator(StrEnum):    
    AND = 'and' # and between left and rights
    ADD_OR =  'and_or' # left and one of the righs  
    OR = 'or' # or between left and rights
    NATIVE = 'native' #default left is native expression
    ISTRUE = 'istrue' # left is right 
    ISNOTTRUE = 'isnottrue' 
    ISFALSE = 'isfalse' # left is false
    ISNOTFALSE = 'isnotfalse' # left is false
    SELECTED = 'selected' # right must be la select and one or several options
    MORE_OR_EQUAL = 'more_or_equal'
    LESS_OR_EQUAL = 'less_or_equal'
    EQUAL = 'equal'
    MORE = 'more'
    NOTEQUAL = 'not_equal'
    BETWEEN = 'between'
    LESS = 'less'
    CONTAINS = 'contains' # ref, txt Does CONTAINS make sense, like Select with wildcard
    NOTEXISTS = 'notexists'
    EXISTS = 'exists'
    NOT = 'not'
    ISNULL = 'isnull'
    ISNOTNULL= 'isnotnull'

    CASE = 'case' # ref (equal value, res), (equal value,res)
    IFS = 'ifs' #(cond, res), (cond,res)
    IF = 'if' # cond val_true, val_false
    
    # CDSS Specific
    HAS_QUALIFIER = 'has_qualifier'
    
    ZSCORE = 'zscore' # left table_name, right Y, gender give Z
    IZSCORE = 'izscore' #left table_name, right Z, gender give Y
    AGE_DAY = 'age_day' # age from dob
    AGE_MONTH = 'age_month' # age from dob
    AGE_YEAR = 'age_year' # age from dob
    DIVIDED = 'divided'
    MULTIPLIED = 'multiplied'
    PLUS = 'plus'
    MINUS = 'minus'
    MODULO = 'modulo'
    COUNT = 'count'
    CAST_NUMBER = 'cast_number'
    CAST_INTEGER = 'cast_integer'
    DRUG_DOSAGE = 'drug_dosage' # drug name, *param1 (ex: weight, age)
    COALESCE = 'coalesce'
    CAST_DATE = 'cast_date'
    PARENTHESIS = 'parenthesis'
    CONCATENATE = 'concatenate'

RETURNS_BOOLEAN =[
    TriccOperator.ADD_OR,
    TriccOperator.AND,
    TriccOperator.OR,
    TriccOperator.BETWEEN,
    TriccOperator.CONTAINS,
    TriccOperator.EXISTS,
    TriccOperator.NOTEXISTS,
    TriccOperator.ISFALSE,
    TriccOperator.ISNOTFALSE,
    TriccOperator.ISNOTNULL,
    TriccOperator.ISTRUE,
    TriccOperator.ISNOTTRUE,
    TriccOperator.SELECTED,
    TriccOperator.HAS_QUALIFIER,
    TriccOperator.NOT,
    TriccOperator.NOTEQUAL,
    TriccOperator.MORE_OR_EQUAL,
    TriccOperator.LESS_OR_EQUAL,
    TriccOperator.EQUAL,
    TriccOperator.MORE,
    TriccOperator.LESS
]

RETURNS_NUMBER = [
    TriccOperator.AGE_DAY,
    TriccOperator.AGE_MONTH,
    TriccOperator.AGE_YEAR,
    TriccOperator.ZSCORE,
    TriccOperator.IZSCORE,
    TriccOperator.PLUS,
    TriccOperator.MINUS,
    TriccOperator.DIVIDED,
    TriccOperator.MULTIPLIED,
    TriccOperator.COUNT,
    TriccOperator.MODULO,
    TriccOperator.CAST_NUMBER,
    TriccOperator.CAST_INTEGER
]

RETURNS_DATE =[
    TriccOperator.CAST_DATE
]

OPERATION_LIST = {
    '>=': TriccOperator.MORE_OR_EQUAL,
    '<=': TriccOperator.LESS_OR_EQUAL,
    '==': TriccOperator.EQUAL,
    '!=': TriccOperator.NOTEQUAL,
    '=': TriccOperator.EQUAL,
    '>': TriccOperator.MORE,
    '<': TriccOperator.LESS
}  

class TriccOperation(BaseModel):
    tricc_type: TriccNodeType = TriccNodeType.operation
    operator: TriccOperator = TriccOperator.NATIVE
    reference: OrderedSet[
        Union[
            TriccStatic, TriccNodeBaseModel, TriccOperation, TriccReference, Expression,
            List[Union[TriccStatic, TriccNodeBaseModel, TriccOperation, TriccReference, Expression]]
        ]
    ] = []
    
    def __str__(self):
        str_ref = map(str, self.reference)
        return f"{self.operator}({', '.join(map(str, str_ref))})"
    
    def __hash__(self):
        return hash(self.__repr__())

    def __repr__(self):
        return "TriccOperation:"+self.__str__()
    
    def __eq__(self, other):
        return self.__str__() == str(other)
    
    def __init__(self, operator, reference=[]):
        super().__init__(operator=operator, reference=reference)
        
    def get_datatype(self):
        if self.operator in RETURNS_BOOLEAN:
            return 'boolean'
        elif self.operator in RETURNS_NUMBER:
            return 'number'
        elif self.operator in RETURNS_DATE:
            return 'date'
        elif self.operator == TriccOperator.CONCATENATE:
            return 'string'
        elif self.operator == TriccOperator.PARENTHESIS:
            return self.get_reference_datatype(self.reference)
        elif self.operator == TriccOperator.IF:
            return self.get_reference_datatype(self.reference[1:])
        elif self.operator in ( TriccOperator.IFS, TriccOperator.CASE):
            rtype = set()
            for rl in self.reference:
                rtype.add(self.get_reference_datatype(self.reference[-2:]))
            if len(rtype)>1:
                return 'mixed'
            else:
                return rtype.pop()     
  
    def get_reference_datatype(self, references):
        rtype = set()
        for r in references:
            if hasattr(r, 'get_datatype'):
                rtype.add(r.get_datatype())
            elif hasattr(r, 'value'):
                return str(type(r.value))
            else:
                return str(type(r))
            
            if len(rtype)>1:
                return 'mixed'
            else:
                return rtype.pop()         
        
    def get_references(self):
        predecessor = OrderedSet()
        if isinstance(self.reference, list):
            for reference in self.reference:
                self._process_reference(reference, predecessor)
        else:
            raise NotImplementedError("cannot find predecessor of a str")
        return predecessor
    
    def _process_reference(self, reference, predecessor):
        if isinstance(reference, list):
            for e in reference:
                self._process_reference(e, predecessor)
        elif isinstance(reference, TriccOperation):
            subs = reference.get_references()
            for s in subs:
                predecessor.add(s)
        elif issubclass(reference.__class__, (TriccNodeBaseModel, TriccReference)):
            predecessor.add(reference)

    def append(self, value):
        self.reference.append(value)
    def replace_node(self, old_node ,new_node):
        if isinstance(self.reference, list):
            for key in [i for i, x in enumerate(self.reference)]:
                self.reference[key] = self._replace_reference(self.reference[key], new_node, old_node) 
        elif self.reference is not None:
            raise NotImplementedError(f"cannot manage {self.reference.__class__}")

    def _replace_reference(self, reference, new_node, old_node):
        if isinstance(reference, list):
            for key in [i for i, x in enumerate(reference)]:
                reference[key] = self._replace_reference(reference[key], new_node, old_node)
        if isinstance(reference, TriccOperation):
            reference.replace_node(old_node ,new_node)
        elif issubclass(reference.__class__, (TriccNodeBaseModel, TriccReference)) and reference == old_node:
            reference = new_node
            # to cover the options
            if hasattr(reference, 'select') and hasattr(new_node, 'select') and issubclass(reference.select.__class__, TriccNodeBaseModel ) :
                self.replace_node(reference.select ,new_node.select)
        return reference
    
    def __copy__(self, keep_node=False):
        # Create a new instance
        if keep_node:
            reference = [e for e in self.reference]
        else:
            reference = [e.copy() if isinstance(e, (TriccReference, TriccOperation)) else (TriccReference(e.name) if hasattr(e, 'name') else e) for e in self.reference]
        
        
        new_instance = type(self)(
            self.operator, 
            reference
        )
        # Copy attributes (shallow copy for mutable attributes)
        
        return new_instance
    
    def copy(self, keep_node=False):
        return self.__copy__(keep_node)

# function that make multipat  and
# @param argv list of expression to join with and
def clean_and_list(argv):
    for a in list(argv):
        if isinstance(a, TriccOperation) and a.operator == TriccOperator.AND:
            argv.remove(a)
            return clean_and_list([*argv,*a.reference])
        elif a == TriccStatic(True) or a == True:
            argv.remove(a)
        elif a == TriccStatic(False) :
            return [TriccStatic(False)]
        
    internal = list(set(argv))
    for a in internal:
        for b in internal[internal.index(a)+1:]:
            if not_clean(b) == a:
                return [TriccStatic(False)]
    return sorted(list(set(argv)), key=str)
            
def not_clean(a):
    new_operator = None
    if a is None or isinstance(a, str) and a == '':
        return TriccStatic(False)
    elif isinstance(a, TriccStatic) and a == TriccStatic(False):
        return TriccStatic(True)
    elif isinstance(a, TriccStatic) and a == TriccStatic(True):
        return TriccStatic(False)
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.ISTRUE:
        new_operator = TriccOperator.ISNOTTRUE
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.ISNOTTRUE:
        new_operator = TriccOperator.ISTRUE
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.ISFALSE:
        new_operator = TriccOperator.ISNOTFALSE
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.ISNOTFALSE:
        new_operator = TriccOperator.ISFALSE
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.ISNULL:
        new_operator = TriccOperator.ISNOTNULL
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.ISNOTNULL:
        new_operator = TriccOperator.ISNULL
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.LESS:
        new_operator = TriccOperator.MORE_OR_EQUAL
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.MORE:
        new_operator = TriccOperator.LESS_OR_EQUAL
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.LESS_OR_EQUAL:
        new_operator = TriccOperator.MORE
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.MORE_OR_EQUAL:
        new_operator = TriccOperator.LESS
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.NOT:
        return a.reference[0]
    
    if new_operator:
        return TriccOperation(
            new_operator,
            a.reference
        )
    
    elif not isinstance(a, TriccOperation) and issubclass(a.__class__, object):
        return TriccOperation(
                operator=TriccOperator.NOTEXISTS,
                reference=[a]
            )
    else:
        return TriccOperation(
            TriccOperator.NOT,
            [a]
        )
        
    
      
# function that generate remove unsure condition
# @param list_or
# @param and elm use upstream
def clean_or_list(list_or, elm_and=None):
    if len(list_or) == 1:
        return list(list_or)
    if TriccStatic(True) in list_or:
        return [TriccStatic(True)]
    for a in list(list_or):
        if isinstance(a, TriccOperation) and a.operator == TriccOperator.OR:
            list_or.remove(a)
            return clean_or_list([*list_or,*a.reference])
        elif a == TriccStatic(False) or a == False or a == 0:
            list_or.remove(a)
        elif a == TriccStatic(True) or a == True or a == 1 or (elm_and is not None and not_clean(a) in list_or):
            return [TriccStatic(True)]
            # if there is x and not(X) in an OR list them the list is always true
        elif elm_and is not None and  (not_clean(a) == elm_and or a == elm_and ):
            list_or.remove(a)
    internal = list(list_or)    
    for a in internal:
        for b in internal[internal.index(a)+1:]:
            if not_clean(b) == a:
                return [TriccStatic(True)]
    if len(list_or) == 0:
        return []

    return sorted(list(set(list_or)), key=str)

def and_join(argv):
    argv=clean_and_list(argv)
    if len(argv) == 0:
        return ''
    elif len(argv) == 1:
        return argv[0]
    else:
        return  TriccOperation(
            TriccOperator.AND,
            argv
        )

# function that make a 2 part and
# @param left part
# @param right part
def simple_and_join(left, right):
    expression = None
    # no term is considered as True
    left_issue = left is None or left == ''
    right_issue = right is None or right == ''
    left_neg = not_clean(left)
    right_neg = not_clean(right)
    if left_issue and right_issue:
        logger.critical("and with both terms empty")
    elif left_neg == right or right_neg == left:
        return TriccStatic(False)
    elif left_issue:
        logger.debug('and with empty left term')
        return  right
    elif left == '1' or left == 1 or left == TriccStatic(True) or left is True:
        return  right
    elif right_issue:
        logger.debug('and with empty right term')
        return  left
    elif right == '1' or right == 1 or right == TriccStatic(True) or right is True:
        return  left
    else:
        return  TriccOperation(
            TriccOperator.AND,
            [left, right]
        )

def or_join(list_or, elm_and=None):
    cleaned_list  = clean_or_list(set(list_or), elm_and)
    if len(cleaned_list) == 1:
        return cleaned_list[0]
    elif len(cleaned_list)>1: 
        return TriccOperation(
            TriccOperator.OR,
            cleaned_list
        )
    else:
        logger.error("empty or list")
    
    
    
# function that make a 2 part NAND
# @param left part
# @param right part
def nand_join(left, right):
    # no term is considered as True
    left_issue = left is None or left == ''
    right_issue = right is None or right == ''
    left_neg = left == False or left == 0 or left == '0' or left == TriccStatic(False)
    right_neg = right == False or right == 0 or right == '0' or right == TriccStatic(False)
    if left_issue and right_issue:
        logger.critical("and with both terms empty")
    elif left_issue:
        logger.debug('and with empty left term')
        return  not_clean(right)
    elif left == '1' or left == 1 or left == TriccStatic(True):
        return  not_clean(right)
    elif right_issue :
        logger.debug('and with empty right term')
        return  TriccStatic(False)
    elif right == '1' or right == 1 or left_neg or right == TriccStatic(True):
        return  TriccStatic(False)
    elif right_neg:
        return left
    else:
        return  and_join([left, not_clean(right)])


TriccGroup.update_forward_refs()
TriccEdge.update_forward_refs()