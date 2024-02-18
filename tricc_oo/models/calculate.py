
import logging
import random
import string
from enum import Enum, auto
from typing import Dict, ForwardRef, List, Optional, Union

from pydantic import BaseModel, constr
from strenum import StrEnum
from .base import *
from .tricc import *
from tricc_oo.converters.utils import generate_id


    

class TriccNodeCalculateBase(TriccNodeBaseModel):
    #input: Dict[TriccOperation, TriccNodeBaseModel] = {}
    reference: Optional[Union[List[Union[TriccNodeBaseModel,TriccStatic]], Expression]]
    expression_reference: Optional[Union[str, TriccOperation]]
    version: int = 1
    last: bool = True

    # to use the enum value of the TriccNodeType
    class Config:
        use_enum_values = True  # <--

    def make_instance(self, instance_nb, activity, **kwargs):
        # shallow copy
        instance = super().make_instance(instance_nb, activity=activity)
        #input = {}
        #instance.input = input
        expression = self.expression.copy() if self.expression is not None else None
        instance.expression = expression
        version = 1
        instance.version = version
        return instance

    def __init__(self, **data):
        super().__init__(**data)
        self.gen_name()
        
    def append(self, elm):
        reference.append(elm)
    
    def get_references(self):
        if isinstance(self.reference, list):
            return self.reference
        else:
            raise NotImplemented("Cannot get reference from a sting")


class TriccNodeDisplayCalculateBase(TriccNodeCalculateBase):
    save: Optional[str]  # contribute to another calculate
    hint: Optional[str]  # for diagnostic display
    help: Optional[str]  # for diagnostic display
    # no need to copy save
    def to_fake(self):
        data = vars(self)
        del data['hint']
        del data['help']
        del data['save']
        fake = TriccNodeFakeCalculateBase(**data)
        replace_node(self,fake)
        return fake


class TriccNodeCalculate(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.calculate


class TriccNodeAdd(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.add


class TriccNodeCount(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.count


class TriccNodeFakeCalculateBase(TriccNodeCalculateBase):
    id: triccId = generate_id()


class TriccNodeDisplayBridge(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.bridge
        

class TriccNodeBridge(TriccNodeFakeCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.bridge
        
class TriccRhombusMixIn():
    
    def make_mixin_instance(self, instance, instance_nb, activity, **kwargs):
        # shallow copy
        reference = []
        instance.path = None
        if isinstance(self.reference, str):
            reference = self.reference
        elif isinstance(self.reference, list):
            for ref in self.reference:
                if issubclass(ref.__class__, TriccBaseModel):
                    pass
                    # get the reference
                    if self.activity == ref.activity:
                        for sub_node in activity.nodes.values():
                            if sub_node.base_instance == ref:
                                reference.append(sub_node)
                    else:  # ref from outside
                        # FIXME find the latest version
                        reference.append(ref)
                elif isinstance(ref, str):
                    logger.debug("passing raw reference {} on node {}".format(ref, self.get_name()))
                    reference.append(ref)
                else:
                    logger.error("unexpected reference in node node {}".format(ref, self.get_name()))
                    exit()
        instance.reference = reference
        instance.name = get_rand_name(8)
        return instance


    

class TriccNodeRhombus(TriccNodeCalculateBase,TriccRhombusMixIn):
    tricc_type: TriccNodeType = TriccNodeType.rhombus
    path: Optional[TriccNodeBaseModel] = None
    reference: Union[List[TriccNodeBaseModel], Expression]
    
    def make_instance(self, instance_nb, activity, **kwargs):
        instance = super(TriccNodeRhombus, self).make_instance(instance_nb, activity, **kwargs)
        instance = self.make_mixin_instance(instance, instance_nb, activity, **kwargs)
        return instance


    def __init__(self, **data):
        super().__init__(**data)
        # rename rhombus
        self.name = get_rand_name(8)


def get_rand_name(k):
    return "r_" + ''.join(random.choices(string.ascii_lowercase, k=k))


class TriccNodeExclusive(TriccNodeFakeCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.exclusive

def get_node_from_id(activity, node, edge_only):
    node_id = getattr(node,'id',node)
    if not isinstance(node_id, str):
        logger.error("can set prev_next only with string or node")
        exit()
    if issubclass(node.__class__, TriccBaseModel):
        return node_id, node
    elif node_id in activity.nodes:
        node = activity.nodes[node_id]
    elif not edge_only:
        logger.error(f"cannot find {node_id} in  {activiy.get_name()}")
        exit()
    return node_id, node

class TriccNodeWait(TriccNodeFakeCalculateBase, TriccRhombusMixIn):
    tricc_type: TriccNodeType = TriccNodeType.wait
    path: Optional[TriccNodeBaseModel] = None
    reference: Union[List[TriccNodeBaseModel], Expression]
    
    def make_instance(self, instance_nb, activity, **kwargs):
        instance = super(TriccNodeWait, self).make_instance(instance_nb, activity, **kwargs)
        instance = self.make_mixin_instance(instance, instance_nb, activity, **kwargs)
        return instance


class TriccNodeActivityEnd(TriccNodeFakeCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.activity_end

    def __init__(self, **data):
        super().__init__(**data)
        # FOR END
        self.set_name()

    def set_name(self):
        self.name = ACTIVITY_END_NODE_FORMAT.format(self.activity.id)


class TriccNodeEnd(TriccNodeCalculate):
    tricc_type: TriccNodeType = TriccNodeType.end

    def __init__(self, **data):
        super().__init__(**data)
        # FOR END
        self.set_name()

    def set_name(self):
        self.name = END_NODE_FORMAT.format(self.activity.id)


class TriccNodeActivityStart(TriccNodeFakeCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.activity_start


def get_node_from_list(in_nodes, node_id):
    nodes = list(filter(lambda x: x.id == node_id, in_nodes))
    if len(nodes) > 0:
        return nodes[0]

# qualculate that saves quantity, or we may merge integer/decimals
class TriccNodeQuantity(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.quantity




TriccNodeCalculate.update_forward_refs()