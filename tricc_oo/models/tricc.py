from __future__ import annotations

import logging
import random
import string
from enum import Enum, auto
from typing import Dict, ForwardRef, List, Optional, Union

from pydantic import BaseModel, constr
from strenum import StrEnum
from .base import *
from tricc_oo.converters.utils import generate_id

class TriccNodeCalculateBase(TriccNodeBaseModel):
    #input: Dict[TriccOperation, TriccNodeBaseModel] = {}
    reference: Union[List[Union[TriccNodeBaseModel,TriccStatic]], Expression] = None
    expression_reference: Union[str, TriccOperation] = None
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
        if isinstance(self.reference, set):
            return self.reference
        elif isinstance(self.reference, list):
            return set(self.reference)
        elif isinstance(self.expression_reference, TriccOperation):
            self.reference =  self.expression_reference.get_references()
            return self.reference
        elif self.reference:
            raise NotImplementedError("Cannot get reference from a sting")


class TriccNodeActivity(TriccNodeBaseModel):
    tricc_type: TriccNodeType = TriccNodeType.activity
    # starting point of the activity
    root: TriccNodeBaseModel
    # edge list
    edges: List[TriccEdge] = []
    # copy of the edge for later restauration
    unused_edges: List[TriccEdge] = []
    # nodes part of that actvity
    nodes: Dict[str, TriccNodeBaseModel] = {}
    # groups
    groups: Dict[str, TriccGroup] = {}
    # save the instance on the base activity     
    instances: Dict[int, TriccNodeBaseModel] = {}
    relevance: Optional[Union[Expression, TriccOperation]] = None
    #caclulate that are not part of the any skip logic:
    # - inputs
    # - dandling calculate
    # - case definition
    calculates: List[TriccNodeCalculateBase] = []

    # redefine 
    def make_instance(self, instance_nb, **kwargs):
        from tricc_oo.models.calculate import (
            TriccNodeDisplayBridge,
            TriccNodeBridge,
 
        )
        # shallow copy
        if instance_nb in self.instances:
            return self.instances[instance_nb]
        else:
            instance = super().make_instance(instance_nb, activity=None)
            self.instances[instance_nb] = instance
            # instance.base_instance = self
            # we duplicate all the related nodes (not the calculate, duplication is manage in calculate version code)
            nodes = {}
            instance.nodes = nodes
            edges = []
            instance.edges = edges
            unused_edges = []
            instance.edges = unused_edges
            calculates = []
            instance.calculates = calculates
            relevance = None
            instance.relevance = relevance
            groups = {}
            instance.groups = groups
            instance.group = instance
            instance.activity = instance
            for edge in self.edges:
                instance.edges.append(edge.make_instance(instance_nb, activity=instance))
            instance.update_nodes(self.root)
            # we walk throught the nodes and replace them when ready
            for node in list(filter(lambda p_node: isinstance(p_node, (TriccNodeDisplayBridge,TriccNodeBridge)),list(self.nodes.values()) )):
                instance.update_nodes(node)
            for node in list(filter(lambda p_node: p_node != self.root and not isinstance(p_node, (TriccNodeDisplayBridge,TriccNodeBridge)),list(self.nodes.values()) )):
                instance_node = instance.update_nodes(node)
                if node in self.calculates and instance_node:
                    instance.calulates.append(instance_node)

            for group in self.groups:
                instance.update_groups(group)
                # update parent group
            for group in self.groups:
                instance.update_groups_group(group)

            return instance

    def update_groups_group(self, group):
        for instance_group in self.groups:
            if instance_group.group == group:
                instance_group.group == instance_group
            elif instance_group.group == self.base_instance:
                instance_group.group == self

    def update_groups(self, group):
        # create new group 
        instance_group = group.make_instance(self.instance, activity=self)
        # update the group in all activity
        for node in list(self.nodes.values()):
            if node.group == group:
                node.group == instance_group
        self.groups[instance_group.id] = instance_group

    def update_nodes(self, node_origin):
        from tricc_oo.models.calculate import (
            TriccNodeEnd,
            TriccNodeActivityStart,
            TriccNodeMainStart,
            TriccNodeActivityEnd,
            TriccRhombusMixIn
        )
        updated_edges = 0
        node_instance = None
        if not isinstance(node_origin, TriccNodeSelectOption):
            # do not perpetuate the instance number in the underlying activities
            if isinstance(node_origin, TriccNodeActivity):
                node_instance = node_origin.make_instance(node_origin.instance if node_origin.instance<100 else 0 , activity=self)
            else:
                node_instance = node_origin.make_instance(self.instance, activity=self)
            self.nodes[node_instance.id] = node_instance
            if isinstance(node_instance, (TriccNodeActivityEnd, TriccNodeEnd)):
                node_instance.set_name()
            # update root
            if isinstance(node_origin, TriccNodeActivityStart) and node_origin == node_origin.activity.root:
                self.root = node_instance
            if issubclass(node_instance.__class__, TriccRhombusMixIn):
                old_path = node_origin.path
                if old_path is not None:
                    for n in node_instance.activity.nodes.values():
                        if n.base_instance.id == old_path.id:
                            node_instance.path = n
                    if node_instance.path is None:
                        logger.error("new path not found")
                elif not (len(node_instance.reference)== 1  and issubclass(node_instance.reference[0].__class__, TriccNodeInputModel)):
                    logger.warning("Rhombus without a path")
                
            # generate options
            elif issubclass(node_instance.__class__, TriccNodeSelect):
                for key, option_instance in node_instance.options.items():
                    updated_edges += self.update_edges(node_origin.options[key], option_instance)
            updated_edges += self.update_edges(node_origin, node_instance)
            if updated_edges == 0:
                node_edge = list(filter(lambda x: (x.source == node_instance.id or x.source == node_instance) , node_instance.activity.edges))
                node_edge_origin = list(filter(lambda x: (x.source == node_origin.id or x.source == node_origin) , node_origin.activity.edges))
                if len(node_edge) == 0:
                    logger.error("no edge was updated for node {}::{}::{}::{}".format(node_instance.activity.get_name(),
                                                                                  node_instance.__class__,
                                                                                  node_instance.get_name(),
                                                                                  node_instance.instance))
        return node_instance

    def update_edges(self, node_origin, node_instance):
        updates = 0
        
        for edge in self.edges: 
            if edge.source == node_origin.id or edge.source == node_origin:
                edge.source = node_instance.id
                updates += 1
            if edge.target == node_origin.id or edge.target == node_origin:
                edge.target = node_instance.id
                updates += 1
        return updates

    def get_end_nodes(self):
        from tricc_oo.models.calculate import (
            TriccNodeEnd,
            TriccNodeActivityEnd,
        )
        return  list(filter(lambda x:  issubclass(x.__class__, (TriccNodeEnd,TriccNodeActivityEnd)), self.nodes.values()))




class TriccNodeDisplayModel(TriccNodeBaseModel):
    name: str
    image: Optional[b64] = None
    hint: Optional[Union[str, Dict[str,str]]] = None
    help: Optional[Union[str, Dict[str,str]]] = None
    group: Optional[Union[TriccGroup, TriccNodeActivity]] = None
    relevance: Optional[Union[Expression, TriccOperation]] = None

    def make_instance(self, instance_nb, activity=None):
        instance = super().make_instance(instance_nb, activity=activity)
        instance.relevance = None
        return instance

    # to use the enum value of the TriccNodeType


class TriccNodeNote(TriccNodeDisplayModel):
    tricc_type: TriccNodeType = TriccNodeType.note

class TriccNodeInputModel(TriccNodeDisplayModel):
    required: Optional[Union[Expression, TriccOperation]] = '1'
    constraint_message: Optional[Union[str, Dict[str,str]]] = None
    constraint: Optional[Expression] = None
    save: Optional[str] = None # contribute to another calculate


class TriccNodeDate(TriccNodeInputModel):
    tricc_type: TriccNodeType = TriccNodeType.date


class TriccNodeMainStart(TriccNodeBaseModel):
    tricc_type: TriccNodeType = TriccNodeType.start
    form_id: Optional[str] = None
    process: Optional[str] = None


class TriccNodeLinkIn(TriccNodeBaseModel):
    tricc_type: TriccNodeType = TriccNodeType.link_in


class TriccNodeLinkOut(TriccNodeBaseModel):
    tricc_type: TriccNodeType = TriccNodeType.link_out
    reference: Optional[Union[TriccNodeLinkIn, triccId]] = None
    # no need to copy


class TriccNodeGoTo(TriccNodeBaseModel):
    tricc_type: TriccNodeType = TriccNodeType.goto
    link: Union[TriccNodeActivity, triccId]

    # no need ot copy
    def make_instance(self, instance_nb, activity, **kwargs):
        # shallow copy
        instance = super().make_instance(instance_nb, activity=activity)
        # do not use activity instance for goto
        instance.instance = self.instance
        return instance


class TriccNodeSelectOption(TriccNodeDisplayModel):
    tricc_type: TriccNodeType = TriccNodeType.select_option
    label: Union[str, Dict[str,str]]
    save: Optional[str] = None
    select: TriccNodeInputModel
    list_name: str


    def make_instance(self, instance_nb, activity, select, **kwargs):
        # shallow copy
        instance = super().make_instance(instance_nb, activity=activity)
        instance.select = select
        return instance

    def get_name(self):
        name = super().get_name()
        select_name = self.select.get_name()
        return select_name + "::" + name


class TriccNodeSelect(TriccNodeInputModel):
    filter: Optional[str] = None
    options: Dict[int, TriccNodeSelectOption] = {}
    list_name: str

    def make_instance(self, instance_nb, activity, **kwargs):
        # shallow copy, no copy of filter and list_name
        instance = super().make_instance(instance_nb, activity=activity)
        instance.options = {}
        for key, option in self.options.items():
            instance.options[key] = option.make_instance(instance_nb, activity=activity, select=instance)
        return instance


class TriccNodeSelectOne(TriccNodeSelect):
    tricc_type: TriccNodeType = TriccNodeType.select_one


class TriccNodeSelectYesNo(TriccNodeSelectOne):
    pass


#    options: List[TriccNodeSelectOption] = [TriccNodeSelectOption(label='Yes', name='yes'),
#                 TriccNodeSelectOption(label='No', name='no')]
class TriccNodeSelectNotAvailable(TriccNodeSelectOne):
    pass


class TriccNodeSelectMultiple(TriccNodeSelect):
    tricc_type: TriccNodeType = TriccNodeType.select_multiple


class TriccNodeNumber(TriccNodeInputModel):
    min: Optional[float] = None
    max: Optional[float] = None
    # no need to copy min max in make isntance


class TriccNodeDecimal(TriccNodeNumber):
    tricc_type: TriccNodeType = TriccNodeType.decimal


class TriccNodeInteger(TriccNodeNumber):
    tricc_type: TriccNodeType = TriccNodeType.integer


class TriccNodeText(TriccNodeInputModel):
    tricc_type: TriccNodeType = TriccNodeType.text

