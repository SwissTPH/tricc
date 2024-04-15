from collections import OrderedDict
from collections.abc import Iterable


class OrderedSet:
    def __init__(self, iterable=None):
        self._od = OrderedDict.fromkeys(iterable or [])

    def copy(self):
        return OrderedSet(self._od.keys())

    def add(self, item):
        self._od[item] = None

    def remove(self, item):
        del self._od[item]

    def pop(self):
        return self._od.popitem(last=False)[0]

    def insert_at_top(self, item):
        self._od.move_to_end(item, last=False)
        
    def insert_at_bottom(self, item):
        self._od[item] = None
    def __contains__(self, item):
        return item in self._od

    def __iter__(self):
        return iter(self._od)

    def __len__(self):
        return len(self._od)

    def __repr__(self):
        return f"{type(self).__name__}({list(self._od.keys())})"

    def _add_items(self, items):
        for item in items:
            if item not in self:
                self.insert_at_bottom(item)

    def __or__(self, other):
        if not isinstance(other, Iterable):
            raise TypeError("Unsupported operand type(s) for |: 'OrderedSet' and '{}'".format(type(other)))
        new_set = self.copy()
        new_set._add_items(other)
        return new_set
    
    def __iadd__(self, other):
        if not isinstance(other, Iterable):
            raise TypeError("Unsupported operand type(s) for +=: 'OrderedSet' and '{}'".format(type(other)))
        self._add_items(other)
        return self
    
    def get(self, index):
        try:
            return list(self._od.keys())[index]
        except IndexError:
            raise IndexError("Index out of range") from None