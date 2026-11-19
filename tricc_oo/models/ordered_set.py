from collections import OrderedDict
from collections.abc import Iterable, Sequence
from itertools import islice

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema


class OrderedSet(Sequence):
    """Insertion-ordered unique collection.

    Backed by ``OrderedDict`` so ``insert_at_top`` / ``pop`` from the front stay
    O(1). Copy, union, and search avoid allocating a full key list on each call.
    """

    __slots__ = ("_od",)

    def __init__(self, iterable=None):
        if isinstance(iterable, OrderedSet):
            self._od = iterable._od.copy()
        elif iterable:
            self._od = OrderedDict.fromkeys(iterable)
        else:
            self._od = OrderedDict()

    def copy(self):
        clone = OrderedSet.__new__(OrderedSet)
        clone._od = self._od.copy()
        return clone

    def add(self, item):
        self.insert_at_bottom(item)

    append = add

    def discard(self, item):
        self._od.pop(item, None)

    def remove(self, item):
        del self._od[item]

    def pop(self):
        return self._od.popitem(last=False)[0]

    def clear(self):
        self._od.clear()

    def insert_at_top(self, item):
        self.insert_at_bottom(item)
        self._od.move_to_end(item, last=False)

    def insert_at_bottom(self, item):
        if item not in self._od:
            self._od[item] = None

    def __contains__(self, item):
        return item in self._od

    def __iter__(self):
        return iter(self._od)

    def __reversed__(self):
        return reversed(self._od)

    def __len__(self):
        return len(self._od)

    def __bool__(self):
        return bool(self._od)

    def __repr__(self):
        return f"{type(self).__name__}({list(self._od.keys())})"

    def _add_items(self, items):
        od = self._od
        if isinstance(items, OrderedSet):
            items = items._od
        for item in items:
            if item not in od:
                od[item] = None

    def __eq__(self, other):
        if not isinstance(other, OrderedSet):
            return False
        # KeysView equality is set-like (order-insensitive), matching the previous
        # OrderedDict.keys() comparison.
        return self._od.keys() == other._od.keys()

    def same_members(self, other):
        """True if both collections contain the same items, ignoring order."""
        if other is self:
            return True
        if len(self._od) != len(other):
            return False
        od = self._od
        return all(item in od for item in other)

    def __or__(self, other):
        if not isinstance(other, Iterable):
            raise TypeError(f"Unsupported operand type(s) for |: 'OrderedSet' and '{type(other).__name__}'")
        new_set = self.copy()
        new_set._add_items(other)
        return new_set

    def __ior__(self, other):
        if not isinstance(other, Iterable):
            raise TypeError(f"Unsupported operand type(s) for |=: 'OrderedSet' and '{type(other).__name__}'")
        self._add_items(other)
        return self

    def union(self, other):
        return self.__or__(other)

    def __iadd__(self, other):
        if not isinstance(other, Iterable):
            raise TypeError("Unsupported operand type(s) for +=: 'OrderedSet' and '{}'".format(type(other)))
        self._add_items(other)
        return self

    def get(self, index):
        return self.__getitem__(index)

    def __getitem__(self, index):
        n = len(self._od)
        if isinstance(index, slice):
            return list(self._od.keys())[index]
        if index < 0:
            index += n
        if index < 0 or index >= n:
            raise IndexError("Index out of range") from None
        return next(islice(self._od, index, index + 1))

    def sort(self, key=None, reverse=False):
        self._od = OrderedDict.fromkeys(sorted(self._od, key=key, reverse=reverse))

    def find_last(self, filter: callable):
        for item in reversed(self._od):
            if filter(item):
                return item
        return None

    def find_first(self, filter: callable):
        for item in self._od:
            if filter(item):
                return item
        return None

    def find_prev(self, obj, filter: callable):
        seen_obj = obj not in self._od
        for item in reversed(self._od):
            if not seen_obj:
                if item == obj:
                    seen_obj = True
                continue
            if filter(item):
                return item
        return None

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: type, handler: GetCoreSchemaHandler) -> CoreSchema:
        return handler.generate_schema(list)
