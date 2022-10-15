import logging
from uuid import uuid4

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
    return str(uuid4())





            