from __future__ import annotations

import logging
import random
import string
from enum import Enum
from typing import Dict, ForwardRef, List, Optional, Union

from pydantic import BaseModel, constr

from tricc.converters.utils import generate_id

logger = logging.getLogger("default")

Expression = constr(regex="^[^\\/]+$")

triccId = constr(regex="^.+$")
triccIdList = constr(regex="^.+$")

b64 = constr(regex="[^-A-Za-z0-9+/=]|=[^=]|={3,}$")

TriccEdge = ForwardRef('TriccEdge')
# data:page/id,UkO_xCL5ZjyshJO9Bexg


ACTIVITY_END_NODE_FORMAT = "aend_{}"
END_NODE_FORMAT = "end_{}"


class TriccNodeType(str, Enum):
    note = 'note'
    calculate = 'calculate'
    select_multiple = 'select_multiple'
    select_one = 'select_one'
    decimal = 'decimal'
    integer = 'integer'
    text = 'text'


class TriccExtendedNodeType(str, Enum):
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


class TriccOperation(str, Enum):
    _and = 'and'
    _or = 'or'
    _not = 'not'


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
    odk_type: Union[TriccNodeType, TriccExtendedNodeType]
    parent: Optional[triccId]
    instance: int = 1
    base_instance: Optional[TriccBaseModel]

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
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.edge
    source: Union[triccId, TriccNodeBaseModel]
    target: Union[triccId, TriccNodeBaseModel]
    value: Optional[str]

    def make_instance(self, instance_nb, activity=None):
        instance = super().make_instance(instance_nb, activity=activity)
        if issubclass(self.source.__class__, TriccNodeBaseModel):
            instance.source = self.source.copy()
        if issubclass(self.target.__class__, TriccNodeBaseModel):
            instance.target = self.target.copy()
        return instance


class TriccGroup(TriccBaseModel):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.page
    group: Optional[TriccBaseModel]
    name: Optional[str]
    label: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        if self.name is None:
            self.name = generate_id()

    def get_name(self):
        if self.label is not None:
            if len(self.label) < 50:
                return self.label
            else:
                return self.label[:50]
        else:
            return self.name


class TriccNodeBaseModel(TriccBaseModel):
    path_len: int = 0
    group: Optional[Union[TriccGroup, TriccNodeActivity]]
    name: Optional[str]
    label: Optional[str]
    next_nodes: List[TriccNodeBaseModel] = []
    prev_nodes: List[TriccNodeBaseModel] = []

    expression_inputs: List[Expression] = []
    activity: Optional[TriccNodeActivity]

    class Config:
        use_enum_values = True  # <--

    # to be updated while processing because final expression will be possible to build$
    # #only the last time the script will go through the node (all prev node expression would be created

    def get_name(self):
        if self.label is not None:
            if len(self.label) < 50:
                return self.label
            else:
                return self.label[:50]
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
        next_nodes = []
        instance.next_nodes = next_nodes
        prev_nodes = []
        instance.prev_nodes = prev_nodes
        expression_inputs = []
        instance.expression_inputs = expression_inputs

        return instance

    def gen_name(self):
        if self.name is None:
            self.name = ''.join(random.choices(string.ascii_lowercase, k=8))


class TriccNodeActivity(TriccNodeBaseModel):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.activity
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
    relevance: Optional[Expression]

    # redefine 
    def make_instance(self, instance_nb, **kwargs):
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
            for node in list(self.nodes.values()):
                instance.update_nodes(node)
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
        updated_edges = 0
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

            # generate options
            elif issubclass(node_instance.__class__, TriccNodeSelect):
                for key, option_instance in node_instance.options.items():
                    updated_edges += self.update_edges(node_origin.options[key], option_instance)
            updated_edges += self.update_edges(node_origin, node_instance)
            if updated_edges == 0:
                logger.error("no edge was updated for node {}::{}::{}::{}".format(node_instance.activity.get_name(),
                                                                                  node_instance.__class__,
                                                                                  node_instance.get_name(),
                                                                                  node_instance.instance))


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
        end_node = []
        activity_end_node = []
        for node in self.nodes.values():
            if isinstance(node, TriccNodeActivityEnd):
                activity_end_node.append(node)
            elif isinstance(node, TriccNodeEnd):
                end_node.append(node)

        return end_node + activity_end_node


class TriccNodeDiplayModel(TriccNodeBaseModel):
    name: str
    image: Optional[b64]
    hint: Optional[str]
    help: Optional[str]
    group: Optional[Union[TriccGroup, TriccNodeActivity]]
    relevance: Optional[Expression]

    def make_instance(self, instance_nb, activity=None):
        instance = super().make_instance(instance_nb, activity=activity)
        instance.relevance = None
        return instance

    # to use the enum value of the TriccNodeType


class TriccNodeNote(TriccNodeDiplayModel):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccNodeType.note


class TriccNodeInputModel(TriccNodeDiplayModel):
    required: Optional[Expression]
    constraint_message: Optional[str]
    constraint: Optional[Expression]
    save: Optional[str]  # contribute to another calculate


class TriccNodeMainStart(TriccNodeBaseModel):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.start
    form_id: Optional[str]


class TriccNodeLinkIn(TriccNodeBaseModel):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.link_in


class TriccNodeLinkOut(TriccNodeBaseModel):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.link_out
    reference: Optional[Union[TriccNodeLinkIn, triccId]]
    # no need to copy


class TriccNodeGoTo(TriccNodeBaseModel):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.goto
    link: Union[TriccNodeActivity, triccId]

    # no need ot copy
    def make_instance(self, instance_nb, activity, **kwargs):
        # shallow copy
        instance = super().make_instance(instance_nb, activity=activity)
        # do not use activity instance for goto
        instance.instance = self.instance
        return instance


class TriccNodeSelectOption(TriccNodeDiplayModel):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.select_option
    label: str
    save: Optional[str]
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
    filter: Optional[str]
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
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccNodeType.select_one


class TriccNodeSelectYesNo(TriccNodeSelectOne):
    pass


#    options: List[TriccNodeSelectOption] = [TriccNodeSelectOption(label='Yes', name='yes'),
#                 TriccNodeSelectOption(label='No', name='no')]
class TriccNodeSelectNotAvailable(TriccNodeSelectOne):
    pass


class TriccNodeSelectMultiple(TriccNodeSelect):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccNodeType.select_multiple


class TriccNodeNumber(TriccNodeInputModel):
    min: Optional[float]
    max: Optional[float]
    # no need to copy min max in make isntance


class TriccNodeDecimal(TriccNodeNumber):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccNodeType.decimal


class TriccNodeInteger(TriccNodeNumber):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccNodeType.integer


class TriccNodeText(TriccNodeInputModel):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccNodeType.text


class TriccNodeCalculateBase(TriccNodeBaseModel):
    input: Dict[TriccOperation, TriccNodeBaseModel] = {}
    expression: Optional[Expression]  # will be generated based on the input
    version: int = 1
    last: bool = True

    # to use the enum value of the TriccNodeType
    class Config:
        use_enum_values = True  # <--

    def make_instance(self, instance_nb, activity, **kwargs):
        # shallow copy
        instance = super().make_instance(instance_nb, activity=activity)
        input = {}
        instance.input = input
        expression = self.expression.copy() if self.expression is not None else None
        instance.expression = expression
        version = 1
        instance.version = version
        return instance

    def __init__(self, **data):
        super().__init__(**data)
        self.gen_name()


class TriccNodeDisplayCalculateBase(TriccNodeCalculateBase):
    save: Optional[str]  # contribute to another calculate
    hint: Optional[str]  # for diagnostic display
    help: Optional[str]  # for diagnostic display
    # no need to copy save


# qualculate that saves quantity, or we may merge integer/decimals
class TriccNodeQuantity(TriccNodeDisplayCalculateBase):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.quantity


class TriccNodeCalculate(TriccNodeDisplayCalculateBase):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccNodeType.calculate


class TriccNodeAdd(TriccNodeDisplayCalculateBase):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.add


class TriccNodeCount(TriccNodeDisplayCalculateBase):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.count


class TriccNodeFakeCalculateBase(TriccNodeCalculateBase):
    pass


class TriccNodeRhombus(TriccNodeCalculateBase):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.rhombus
    reference: Union[List[TriccNodeBaseModel], Expression]
    expression_reference: Optional[str]
    path: Optional[TriccNodeBaseModel]

    def make_instance(self, instance_nb, activity, **kwargs):
        # shallow copy
        reference = []
        instance = super().make_instance(instance_nb, activity=activity)
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

    def __init__(self, **data):
        super().__init__(**data)
        # rename rhombus
        self.name = get_rand_name(8)


def get_rand_name(k):
    return "r_" + ''.join(random.choices(string.ascii_lowercase, k=k))


class TriccNodeExclusive(TriccNodeFakeCalculateBase):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.exclusive


# Set the source next node to target and clean  next nodes of replace node
def set_prev_next_node(source_node, target_node, replaced_node=None):
    # if it is end node, attached it to the activity/page
    set_prev_node(source_node, target_node, replaced_node)
    if replaced_node is not None and hasattr(source_node, 'next_nodes') and replaced_node in source_node.next_nodes:
        source_node.next_nodes.remove(replaced_node)
    if replaced_node is not None and hasattr(target_node, 'next_nodes') and replaced_node in target_node.next_nodes:
        target_node.next_nodes.remove(replaced_node)
    if target_node not in source_node.next_nodes:
        source_node.next_nodes.append(target_node)
    # if rhombus in next_node of prev node and next node as ref
    if replaced_node is not None:
        rhombus_list = list(filter(lambda x: isinstance(x, TriccNodeRhombus), source_node.next_nodes))
        for rhm in rhombus_list:
            if isinstance(rhm.reference, list):
                if replaced_node in rhm.reference:
                    rhm.reference.remove(replaced_node)
                    rhm.reference.append(target_node)


# Set the target_node prev node to source and clean prev nodes of replace_node
def set_prev_node(source_node, target_node, replaced_node=None):
    # update the prev node of the target not if not an end node
    # update directly the prev node of the target

    if replaced_node is not None and hasattr(target_node, 'prev_nodes') and replaced_node in target_node.prev_nodes:
        target_node.prev_nodes.remove(replaced_node)
    if replaced_node is not None and hasattr(source_node, 'prev_nodes') and replaced_node in source_node.prev_nodes:
        source_node.prev_nodes.remove(replaced_node)
    if source_node not in target_node.prev_nodes:
        target_node.prev_nodes.append(source_node)


def replace_node(old, new, page):
    logger.debug("replacing node {} with node {} from page {}".format(old.get_name(), new.get_name(), page.get_name()))
    # list_node used to avoid updating a list in the loop
    list_nodes = []
    for prev_node in old.prev_nodes:
        list_nodes.append(prev_node)
    for prev_node in list_nodes:
        set_prev_next_node(prev_node, new, old)
    old.prev_nodes = []
    list_nodes = []
    for next_node in old.next_nodes:
        list_nodes.append(next_node)
    for next_node in list_nodes:
        set_prev_next_node(new, next_node, old)
    old.next_nodes = []
    page.nodes[new.id] = new
    # if old.id in page.nodes:
    del page.nodes[old.id]
    for edge in page.edges:
        if edge.source == old.id:
            edge.source = new.id
        if edge.target == old.id:
            edge.target = new.id


def reorder_node_list(list_node, group):
    if len(list_node)>1:
        list_out = []
        list_out_group = []
        list_out_other = []
        for l_node in list_node:
            group_id = l_node.group.id if hasattr(l_node, 'group') and l_node.group is not None else None
            if group is not None and group.id == group_id:
                list_out.append(l_node)
            elif hasattr(group, 'group') and group.group.id == group_id:
                list_out_group.append(l_node)
            else:
                list_out_other.append(l_node)

        list_node = []
        if len(list_out)>0:
            list_node.extend(list_out)
        if len(list_out_group)>0:
            list_node.extend(list_out_group)
        if len(list_out_other)>0:
            list_node.extend(list_out_other)
            
        logger.debug("reorder list init len: {}, group : {} group.group: {} other: {}".format(len(list_node), len(list_out), len(list_out_group), len(list_out_other)))




# walkthough all node in an iterative way, the same node might be parsed 2 times 
# therefore to avoid double processing the nodes variable saves the node already processed
# there 2 strategies : process it the first time or the last time (wait that all the previuous node are processed)

def walktrhough_tricc_node_processed_stached(node, callback, processed_nodes, stashed_nodes, path_len, recursive=True,
                                             **kwargs):
    # logger.debug("walkthrough::{}::{}".format(callback.__name__, node.get_name()))
    if hasattr(node, 'prev_nodes') and len(node.prev_nodes) > 0:
        sorted_list = sorted(node.prev_nodes, key=lambda p_node: p_node.path_len, reverse=True)
        path_len = max(path_len, sorted_list[0].path_len + 1)
    node.path_len = max(node.path_len, path_len)
    if (callback(node, processed_nodes=processed_nodes, stashed_nodes=stashed_nodes, **kwargs)):
        # node processing succeed 
        if node not in processed_nodes:
            processed_nodes.append(node)
            logger.debug("{}::{}: processed ({})".format(callback.__name__, node.get_name(), len(processed_nodes)))
        if node in stashed_nodes:
            stashed_nodes.remove(node)
            # logger.debug("{}::{}: unstashed ({})".format(callback.__name__, node.get_name(), len(stashed_nodes)))
        # put the stached node from that group first
        # if has next, walkthrough them (support options)
        # if len(stashed_nodes)>1:
        if not recursive:
            reorder_node_list(stashed_nodes, node.group)
        # logger.debug("{}::{}: reorder stashed ({})".format(callback.__name__, node.get_name(), len(stashed_nodes)))
        if isinstance(node, TriccNodeActivity):
            if node.root is not None:
                node.root.path_len = max(path_len,  node.root.path_len)
                if recursive:
                    walktrhough_tricc_node_processed_stached(node.root, callback, processed_nodes, stashed_nodes, path_len,
                                                         recursive, **kwargs)
                elif node.root not in stashed_nodes:
                    stashed_nodes.insert(0,node.root)
                return
        elif isinstance(node, TriccNodeActivityEnd):
            for next_node in node.activity.next_nodes:
                if next_node not in stashed_nodes:
                    stashed_nodes.insert(0,next_node)

        elif issubclass(node.__class__, TriccNodeSelect):
            for option in node.options.values():
                option.path_len = max(path_len,  option.path_len)
                callback(option, processed_nodes=processed_nodes, stashed_nodes=stashed_nodes, **kwargs)
                if option not in processed_nodes:
                    processed_nodes.append(option)
                    logger.debug(
                        "{}::{}: processed ({})".format(callback.__name__, option.get_name(), len(processed_nodes)))
                walkthrough_tricc_option(node, callback, processed_nodes, stashed_nodes, path_len + 1, recursive,
                                         **kwargs)
        if hasattr(node, 'next_nodes') and len(node.next_nodes) > 0:
            walkthrough_tricc_next_nodes(node, callback, processed_nodes, stashed_nodes, path_len + 1, recursive,
                                             **kwargs)
    else:
        if node not in processed_nodes and node not in stashed_nodes:
            if node not in stashed_nodes:
                stashed_nodes.insert(0,node)
                logger.debug("{}::{}: stashed({})".format(callback.__name__, node.get_name(), len(stashed_nodes)))


def walkthrough_tricc_next_nodes(node, callback, processed_nodes, stashed_nodes, path_len, recursive, **kwargs):
    if not recursive:
        for next_node in node.next_nodes:
            if next_node not in stashed_nodes:
                stashed_nodes.append(next_node)
    else:
        list_next = []
        while not all(elem in list_next for elem in node.next_nodes):
            for next_node in node.next_nodes:
                if next_node not in list_next:
                    list_next.append(next_node)
                    if not isinstance(node, (TriccNodeActivityEnd, TriccNodeEnd)):
                        walktrhough_tricc_node_processed_stached(next_node, callback, processed_nodes, stashed_nodes,
                                                                path_len + 1,recursive, **kwargs)
                    else:
                        logger.error(
                            "{}::end node of {} has a next node".format(callback.__name__.node.activity.get_name()))
                        exit()


def walkthrough_tricc_option(node, callback, processed_nodes, stashed_nodes, path_len, recursive, **kwargs):
    if not recursive:
        for option in node.options.values():
            if hasattr(option, 'next_nodes') and len(option.next_nodes) > 0:
                for next_node in option.next_nodes:
                    if next_node not in stashed_nodes:
                        stashed_nodes.append(next_node)
    else:
        list_option = []
        while not all(elem in list_option for elem in list(node.options.values())):
            for option in node.options.values():
                if option not in list_option:
                    list_option.append(option)
                    # then walk the options   
                    if hasattr(option, 'next_nodes') and len(option.next_nodes) > 0:
                        list_next = []
                        while not all(elem in list_next for elem in option.next_nodes):
                            for next_node in option.next_nodes:
                                if next_node not in list_next:
                                    list_next.append(next_node)
                                    walktrhough_tricc_node_processed_stached(next_node, callback, processed_nodes,
                                                                            stashed_nodes, path_len + 1, recursive,
                                                                            **kwargs)


def stashed_node_func(node, callback, recusive=False, **kwargs):
    processed_nodes = kwargs.get('processed_nodes', [])
    stashed_nodes = kwargs.get('stashed_nodes', [])
    path_len = 0
    walktrhough_tricc_node_processed_stached(node, callback, processed_nodes, stashed_nodes, path_len, recusive,
                                             **kwargs)
    # callback( node, **kwargs)
    ## MANAGE STASHED NODES
    prev_stashed_nodes = stashed_nodes.copy()
    loop_count = 0
    len_prev_processed_nodes = 0
    while len(stashed_nodes) > 0:
        loop_count = check_stashed_loop(stashed_nodes, prev_stashed_nodes, processed_nodes, len_prev_processed_nodes,
                                        loop_count)
        prev_stashed_nodes = stashed_nodes.copy()
        len_prev_processed_nodes = len(processed_nodes)
        if len(stashed_nodes) > 0:
            s_node = stashed_nodes.pop()
            # remove duplicates
            if s_node in stashed_nodes:
                stashed_nodes.remove(s_node)
            logger.debug("{}::{}: unstashed for processing ({})".format(callback.__name__, s_node.get_name(),
                                                                        len(stashed_nodes)))
            walktrhough_tricc_node_processed_stached(s_node, callback, processed_nodes, stashed_nodes, path_len,
                                                     recusive, **kwargs)


# check if the all the prev nodes are processed
def is_ready_to_process(in_node, processed_nodes, strict=True):
    if isinstance(in_node, TriccNodeSelectOption):
        node = in_node.select
    elif isinstance(in_node, TriccNodeActivityStart):
        node = in_node.activity
    else:
        node = in_node
    if hasattr(node, 'prev_nodes'):
        # ensure the  previous node of the select are processed, not the option prev nodes
        for prev_node in node.prev_nodes:
            if isinstance(prev_node, TriccNodeActivity):
                activity_end_nodes = prev_node.get_end_nodes()
                if len(activity_end_nodes) == 0:
                    logger.error("is_ready_to_process:failed: {1} -act-> {0} NO end nodes".format(prev_node.get_name(),
                                                                                                  node.get_name()))
                    return False
                for end_node in activity_end_nodes:
                    if end_node not in processed_nodes:
                        logger.debug(
                            "is_ready_to_process:failed: {2} -act-> {0} -end-> {1}".format(prev_node.get_name(),
                                                                                           end_node.get_name(),
                                                                                           node.get_name()))
                        return False
            elif prev_node not in processed_nodes:
                if isinstance(prev_node, TriccNodeExclusive):
                    logger.debug("is_ready_to_process:failed: {0} -excl-> {2} --> {1}".format(node.get_name(),
                                                                                              prev_node.prev_nodes[
                                                                                                  0].get_name(),
                                                                                              prev_node.get_name()))
                else:
                    logger.debug(
                        "is_ready_to_process:failed: {1}  --> {0}".format(node.get_name(), prev_node.get_name()))

                logger.debug("prev node node {}:{} for node {} not in processed".format(prev_node.__class__,
                                                                                        prev_node.get_name(),
                                                                                        node.get_name()))
                return False
        if strict:
            return is_rhombus_ready_to_process(node, processed_nodes)
        else:
            return True
    else:
        return True


def print_trace(node, prev_node, processed_nodes, stashed_nodes):
    if node != prev_node:
        if node in processed_nodes:
            logger.warning("print trace :: node {}::{}::{} was the last not processed ({}::{} is porcessed)".format(
                prev_node.__class__, prev_node.get_name(), prev_node.instance, node.id, node.get_name()))
            processed_nodes.append(prev_node)
            return False
        elif node in stashed_nodes:
            #            logger.debug("print trace :: node {}::{} in stashed".format(node.__class__,node.get_name()))
            return False
            # else:
        # logger.debug("print trace :: node {} not processed/stashed".format(node.get_name()))     
    return True


def reverse_walkthrough(in_node, next_node, callback, processed_nodes, stashed_nodes):
    # transform dead-end nodes
    if next_node == in_node and next_node not in stashed_nodes:
        # workaround fir loop
        return False

    if isinstance(in_node, TriccNodeSelectOption):
        node = in_node.select
    elif isinstance(in_node, TriccNodeActivityStart):
        node = in_node.activity
    else:
        node = in_node
    if callback(node, next_node, processed_nodes, stashed_nodes):
        if isinstance(in_node, TriccNodeActivity):
            prev_nodes = in_node.get_end_nodes()
            for prev in prev_nodes:
                reverse_walkthrough(prev, next_node, callback, processed_nodes, stashed_nodes)
        if hasattr(node, 'prev_nodes'):
            for prev in node.prev_nodes:
                reverse_walkthrough(prev, node, callback, processed_nodes, stashed_nodes)
        if isinstance(node, TriccNodeRhombus):
            if isinstance(node.reference, list):
                for ref in node.reference:
                    reverse_walkthrough(ref, node, callback, processed_nodes, stashed_nodes)


def is_rhombus_ready_to_process(node, processed_nodes):
    if isinstance(node, TriccNodeRhombus):
        if isinstance(node.reference, str):
            return False  # calculate not yet processed
        elif isinstance(node.reference, list):
            for ref in node.reference:
                if issubclass(ref.__class__, TriccNodeBaseModel) and ref not in processed_nodes:
                    return False
                elif issubclass(ref.__class__, str):
                    logger.debug("Node {1} as still a reference to string")
    return True


def get_prev_node_by_name(processed_nodes, name, node):
    filtered = list(filter(lambda p_node: hasattr(p_node,'name') and p_node.name == name and p_node.instance == node.instance and p_node.path_len <= node.path_len, processed_nodes))
    if len(filtered) == 0:
        filtered = list(filter(lambda p_node: hasattr(p_node, 'name') and p_node.name == name, processed_nodes))
    if len(filtered) > 0:
        return sorted(filtered, key=lambda x: x.path_len, reverse=False)[0]


def check_stashed_loop(stashed_nodes, prev_stashed_nodes, processed_nodes, len_prev_processed_nodes, loop_count):
    loop_out = {}
    if len(stashed_nodes) == len(prev_stashed_nodes):

        # copy to sort
        cur_stashed_nodes = sorted(stashed_nodes, key=lambda x: x.id, reverse=True)

        prev_stashed_nodes = sorted(prev_stashed_nodes, key=lambda x: x.id, reverse=True)

        if cur_stashed_nodes == prev_stashed_nodes and len(processed_nodes) == len_prev_processed_nodes:
            loop_count += 1
            if loop_count > 10 * len(prev_stashed_nodes) + 1:
                logger.error("Stashed node list was unchanged: loop likely or a cyclic redundancy")
                for es_node in cur_stashed_nodes:
                    logger.error("Stashed node {}:{}:{}:{}".format(es_node.__class__, es_node.activity.get_name(),
                                                                   es_node.instance, es_node.get_name()))
                    reverse_walkthrough(es_node, es_node, print_trace, processed_nodes, stashed_nodes)
                if len(stashed_nodes) == len(prev_stashed_nodes):
                    exit()
        else:
            loop_count = 0
    else:
        loop_count = 0
    return loop_count


class TriccNodeActivityEnd(TriccNodeCalculateBase):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.activity_end

    def __init__(self, **data):
        super().__init__(**data)
        # FOR END
        self.set_name()

    def set_name(self):
        self.name = ACTIVITY_END_NODE_FORMAT.format(self.activity.id)


class TriccNodeEnd(TriccNodeCalculate):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.end

    def __init__(self, **data):
        super().__init__(**data)
        # FOR END
        self.set_name()

    def set_name(self):
        self.name = END_NODE_FORMAT.format(self.activity.id)


class TriccNodeActivityStart(TriccNodeCalculate):
    odk_type: Union[TriccNodeType, TriccExtendedNodeType] = TriccExtendedNodeType.activity_start


class TriccExpression(BaseModel):
    list_or: List[Union[TriccExpression, TriccExpressionNot, str]]
    next_and: Optional[Union[TriccExpression, TriccExpressionNot, str]]


class TriccExpressionNot(BaseModel):
    exp = TriccExpression


def get_node_from_list(in_nodes, node_id):
    nodes = list(filter(lambda x: x.id == node_id, in_nodes))
    if len(nodes) > 0:
        return nodes[0]


# update FF
TriccEdge.update_forward_refs()
