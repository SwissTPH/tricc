from importlib.metadata import entry_points
from enum import Enum
from typing import Dict, List, Optional,  Union
from pandas import DataFrame
from pydantic import BaseModel, constr

Expression= constr(regex="^[^\\/]$")

triccId = constr(regex="^.+$")

base64 = constr(regex="[^-A-Za-z0-9+/=]|=[^=]|={3,}$")

#data:page/id,UkO_xCL5ZjyshJO9Bexg

class TriccNodeType(str, Enum):
    note='note'
    calculate='calculate'
    select_multiple='select_multiple'
    select_one='select_one'
    decimal='decimal'
    integer='integer'
    text='text'

    
    

class TriccExtendedNodeType(str, Enum):
    rhombus='rhombus' # fetch data
    goto='goto'#: start the linked activity within the target activity
    start='start'#: main start of the algo
    activity_start='activity_start'#: start of an activity (link in)
    link_in='link_in'
    link_out='link_out'
    count='count'#: count the number of valid input
    add='add' # add counts
    container_hint_media='container_hint_media'
    activity='activity'
    #select_yesno='select_one yesno'
    select_option='select_option'
    hint='hint-message'
    help='help-message'
    exclusive='not'
    end='end'
    activity_end='activity_end'
    edge='edge'

class TriccOperation(str, Enum):
    _and='and'
    _or='or'
    _not='not'
    

media_nodes = [
    TriccNodeType.note,
    TriccNodeType.select_multiple,
    TriccNodeType.select_one,
    TriccNodeType.decimal,
    TriccNodeType.integer,
    TriccNodeType.text,
]

class TriccBaseModel(BaseModel):
    odk_type: Union[TriccNodeType,TriccExtendedNodeType]
    id:Optional[triccId]
    parent:Optional[triccId]
    class Config:  
        use_enum_values = True  # <--
    
class TriccNodeBaseModel(TriccBaseModel):
    name: Optional[str]
    label: Optional[str]
    next_nodes : List[TriccBaseModel] = []
    prev_nodes : List[TriccBaseModel] = []
    
class TriccNodeDiplayModel(TriccNodeBaseModel):
    name: str
    image: Optional[base64]
    hint: Optional[str]
    help: Optional[str]
    
    relevance: Optional[Expression]
    # to use the enum value of the TriccNodeType



class TriccNodeNote(TriccNodeDiplayModel):
    odk_type = TriccNodeType.note
        
class TriccEdge(TriccBaseModel):
    odk_type = TriccExtendedNodeType.edge
    source: Union[triccId, TriccNodeDiplayModel]
    target: Union[triccId, TriccNodeDiplayModel]


class TriccNodeActivityEnd(TriccBaseModel):
    odk_type = TriccExtendedNodeType.activity_end

class TriccNodeEnd(TriccBaseModel):
    odk_type = TriccExtendedNodeType.end

class TriccNodeActivity(TriccNodeBaseModel):
    odk_type = TriccExtendedNodeType.activity
    # starting point of the activity
    root: TriccNodeBaseModel
    # edge list
    edges: List[TriccEdge]= []
    # copy of the edge for later restauration
    edges_copy: List[TriccEdge]= []
    # nodes part of that actvity
    nodes: Dict[str, TriccNodeBaseModel] = {}
    # node that lead to the end of the interogation
    end_prev_nodes:  List[TriccBaseModel] = []
    # node that leads to the end of the activity
    activity_end_prev_nodes:  List[TriccBaseModel] = []


    
class TriccNodeInputModel(TriccNodeDiplayModel):
    required:Optional[bool]
    constraint_message:Optional[str]
    constraint:Optional[Expression]
    save: Optional[str] # contribute to another calculate

class TriccNodeExclusive(TriccNodeBaseModel):
    odk_type = TriccExtendedNodeType.exclusive
        
class TriccNodeCalculate(TriccNodeBaseModel):
    odk_type = TriccNodeType.calculate
    input: Dict[TriccOperation, TriccNodeBaseModel] = {}
    expression : Optional[Expression] # will be generated based on the input
    save: Optional[str] # contribute to another calculate
        # to use the enum value of the TriccNodeType
    class Config:  
        use_enum_values = True  # <--
    
class TriccNodeMainStart(TriccNodeBaseModel):
    odk_type = TriccExtendedNodeType.start
    
class TriccNodeActivityStart(TriccNodeBaseModel):
    odk_type = TriccExtendedNodeType.activity_start
   
class TriccNodeLinkIn(TriccNodeBaseModel):
    odk_type = TriccExtendedNodeType.link_in
    
class TriccNodeLinkOut(TriccNodeBaseModel):
    odk_type = TriccExtendedNodeType.link_out
    reference: Optional[Union[TriccNodeLinkIn, triccId]]

class TriccNodeGoTo(TriccNodeBaseModel):
    odk_type = TriccExtendedNodeType.goto 
    link: Union[TriccNodeActivity , triccId]

    

class TriccNodeSelectOption(TriccNodeDiplayModel):
    odk_type = TriccExtendedNodeType.select_option
    label:str
    save:Optional[str]
    
    

class TriccNodeSelect(TriccNodeInputModel):
    filter: Optional[str]
    options : Dict[int, TriccNodeSelectOption]

class TriccNodeSelectOne(TriccNodeSelect):
    odk_type = TriccNodeType.select_one

#class TriccNodeSelectYesNo(TriccNodeSelect):
#    odk_type = TriccNodeType.select_one
#    options: List[TriccNodeSelectOption] = [TriccNodeSelectOption(label='Yes', name='yes'),
#                 TriccNodeSelectOption(label='No', name='no')]

class TriccNodeSelectMultiple(TriccNodeSelect):
    odk_type = TriccNodeType.select_multiple

class TriccNodeDecimal(TriccNodeInputModel):
    odk_type = TriccNodeType.decimal
    min:Optional[float]
    max:Optional[float]

class TriccNodeInteger(TriccNodeInputModel):
    odk_type = TriccNodeType.integer
    min:Optional[int]
    max:Optional[int]
    
class TriccNodeText(TriccNodeInputModel):
    odk_type = TriccNodeType.text
    
class TriccNodeAdd(TriccNodeCalculate):
    odk_type:TriccExtendedNodeType = TriccExtendedNodeType.add
    
class TriccNodeCount(TriccNodeCalculate):
    odk_type:TriccExtendedNodeType = TriccExtendedNodeType.count
    
class TriccNodeRhombus(TriccNodeCalculate):
    odk_type:TriccExtendedNodeType = TriccExtendedNodeType.rhombus