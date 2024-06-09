from strenum import StrEnum
from enum import auto


# IDEALLY use ELM
class TriccOperator(StrEnum):
    AND = auto()  # and between left and rights
    ADD_OR = auto()  # left and one of the righs
    OR = auto()  # or between left and rights
    NATIVE = auto()  # default left is native expression
    ISTRUE = auto()  # left is right
    ISFALSE = auto()  # left is false
    SELECTED = auto()  # right must be la select and one or several options
    MORE_OR_EQUAL = auto()
    LESS_OR_EQUAL = auto()
    EQUAL = auto()
    NOT_EQUAL = auto()
    BETWEEN = auto()
    LESS = auto()
    CASE = auto()  # (cond, res), (cond,res)
    IF = auto()  # cond val_true, val_false
    CONTAINS = auto()  # ref, txt Does CONTAINS make sense, like Select with wildcard
    EXISTS = auto()
    # CDSS Specific
    HAS_QUALIFIER = auto()
    ZSCORE = auto()  # left table_name, right Y, gender give Z
    IZSCORE = auto()  # left table_name, right Z, gender give Y
    AGE_DAY = auto()  # age from dob
    AGE_MONTH = auto()  # age from dob
    AGE_YEAR = auto()  # age from dob
    # scalar / quantity opperator
    ADD = auto()  # add
    SUB = auto()  # substract
    DIV = auto()  # divide
    MUL = auto()  # multiply
