"""``TriccText``: a display text with structure, as it travels through the pipeline.

The document is ProseMirror JSON (``doc``); its ``interp`` nodes name values. ``refs`` maps
each name to what it stands for: a ``TriccReference`` after load, the node (or an operation
picking between its versions) once ``process_reference`` resolved it. The pipeline resolves
and copies a text through ``get_references`` / ``replace_node`` / ``copy``, as it does for an
operation. A text without structure stays a plain ``str``.
"""

from __future__ import annotations

import copy as _copy
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from tricc_oo.models.base import TriccNodeBaseModel, TriccOperation, TriccReference
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.text.render import first_text, references


class TriccText(BaseModel):
    """A structured display text (one locale value)."""

    doc: Dict[str, Any]
    refs: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "TriccText":
        """A text over ``doc``, every ``interp`` name as an unresolved ``TriccReference``."""
        return cls(doc=doc, refs={name: TriccReference(name) for name in references(doc)})

    def names(self):
        """The ``interp`` names, in reading order."""
        return references(self.doc)

    def ref(self, name: str) -> Any:
        """What ``name`` stands for (a ``TriccReference`` until resolved)."""
        found = self.refs.get(name)
        return found if found is not None else TriccReference(name)

    def get_references(self) -> OrderedSet:
        predecessor = OrderedSet()
        for name in self.names():
            value = self.ref(name)
            if isinstance(value, TriccOperation):
                for ref in value.get_references() or []:
                    predecessor.add(ref)
            elif isinstance(value, TriccReference) or issubclass(value.__class__, TriccNodeBaseModel):
                predecessor.add(value)
            elif hasattr(value, "get_references"):
                for ref in value.get_references() or []:
                    predecessor.add(ref)
        return predecessor

    def replace_node(self, old_node: Any, new_node: Any) -> None:
        for name in self.names():
            value = self.ref(name)
            if isinstance(value, TriccOperation):
                value.replace_node(old_node, new_node)
            elif value == old_node:
                self.refs[name] = new_node

    def copy(self, keep_node: bool = False, **kwargs) -> "TriccText":
        refs = {}
        for name in self.names():
            value = self.ref(name)
            if isinstance(value, TriccOperation):
                refs[name] = value.copy(keep_node=keep_node, **kwargs)
            elif isinstance(value, TriccReference):
                refs[name] = value.copy()
            elif keep_node or not hasattr(value, "name"):
                refs[name] = value
            else:
                refs[name] = TriccReference(value.name)
        return TriccText(doc=_copy.deepcopy(self.doc), refs=refs)

    def __copy__(self) -> "TriccText":
        return self.copy()

    def first_text(self) -> Optional[str]:
        return first_text(self.doc)

    def __str__(self) -> str:
        from tricc_oo.visitors.text_injection import serialize_injection_for_js_text

        return serialize_injection_for_js_text(self)
