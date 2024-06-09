from typing import Dict, ForwardRef, List, Optional, Union, Set
from pydantic import BaseModel, constr, validator
from .opperators import TriccOperator
import logging
from networkx import MultiDiGraph
from strenum import StrEnum
from enum import auto

TriccCode = constr(regex="^.+$")
TriccSystem = constr(regex="^.+$")
TriccVersion = constr(regex="^.+$")
logger = logging.getLogger("default")


class TriccMixinRef(BaseModel):
    system: TriccSystem = "tricc"
    code: TriccCode
    version: TriccVersion = None
    instance: int = None
    

    def get_name(self):
        return (
            f"{self.system}|{self.code}"
            + (f"|{self.version}" if self.version else "")
            + (f"::{self.instance}" if self.instance else "")
        )

    def __resp__(self):
        return self.get_name()

    def __hash__(self):
        return hash(self.get_name())
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
SelfTriccBaseModel = ForwardRef("TriccBaseModel")

class AttributesMixin(BaseModel):
    attributes: Dict[str, Union[str, SelfTriccBaseModel]] = {}


class TriccBaseModel(TriccMixinRef, AttributesMixin, TriccTypeMixIn):
    def __str__(self):
        return self.__resp__()

    # def __resp__(self):
    #     return f"{self.type_scv.get_name()}:{self.get_name()}"

    instantiate: SelfTriccBaseModel = None
    instances: List[SelfTriccBaseModel] = []
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


class TriccStatic(BaseModel):
    value: Union[str, float, int]

    def __init__(self, value):
        super().__init__(value=value)


class TriccOperation(BaseModel):
    operator: TriccOperator = TriccOperator.NATIVE
    reference: List[Union[TriccStatic, TriccBaseModel]] = []

    def __init__(self, tricc_operator):
        super().__init__(operator=tricc_operator)

    def get_references(self):
        predecessor = set()
        if isinstance(self.reference, list):
            for reference in self.reference:
                if isinstance(reference, TriccOperation):
                    predecessor = predecessor | reference.get_references()
                elif issubclass(reference.__class__, TriccBaseModel):
                    predecessor.add(reference)
        else:
            raise NotImplementedError("cannot find predecessor of a str")
        return predecessor

    def append(self, value):
        self.reference.append(value)

    def replace_node(self, old_node, new_node):
        if isinstance(self.reference, list):
            for key in [i for i, x in enumerate(self.reference)]:
                if isinstance(self.reference[key], TriccOperation):
                    self.reference[key].replace_node(old_node, new_node)
                elif (
                    issubclass(self.reference[key].__class__, TriccBaseModel)
                    and self.reference[key] == old_node
                ):
                    self.reference[key] = new_node
                    # to cover the options
                    if (
                        hasattr(self.reference[key], "select")
                        and hasattr(new_node, "select")
                        and issubclass(
                            self.reference[key].select.__class__, TriccBaseModel
                        )
                    ):
                        self.replace_node(self.reference[key].select, new_node.select)
        elif self.reference is not None:
            raise NotImplementedError(f"cannot manage {self.reference.__class__}")


SelfTriccMixinContext = ForwardRef("TriccContext")


class TriccContext(TriccMixinRef, TriccTypeMixIn, AttributesMixin):
    context: SelfTriccMixinContext = None
    label: str


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
    inputs: Set[TriccDataInputModel] = set()
    outputs: Set[TriccDataModel] = set()
    rules: Set[TriccOperation] = set()
    applicability: TriccOperation = None
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
    # guide line level
    # abstract_elements: Set[TriccActivity] = set()
    # design level
    # authored_elements: Set[Union[TriccTask, TriccActivity]] = set()
    # actual element that might have several instance of the same authored elements to unloop
    # impl_elements: Set[
    #     Union[
    #         TriccImplementationTask,
    #         TriccImplementationActivity
    #     ]
    # ] = set()
    # abstract graph
    abs_graph: MultiDiGraph = MultiDiGraph()
    # implementation graph
    impl_graph: MultiDiGraph = MultiDiGraph()
    # authored graph
    graph: MultiDiGraph = MultiDiGraph()

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
