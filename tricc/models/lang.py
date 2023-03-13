from polib import POEntry, POFile


class SingletonLangClass(object):
    languages = None

    po_file = None
    
    def __init__(self):
        self.po_file = POFile()
        
    def __new__(self):
        if not hasattr(self, 'instance'):
            self.instance = super(SingletonLangClass, self).__new__(self)
        return self.instance
    
    def add_trad(self, code, lang):
        if self.languages is None:
            self.languages = {}
        self.languages[code] = lang
    
    def get_trads(self, message, force_dict = False):

        self.po_file.insert(0,POEntry(msgid = message))
        
        if self.languages is None:
            if force_dict:
                return {'default', message}
            else :
                return message
        else:
            trads = {}
            for code, lang in self.languages.items():
                trads[code]= lang.gettext(message)
            return trads

    def get_trads_map(self, col):
        if self.languages is None:
            return {col:col}
        else:
            map = {}
            for code, lang in self.languages.items():
                map[col+'::'+code] = col+'['+code+']'
            
            return map 

    def join_trads(trads_1, trads_2, separator= ' '):
        dict_3 = {**trads_1, **trads_1}
        for key, value in dict_3.items():
            if key in trads_1 and key in trads_2:
                    dict_3[key] = value + separator +  trads_1[key]
        return dict_3       
        
    def to_po_file(self, path):
        self.po_file.save(fpath = path)
        