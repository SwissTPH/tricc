def replace_all(text, list, replacement):
    for i in list:
        text = text.replace(i, replacement)
    return text
def clean_name( name):
    return replace_all(name, ['-', ' ', '.', ','],'_')
