
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


    



class TriccNodeDisplayCalculateBase(TriccNodeCalculateBase):
    save: Optional[str] = None  # contribute to another calculate
    hint: Optional[str] = None  # for diagnostic display
    help: Optional[str] = None  # for diagnostic display
    # no need to copy save
    def to_fake(self):
        data = vars(self)
        del data['hint']
        del data['help']
        del data['save']
        fake = TriccNodeFakeCalculateBase(**data)
        replace_node(self,fake)
        return fake
    def __str__(self):
        return self.get_name()

    def __repr__(self):
        return self.get_name()
    
class TriccNodeCalculate(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.calculate


class TriccNodeAdd(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.add


class TriccNodeCount(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.count


class TriccNodeProposedDiagnosis(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.proposed_diagnosis
    severity: str = None
    
class TriccNodeFakeCalculateBase(TriccNodeCalculateBase):
    id: triccId = generate_id()

class TriccNodeInput(TriccNodeFakeCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.input
    
class TriccNodeDisplayBridge(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.bridge
        

class TriccNodeBridge(TriccNodeFakeCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.bridge
        
class TriccRhombusMixIn():
    
    def make_mixin_instance(self, instance, instance_nb, activity, **kwargs):
        # shallow copy
        reference = []
        expression_reference = None
        instance.path = None
        if isinstance(self.expression_reference, (str, TriccOperation)):
            expression_reference = self.expression_reference.copy()
            reference = list(expression_reference.get_references())
        if isinstance(self.reference, (str, TriccOperation)):
            expression_reference = self.reference.copy()
            reference = list(expression_reference.get_references())
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
                elif isinstance(ref, TriccReference):
                    reference.append(ref)
                elif isinstance(ref, str):
                    logger.debug("passing raw reference {} on node {}".format(ref, self.get_name()))
                    reference.append(ref)
                else:
                    logger.error("unexpected reference {} in node {}".format(ref, self.get_name()))
                    exit(1)
        instance.reference = reference
        instance.expression_reference = expression_reference
        instance.name = get_rand_name(8)
        return instance


    

class TriccNodeRhombus(TriccNodeCalculateBase,TriccRhombusMixIn):
    tricc_type: TriccNodeType = TriccNodeType.rhombus
    path: Optional[TriccNodeBaseModel] = None
    reference: Union[List[TriccNodeBaseModel], Expression, TriccOperation, TriccReference, List[TriccReference]]
    
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

class TriccNodeDiagnosis(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.diagnosis
    severity: str = None
    def __init__(self, **data):
        data['reference'] = f'"final.{data["name"]}" is true'
        super().__init__(**data)

        # rename rhombus
        self.name = get_rand_name(8)

class TriccNodeExclusive(TriccNodeFakeCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.exclusive

def get_node_from_id(activity, node, edge_only):
    node_id = getattr(node,'id',node)
    if not isinstance(node_id, str):
        logger.error("can set prev_next only with string or node")
        exit(1)
    if issubclass(node.__class__, TriccBaseModel):
        return node_id, node
    elif node_id in activity.nodes:
        node = activity.nodes[node_id]
    elif not edge_only:
        logger.error(f"cannot find {node_id} in  {activiy.get_name()}")
        exit(1)
    return node_id, node

class TriccNodeWait(TriccNodeFakeCalculateBase, TriccRhombusMixIn):
    tricc_type: TriccNodeType = TriccNodeType.wait
    path: Optional[TriccNodeBaseModel] = None
    reference: Union[List[TriccNodeBaseModel], Expression, TriccOperation]
    
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


class TriccNodeEnd(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.end
    process: str = None
    def __init__(self, **data):
        super().__init__(**data)
        # FOR END
        
        self.set_name()

    def set_name(self):
        if self.name is None:
            self.name = 'tricc_end'
        #self.name = END_NODE_FORMAT.format(self.activity.id)


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