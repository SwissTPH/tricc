from operator import attrgetter
import re

from tricc_oo.converters.utils import clean_str,clean_name
from tricc_oo.models import *
from tricc_oo.visitors.tricc import clean_or_list, negate_term

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
VERSION_SEPARATOR = '_Vv_'
INSTANCE_SEPARATOR = "_Ii_"

import logging

logger = logging.getLogger("default")

# gettext language dict {'code':gettext}


def get_export_name(node, replace_dots=True):
    if isinstance(node, str):
        return clean_name(node, replace_dots=replace_dots)
    if node.export_name is None:
        node.gen_name()
        if isinstance(node, TriccNodeSelectOption):
                node.export_name = node.name
        elif node.last == False:
            node.export_name = clean_name(node.name + VERSION_SEPARATOR + str(node.version), replace_dots=replace_dots)
        # elif node.activity.instance>1:
        #     if node.version:
        #         node.export_name = clean_name(node.name + VERSION_SEPARATOR + str(node.version), replace_dots=replace_dots)
        #     else:
        #         node.export_name =  clean_name(node.name +  INSTANCE_SEPARATOR + str(node.activity.instance), replace_dots=replace_dots)
            
        elif isinstance(node, TriccNodeInput):
            node.export_name = clean_name('load.' +node.name, replace_dots=replace_dots)
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
