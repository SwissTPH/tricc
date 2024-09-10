from __future__ import annotations

import logging
import random
import string
from enum import Enum, auto
from typing import Dict, ForwardRef, List, Optional, Union, Set

from pydantic import BaseModel, constr
from strenum import StrEnum

from tricc_oo.converters.utils import generate_id


logger = logging.getLogger("default")

Expression = constr(regex="^[^\\/]+$")

triccId = constr(regex="^.+$")
triccIdList = constr(regex="^.+$")

b64 = constr(regex="[^-A-Za-z0-9+/=]|=[^=]|={3,}$")

TriccEdge = ForwardRef('TriccEdge')
# data:page/id,UkO_xCL5ZjyshJO9Bexg


ACTIVITY_END_NODE_FORMAT = "aend_{}"
END_NODE_FORMAT = "end_{}"


class TriccNodeType(StrEnum):
    #replace with auto ? 
    note = 'note'
    calculate = 'calculate'
    select_multiple = 'select_multiple'
    select_one = 'select_one'
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
    select_yesno = 'select_one yesno'  # NOT YET SUPPORTED
    select_option = 'select_option'
    hint = 'hint-message'
    help = 'help-message'
    exclusive = 'not'
    end = 'end'
    activity_end = 'activity_end'
    edge = 'edge'
    page = 'page'
    not_available = 'not_available'
    quantity = 'quantity'
    bridge = 'bridge'
    wait = 'wait'
    operation = 'operation'



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
    tricc_type: TriccNodeType
    #parent: Optional[triccId]#TODO: used ?
    instance: int = 1
    base_instance: Optional[TriccBaseModel] = None

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
        return id


class TriccEdge(TriccBaseModel):
    tricc_type: TriccNodeType = TriccNodeType.edge
    source: Union[triccId, TriccNodeBaseModel]
    target: Union[triccId, TriccNodeBaseModel]
    value: Optional[str]  = None

    def make_instance(self, instance_nb, activity=None):
        instance = super().make_instance(instance_nb, activity=activity)
        #if issubclass(self.source.__class__, TriccBaseModel):
        instance.source = self.source if isinstance(self.source, str) else self.source.copy() #TODO should we copy  the nodes ?  
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
    prev_nodes: List[TriccBaseModel] = []
    def __init__(self, **data):
        super().__init__(**data)
        if self.name is None:
            self.name = generate_id()

    def get_name(self):
        
        if self.label is not None:
            name = self.label[self.label.keys()[0]] if isinstance(self.label, Dict) else self.label
            if len(name) < 50:
                return name
            else:
                return name[:50]
        else:
            return self.name


class TriccNodeBaseModel(TriccBaseModel):
    path_len: int = 0
    group: Optional[Union[TriccGroup, TriccNodeActivity]] = None
    name: Optional[str] = None
    export_name:Optional[str] = None
    label: Optional[Union[str, Dict[str,str]]] = None
    next_nodes: Set[TriccNodeBaseModel] = set()
    prev_nodes: Set[TriccNodeBaseModel] = set()
    expression: Optional[Union[Expression, TriccOperation]] = None  # will be generated based on the input
    expression_inputs: List[Expression] = []
    activity: Optional[TriccNodeActivity] = None
    ref_def: Optional[Union[int,str]]  = None# for medal creator

    class Config:
        use_enum_values = True  # <--

    # to be updated while processing because final expression will be possible to build$
    # #only the last time the script will go through the node (all prev node expression would be created

    def get_name(self):
        if self.label is not None:
            name = next(iter(self.label.values())) if isinstance(self.label, Dict) else self.label
            if len(name) < 50:
                return name
            else:
                return name[:50]
        elif self.name is not None:
            return self.name
        else:
            # TODO call parent.get_name instead
            return self.id

    def make_instance(self, instance_nb, activity=None):
        instance = super().make_instance(instance_nb)
        instance.group = activity
        if hasattr(self, 'activity') and activity is not None:
            instance.activity = activity
        next_nodes = set()
        instance.next_nodes = next_nodes
        prev_nodes = set()
        instance.prev_nodes = prev_nodes
        expression_inputs = []
        instance.expression_inputs = expression_inputs

        return instance

    def gen_name(self):
        if self.name is None:
            self.name = ''.join(random.choices(string.ascii_lowercase, k=8))
class TriccStatic(BaseModel):
    value: Union[str, float, int]
    def __init__(self,value):
        super().__init__(value = value)

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
    NOT_EQUAL = 'not_equal'
    BETWEEN = 'between'
    LESS = 'less'
    CASE = 'case' #(cond, res), (cond,res), default
    IF = 'if' # cond val_true, val_false
    CONTAINS = 'contains' # ref, txt Does CONTAINS make sense, like Select with wildcard
    EXISTS = 'exists'
    # CDSS Specific
    HAS_QUALIFIER = 'has_qualifier'
    ZSCORE = 'zscore' # left table_name, right Y, gender give Z
    IZSCORE = 'izscore' #left table_name, right Z, gender give Y
    AGE_DAY = 'age_day' # age from dob
    AGE_MONTH = 'age_month' # age from dob
    AGE_YEAR = 'age_year' # age from dob
    
    
class TriccOperation(BaseModel):
    tricc_type: TriccNodeType = TriccNodeType.operation
    operator: TriccOperator = TriccOperator.NATIVE
    reference: List[Union[TriccStatic,TriccNodeBaseModel]] = []
    def __init__(self, tricc_operator):
        super().__init__(operator = tricc_operator)
        
    def get_references(self):
        predecessor = set()
        if isinstance(self.reference, list):
            for reference in self.reference:
                if isinstance(reference, TriccOperation):
                    predecessor = predecessor | reference.get_references()
                elif issubclass(reference.__class__, TriccNodeBaseModel):
                    predecessor.add(reference)
        else:
            raise NotImplementedError("cannot find predecessor of a str")
        return predecessor
    def append(self, value):
        self.reference.append(value)
    def replace_node(self, old_node ,new_node):
        if isinstance(self.reference, list):
            for key in [i for i, x in enumerate(self.reference)]:
                if isinstance(self.reference[key], TriccOperation):
                    self.reference[key].replace_node(old_node ,new_node)
                elif issubclass(self.reference[key].__class__, TriccNodeBaseModel )  and  self.reference[key] == old_node:
                    self.reference[key] = new_node
                    # to cover the options
                    if hasattr(self.reference[key], 'select') and hasattr(new_node, 'select') and issubclass(self.reference[key].select.__class__, TriccNodeBaseModel ) :
                        self.replace_node(self.reference[key].select ,new_node.select)
        elif self.reference is not None:
            raise NotImplementedError(f"cannot manage {self.reference.__class__}")

TriccGroup.update_forward_refs()
TriccEdge.update_forward_refs()