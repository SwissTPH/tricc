def replace_all(text, list_char, replacement):
    for i in list_char:
        text = text.replace(i, replacement)
    return text
def clean_name( name):
    return replace_all(name, ['-', ' ', '.', ','],'_')
