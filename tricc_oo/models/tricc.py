from __future__ import annotations

import logging
import random
import string
from enum import Enum, auto
from typing import Dict, ForwardRef, List, Optional, Union
from fhir.resources.codesystem import CodeSystem
from fhir.resources.valueset import ValueSet
from pydantic import BaseModel, constr
from strenum import StrEnum
from .base import *
from tricc_oo.converters.utils import generate_id

class TriccNodeCalculateBase(TriccNodeBaseModel):
    #input: Dict[TriccOperation, TriccNodeBaseModel] = {}
    reference: Union[List[Union[TriccNodeBaseModel,TriccStatic]], Expression, TriccStatic] = None
    expression_reference: Union[str, TriccOperation] = None
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
        if self.reference:
            instance.reference = [e.copy() if isinstance(e, (TriccReference, TriccOperation)) else (TriccReference(e.name) if hasattr(e, 'name') else e) for e in self.reference]
        else:
            instance.reference = None
        if self.expression_reference:
            instance.expression_reference = self.expression_reference.copy()
        version = self.version + 1
        instance.version = version
        return instance

    def __init__(self, **data):
        if 'name' not in data:
            data['name'] = get_rand_name(data.get('id', None))
        super().__init__(**data)
        
        
    def append(self, elm):
        self.reference.append(elm)
    
    def get_references(self):
        if isinstance(self.reference, set):
            return self.reference
        elif isinstance(self.reference, list):
            return set(self.reference)
        elif isinstance(self.expression_reference, TriccOperation):
            return self.expression_reference.get_references()
        elif isinstance(self.reference, TriccOperation):
            return self.reference.get_references()
        
        elif self.reference:
            return self.reference
            logger.critical("Cannot get reference from a sting")
    def __str__(self):
        return self.get_name()


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
    # - dangling calculate
    # - case definition
    calculates: List[TriccNodeCalculateBase] = []
    applicability: Optional[Union[Expression, TriccOperation]] = None

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
                    instance.calculates.append(instance_node)
            # update parents        
            for node in list(filter(lambda p_node: hasattr(p_node, 'parent'),list(instance.nodes.values()))):
                new_parent = list(filter(lambda p_node: p_node.base_instance == node.parent,list(instance.nodes.values())))
                if new_parent:
                    node.parent = new_parent[0]
                else:
                    logger.error("Parent not found in the activity")
            for group in self.groups.values():
                instance.update_groups(group)
                # update parent group
            for group in self.groups.values():
                instance.update_groups_group(group)

            return instance

    def update_groups_group(self, group):
        for instance_group in self.groups.values():
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
            if isinstance(node_instance, (TriccNodeActivityEnd)):
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
                    # test next_nodes to check that the instance has already prev/next 
                    if node_instance.path is None and node_instance.next_nodes:
                        logger.critical("new path not found")
                elif len(node_instance.prev_nodes) == 1:
                    node.path = list(node_instance.prev_nodes)[0]
                elif not (len(node_instance.reference)== 1  and issubclass(node_instance.reference[0].__class__, TriccNodeInputModel)):
                    error.warning("Rhombus without a path")
                    exit(1)
            # generate options
            elif issubclass(node_instance.__class__, TriccNodeSelect):
                for key, option_instance in node_instance.options.items():
                    updated_edges += self.update_edges(node_origin.options[key], option_instance)
            updated_edges += self.update_edges(node_origin, node_instance)
            if updated_edges == 0:
                node_edge = list(filter(lambda x: (x.source == node_instance.id or x.source == node_instance) , node_instance.activity.edges))
                node_edge_origin = list(filter(lambda x: (x.source == node_origin.id or x.source == node_origin) , node_origin.activity.edges))
                if len(node_edge) == 0 and not issubclass(node_origin.__class__, TriccNodeCalculateBase):
                    logger.warning("no edge was updated for node {}::{}::{}::{}".format(node_instance.activity.get_name(),
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
    hint: Optional[Union[str, TriccNodeBaseModel]] = None
    help: Optional[Union[str, TriccNodeBaseModel]] = None
    group: Optional[Union[TriccGroup, TriccNodeActivity]] = None
    relevance: Optional[Union[Expression, TriccOperation]] = None

    def make_instance(self, instance_nb, activity=None):
        instance = super().make_instance(instance_nb, activity=activity)
        instance.relevance = self.relevance.copy() if self.relevance else None
       
        return instance

    # to use the enum value of the TriccNodeType


class TriccNodeNote(TriccNodeDisplayModel):
    tricc_type: TriccNodeType = TriccNodeType.note

class TriccNodeInputModel(TriccNodeDisplayModel):
    required: Optional[Union[Expression, TriccOperation, TriccStatic]] = '1'
    constraint_message: Optional[Union[str, Dict[str,str]]] = None
    constraint: Optional[Expression] = None
    save: Optional[str] = None # contribute to another calculate


class TriccNodeDate(TriccNodeInputModel):
    tricc_type: TriccNodeType = TriccNodeType.date


class TriccNodeMainStart(TriccNodeBaseModel):
    tricc_type: TriccNodeType = TriccNodeType.start
    form_id: Optional[str] = None
    process: Optional[str] = None
    relevance: Optional[Union[Expression, TriccOperation]] = None


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

class TriccNodeAcceptDiagnostic(TriccNodeSelectOne):
    severity: Optional[str] = None


class TriccParentMixIn(BaseModel):
    parent: Optional[TriccNodeBaseModel]  = None

#    options: List[TriccNodeSelectOption] = [TriccNodeSelectOption(label='Yes', name='yes'),
#                 TriccNodeSelectOption(label='No', name='no')]
class TriccNodeSelectNotAvailable(TriccNodeSelectOne, TriccParentMixIn):
    ...


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

class TriccNodeMoreInfo(TriccNodeInputModel, TriccParentMixIn):
    tricc_type: TriccNodeType = TriccNodeType.help
    
    
class TriccProject(BaseModel):
    title: str = "My project"
    description: str = ""
    lang_code: str = "en"
    # abstract graph / Scheduling
    #abs_graph: MultiDiGraph = MultiDiGraph()
    #abs_graph_process_start: Dict = {}
    # implementation graph
    #impl_graph: MultiDiGraph = MultiDiGraph()
    #impl_graph_process_start: Dict = {}
    # authored graph
    #graph: MultiDiGraph = MultiDiGraph()
    #graph_process_start: Dict = {}
    # list of context:
    pages: Dict[str, TriccNodeActivity]= {}
    start_pages: Dict[str, TriccNodeActivity] = {}
    images: List[Dict[str,str]] = []
    contexts : Set[triccName] = set()
    # TODO manage trad properly
    def get_keyword_trad(keyword):
        return keyword
    # dict of code_system_id: codesystem
    code_systems: Dict[str, CodeSystem] = {}
    # dict of valueset_id: valueset
    value_sets: Dict[str, ValueSet] = {}
    
    #class Config:
        # Allow arbitrary types for validation
    #    arbitrary_types_allowed = True