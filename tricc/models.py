
from enum import Enum
import logging
from typing import Dict, List, Optional,  Union
from pydantic import BaseModel, constr

from tricc.converters.utils import generate_id

logger = logging.getLogger("default")


Expression= constr(regex="^[^\\/]+$")

triccId = constr(regex="^.+$")

base64 = constr(regex="[^-A-Za-z0-9+/=]|=[^=]|={3,}$")

#data:page/id,UkO_xCL5ZjyshJO9Bexg

TRICC_INSTANCE = "I_{0}_{1}"

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
    container_hint_media='container_hint_media'#DEPRECATED
    activity='activity'
    select_yesno='select_one yesno'
    select_option='select_option'
    hint='hint-message'
    help='help-message'
    exclusive='not'
    end='end'
    activity_end='activity_end'
    edge='edge'
    page='page'
    not_available='not_available'

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
    instance: int = 1
    base_instance : Optional[BaseModel]
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
    
    def  make_instance(self, nb_instance, activity, **kwargs):
        instance = self.copy()
        # change the id to avoid colision of name
        instance.id = generate_id()
        instance.instance=nb_instance
        instance.base_instance = self
        instance.group = activity
        # assign the defualt group
        #if activity is not None and self.group == activity.base_instance:
        #    instance.group = instance
        return instance
 
        

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
    def get_name(self):
        if self.label is not None:
            if len(self.label)<50:
                return self.label.encode("utf-8")
            else:
                return self.label[:50].encode("utf-8")
        elif self.name is not None:
            return self.name
        else:
            # TODO call parent.get_name instead
            return self.id
    def  make_instance(self, instance_nb, activity = None):
        instance = super().make_instance(instance_nb, activity = activity)
        if hasattr(self, 'name') \
            and not isinstance(self, TriccNodeSelectOption)\
            and not issubclass(self.__class__, TriccNodeDisplayCalculateBase):
                
            instance.name = TRICC_INSTANCE.format(instance_nb, self.name)
        if hasattr(self, 'activity') and activity is not None:
            instance.activity = activity
        next_nodes = []
        instance.next_nodes = next_nodes
        prev_nodes = []
        instance.prev_nodes = prev_nodes
        expression_inputs = []
        instance.expression_inputs =expression_inputs
        
        return instance
            

class TriccGroup(TriccBaseModel):
    odk_type = TriccExtendedNodeType.page

class TriccEdge(TriccBaseModel):
    odk_type = TriccExtendedNodeType.edge
    source: Union[triccId, TriccNodeBaseModel]
    target: Union[triccId, TriccNodeBaseModel]
    def  make_instance(self, instance_nb, activity = None):
        instance = super().make_instance(instance_nb, activity = activity)
        if issubclass(self.source.__class__, TriccNodeBaseModel):
            instance.source = self.source.copy()
        if issubclass(self.target.__class__, TriccNodeBaseModel):
            instance.target = self.target.copy()
        return instance
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
    # redefine 
    def make_instance(self,instance_nb, **kwargs):
        #shallow copy
        instance = super().make_instance(instance_nb, activity = None)
        #instance.base_instance = self
        # we duplicate all the related nodes (not the calculate, duplication is manage in calculate version code)
        nodes = {}
        instance.nodes = nodes
        edges = []
        instance.edges = edges
        end_prev_nodes = []
        instance.end_prev_nodes = end_prev_nodes
        activity_end_prev_nodes = []
        instance.activity_end_prev_nodes = activity_end_prev_nodes
        relevance= None
        instance.relevance= relevance
        groups = {}
        instance.groups = groups
        instance.group = instance
        for edge in self.edges:
            instance.edges.append(edge.make_instance(instance_nb, activity = instance))
        instance.edges_copy = instance.edges.copy() 
        update_nodes(instance, self.root) 
        # we walk throught the nodes and replace them when ready
        for node in list(self.nodes.values()):
            update_nodes( instance, node)
        for group in self.groups:
            instance.update_groups(group)         
        # update parent group
        for group in self.groups:
            instance.update_groups_group(group)
                 
        #processed_nodes = {}
        
        ##walktrhough_tricc_node( instance.root, make_node_instance, page = instance , processed_nodes= processed_nodes, instance_nb=instance_nb)
        
        return instance
    
    
    def update_groups_group(self, group):   
        for instance_group in self.groups:
            if instance_group.group == group:
                instance_group.group == instance_group
            elif instance_group.group == self.base_instance:
                instance_group.group == self    
        
    def update_groups(self,  group):
        # create new group 
        instance_group = group.make_instance(self.instance, activity = self)
        #update the group in all activity
        for node in list(self.nodes.values()):
            if node.group == group:
                node.group == instance_group
        self.groups[instance_group.id] = instance_group


def update_nodes(instance, node):
    if not isinstance(node, TriccNodeSelectOption):
        node_instance = node.make_instance(instance.instance, activity = instance)
        instance.nodes[node_instance.id] = node_instance
        if isinstance(node, TriccNodeActivityStart):
            instance.root = node_instance
        elif issubclass(node_instance.__class__, TriccNodeSelect):
            for key,  option_instance in node_instance.options.items():
                update_edges(instance, node.options[key], option_instance)
        update_edges(instance, node, node_instance)


def update_edges(instance, node, node_instance):
    for edge in instance.edges:
        if edge.source == node.id or edge.source == node:
            edge.source = node_instance.id
        if edge.target == node.id or edge.target == node:
            edge.target = node_instance.id
        
        
class TriccNodeDiplayModel(TriccNodeBaseModel):
    name: str
    image: Optional[base64]
    hint: Optional[str]
    help: Optional[str]
    group:Optional[Union[TriccGroup,TriccNodeActivity]]
    relevance: Optional[Expression]
    def  make_instance(self, instance_nb, activity = None):
        instance = super().make_instance(instance_nb, activity = activity)
        instance.relevance = None
        return instance

    # to use the enum value of the TriccNodeType

class TriccNodeNote(TriccNodeDiplayModel):
    odk_type = TriccNodeType.note
        
class TriccNodeActivityEnd(TriccBaseModel):
    activity: Optional[TriccBaseModel]
    odk_type = TriccExtendedNodeType.activity_end
    def make_instance(self,instance_nb,activity,   **kwargs):
        #shallow copy
        instance = super().make_instance(instance_nb, activity = activity)
        instance.activity = activity
        return instance   

class TriccNodeEnd(TriccBaseModel):
    activity:Optional[TriccBaseModel]
    odk_type = TriccExtendedNodeType.end
    def make_instance(self,instance_nb,activity,  **kwargs):
        #shallow copy
        instance = super().make_instance(instance_nb, activity = activity)
        instance.activity = activity
        return instance   
    
class TriccNodeInputModel(TriccNodeDiplayModel):
    required:Optional[Expression]
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
    # no need to copy

class TriccNodeGoTo(TriccNodeBaseModel):
    odk_type = TriccExtendedNodeType.goto 
    link: Union[TriccNodeActivity , triccId]
    # no need ot copy


    

class TriccNodeSelectOption(TriccNodeDiplayModel):
    odk_type = TriccExtendedNodeType.select_option
    label:str
    save:Optional[str]
    select:TriccNodeInputModel
    list_name: str
    def make_instance(self,instance_nb,activity,  select, **kwargs):
        #shallow copy
        instance = super().make_instance(instance_nb, activity = activity)
        instance.select = select
        return instance
    

class TriccNodeSelect(TriccNodeInputModel):
    filter: Optional[str]
    options : Dict[int, TriccNodeSelectOption] = {}
    list_name: str
    def make_instance(self,instance_nb,activity, **kwargs):
        #shallow copy, no copy of filter and list_name
        instance = super().make_instance(instance_nb, activity = activity)
        instance.options = {}
        for key, option in self.options.items():
            instance.options[key] = option.make_instance(instance_nb, activity = activity, select=instance)
        return instance
            

class TriccNodeSelectOne(TriccNodeSelect):
    odk_type = TriccNodeType.select_one

class TriccNodeSelectYesNo(TriccNodeSelectOne):
    pass
#    options: List[TriccNodeSelectOption] = [TriccNodeSelectOption(label='Yes', name='yes'),
#                 TriccNodeSelectOption(label='No', name='no')]
class TriccNodeSelectNotAvailable(TriccNodeSelectOne):
    pass
class TriccNodeSelectMultiple(TriccNodeSelect):
    odk_type = TriccNodeType.select_multiple

class TriccNodeNumber(TriccNodeInputModel):
    min:Optional[float]
    max:Optional[float]
    # no need to copy min max in make isntance
    
    
    
class TriccNodeDecimal(TriccNodeNumber):
    odk_type = TriccNodeType.decimal
    

class TriccNodeInteger(TriccNodeNumber):
    odk_type = TriccNodeType.integer

    
class TriccNodeText(TriccNodeInputModel):
    odk_type = TriccNodeType.text
    
class TriccNodeCalculateBase(TriccNodeBaseModel):
    input: Dict[TriccOperation, TriccNodeBaseModel] = {}
    expression : Optional[Expression] # will be generated based on the input
    version: int = 1
    # to use the enum value of the TriccNodeType
    class Config:  
        use_enum_values = True  # <--
    def make_instance(self,instance_nb,activity,  **kwargs):
        #shallow copy
        instance = super().make_instance(instance_nb, activity = activity)
        input = {}
        instance.input = input
        expression = None
        instance.expression = expression
        version = 0 
        instance.version = version
        return instance
    

class TriccNodeDisplayCalculateBase(TriccNodeCalculateBase):
    save: Optional[str] # contribute to another calculate
    # no need to copy save
    

class TriccNodeCalculate(TriccNodeDisplayCalculateBase):
    odk_type = TriccNodeType.calculate
class TriccNodeAdd(TriccNodeDisplayCalculateBase):
    odk_type = TriccExtendedNodeType.add
    
class TriccNodeCount(TriccNodeDisplayCalculateBase):
    odk_type = TriccExtendedNodeType.count
    
class TriccNodeFakeCalculateBase(TriccNodeCalculateBase):
    pass
class TriccNodeRhombus(TriccNodeFakeCalculateBase):
    odk_type = TriccExtendedNodeType.rhombus
    reference: Optional[Union[TriccNodeBaseModel, triccId]]
    def make_instance(self,instance_nb,activity,   **kwargs):
        #shallow copy
        instance = super().make_instance(instance_nb, activity = activity)
        reference = None
        instance.reference = reference
        return instance
    
class TriccNodeExclusive(TriccNodeFakeCalculateBase):
    odk_type = TriccExtendedNodeType.exclusive
    

# Set the source next node to target and clean  next nodes of replace node
def set_prev_next_node( source_node, target_node, replaced_node = None):
    # if it is end node, attached it to the activity/page
    set_prev_node( source_node, target_node, replaced_node )
    if replaced_node is not None and replaced_node in source_node.next_nodes:
        source_node.next_nodes.remove(replaced_node)
    if replaced_node is not None and replaced_node in target_node.next_nodes:
        target_node.next_nodes.remove(replaced_node)
    source_node.next_nodes.append(target_node)


# Set the target_node prev node to source and clean prev nodes of replace_node
def set_prev_node( source_node, target_node, replaced_node = None):
    #update the prev node of the target not if not an end node
    if target_node.odk_type == TriccExtendedNodeType.end:
        if replaced_node is not None and replaced_node in source_node.activity.end_prev_nodes:
            source_node.activity.end_prev_nodes.remove(replaced_node)
        if replaced_node is not None and replaced_node in source_node.activity.end_prev_nodes:
            source_node.activity.end_prev_nodes.remove(replaced_node)
        source_node.activity.end_prev_nodes.append(source_node)
    elif target_node.odk_type == TriccExtendedNodeType.activity_end:
        if replaced_node is not None and replaced_node in source_node.activity.activity_end_prev_nodes:
            source_node.activity.activity_end_prev_nodes.remove(replaced_node)
        if replaced_node is not None and replaced_node in source_node.activity.activity_end_prev_nodes:
            source_node.activity.activity_end_prev_nodes.remove(replaced_node)
        source_node.activity.activity_end_prev_nodes.append(source_node)
    else:
        # update directly the prev node of the target
        target_node.prev_nodes.append(source_node)
        if replaced_node is not None and replaced_node in target_node.prev_nodes:
            target_node.prev_nodes.remove(replaced_node)
        if replaced_node is not None and replaced_node in source_node.prev_nodes:
            source_node.prev_nodes.remove(replaced_node)
        
def replace_node(old, new, page):
    for prev_node in old.prev_nodes:
        set_prev_next_node(prev_node, new, old)
    old.prev_nodes = []
    for next_node in old.next_nodes:
        set_prev_next_node( new, next_node,old)
    old.next_nodes = []
    page.nodes[new.id]=new
    del page.nodes[old.id]
    for edge in page.edges:
        if edge.source == old.id:
           edge.source = new.id
        if edge.target == old.id:
           edge.target = new.id 
# walkthough all node in an iterative way, the same node might be parsed 2 times 
# therefore to avoid double processing the nodes variable saves the node already processed
# there 2 strategies : process it the first time or the last time (wait that all the previuous node are processed)
def walktrhough_tricc_node( node, callback, **kwargs):
        if ( callback(node, **kwargs)):
            # if has next, walkthrough them (support options)
            if isinstance(node, TriccNodeActivity):
                if node.root is not None:
                    walktrhough_tricc_node(node.root, callback, **kwargs)
            elif issubclass(node.__class__, TriccNodeSelect):
                for key, option in node.options.items():
                    # process all the options first
                    callback(option, **kwargs)
                for key, option in node.options.items():
                    # then walk the options   
                    if hasattr(option,'next_nodes') and len(option.next_nodes)>0:
                        for next_node in option.next_nodes:
                            walktrhough_tricc_node(next_node, callback, **kwargs)
            if hasattr(node,'next_nodes') and len(node.next_nodes)>0:
                for next_node in node.next_nodes:
                    walktrhough_tricc_node(next_node, callback, **kwargs)
                
def make_node_instance(node, processed_nodes, page, instance_nb):
    if is_ready_to_process(node, processed_nodes) and node.id not in processed_nodes:
        for next_node in node.next_nodes:
            next_instance = next_node.make_instance(instance_nb , page )
            set_prev_next_node(node,next_instance, next_node)
            for edge in page.edges:
                if edge.source == next_node.id:
                    edge.source  = next_instance.id
                if edge.target == next_node.id:
                    edge.target  = next_instance.id
        processed_nodes[node.id]=node     
        return True
    else:
        return False


# check if the all the prev nodes are processed
def is_ready_to_process(in_node, processed_nodes):
    if isinstance(in_node, TriccNodeSelectOption):
        node = in_node.select
    else:
        node = in_node
    if hasattr(node, 'prev_nodes'):
        # ensure the the previous node of the select are processed, not the option prev nodes
        for prev_node in node.prev_nodes:
            if isinstance(prev_node,TriccNodeActivity):
                if len(prev_node.end_prev_nodes)==0 and len(prev_node.activity_end_prev_nodes)==0:
                    return False
                for end_node in prev_node.end_prev_nodes:
                    if end_node.id not in processed_nodes:
                        logger.debug("At least activity {0} interrogation end node {1} not yet processed".format(prev_node.get_name(),end_node.get_name() ))
                        return False
                for activity_end_node in prev_node.activity_end_prev_nodes:
                    if activity_end_node.id not in processed_nodes:
                        logger.debug("At least activity {0} end node {1} not yet processed".format(prev_node.get_name(),activity_end_node.get_name() ))
                        return False
            elif prev_node.id not in processed_nodes:
                if isinstance(prev_node, TriccNodeExclusive):
    
                    logger.debug("Prev node {0} (via exclusive) {1} not yet processed".format(prev_node.prev_nodes[0].get_name(), prev_node.get_name() ))
                else :
                    logger.debug("Prev node {0} not yet processed".format(prev_node.get_name() ))
                return False
        return True
    else:
        return True
    
def get_prev_node_by_name(nodes, name, instance_nb = 1): 
    for node in list(nodes.values()) if isinstance(nodes, Dict)  else nodes:
        if hasattr(node, 'name'):
            if int(instance_nb) > 1 and node.name == TRICC_INSTANCE.format(instance_nb, name):
                return node
            elif node.name == name:
                return node