from collections import OrderedDict
from collections.abc import Iterable


class OrderedSet:
    def __init__(self, iterable=None):
        self._od = OrderedDict.fromkeys(iterable or [])

    def copy(self):
        return OrderedSet(list(self._od.keys()))

    def add(self, item):
        self.insert_at_bottom(item)

    def remove(self, item):
        del self._od[item]

    def pop(self):
        return self._od.popitem(last=False)[0]

    def insert_at_top(self, item):
            # Add item if not already present
        self.insert_at_bottom(item)
        # Move item to the top
        self._od.move_to_end(item, last=False)
        
    def insert_at_bottom(self, item):
        if item not in self._od:
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
        
    def sort(self, key=None, reverse=False):
        sorted_keys = sorted(self._od.keys(), key=key, reverse=reverse)
        self._od = OrderedDict.fromkeys(sorted_keys)