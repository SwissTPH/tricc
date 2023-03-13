import logging
import random
import string
from typing import Dict
from uuid import uuid4
from gettext import gettext

from tricc.models.lang import SingletonLangClass


OPERATION_LIST = [ '>=', '<=', '==','=','>','<']


logger = logging.getLogger("default")

def replace_all(text, list_char, replacement):
    for i in list_char:
        text = text.replace(i, replacement)
    return text

def clean_str(name):
    return replace_all(name, ['-', ' ', '.', ','],'_')

def clean_name( name, prefix='' ):
    name = clean_str(name)
    if name[0].isdigit():
        name = 'id_' + name
    return name

def generate_id():
    return ''.join(random.choices(string.ascii_lowercase, k=8))






            