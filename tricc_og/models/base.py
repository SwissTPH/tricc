from typing import Dict, ForwardRef, List, Optional, Union, Set
from pydantic import BaseModel, constr, validator
from .operators import TriccOperator
import logging
from networkx import MultiDiGraph
from strenum import StrEnum
from enum import auto
from tricc_og.models.tricc import TriccNodeType

TriccCode = constr(regex="^.+$")
TriccSystem = constr(regex="^.+$")
TriccVersion = constr(regex="^.+$")
logger = logging.getLogger("default")


def to_scv_str(system, code, version=None, instance=None):
    return (
        f"{system}|{code}"
        + (f"|{version}" if version else "")
        + (f"::{instance}" if instance else "")
    )


class TriccMixinRef(BaseModel):
    system: TriccSystem = "tricc"
    code: TriccCode
    version: TriccVersion = None
    instance: int = None
    
    def get_name(self):
        return self.scv()
    
    def scv(self):
        return to_scv_str(
            self.system,
            self.code,
            self.version,
            self.instance
        )
    
    def __hash__(self):
        return hash(self.scv())
        # return hash(f"{self.__class__.__name__}{self.get_name()}")

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def __ne__(self, other):
        return not self.__eq__(other)


class TriccTypeMixIn(BaseModel):
    type_scv: TriccMixinRef = None


class TriccBaseAbstractModel(TriccMixinRef, TriccTypeMixIn):

    def make_instance(self, **kwargs):
        logger.error(f"cannot create an instance of an abstract model ")




# Define a forward reference to refer to the class being defined
FwTriccBaseModel = ForwardRef("TriccBaseModel")



class TriccStatic(BaseModel):
    value: Union[str, float, int]

    def __init__(self, value):
        super().__init__(value=value)
        
class TriccSCV(BaseModel):
    value: str

    def __init__(self, value):
        super().__init__(value=value)

FwTriccOperation = ForwardRef("TriccOperation")

class TriccOperation(BaseModel):
    operator: TriccOperator = TriccOperator.NATIVE
    reference: List[Union[FwTriccOperation, TriccStatic, FwTriccBaseModel]] = []

    def __init__(self, tricc_operator, reference=[]):
        operator = tricc_operator.upper() if isinstance(tricc_operator, str) else tricc_operator
        super().__init__(operator=operator, reference=reference)

    def get_references(self):
        predecessor = set()
        if isinstance(self.reference, list):
            for reference in self.reference:
                if isinstance(reference, TriccOperation):
                    predecessor = predecessor | reference.get_references()
                elif issubclass(reference.__class__, FwTriccBaseModel):
                    predecessor.add(reference)
        else:
            raise NotImplementedError("cannot find predecessor of a str")
        return predecessor

    def append(self, value):
        self.reference.append(value)

    def replace_node(self, old_node, new_node, graph):
        if isinstance(self.reference, list):
            for key in [i for i, x in enumerate(self.reference)]:
                if isinstance(self.reference[key], TriccOperation):
                    self.reference[key].replace_node(old_node, new_node)
                elif (
                    issubclass(self.reference[key].__class__, FwTriccBaseModel)
                    and self.reference[key] == old_node.scv() if hasattr(old_node, 'scv') else old_node
                ):
                    self.reference[key] = new_node.scv() if hasattr(new_node, 'scv') else new_node
        elif self.reference is not None:
            raise NotImplementedError(f"cannot manage {self.reference.__class__}")



class AttributesMixin(BaseModel):
    attributes: Dict[str, Union[str, FwTriccBaseModel]] = {}


SelfTriccMixinContext = ForwardRef("TriccContext")


class TriccContext(TriccMixinRef, TriccTypeMixIn, AttributesMixin):
    # context: SelfTriccMixinContext = None
    label: str


class TriccBaseModel(TriccMixinRef, AttributesMixin, TriccTypeMixIn):
    def __str__(self):
        return self.scv()

    # def scv(self):
    #     return f"{self.type_scv.get_name()}:{self.get_name()}"

    instantiate: FwTriccBaseModel = None
    instances: List[FwTriccBaseModel] = []
    context: TriccContext = None
    applicability: TriccOperation = None
    expression: TriccOperation = None
    label: str = ""
    
    class Config:
        # Allow arbitrary types for validation
        arbitrary_types_allowed = True

    def make_instance(self, sibling=False, **kwargs):
        instance = self.copy()
        # change the id to avoid collision of name
        if sibling and not self.instantiate:
            raise ValueError(
                f"cannot make a sibling of {self} because it does not instantiate anything"
            )
        instance.instantiate = self.instantiate if sibling else self
        instance.instance = instance.instantiate.get_next_instance()
        instance.instantiate.instances.append(instance)
        return instance

    def get_next_instance(self):
        return len(self.instances) + 1

class TriccDataModel(TriccBaseAbstractModel):
    validator: Set[TriccOperation] = set()  #


class TriccDataInputModel(TriccDataModel):
    criteria = TriccOperation  # search criteria


class FlowType(StrEnum):
    SEQUENCE = auto()  # and between left and rights
    ASSOCIATION = auto()  # left and one of the rights
    MANDATORY_ASSOCIATION = auto()
    MESSAGE = auto()
    OPTION = auto()


class TriccActivity(TriccBaseModel):
    
    def scv(self):
        return super().scv()
    
    # TODO: how to define the default/ main outputs
    data_inputs: Set[TriccDataInputModel] = set()
    process_output: TriccOperation = None
    data_outputs: Set[TriccDataModel] = set()
    # rules that should be used for conformance
    conformance_rules: Set[TriccOperation] = set()
    elements: Set[TriccBaseModel] = set()
    graph: MultiDiGraph = MultiDiGraph()

    class Config:
        # Allow arbitrary types for validation
        arbitrary_types_allowed = True

    @validator("graph")
    def validate_graph(cls, value):
        validate_graph(value)


def validate_graph(value):
    # Add your custom validation logic here if needed
    if not isinstance(value, MultiDiGraph):
        raise ValueError("graph must be an instance of networkx.MultiDiGraph")
    return value


class TriccTask(TriccBaseModel):
    pass


class TriccProject(TriccBaseAbstractModel, TriccContext):
    lang_code: str = "en"
    # abstract graph / Scheduling
    abs_graph: MultiDiGraph = MultiDiGraph()
    abs_graph_process_start: Dict = {}
    # implementation graph
    impl_graph: MultiDiGraph = MultiDiGraph()
    impl_graph_process_start: Dict = {}
    # authored graph
    graph: MultiDiGraph = MultiDiGraph()
    graph_process_start: Dict = {}
    # list of context:
    contexts : Set[TriccContext] = set()
    # TODO manage trad properly
    def get_keyword_trad(keyword):
        return keyword

    class Config:
        # Allow arbitrary types for validation
        arbitrary_types_allowed = True

    @validator("graph", allow_reuse=True)
    @validator("impl_graph", allow_reuse=True)
    @validator("abs_graph", allow_reuse=True)
    def validate_graph(cls, value):
        validate_graph(value)
    
    def get_context(self, system, code, version=None):
        for context in self.contexts:
            if (
                code == context.code and
                system == context.system and
                version == context.version
            ):
                return context 
        context = TriccContext(
                code=code,
                system=system,
                version=version,
                label=code,
                type_scv=TriccMixinRef(system="tricc_type", code=str(TriccNodeType.context)),
            )
        self.contexts.add(context)
        return context


def to_scv_type(tricc_node_type):
    if isinstance(tricc_node_type, TriccNodeType):
        return TriccMixinRef( 
            system='tricc_type',
            code=tricc_node_type
        )
        
TriccOperation.update_forward_refs()