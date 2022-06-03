
from enum import Enum
from typing import Dict, List, Optional,  Union

from pydantic import BaseModel, constr

Expression= constr(regex="^[^\\/]+$")

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
    page='page'

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
    id:triccId
    parent:Optional[triccId]
    group : Optional[BaseModel]
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

    class Config:  
        use_enum_values = True  # <--
    
class TriccNodeBaseModel(TriccBaseModel):
    name: Optional[str]
    label: Optional[str]
    next_nodes: List[TriccBaseModel] = []
    prev_nodes: List[TriccBaseModel] = []
    # to be updated while processing because final expression will be possible to build$
    # #only the last time the script will go through the node (all prev node expression would be created
    expression_inputs: List[Expression] = []
    activity: Optional[TriccBaseModel]
    

class TriccGroup(TriccBaseModel):
    odk_type = TriccExtendedNodeType.page

class TriccEdge(TriccBaseModel):
    odk_type = TriccExtendedNodeType.edge
    source: Union[triccId, TriccNodeBaseModel]
    target: Union[triccId, TriccNodeBaseModel]
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
    #groups
    groups : Dict[str, TriccGroup] = {}
    # node that lead to the end of the interogation
    end_prev_nodes:  List[TriccBaseModel] = []
    # node that leads to the end of the activity
    activity_end_prev_nodes:  List[TriccBaseModel] = []
    relevance: Optional[Expression]
class TriccNodeDiplayModel(TriccNodeBaseModel):
    name: str
    image: Optional[base64]
    hint: Optional[str]
    help: Optional[str]
    group:Optional[Union[TriccGroup,TriccNodeActivity]]
    relevance: Optional[Expression]

    # to use the enum value of the TriccNodeType



class TriccNodeNote(TriccNodeDiplayModel):
    odk_type = TriccNodeType.note
        



class TriccNodeActivityEnd(TriccBaseModel):
    activity: Optional[TriccBaseModel]
    odk_type = TriccExtendedNodeType.activity_end

class TriccNodeEnd(TriccBaseModel):
    activity:Optional[TriccBaseModel]
    odk_type = TriccExtendedNodeType.end




    
class TriccNodeInputModel(TriccNodeDiplayModel):
    required:Optional[bool]
    constraint_message:Optional[str]
    constraint:Optional[Expression]
    save: Optional[str] # contribute to another calculate



    
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
    select:TriccNodeInputModel
    
    

class TriccNodeSelect(TriccNodeInputModel):
    filter: Optional[str]
    options : Dict[int, TriccNodeSelectOption] = {}

class TriccNodeSelectOne(TriccNodeSelect):
    odk_type = TriccNodeType.select_one

#class TriccNodeSelectYesNo(TriccNodeSelect):
#    odk_type = TriccNodeType.select_one
#    options: List[TriccNodeSelectOption] = [TriccNodeSelectOption(label='Yes', name='yes'),
#                 TriccNodeSelectOption(label='No', name='no')]

class TriccNodeSelectMultiple(TriccNodeSelect):
    odk_type = TriccNodeType.select_multiple

class TriccNodeNumber(TriccNodeInputModel):
    min:Optional[float]
    max:Optional[float]
    
    
    
class TriccNodeDecimal(TriccNodeNumber):
    odk_type = TriccNodeType.decimal
    

class TriccNodeInteger(TriccNodeNumber):
    odk_type = TriccNodeType.integer

    
class TriccNodeText(TriccNodeInputModel):
    odk_type = TriccNodeType.text
    
class TriccNodeCalculateBase(TriccNodeBaseModel):
    odk_type = TriccNodeType.calculate
    input: Dict[TriccOperation, TriccNodeBaseModel] = {}
    expression : Optional[Expression] # will be generated based on the input
    save: Optional[str] # contribute to another calculate
    version: int = 0
    # to use the enum value of the TriccNodeType
    class Config:  
        use_enum_values = True  # <--


class TriccNodeCalculate(TriccNodeCalculateBase):
    odk_type = TriccNodeType.calculate
class TriccNodeAdd(TriccNodeCalculateBase):
    odk_type:TriccExtendedNodeType = TriccExtendedNodeType.add
    
class TriccNodeCount(TriccNodeCalculateBase):
    odk_type:TriccExtendedNodeType = TriccExtendedNodeType.count
    
class TriccNodeRhombus(TriccNodeCalculateBase):
    odk_type:TriccExtendedNodeType = TriccExtendedNodeType.rhombus
    reference: Optional[Union[TriccNodeBaseModel, triccId]]
    
class TriccNodeExclusive(TriccNodeCalculateBase):
    odk_type = TriccExtendedNodeType.exclusive
        