import logging
from tricc_oo.converters.utils import clean_name, clean_str
from tricc_oo.models.tricc import TriccNodeSelectOption, TRICC_TRUE_VALUE, TRICC_FALSE_VALUE
from tricc_oo.models.calculate import TriccNodeInput
from tricc_oo.models.base import TriccNodeBaseModel, TriccStatic, TriccReference

# from babel import _

# TRICC_SELECT_MULTIPLE_CALC_EXPRESSION = "count-selected(${{{0}}}) - number(selected(${{{0}}},'opt_none'))"
# TRICC_SELECT_MULTIPLE_CALC_NONE_EXPRESSION = "selected(${{{0}}},'opt_none')"
# TRICC_CALC_EXPRESSION = "${{{0}}}>0"
# TRICC_CALC_NOT_EXPRESSION = "${{{0}}}=0"
# TRICC_EMPTY_EXPRESSION = "coalesce(${{{0}}},'') != ''"
# TRICC_SELECTED_EXPRESSION = 'selected(${{{0}}}, "{1}")'
# TRICC_SELECTED_NEGATE_EXPRESSION = 'count-selected(${{{0}}})>0 and not(selected(${{{0}}}, "{1}"))'
# TRICC_REF_EXPRESSION = "${{{0}}}"
TRICC_NEGATE = "not({})"
# TRICC_NUMBER = "number({})"
# TRICC_AND_EXPRESSION = '{0} and {1}'
VERSION_SEPARATOR = "_Vv_"
INSTANCE_SEPARATOR = "_Ii_"
BOOLEAN_MAP = {
    str(TRICC_TRUE_VALUE): 1,
    str(TRICC_FALSE_VALUE): 0,
}


logger = logging.getLogger("default")

# gettext language dict {'code':gettext}


def get_export_name(node, replace_dots=True):
    if hasattr(node, 'export_name') and node.export_name is not None:
        return node.export_name
    elif isinstance(node, bool):
        return BOOLEAN_MAP[str(TRICC_TRUE_VALUE)] if node else BOOLEAN_MAP[str(TRICC_FALSE_VALUE)]
    elif isinstance(node, TriccReference):
        logger.warning(f"Reference {node.value} use in export, bad serialiuation probable")
        return str(node.value)
    elif isinstance(node, (str, TriccStatic, TriccNodeSelectOption)):
        if isinstance(node, TriccNodeSelectOption):
            value = node.name
        elif isinstance(node, TriccStatic):
            value = node.value
        else:
            value = node
        if isinstance(value, bool):  # or r.value in ('true', 'false')
            export_name = BOOLEAN_MAP[str(TRICC_TRUE_VALUE)] if value else BOOLEAN_MAP[str(TRICC_FALSE_VALUE)]
        elif value == TRICC_TRUE_VALUE:
            export_name = BOOLEAN_MAP[str(TRICC_TRUE_VALUE)]
        elif value == TRICC_FALSE_VALUE:
            export_name = BOOLEAN_MAP[str(TRICC_FALSE_VALUE)]
        elif value == '$this':
            export_name = '.'
        elif isinstance(value, str) and not isinstance(node, str):
            export_name = f"'{value}'"
        else:
            export_name = value
        if hasattr(node, 'export_name'):
            node.export_name = export_name
        return export_name
    elif not hasattr(node, 'export_name'):
        return node
    else:
        node.gen_name()
        if isinstance(node, TriccNodeSelectOption):
            node.export_name = node.name
        elif node.last is False:
            node.export_name = clean_name(
                node.name + VERSION_SEPARATOR + str(node.version),
                replace_dots=replace_dots,
            )
        elif isinstance(node, TriccNodeInput):
            node.export_name = clean_name("load." + node.name, replace_dots=replace_dots)
        else:
            node.export_name = clean_name(node.name, replace_dots=replace_dots)
        return node.export_name


def get_list_names(list):
    names = []
    for elm in list:
        if issubclass(elm.__class__, TriccNodeBaseModel):
            names.append(get_export_name(elm))
        elif isinstance(elm, str):
            names.append(elm)
    return names
