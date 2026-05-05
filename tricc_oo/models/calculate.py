from typing import List, Optional, Union
import logging
import re
from pydantic import field_validator
from dateutil.relativedelta import relativedelta

from tricc_oo.models.base import (
    TriccBaseModel, TriccOperation, TriccStatic, TriccReference, Expression, TriccNodeType
)

from tricc_oo.models.tricc import (
    TriccNodeCalculateBase, TriccNodeBaseModel,
)

from tricc_oo.converters.utils import get_rand_name

logger = logging.getLogger(__name__)

ACTIVITY_END_NODE_FORMAT = "aend_{}"


class TriccFrom:
    """Object model for the 'from' attribute on active/repeated populate nodes.
    Supports 'E'/'encounter', 'T'/'today', and ISO 8601 durations like P14D, P1M, P1Y.
    Used in __init__/validation of from_ field.
    """
    def __init__(self, value: str = "E"):
        self.raw = str(value).strip() if value else "E"
        self.scope = None
        self.delta = None
        self._parse()

    def _parse(self):
        val = self.raw.upper()
        if val in ("E", "ENCOUNTER"):
            self.scope = "encounter"
            self.delta = None
        elif val in ("T", "TODAY"):
            self.scope = "today"
            self.delta = None
        else:
            self.scope = "duration"
            self.delta = self._parse_iso_duration(val)

    def _parse_iso_duration(self, s: str):
        # Matches P1Y2M3W4D or P1Y2M3DT4H5M etc.
        pattern = r'^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$'
        match = re.match(pattern, s)
        if match:
            y, m, w, d, h, min_, sec = match.groups()
            return relativedelta(
                years=int(y or 0),
                months=int(m or 0),
                weeks=int(w or 0),
                days=int(d or 0),
                hours=int(h or 0),
                minutes=int(min_ or 0),
                seconds=int(sec or 0)
            )
        logger.warning(f"Could not parse ISO duration: {s}, treating as raw string")
        return None

    def __str__(self):
        return self.raw

    def __repr__(self):
        return f"TriccFrom({self.raw}, scope={self.scope})"

    def is_encounter(self):
        return self.scope == "encounter"

    def is_today(self):
        return self.scope == "today"

    def is_duration(self):
        return self.scope == "duration"


class TriccNodeDisplayCalculateBase(TriccNodeCalculateBase):
    save: Optional[str] = None  # contribute to another calculate
    hint: Optional[str] = None  # for diagnostic display
    help: Optional[str] = None  # for diagnostic display
    trigger: Optional[Union[Expression, TriccOperation, TriccReference]] = None
    applicability: Optional[Union[Expression, TriccOperation, TriccReference]] = None

    # no need to copy save
    def to_fake(self):
        data = vars(self)
        del data["hint"]
        del data["help"]
        del data["save"]
        fake = TriccNodeFakeCalculateBase(**data)
        self.replace_node(fake)
        return fake

    def __str__(self):
        return self.get_name()

    def __repr__(self):
        return self.get_name()


class TriccNodeCalculate(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.calculate
    remote_reference: Optional[Union[Expression, TriccOperation, TriccReference]] = None


class TriccNodeAdd(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.add
    datatype: str = "number"


class TriccNodeCount(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.count
    datatype: str = "number"


class TriccNodeProposedDiagnosis(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.proposed_diagnosis
    severity: str = None
    remote_reference: Optional[Union[Expression, TriccOperation, TriccReference]] = None


class TriccNodeFakeCalculateBase(TriccNodeCalculateBase):
    """Base for fake/calculate-only nodes that don't require display attributes."""
    ... # is_sequence_defined: bool = False


class TriccNodePopulateBase(TriccNodeFakeCalculateBase):
    """Base for all populate/input node types with common attributes."""
    data_type: Optional[str] = None
    concept_type: Optional[str] = None
    is_sequence_defined: bool = False


class TriccNodePopulatePersistent(TriccNodePopulateBase):
    tricc_type: TriccNodeType = TriccNodeType.persistent
    context: str = "patient"  # patient, practitioner, facility, location - default patient per spec


class TriccNodePopulateActive(TriccNodePopulateBase):
    tricc_type: TriccNodeType = TriccNodeType.active
    from_: Optional[Union[str, TriccFrom]] = "E"  # 'from' in spec/JSON, from_ in python; supports E,T,ISO via TriccFrom

    @field_validator('from_', mode='before')
    @classmethod
    def validate_from(cls, v):
        if isinstance(v, TriccFrom):
            return v
        if v is None:
            return TriccFrom("E")
        return TriccFrom(str(v))


class TriccNodePopulateRepeated(TriccNodePopulateBase):
    tricc_type: TriccNodeType = TriccNodeType.repeated
    from_: Optional[Union[str, TriccFrom]] = "E"  # 'from' in spec/JSON, from_ in python

    @field_validator('from_', mode='before')
    @classmethod
    def validate_from(cls, v):
        if isinstance(v, TriccFrom):
            return v
        if v is None:
            return TriccFrom("E")
        return TriccFrom(str(v))


class TriccNodeDisplayBridge(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.bridge


class TriccNodeBridge(TriccNodeFakeCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.bridge


class TriccRhombusMixIn:

    def make_mixin_instance(self, instance, instance_nb, activity, **kwargs):
        # shallow copy
        reference = []
        expression_reference = None
        instance.path = None
        if isinstance(
            self.expression_reference,
            (str, TriccOperation, TriccReference, TriccStatic),
        ):
            expression_reference = self.expression_reference.copy()
            reference = list(expression_reference.get_references())
        if isinstance(self.reference, (str, TriccOperation, TriccReference, TriccStatic)):
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
                        reference.append(ref)
                        logger.warning("new instance of a rhombus use the reference of the base one")
                elif isinstance(ref, TriccReference):
                    reference.append(ref)
                elif isinstance(ref, str):
                    logger.debug("passing raw reference {} on node {}".format(ref, self.get_name()))
                    reference.append(ref)
                else:
                    logger.critical("unexpected reference {} in node {}".format(ref, self.get_name()))
                    exit(1)
        instance.reference = reference
        instance.expression_reference = expression_reference
        instance.name = get_rand_name(self.id)
        return instance


class TriccNodeRhombus(TriccNodeCalculateBase, TriccRhombusMixIn):
    tricc_type: TriccNodeType = TriccNodeType.rhombus
    path: Optional[TriccNodeBaseModel] = None
    reference: Union[
        List[TriccNodeBaseModel],
        Expression,
        TriccOperation,
        TriccReference,
        List[TriccReference],
    ]
    remote_reference: Optional[Union[Expression, TriccOperation, TriccReference]] = None

    def make_instance(self, instance_nb, activity, **kwargs):
        instance = super(TriccNodeRhombus, self).make_instance(instance_nb, activity, **kwargs)
        instance = self.make_mixin_instance(instance, instance_nb, activity, **kwargs)
        return instance

    def __init__(self, **data):
        data["name"] = get_rand_name(data.get("id", None))
        super().__init__(**data)


class TriccNodeDiagnosis(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.diagnosis
    severity: str = None

    def __init__(self, **data):
        data["reference"] = f'"final.{data["name"]}" is true'
        super().__init__(**data)

        # rename rhombus
        self.name = f"anchor.{data["name"]}"


class TriccNodeExclusive(TriccNodeFakeCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.exclusive


def get_node_from_id(activity, node, edge_only):
    node_id = getattr(node, "id", node)
    if not isinstance(node_id, str):
        logger.critical("can set prev_next only with string or node")
        exit(1)
    if issubclass(node.__class__, TriccBaseModel):
        return node_id, node
    elif node_id in activity.nodes:
        node = activity.nodes[node_id]
    elif not edge_only:
        logger.critical(f"cannot find {node_id} in  {activity.get_name()}")
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
    priority: int = 1000

    def __init__(self, **data):
        if data.get("name", None) is None:
            data["name"] = "tricc_end_" + data.get("process", "")
        super().__init__(**data)
        # FOR END

    def set_name(self):
        if self.name is None:
            self.name = self.get_reference()
        # self.name = END_NODE_FORMAT.format(self.activity.id)

    def get_reference(self):
        return "tricc_end_" + (self.process or "")


class TriccNodeActivityStart(TriccNodeFakeCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.activity_start
    relevance: Optional[Union[Expression, TriccOperation]] = None
    status: Optional[str] = None


def get_node_from_list(in_nodes, node_id):
    nodes = list(filter(lambda x: x.id == node_id, in_nodes))
    if len(nodes) > 0:
        return nodes[0]


# qualculate that saves quantity, or we may merge integer/decimals
class TriccNodeQuantity(TriccNodeDisplayCalculateBase):
    tricc_type: TriccNodeType = TriccNodeType.quantity


TriccNodeCalculate.model_rebuild()
