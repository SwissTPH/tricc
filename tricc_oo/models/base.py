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
    instance: int = 1
    base_instance: Optional[TriccBaseModel] = None
    last: bool = None
    version: int = 1

    def make_instance(self, nb_instance, **kwargs):
        instance = self.copy()
        # change the id to avoid collision of name
        instance.id = generate_id()
        instance.instance = int(nb_instance)
        instance.base_instance = self

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
            data['id'] = generate_id()
        super().__init__(**data)


class TriccEdge(TriccBaseModel):
    tricc_type: TriccNodeType = TriccNodeType.edge
    source: Union[triccId, TriccNodeBaseModel]
    source_external_id: triccId = None
    target: Union[triccId, TriccNodeBaseModel]
    target_external_id: triccId = None
    value: Optional[str]  = None

    def make_instance(self, instance_nb, activity=None):
        instance = super().make_instance(instance_nb, activity=activity)
        #if issubclass(self.source.__class__, TriccBaseModel):
        instance.source = self.source if isinstance(self.source, str) else self.source.copy()
        #if issubclass(self.target.__class__, TriccBaseModel):
        instance.target = self.target if isinstance(self.target, str) else self.target.copy()
        return instance


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
            self.name = generate_id()

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
    expression: Optional[Union[Expression, TriccOperation]] = None  # will be generated based on the input
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
        result = str(super().get_name())
        name =  getattr(self, 'name', None) 
        label =  getattr(self, 'label', None)
    
        if name:
            result = result + "::" + name
        if label:
            result = result + "::" + (
                next(iter(self.label.values())) if isinstance(self.label, Dict) else self.label
            )
        if len(result) < 50:
            return result
        else:
            return result[:50]        
        


    def make_instance(self, instance_nb, activity=None):
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
        return OrderedSet([self])

class TriccStatic(BaseModel):
    value: Union[str, float, int, bool]
    def __init__(self,value):
        super().__init__(value = value)
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
        return "TriccStatic:"+str(type(self.value))+':' +str(self.value)

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
    ISFALSE = 'isfalse' # left is false
    SELECTED = 'selected' # right must be la select and one or several options
    MORE_OR_EQUAL = 'more_or_equal'
    LESS_OR_EQUAL = 'less_or_equal'
    EQUAL = 'equal'
    MORE = 'more'
    NOT_EQUAL = 'not_equal'
    BETWEEN = 'between'
    LESS = 'less'
    CASE = 'case' # ref (equal value, res), (equal value,res)
    IFS = 'ifs' #(cond, res), (cond,res)
    IF = 'if' # cond val_true, val_false
    CONTAINS = 'contains' # ref, txt Does CONTAINS make sense, like Select with wildcard
    EXISTS = 'exists'
    # CDSS Specific
    HAS_QUALIFIER = 'has_qualifier'
    ZSCORE = 'zscore' # left table_name, right Y, gender give Z
    IZSCORE = 'izscore' #left table_name, right Z, gender give Y
    DRUG_DOSAGE = 'drug_dosage' # drug name, *param1 (ex: weight, age)
    AGE_DAY = 'age_day' # age from dob
    AGE_MONTH = 'age_month' # age from dob
    AGE_YEAR = 'age_year' # age from dob
    NOT = 'not'
    DIVIDED = 'divided'
    MULTIPLIED = 'multiplied'
    COALESCE = 'coalesce'
    ISNULL = 'isnull'
    ISNOTNULL= 'isnotnull'
    PLUS = 'plus'
    MINUS = 'minus'
    MODULO = 'modulo'
    COUNT = 'count'
    CAST_NUMBER = 'cast_number'
    CAST_INTEGER = 'cast_integer'
    CAST_DATE = 'cast_date'
    PARENTHESIS = 'parenthesis'
    CONCATENATE = 'concatenate'

OPERATION_LIST = {
    '>=': TriccOperator.MORE_OR_EQUAL,
    '<=': TriccOperator.LESS_OR_EQUAL,
    '==': TriccOperator.EQUAL,
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
    
    def __repr__(self):
        return "TriccOperation:"+self.__str__()
    
    def __eq__(self, other):
        return self.__str__() == str(other)
    
    def __init__(self, operator, reference=[]):
        super().__init__(operator=operator, reference=reference)
        
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


TriccGroup.update_forward_refs()
TriccEdge.update_forward_refs()