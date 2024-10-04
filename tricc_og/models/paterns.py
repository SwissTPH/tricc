from strenum import StrEnum
from enum import auto


class TriccPaterns(StrEnum):
    # base model
    abstract_activity = (
        auto()
    )  # replace goto = 'goto'  #: start the linked activity within the target activity
    implemented_activity = auto()

    # start node
    activity_start = auto()  # THIS is higher that process
    process_start = auto()  #: main start of the algo

    # basic flow nodes
    link_throw = auto()  # old link_in
    link_catch = auto()  # old link_out
    logic = auto()

    # gateway
    exclusive = auto()
    inclusive = auto()  # old bridge
    wait = auto()  # parallel ?

    # end
    escalated_end = auto()
    activity_end = auto()
    output = auto()

    # processing patern
    calculate = auto()
    count = auto()  #: count the number of valid input
    add = auto()  # add count
    operation = auto()

    # interface
    data_in = auto()
    data_out = auto()

    ##### this part should be extendable ####
    # may be runtime loading of config file

    # display patern
    note = auto()  # message ?
    container_hint_media = auto()  # DEPRECATED
    hint = auto()
    help = auto()

    # input patern
    select_multiple = auto()
    select_one = auto()
    decimal = auto()
    integer = auto()
    text = auto()
    date = auto()
    select_yesno = auto()
    select_option = auto()
    not_available = auto()
    quantity = auto()
