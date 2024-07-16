from strenum import StrEnum


class TriccNodeType(StrEnum):
    #replace with auto ? 
    note = 'note'
    calculate = 'calculate'
    select_multiple = 'select_multiple'
    select_one = 'select_one'
    select_yesno = 'select_yesno'
    select_option = 'select_option'
    decimal = 'decimal'
    integer = 'integer'
    text = 'text'
    date = 'date'
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
    help = 'help-message'
    hint = 'hint-message'
    exclusive = 'not'
    end = 'end'
    activity_end = 'activity_end'
    edge = 'edge'
    page = 'page'
    not_available = 'not_available'
    quantity = 'quantity'
    bridge = 'bridge'
    wait = 'wait'
    operation = 'operation'
    context = 'context'



