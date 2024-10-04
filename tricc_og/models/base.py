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


def to_scv_str(system, code, version=None, instance=None, with_instance=True):
    return (
        f"{system}_{code}" # here it was a pipe but I was getting './tricc_oo/tests/data/tricc|medlacreator.xlsx' so changed. Not sure of other implications so comenting FIXME
        + (f"|{version}" if version else "")
        + (f"::{instance}" if instance and with_instance else "")
    )


class TriccMixinRef(BaseModel):
    system: TriccSystem = "tricc"
    code: TriccCode
    version: TriccVersion = None
    instance: int = None
    
    def get_name(self):
        return self.scv()
    
    def scv(self,with_instance=True):
        return to_scv_str(
            self.system,
            self.code,
            self.version,
            self.instance,
            with_instance=with_instance
        )
    
    def __hash__(self):
        return hash(self.scv())
        # return hash(f"{self.__class__.__name__}{self.get_name()}")

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def __ne__(self, other):
        return not self.__eq__(other)


class TriccTypeMixIn(BaseModel):
    def __str__():
        return type_scv.code
                                                                                
    type_scv: TriccMixinRef = None


class TriccBaseAbstractModel(TriccMixinRef, TriccTypeMixIn):

    def make_instance(self, **kwargs):
        logger.error(f"cannot create an instance of an abstract model ")




# Define a forward reference to refer to the class being defined
FwTriccBaseModel = ForwardRef("TriccBaseModel")



class TriccStatic(BaseModel):
    value: Union[str, float, int]

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, cls):
            return v
        return cls(value=v)

    def __init__(self, value):
        super().__init__(value=value)
        
class TriccSCV(BaseModel):
    value: str

    def __hash__(self):
        return hash(self.value)

    def __init__(self, value):
        super().__init__(value=value)
    
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, cls):
            return v
        return cls(value=v)

FwTriccOperation = ForwardRef("TriccOperation")

class TriccOperation(BaseModel):
    operator: TriccOperator = TriccOperator.NATIVE
    reference: List[Union[FwTriccOperation, TriccSCV, TriccStatic, FwTriccBaseModel]] = []
    @validator('reference', pre=True, each_item=True)
    def validate_reference_items(cls, v):
        if isinstance(v, (TriccOperation, TriccSCV, TriccStatic, FwTriccBaseModel)):
            return v
        raise ValueError(f"Invalid type in reference: {type(v)}")
    def __str__(self):

        str_ref = map(str, self.reference)
        return f"{self.operator}({', '.join(str_ref)})"
    def __init__(self, tricc_operator, reference=[]):
        operator = tricc_operator.upper() if isinstance(tricc_operator, str) else tricc_operator
        super().__init__(operator=operator, reference=reference)

    def get_references(self):
        predecessor = set()
        if isinstance(self.reference, list):
            for reference in self.reference:
                if isinstance(reference, TriccOperation):
                    predecessor = predecessor | reference.get_references()
                    #predecessor.update(reference.get_references())
                elif isinstance(reference, (TriccSCV, TriccBaseModel, TriccActivity, TriccTask)):
                    predecessor.add(reference)
        elif isinstance(self.reference, TriccOperation):
            predecessor = predecessor | reference.get_references()
            #predecessor.update(self.reference.get_references())
        elif isinstance(self.reference, TriccSCV):
            predecessor.add(self.reference)
        elif isinstance(self.reference, (TriccBaseModel, TriccActivity, TriccTask)):
            predecessor.add(self.reference.scv())
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
                    issubclass(self.reference[key].__class__, TriccBaseModel)
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
    def __repr__(self):
        return f"{self.scv()}: {self.label} ({self.context.scv() if self.context else ''}) ; expression:{self.expression}"
    # def scv(self):
    #     return f"{self.type_scv.get_name()}:{self.get_name()}"

    instantiate: FwTriccBaseModel = None
    instances: List[FwTriccBaseModel] = []
    context: TriccContext = None
    applicability: TriccOperation = None
    expression: TriccOperation = None
    label: str = ""
    reference: str = ""
    
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
    
    def scv(self, with_instance=True):
        return super().scv(with_instance=True)
    
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

    def make_instance(self, sibling=False, **kwargs):
        instance = super(TriccActivity, self).make_instance(sibling=sibling, **kwargs)
        # the base instance might be already expended
        if sibling:
            instance.attributes['expended'] = False
        instance.graph = MultiDiGraph()
        return instance
        
        
def validate_graph(value):
    # Add your custom validation logic here if needed
    if not isinstance(value, MultiDiGraph):
        raise ValueError("graph must be an instance of networkx.MultiDiGraph")
    return value


class TriccTask(TriccBaseModel):
    
    pass



class TriccProject(TriccBaseAbstractModel, TriccContext):
    title: str = "My project"
    description: str = ""
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