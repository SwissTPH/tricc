from operator import attrgetter
import re

from tricc_oo.converters.utils import clean_str,clean_name
from tricc_oo.models import *
from tricc_oo.visitors.tricc import clean_list_or, negate_term

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


def get_export_name(node):
    if isinstance(node, str):
        return clean_name(node)
    if node.export_name is None:
        node.export_name = clean_name(node.name)
        if node.name is None:
            node.export_name= clean_name("id_" + node.id)
        elif not ( INSTANCE_SEPARATOR  in node.name or  VERSION_SEPARATOR in node.name):
            if issubclass(node.__class__, TriccNodeCalculateBase):
                node.gen_name()
                if node.last == False:
                    node.export_name = clean_name(node.name + VERSION_SEPARATOR + str(node.path_len))
                else:
                    node.export_name = clean_name(node.name)
            elif issubclass(node.__class__, (TriccNodeDisplayModel)):
                node.gen_name()
                if isinstance(node, TriccNodeSelectOption):
                    node.export_name = node.name
                elif not isinstance(node, TriccNodeSelectOption) and node.activity.instance!=1:
                    node.export_name = clean_name(node.name +  INSTANCE_SEPARATOR + str(node.instance))
            #elif isinstance(node, TriccNodeActivityEnd):
            #    node.export_name =  clean_name(node.name +  INSTANCE_SEPARATOR + str(node.instance))
            elif isinstance(node,  TriccNodeActivityStart):
                node.export_name =  clean_name(node.name +  INSTANCE_SEPARATOR + str(node.instance))
                
    return node.export_name 






def get_list_names(list):
    names = []
    for elm in list:
        if issubclass(elm.__class__, TriccNodeBaseModel):
            names.append(get_export_name(elm))
        elif isinstance(elm, str):
            names.append(elm)
    return names
