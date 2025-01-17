import logging
import random
import string
import hashlib
import html2text



logger = logging.getLogger("default")

def replace_all(text, list_char, replacement):
    for i in list_char:
        text = text.replace(i, replacement)
    return text

def clean_str(name):
    return replace_all(name, ['-', ' ', ','],'_')

def clean_name( name, prefix='' ):
    name = clean_str(name)
    if name[0].isdigit():
        name = 'id_' + name
    elif  name[0].isdigit() == '_':
         name =  name[1:]
    return name

def generate_id(name=None):
    if name:
        return hashlib.md5(name.encode('utf-8') if isinstance(name, str) else name).hexdigest()
    else:
        return ''.join(random.choices(string.ascii_lowercase, k=8))

# the soup.text strips off the html formatting also
def remove_html(string):
    text = html2text.html2text(string) # retrive pure text from html
    text = text.strip('\n') # get rid of empty lines at the end (and beginning)
    text = text.split('\n') # split string into a list at new lines
    text = '\n'.join([i.strip(' ') for i in text if i]) # in each element in that list strip empty space (at the end of line) 
    # and delete empty lines
    return text




            