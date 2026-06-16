from __future__ import annotations

import logging
from typing import Annotated, Dict, ForwardRef, List, Optional, Union

from pydantic import BaseModel, StringConstraints
from strenum import StrEnum

from tricc_oo.converters.utils import generate_id, get_rand_name
from tricc_oo.models.ordered_set import OrderedSet

logger = logging.getLogger("default")

Expression = Annotated[str, StringConstraints(pattern=r".+")]

triccId = Annotated[str, StringConstraints(pattern=r"^[^\\/\: ]+$")]

triccName = Annotated[str, StringConstraints(pattern=r"^[^\s]+( [^\s]+)*$")]

b64 = Annotated[str, StringConstraints(pattern=r"^[^-A-Za-z0-9+/=]|=[^=]|={3,}$")]

END_NODE_FORMAT = "end_{}"


class TriccNodeType(StrEnum):
    # replace with auto ?
    note = "note"
    calculate = ("calculate",)
    output = ("output",)
    select_multiple = "select_multiple"
    select_one = "select_one"
    select_yesno = "select_one yesno"
    select_option = "select_option"
    decimal = "decimal"
    integer = "integer"
    text = "text"
    date = "date"
    rhombus = "rhombus"  # fetch data
    factor = "factor"  # sequence scoring: if path then reference else 0
    goto = "goto"  #: start the linked activity within the target activity
    start = "start"  #: main start of the algo
    activity_start = "activity_start"  #: start of an activity (link in)
    link_in = "link_in"
    link_out = "link_out"
    count = "count"  #: count the number of valid input
    add = "add"  # add counts
    container_hint_media = "container_hint_media"  # DEPRECATED
    activity = "activity"
    help = "help-message"
    hint = "hint-message"
    exclusive = "not"
    end = "end"
    activity_end = "activity_end"
    edge = "edge"
    page = "container_page"
    not_available = "not_available"
    quantity = "quantity"
    bridge = "bridge"
    wait = "wait"
    operation = "operation"
    context = "context"
    diagnosis = "diagnosis"
    proposed_diagnosis = "proposed_diagnosis"
    input = "input"
    populate = "populate"
    remote_reference = "remote_reference"

    def __iter__(self):
        return iter(self.__members__.values())

    def __next__(self):
        return next(iter(self))


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
    external_id: triccId = None
    tricc_type: TriccNodeType
    datatype: str = None
    instance: int = 0
    base_instance: Optional[TriccBaseModel] = None
    last: bool = None
    version: int = 1

    def get_datatype(self):
        return self.datatype or self.tricc_type

    def get_next_instance(self):
        if getattr(self, "instances", None):
            return max(100, *[n.instance for n in self.instances.values()]) + 1
        if getattr(self, "base_instance", None) and getattr(self.base_instance, "instances", None):
            return max(100, *[n.instance for n in self.base_instance.instances.values()]) + 1
        return max(100, self.instance) + 1

    def to_dict(self):
        return {key: value for key, value in vars(self).items() if not key.startswith("_")}

    def make_instance(self, nb_instance=None, **kwargs):
        if nb_instance is None:
            nb_instance = self.get_next_instance()
        instance = self.copy()
        attr_dict = self.to_dict()
        for attr, value in attr_dict.items():
            if not attr.startswith("_") and value is not None:
                try:
                    if hasattr(value, "copy"):
                        setattr(instance, attr, value.copy())
                    else:
                        setattr(instance, attr, value)
                except Exception as e:
                    logger.warning(f"Warning: Could not copy attribute {attr}: {e}")

        # change the id to avoid collision of name
        instance.id = generate_id(f"{self.id}{nb_instance}")
        instance.instance = int(nb_instance)
        instance.base_instance = self
        if hasattr(self, "instances"):
            self.instances[nb_instance] = instance

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
        return f"{self.id}|{self.instance}|{self.version}" 
    
    def __str__(self):
        return self.get_name()

    def __repr__(self):
        return f"{self.tricc_type}:{self.get_name()}({self.id})"

    def __init__(self, **data):
        if "id" not in data:
            data["id"] = generate_id(str(data))
        super().__init__(**data)


class TriccEdge(TriccBaseModel):
    tricc_type: TriccNodeType = TriccNodeType.edge
    source: Union[triccId, TriccNodeBaseModel]
    source_external_id: triccId = None
    target: Union[triccId, TriccNodeBaseModel]
    target_external_id: triccId = None
    value: Optional[str] = None


class TriccGroup(TriccBaseModel):
    tricc_type: TriccNodeType = TriccNodeType.page
    group: Optional[TriccBaseModel] = None
    activity: TriccBaseModel
    name: Optional[str] = None
    export_name: Optional[str] = None
    label: Optional[Union[str, Dict[str, str]]] = None
    relevance: Optional[Union[Expression, TriccOperation]] = None
    path_len: int = 0
    prev_nodes: OrderedSet[TriccBaseModel] = OrderedSet()

    def __init__(self, **data):
        super().__init__(**data)
        if self.name is None:
            self.name = generate_id(str(data))

    def gen_name(self):
        if self.name is None:
            self.name = get_rand_name(self.id)

    def get_name(self):
        result = str(super().get_name())
        name = getattr(self, "name", None)
        label = getattr(self, "label", None)

        if name:
            result = result + "|" + name
        if label:
            result = result + "|" + (next(iter(self.label.values())) if isinstance(self.label, Dict) else self.label)
        if len(name) < 50:
            return result
        else:
            return result[:50]


FwTriccNodeBaseModel = ForwardRef("TriccNodeBaseModel")


def get_repeat(node) -> int:
    """Return effective repeat slot for concept instance scoping. Default 1."""
    if node is None:
        return 1
    value = getattr(node, "repeat", None)
    if value is None:
        return 1
    return int(value)


class TriccNodeBaseModel(TriccBaseModel):
    path_len: int = 0
    group: Optional[Union[TriccGroup, FwTriccNodeBaseModel]] = None
    name: Optional[str] = None
    repeat: Optional[int] = None
    export_name: Optional[str] = None
    label: Optional[Union[str, Dict[str, str]]] = None
    next_nodes: OrderedSet[TriccNodeBaseModel] = OrderedSet()
    prev_nodes: OrderedSet[TriccNodeBaseModel] = OrderedSet()
    expression: Optional[Union[Expression, TriccOperation, TriccStatic]] = None  # will be generated based on the input
    expression_inputs: List[Expression] = []
    activity: Optional[FwTriccNodeBaseModel] = None
    ref_def: Optional[Union[int, str]] = None  # for medal creator
    is_sequence_defined: bool = False

    class Config:
        use_enum_values = True  # <--

    def __hash__(self):
        return hash(self.id)

    # to be updated while processing because final expression will be possible to build$
    # #only the last time the script will go through the node (all prev node expression would be created
    def get_name(self):
        result = self.__class__.__name__[9:]  # str(super().get_name())
        name = getattr(self, "name", None)
        label = getattr(self, "label", None)

        if name:
            result += f"|{name}|{self.instance}|{self.version}" 
        if label:
            result += "|" + (next(iter(self.label.values())) if isinstance(self.label, Dict) else self.label)
        if len(result) < 80:
            return result
        else:
            return result[:80]

    def make_instance(self, instance_nb=None, activity=None):
        instance = super().make_instance(instance_nb)
        instance.group = activity
        if hasattr(self, "activity") and activity is not None:
            instance.activity = activity
        next_nodes = OrderedSet()
        instance.next_nodes = next_nodes
        prev_nodes = OrderedSet()
        instance.prev_nodes = prev_nodes
        expression_inputs = []
        instance.expression_inputs = expression_inputs

        for attr in [
            "expression",
            "relevance",
            "default",
            "reference",
            "remote_reference",
            "expression_reference",
        ]:
            if getattr(self, attr, None):
                setattr(instance, attr, getattr(self, attr))

        return instance

    def gen_name(self):
        if self.name is None:
            self.name = get_rand_name(self.id)

    def get_references(self):
        return OrderedSet()


class TriccStatic(BaseModel):
    value: Union[str, float, int, bool, TriccNodeBaseModel]

    def __init__(self, value):
        super().__init__(value=value)

    def get_datatype(self):
        if str(type(self.value)) == "bool":
            return "boolean"
        elif str(self.value).isnumeric():
            return "number"
        else:
            return str(type(self.value))

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.value == other.value
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        hash_value = hash(self.value)
        return hash_value

    def get_name(self):
        return self.value

    def __str__(self):
        return str(self.value)

    def __copy__(self, **argv):
        return super().__copy__()

    def copy(self, **argv):
        return self.__copy__()

    def __repr__(self):
        return self.__class__.__name__ + "|" + str(type(self.value)) + "|" + str(self.value)

    def get_references(self):
        return OrderedSet()


class TriccReference(TriccStatic):
    value: str

    def __copy__(self):
        return type(self)(self.value)

    def copy(self):
        return self.__copy__()

    def get_references(self):
        return OrderedSet([self])


class TriccOperator(StrEnum):
    AND = "and"  # and between left and rights
    ADD_OR = "and_or"  # left and one of the righs
    # ADD_STRING: 'add_string'
    OR = "or"  # or between left and rights
    NATIVE = "native"  # default left is native expression
    ISTRUE = "istrue"  # left is right
    ISNOTTRUE = "isnottrue"
    ISFALSE = "isfalse"  # left is false
    ISNOTFALSE = "isnotfalse"  # left is false
    SELECTED = "selected"  # right must be la select and one or several options
    MORE_OR_EQUAL = "more_or_equal"
    LESS_OR_EQUAL = "less_or_equal"
    EQUAL = "equal"
    MORE = "more"
    NOTEQUAL = "not_equal"
    BETWEEN = "between"
    LESS = "less"
    CONTAINS = "contains"  # ref, txt Does CONTAINS make sense, like Select with wildcard
    NOTEXISTS = "notexists"
    EXISTS = "exists"
    NOT = "not"
    ISNULL = "isnull"
    ISNOTNULL = "isnotnull"
    ROUND = "round"

    CASE = "case"  # ref (equal value, res), (equal value,res)
    IFS = "ifs"  # (cond, res), (cond,res)
    IF = "if"  # cond val_true, val_false

    # CDSS Specific
    HAS_QUALIFIER = "has_qualifier"
    ZSCORE = "zscore"  # left table_name, right Y, gender give Z
    IZSCORE = "izscore"  # left table_name, right Z, gender give Y
    AGE_DAY = "age_day"  # age from dob
    AGE_MONTH = "age_month"  # age from dob
    AGE_YEAR = "age_year"  # age from dob
    DIVIDED = "divided"
    MULTIPLIED = "multiplied"
    PLUS = "plus"
    MINUS = "minus"
    MODULO = "modulo"
    COUNT = "count"
    CAST_NUMBER = "cast_number"
    CAST_INTEGER = "cast_integer"
    DRUG_DOSAGE = "drug_dosage"  # drug name, *param1 (ex: weight, age)
    COALESCE = "coalesce"
    GET_INHERITED_VALUE = "get_inherited_value"
    CAST_DATE = "cast_date"
    CAST_STRING = "cast_string"
    CAST_BOOLEAN = "cast_boolean"
    PARENTHESIS = "parenthesis"
    CONCATENATE = "concatenate"
    DATETIME_TO_DECIMAL = "datetime_to_decimal"
    DIAGNOSIS_LIST = "diagnosis_list"
    LENGTH = "length"
    TODAY = "today"
    NOW = "now"
    ABS = "abs"
    MIN = "min"
    MAX = "max"
    SUM = "sum"
    FORMAT_DATE = "format_date"




RETURNS_BOOLEAN = [
    TriccOperator.ADD_OR,
    TriccOperator.AND,
    TriccOperator.OR,
    TriccOperator.BETWEEN,
    TriccOperator.CONTAINS,
    TriccOperator.EXISTS,
    TriccOperator.NOTEXISTS,
    TriccOperator.ISFALSE,
    TriccOperator.ISNOTFALSE,
    TriccOperator.ISNOTNULL,
    TriccOperator.ISTRUE,
    TriccOperator.ISNOTTRUE,
    TriccOperator.SELECTED,
    TriccOperator.HAS_QUALIFIER,
    TriccOperator.NOT,
    TriccOperator.NOTEQUAL,
    TriccOperator.MORE_OR_EQUAL,
    TriccOperator.LESS_OR_EQUAL,
    TriccOperator.EQUAL,
    TriccOperator.MORE,
    TriccOperator.LESS,
]

RETURNS_NUMBER = [
    TriccOperator.AGE_DAY,
    TriccOperator.AGE_MONTH,
    TriccOperator.AGE_YEAR,
    TriccOperator.ZSCORE,
    TriccOperator.IZSCORE,
    TriccOperator.ROUND,
    TriccOperator.DATETIME_TO_DECIMAL,
    TriccOperator.PLUS,
    TriccOperator.MINUS,
    TriccOperator.DIVIDED,
    TriccOperator.MULTIPLIED,
    TriccOperator.COUNT,
    TriccOperator.MODULO,
    TriccOperator.CAST_NUMBER,
    TriccOperator.CAST_INTEGER,
]

RETURNS_DATE = [TriccOperator.CAST_DATE]

RETURNS_STRING = [TriccOperator.DIAGNOSIS_LIST]

OPERATION_LIST = {
    ">=": TriccOperator.MORE_OR_EQUAL,
    "<=": TriccOperator.LESS_OR_EQUAL,
    "==": TriccOperator.EQUAL,
    "!=": TriccOperator.NOTEQUAL,
    "=": TriccOperator.EQUAL,
    ">": TriccOperator.MORE,
    "<": TriccOperator.LESS,
}


class TriccOperation(BaseModel):
    tricc_type: TriccNodeType = TriccNodeType.operation
    operator: TriccOperator = TriccOperator.NATIVE
    reference: OrderedSet[
        Union[
            TriccStatic,
            TriccNodeBaseModel,
            TriccOperation,
            TriccReference,
            Expression,
            List[
                Union[
                    TriccStatic,
                    TriccNodeBaseModel,
                    TriccOperation,
                    TriccReference,
                    Expression,
                ]
            ],
        ]
    ] = []

    def __str__(self):
        str_ref = map(str, self.reference)
        return f"{self.operator}({', '.join(map(str, str_ref))})"

    def __hash__(self):
        return hash(self.__repr__())

    def __repr__(self):
        str_ref = map(repr, self.reference)
        return f"TriccOperation:{self.operator}({', '.join(map(str, str_ref))})"

    def __eq__(self, other):
        return self.__str__() == str(other)

    def __init__(self, operator, reference=[]):
        super().__init__(operator=operator, reference=reference)

    def get_datatype(self):
        if self.operator in RETURNS_BOOLEAN:
            return "boolean"
        elif self.operator in RETURNS_NUMBER:
            return "number"
        elif self.operator in RETURNS_DATE:
            return "date"
        elif self.operator in RETURNS_STRING:
            return "string"
        elif self.operator == TriccOperator.CONCATENATE:
            return "string"
        elif self.operator == TriccOperator.PARENTHESIS:
            return self.get_reference_datatype(self.reference)
        elif self.operator == TriccOperator.IF:
            return self.get_reference_datatype(self.reference[1:])
        elif self.operator in (TriccOperator.IFS, TriccOperator.CASE):
            rtype = set()
            for rl in self.reference:
                rtype.add(self.get_reference_datatype(self.reference[-2:]))
            if len(rtype) > 1:
                return "mixed"
            else:
                return rtype.pop()
        else:
            return self.get_reference_datatype(self.reference)

    def get_reference_datatype(self, references):
        rtype = set()
        for r in references:
            if hasattr(r, "get_datatype"):
                rtype.add(r.get_datatype())
            elif hasattr(r, "value"):
                return str(type(r.value))
            else:
                return str(type(r))

            if len(rtype) > 1:
                return "mixed"
            else:
                return rtype.pop()

    def get_references(self):
        predecessor = OrderedSet()
        if isinstance(self.reference, list):
            for reference in self.reference:
                self._process_reference(reference, predecessor)
        else:
            raise NotImplementedError("cannot find predecessor of a str")
        return predecessor

    def _process_reference(self, reference, predecessor):
        if isinstance(reference, list):
            for e in reference:
                self._process_reference(e, predecessor)
        elif isinstance(reference, TriccOperation):
            subs = reference.get_references()
            for s in subs:
                predecessor.add(s)
        elif issubclass(reference.__class__, (TriccNodeBaseModel, TriccReference)):
            predecessor.add(reference)

    def append(self, value):
        self.reference.append(value)

    def replace_node(self, old_node, new_node):
        if isinstance(self.reference, list):
            for key in [i for i, x in enumerate(self.reference)]:
                self.reference[key] = self._replace_reference(self.reference[key], new_node, old_node)
        elif self.reference is not None:
            raise NotImplementedError(f"cannot manage {self.reference.__class__}")

    def _replace_reference(self, reference, new_node, old_node):
        if isinstance(reference, list):
            for key in [i for i, x in enumerate(reference)]:
                reference[key] = self._replace_reference(reference[key], new_node, old_node)
        if isinstance(reference, TriccOperation):
            reference.replace_node(old_node, new_node)
        elif issubclass(reference.__class__, (TriccNodeBaseModel, TriccReference)) and reference == old_node:
            reference = new_node
            # to cover the options
            if (
                hasattr(reference, "select")
                and hasattr(new_node, "select")
                and issubclass(reference.select.__class__, TriccNodeBaseModel)
            ):
                self.replace_node(reference.select, new_node.select)
        return reference

    def __copy__(self, keep_node=False):
        # Create a new instance
        if keep_node:
            reference = [e for e in self.reference]
        else:
            reference = [
                (
                    e.copy()
                    if isinstance(e, (TriccReference, TriccOperation))
                    else (TriccReference(e.name) if hasattr(e, "name") else e)
                )
                for e in self.reference
            ]

        new_instance = type(self)(self.operator, reference)
        # Copy attributes (shallow copy for mutable attributes)

        return new_instance

    def copy(self, keep_node=False):
        return self.__copy__(keep_node)


# function that make multipat  and
# @param argv list of expression to join with and
def clean_and_list(argv):
    for a in list(argv):
        if isinstance(a, TriccOperation) and a.operator == TriccOperator.AND:
            argv.remove(a)
            return clean_and_list([*argv, *a.reference])
        elif a == TriccStatic(True) or a is True:
            argv.remove(a)
        elif a == TriccStatic(False):
            return [TriccStatic(False)]

    internal = list(set(argv))
    for a in internal:
        for b in internal[internal.index(a) + 1:]:
            if not_clean(a) == b or not_clean(b) == a:
                return [TriccStatic(False)]
    return sorted(list(set(argv)), key=str)


def not_clean(a):
    new_operator = None
    if a is None or isinstance(a, str) and a == "":
        return TriccStatic(False)
    elif isinstance(a, TriccStatic) and a == TriccStatic(False):
        return TriccStatic(True)
    elif isinstance(a, TriccStatic) and a == TriccStatic(True):
        return TriccStatic(False)
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.ISTRUE:
        new_operator = TriccOperator.ISNOTTRUE
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.ISNOTTRUE:
        new_operator = TriccOperator.ISTRUE
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.ISFALSE:
        new_operator = TriccOperator.ISNOTFALSE
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.ISNOTFALSE:
        new_operator = TriccOperator.ISFALSE
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.ISNULL:
        new_operator = TriccOperator.ISNOTNULL
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.ISNOTNULL:
        new_operator = TriccOperator.ISNULL
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.LESS:
        new_operator = TriccOperator.MORE_OR_EQUAL
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.MORE:
        new_operator = TriccOperator.LESS_OR_EQUAL
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.LESS_OR_EQUAL:
        new_operator = TriccOperator.MORE
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.MORE_OR_EQUAL:
        new_operator = TriccOperator.LESS
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.EXISTS:
        new_operator = TriccOperator.NOTEXISTS
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.NOTEXISTS:
        new_operator = TriccOperator.EXISTS
    elif isinstance(a, TriccOperation) and a.operator == TriccOperator.NOT:
        return a.reference[0]

    if new_operator:
        return TriccOperation(new_operator, a.reference)

    elif not isinstance(a, TriccOperation) and issubclass(a.__class__, object):
        return TriccOperation(operator=TriccOperator.NOTEXISTS, reference=[a])
    else:
        return TriccOperation(TriccOperator.NOT, [a])


# function that generate remove unsure condition
# @param list_or
# @param and elm use upstream
def clean_or_list(list_or, elm_and=None):
    if len(list_or) == 1:
        return list(list_or)
    if TriccStatic(True) in list_or:
        return [TriccStatic(True)]
    for a in list(list_or):
        if isinstance(a, TriccOperation) and a.operator == TriccOperator.OR:
            list_or.remove(a)
            return clean_or_list([*list_or, *a.reference])
        elif a == TriccStatic(False) or a is False or a == 0:
            list_or.remove(a)
        elif a == TriccStatic(True) or a is True or a == 1 or (elm_and is not None and not_clean(a) in list_or):
            return [TriccStatic(True)]
            # if there is x and not(X) in an OR list them the list is always true
        elif elm_and is not None and (not_clean(a) == elm_and or a == elm_and):
            list_or.remove(a)
    internal = list(list_or)
    for a in internal:
        for b in internal[internal.index(a) + 1:]:
            if not_clean(b) == a:
                return [TriccStatic(True)]
    if len(list_or) == 0:
        return []

    return sorted(list(set(list_or)), key=repr)


def and_join(argv):
    argv = clean_and_list(argv)
    if len(argv) == 0:
        return ""
    elif len(argv) == 1:
        return argv[0]
    else:
        return TriccOperation(TriccOperator.AND, argv)


def string_join(left: Union[str, TriccOperation], right: Union[str, TriccOperation]) -> TriccOperation:
    """
    Concatenates two arguments (strings or TriccOperation) into a TriccOperation with CONCATENATE operator.
    If either argument is a TriccOperation with CONCATENATE operator, its operands are merged into the result.
    """
    # Initialize operands list for the new TriccOperation
    operands: List[Union[str, TriccOperation]] = []

    # Check if left is a TriccOperation with CONCATENATE
    if isinstance(left, TriccOperation) and left.operator == TriccOperator.CONCATENATE:
        operands.extend(left.reference)  # Merge left's operands
    else:
        operands.append(left)  # Add left as-is

    # Check if right is a TriccOperation with CONCATENATE
    if isinstance(right, TriccOperation) and right.operator == TriccOperator.CONCATENATE:
        operands.extend(right.reference)  # Merge right's operands
    else:
        operands.append(right)  # Add right as-is

    # Return a new TriccOperation with the merged operands
    return TriccOperation(operator=TriccOperator.CONCATENATE, reference=operands)


# function that make a 2 part and
# @param left part
# @param right part
def simple_and_join(left, right):
    pass
    # no term is considered as True
    left_issue = left is None or left == ""
    right_issue = right is None or right == ""
    left_neg = not_clean(left)
    right_neg = not_clean(right)
    if left_issue and right_issue:
        logger.critical("and with both terms empty")
    elif left_neg == right or right_neg == left:
        return TriccStatic(False)
    elif left_issue:
        logger.debug("and with empty left term")
        return right
    elif left == "1" or left == 1 or left == TriccStatic(True) or left is True:
        return right
    elif right_issue:
        logger.debug("and with empty right term")
        return left
    elif right == "1" or right == 1 or right == TriccStatic(True) or right is True:
        return left
    else:
        return TriccOperation(TriccOperator.AND, [left, right])


def or_join(list_or, elm_and=None):
    cleaned_list = clean_or_list(set(list_or), elm_and)
    if len(cleaned_list) == 1:
        return cleaned_list[0]
    elif len(cleaned_list) > 1:
        return TriccOperation(TriccOperator.OR, cleaned_list)
    else:
        logger.error("empty or list")


# function that make a 2 part NAND
# @param left part
# @param right part
def nand_join(left, right):
    # no term is considered as True
    left_issue = left is None or left == ""
    right_issue = right is None or right == ""
    left_neg = left is False or left == 0 or left == "0" or left == TriccStatic(False)
    right_neg = right is False or right == 0 or right == "0" or right == TriccStatic(False)
    if left_issue and right_issue:
        logger.critical("and with both terms empty")
    elif left_issue:
        logger.debug("and with empty left term")
        return not_clean(right)
    elif left == "1" or left == 1 or left == TriccStatic(True):
        return not_clean(right)
    elif right_issue:
        logger.debug("and with empty right term")
        return TriccStatic(False)
    elif right == "1" or right == 1 or left_neg or right == TriccStatic(True):
        return TriccStatic(False)
    elif right_neg:
        return left
    else:
        return and_join([left, not_clean(right)])


def collect_istrue_references(operation):
    """Collect all references that appear in istrue operations"""
    istrue_refs = set()

    def _collect_istrue(op):
        if isinstance(op, TriccOperation):
            if op.operator == TriccOperator.ISTRUE and len(op.reference) == 1:
                ref = op.reference[0]
                # Use structural key for comparison
                if isinstance(ref, TriccReference):
                    istrue_refs.add(f"ref_{ref.value}")
                elif hasattr(ref, 'id'):
                    istrue_refs.add(f"{ref.__class__.__name__}_{ref.id}")
                else:
                    istrue_refs.add(str(ref))
            # Recursively collect from sub-operations
            for ref in op.reference:
                _collect_istrue(ref)

    _collect_istrue(operation)
    return istrue_refs


def restore_istrue_wrappers(operation, istrue_refs):
    """Restore istrue wrappers around references that were originally istrue-wrapped"""
    if not isinstance(operation, TriccOperation):
        return operation

    def _get_structural_key(ref):
        """Generate a canonical key based on structural equality"""
        if isinstance(ref, TriccReference):
            return f"ref_{ref.value}"
        elif hasattr(ref, 'id'):
            return f"{ref.__class__.__name__}_{ref.id}"
        else:
            return str(ref)

    def _restore_istrue(op):
        if isinstance(op, TriccOperation):
            # If this is already an istrue operation, leave it as-is
            if op.operator == TriccOperator.ISTRUE:
                return op

            # Check if this single-reference operation should be wrapped in istrue
            if len(op.reference) == 1:
                ref = op.reference[0]
                ref_key = _get_structural_key(ref)
                if ref_key in istrue_refs:
                    # This reference was originally istrue-wrapped, restore it
                    return TriccOperation(TriccOperator.ISTRUE, [op])

            # Recursively restore in sub-operations
            restored_refs = []
            for ref in op.reference:
                restored_refs.append(_restore_istrue(ref))
            op.reference = restored_refs

        elif not isinstance(op, TriccOperation):
            # Check if this bare reference should be wrapped in istrue
            ref_key = _get_structural_key(op)
            if ref_key in istrue_refs:
                return TriccOperation(TriccOperator.ISTRUE, [op])

        return op

    return _restore_istrue(operation)


def contains_istrue_operation(operation):
    """Check if an operation contains any istrue operations (recursively)"""
    if not isinstance(operation, TriccOperation):
        return False

    if operation.operator == TriccOperator.ISTRUE:
        return True

    # Check recursively in all references
    for ref in operation.reference:
        if isinstance(ref, TriccOperation):
            if contains_istrue_operation(ref):
                return True
        elif isinstance(ref, list):
            for item in ref:
                if isinstance(item, TriccOperation) and contains_istrue_operation(item):
                    return True

    return False


def simplify_with_sympy(operation):
    """
    Simplify a TriccOperation using SymPy boolean and algebraic operations.

    This enhanced version preserves istrue semantic information by tracking which
    references were originally wrapped in istrue operations and restoring them
    after simplification.

    For expressions containing istrue operations, simplification is skipped entirely
    to preserve the original structure.

    Args:
        operation: TriccOperation to simplify

    Returns:
        Simplified TriccOperation with preserved istrue semantics, or original if no simplification possible
    """
    # Step 1: Check if operation contains operations that can be simplified
    if not isinstance(operation, TriccOperation):
        return operation

    # Step 2: If operation contains istrue, skip simplification to preserve structure
    if contains_istrue_operation(operation):
        logger.debug(f"Skipping SymPy simplification for operation containing istrue: {operation}")
        return operation

    try:
        import sympy as sp
        from sympy.logic.boolalg import simplify_logic
        from sympy import Add, Mul, Pow, Eq, Ne, And, Or, Not, Gt, Ge, Lt, Le
        from sympy.functions import Abs, sign
    except ImportError:
        logger.warning("SymPy not available, skipping algebraic simplification")
        return operation

    # Step 2: Create comprehensive Tricc-to-SymPy operator mapping
    tricc_to_sympy_map = {
        # Boolean operations - treat as symbols to preserve structure
        TriccOperator.AND: And,
        TriccOperator.OR: Or,
        TriccOperator.NOT: Not,
        TriccOperator.ISTRUE: None,  # Will be treated as symbol
        TriccOperator.ISFALSE: None,  # Will be treated as symbol
        TriccOperator.EXISTS: None,  # Will be treated as symbol
        TriccOperator.NOTEXISTS: None,  # Will be treated as symbol
        TriccOperator.ISNOTTRUE: None,  # Will be treated as symbol
        TriccOperator.ISNOTFALSE: None,  # Will be treated as symbol

        # Arithmetic operations
        TriccOperator.PLUS: Add,
        TriccOperator.MINUS: lambda *args: Add(args[0], Mul(-1, args[1])) if len(args) == 2 else Mul(-1, args[0]),
        TriccOperator.MULTIPLIED: Mul,
        TriccOperator.DIVIDED: lambda x, y: Mul(x, Pow(y, -1)),
        TriccOperator.MODULO: lambda x, y: x % y,  # Modulo

        # Comparison operations
        TriccOperator.EQUAL: Eq,
        TriccOperator.NOTEQUAL: Ne,
        TriccOperator.MORE: Gt,
        TriccOperator.LESS: Lt,
        TriccOperator.MORE_OR_EQUAL: Ge,
        TriccOperator.LESS_OR_EQUAL: Le,

        # Numeric operations
        TriccOperator.ROUND: lambda x: sp.round(x),
        TriccOperator.CAST_NUMBER: lambda x: x,  # Identity for numbers
        TriccOperator.CAST_INTEGER: lambda x: sp.floor(x),

        # Special operations (placeholders for now)
        TriccOperator.COALESCE: None,  # Will use placeholder
        TriccOperator.GET_INHERITED_VALUE: None,  # Will use placeholder
        TriccOperator.CONCATENATE: None,  # Will use placeholder
        TriccOperator.CASE: None,  # Will use placeholder
        TriccOperator.IFS: None,  # Will use placeholder
    }

    # Step 3: Create reference mapping with structural keys
    ref_counter = 0
    ref_map = {}  # SymPy symbol -> (actual reference, is_boolean_symbol)
    reverse_map = {}  # structural key -> SymPy symbol

    def get_structural_key(ref):
        """Generate a canonical key based on structural equality"""
        if isinstance(ref, TriccOperation):
            ref_keys = [get_structural_key(r) for r in ref.reference]
            return f"op_{ref.operator}_{'_'.join(ref_keys)}"
        elif isinstance(ref, TriccReference):
            return f"ref_{ref.value}"
        elif isinstance(ref, TriccStatic):
            return f"static_{ref.value}"
        elif hasattr(ref, 'id'):
            return f"{ref.__class__.__name__}_{ref.id}"
        else:
            return str(ref)

    def get_sympy_symbol(ref):
        """Get or create SymPy symbol for a reference"""
        nonlocal ref_counter
        ref_key = get_structural_key(ref)
        if ref_key in reverse_map:
            return reverse_map[ref_key]

        # Create unique symbol name
        if hasattr(ref, 'reference') and isinstance(ref.reference, (list, OrderedSet)):
            # For operations, create path-based name
            path_parts = []
            current = ref
            depth = 0
            while hasattr(current, 'reference') and depth < 3:
                if isinstance(current.reference, (list, OrderedSet)) and len(current.reference) > 0:
                    path_parts.insert(0, str(len(current.reference)))
                    current = current.reference[0]
                    depth += 1
                else:
                    break
            if path_parts:
                symbol_name = f"r_{'_'.join(path_parts)}"
            else:
                symbol_name = f"r_{ref_counter}"
        else:
            symbol_name = f"r_{ref_counter}"

        ref_counter += 1
        symbol = sp.Symbol(symbol_name)
        ref_map[symbol] = ref
        reverse_map[ref_key] = symbol
        return symbol

    def tricc_to_sympy_expr(op):
        """Convert TriccOperation to SymPy expression"""
        if isinstance(op, TriccOperation):
            # Special handling for boolean operations - ensure consistent symbols
            if op.operator in (TriccOperator.ISTRUE, TriccOperator.ISNOTTRUE, TriccOperator.ISFALSE, TriccOperator.ISNOTFALSE):
                # For boolean operations on single references, use a consistent base symbol
                if len(op.reference) == 1:
                    # Create a base symbol key using the reference, not the operation
                    base_ref = op.reference[0]
                    base_key = get_structural_key(base_ref)

                    # Create a boolean symbol name based on the base reference
                    if base_key not in reverse_map:
                        nonlocal ref_counter
                        symbol_name = f"bool_{ref_counter}"
                        ref_counter += 1
                        base_symbol = sp.Symbol(symbol_name)
                        ref_map[base_symbol] = base_ref
                        reverse_map[base_key] = base_symbol

                    base_symbol = reverse_map[base_key]

                    # Apply the boolean operation
                    if op.operator == TriccOperator.ISTRUE:
                        return base_symbol
                    elif op.operator == TriccOperator.ISNOTTRUE:
                        return Not(base_symbol)
                    elif op.operator == TriccOperator.ISFALSE:
                        return Not(base_symbol)  # isfalse(x) = not(istrue(x))
                    elif op.operator == TriccOperator.ISNOTFALSE:
                        return base_symbol  # isnotfalse(x) = istrue(x)
                else:
                    # Fallback for multi-reference boolean operations
                    return get_sympy_symbol(op)
            elif op.operator == TriccOperator.NOT and len(op.reference) == 1:
                # Handle NOT(boolean_operation) by applying SymPy to inner and wrapping
                inner = op.reference[0]
                if isinstance(inner, TriccOperation) and inner.get_datatype() == "boolean":
                    # Apply SymPy to the inner boolean expression
                    inner_sympy = tricc_to_sympy_expr(inner)
                    if inner_sympy != get_sympy_symbol(inner):
                        # Inner was simplified, wrap with NOT
                        return Not(inner_sympy)
                    else:
                        # Inner wasn't simplified, return as symbol
                        return get_sympy_symbol(op)
                else:
                    # Not a boolean operation, handle normally
                    sympy_op = tricc_to_sympy_map.get(op.operator)
                    if sympy_op is None:
                        return get_sympy_symbol(op)

                    sympy_refs = [tricc_to_sympy_expr(ref) for ref in op.reference]
                    if callable(sympy_op):
                        try:
                            if len(sympy_refs) == 1:
                                return sympy_op(sympy_refs[0])
                            elif len(sympy_refs) == 2:
                                return sympy_op(sympy_refs[0], sympy_refs[1])
                            else:
                                result = sympy_refs[0]
                                for ref in sympy_refs[1:]:
                                    result = sympy_op(result, ref)
                                return result
                        except Exception as e:
                            logger.debug(f"Failed to apply {sympy_op} to {sympy_refs}: {e}")
                            return get_sympy_symbol(op)
                    else:
                        try:
                            return sympy_op(*sympy_refs)
                        except Exception as e:
                            logger.debug(f"Failed to create {sympy_op} with {sympy_refs}: {e}")
                            return get_sympy_symbol(op)
            else:
                # Normal operation handling
                sympy_op = tricc_to_sympy_map.get(op.operator)

                if sympy_op is None:
                    # Use placeholder for unmapped operations
                    return get_sympy_symbol(op)

                # Convert references to SymPy expressions
                sympy_refs = [tricc_to_sympy_expr(ref) for ref in op.reference]

                # Apply the SymPy operation
                if callable(sympy_op):
                    try:
                        if len(sympy_refs) == 1:
                            return sympy_op(sympy_refs[0])
                        elif len(sympy_refs) == 2:
                            return sympy_op(sympy_refs[0], sympy_refs[1])
                        else:
                            # For operations with multiple args, apply sequentially
                            result = sympy_refs[0]
                            for ref in sympy_refs[1:]:
                                result = sympy_op(result, ref)
                            return result
                    except Exception as e:
                        logger.debug(f"Failed to apply {sympy_op} to {sympy_refs}: {e}")
                        return get_sympy_symbol(op)
                else:
                    # Direct SymPy operation class
                    try:
                        return sympy_op(*sympy_refs)
                    except Exception as e:
                        logger.debug(f"Failed to create {sympy_op} with {sympy_refs}: {e}")
                        return get_sympy_symbol(op)

        elif isinstance(op, TriccStatic):
            if isinstance(op.value, bool):
                return sp.true if op.value else sp.false
            elif isinstance(op.value, (int, float)):
                return sp.S(op.value)
            else:
                return get_sympy_symbol(op)
        else:
            # References and other objects
            return get_sympy_symbol(op)

    def sympy_expr_to_tricc(expr):
        """Convert SymPy expression back to TriccOperation using expression tree"""
        if isinstance(expr, sp.Symbol):
            # Direct symbol lookup
            if expr in ref_map:
                original_ref = ref_map[expr]
                # If this symbol represents a reference that was originally wrapped in istrue,
                # reconstruct it as istrue(reference)
                if isinstance(original_ref, TriccReference):
                    ref_key = get_structural_key(original_ref)
                    if ref_key in istrue_refs:  # Check if this reference was originally istrue-wrapped
                        return TriccOperation(TriccOperator.ISTRUE, [original_ref])
                return original_ref
            else:
                # This shouldn't happen, but handle gracefully
                return TriccReference(str(expr))

        elif expr is sp.true:
            return TriccStatic(True)
        elif expr is sp.false:
            return TriccStatic(False)

        elif isinstance(expr, (sp.Integer, sp.Float)):
            return TriccStatic(float(expr))



        elif isinstance(expr, And):
            args = [sympy_expr_to_tricc(arg) for arg in expr.args]
            return and_join(args)

        elif isinstance(expr, Or):
            args = [sympy_expr_to_tricc(arg) for arg in expr.args]
            return or_join(args)

        elif isinstance(expr, Not):
            inner = sympy_expr_to_tricc(expr.args[0])
            return TriccOperation(TriccOperator.NOT, [inner])

        elif isinstance(expr, Add):
            if len(expr.args) == 2:
                left, right = [sympy_expr_to_tricc(arg) for arg in expr.args]
                # Check if right is negative (indicating subtraction)
                if isinstance(right, TriccOperation) and right.operator == TriccOperator.MINUS and len(right.reference) == 1:
                    return TriccOperation(TriccOperator.MINUS, [left, right.reference[0]])
                else:
                    return TriccOperation(TriccOperator.PLUS, [left, right])
            else:
                # Multiple addition
                args = [sympy_expr_to_tricc(arg) for arg in expr.args]
                return TriccOperation(TriccOperator.PLUS, args)

        elif isinstance(expr, Mul):
            if len(expr.args) == 2:
                left, right = [sympy_expr_to_tricc(arg) for arg in expr.args]
                # Check for division (multiplication by reciprocal)
                if isinstance(right, TriccOperation) and right.operator == TriccOperator.DIVIDED:
                    if len(right.reference) == 1:
                        return TriccOperation(TriccOperator.DIVIDED, [left, right.reference[0]])
                else:
                    return TriccOperation(TriccOperator.MULTIPLIED, [left, right])
            else:
                # Multiple multiplication
                args = [sympy_expr_to_tricc(arg) for arg in expr.args]
                return TriccOperation(TriccOperator.MULTIPLIED, args)

        elif isinstance(expr, Pow):
            # Handle division (x^(-1) = 1/x)
            if len(expr.args) == 2 and expr.args[1] == -1:
                numerator = sympy_expr_to_tricc(expr.args[0])
                denominator = TriccStatic(1)
                return TriccOperation(TriccOperator.DIVIDED, [numerator, denominator])
            else:
                # Other powers - fallback to placeholder
                return TriccReference(str(expr))

        elif isinstance(expr, (Eq, Ne, Lt, Le, Gt, Ge)):
            left, right = [sympy_expr_to_tricc(arg) for arg in expr.args]
            op_map = {
                Eq: TriccOperator.EQUAL,
                Ne: TriccOperator.NOTEQUAL,
                Lt: TriccOperator.LESS,
                Le: TriccOperator.LESS_OR_EQUAL,
                Gt: TriccOperator.MORE,
                Ge: TriccOperator.MORE_OR_EQUAL,
            }
            operator = op_map.get(type(expr), TriccOperator.EQUAL)
            return TriccOperation(operator, [left, right])

        else:
            # Unknown SymPy expression type - fallback to string representation
            logger.debug(f"Unknown SymPy expression type: {type(expr)}, falling back to placeholder")
            return TriccReference(str(expr))

    # Step 4: Collect istrue metadata before simplification
    istrue_refs = collect_istrue_references(operation)

    # Step 5: Apply custom boolean simplifications first
    if operation.get_datatype() == "boolean":
        # Apply our custom boolean simplifications
        custom_simplified = apply_boolean_simplifications(operation)
        if custom_simplified != operation:
            logger.debug(f"Custom boolean simplification: {operation} -> {custom_simplified}")
            return restore_istrue_wrappers(custom_simplified, istrue_refs)

    # Step 6: Convert to SymPy and simplify
    try:
        sympy_expr = tricc_to_sympy_expr(operation)
        logger.debug(f"Original SymPy expression: {sympy_expr}")

        # Apply appropriate simplification based on expression type
        if operation.get_datatype() == "boolean":
            # Use boolean algebra simplification
            simplified_expr = simplify_logic(sympy_expr)
        else:
            # Use general algebraic simplification
            simplified_expr = sp.simplify(sympy_expr)

        logger.debug(f"Simplified SymPy expression: {simplified_expr}")
        logger.debug(f"SymPy expressions equal: {simplified_expr == sympy_expr}")

        # Step 7: Convert back to TriccOperation if different
        if simplified_expr != sympy_expr:
            reconstructed = sympy_expr_to_tricc(simplified_expr)
            logger.debug(f"SymPy simplified {operation} to {reconstructed}")

            # Step 8: Restore istrue wrappers
            result = restore_istrue_wrappers(reconstructed, istrue_refs)
            logger.debug(f"After restoring istrue wrappers: {result}")
            return result

    except Exception as e:
        logger.warning(f"SymPy simplification failed for {operation}: {e}")

    return operation


def apply_boolean_simplifications(operation):
    """Apply custom boolean simplifications that SymPy might miss"""
    if not isinstance(operation, TriccOperation):
        return operation

    if operation.operator == TriccOperator.OR:
        # Apply clean_or_list which includes our pattern recognition
        cleaned_list = clean_or_list(set(operation.reference))
        if len(cleaned_list) == 1:
            return cleaned_list[0]
        elif len(cleaned_list) != len(operation.reference):
            return TriccOperation(TriccOperator.OR, cleaned_list)

    elif operation.operator == TriccOperator.AND:
        # Apply clean_and_list
        cleaned_list = clean_and_list(operation.reference)
        if len(cleaned_list) == 1:
            return cleaned_list[0]
        elif len(cleaned_list) != len(operation.reference):
            return TriccOperation(TriccOperator.AND, cleaned_list)

    # Recursively apply to sub-operations
    simplified_refs = []
    changed = False
    for ref in operation.reference:
        if isinstance(ref, TriccOperation):
            simplified_ref = apply_boolean_simplifications(ref)
            if simplified_ref != ref:
                changed = True
            simplified_refs.append(simplified_ref)
        else:
            simplified_refs.append(ref)

    if changed:
        return TriccOperation(operation.operator, simplified_refs)

    return operation


TriccGroup.update_forward_refs()
