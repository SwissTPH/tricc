"""Display-text AST (formatted messages with ``${REF}`` interpolations).

Not a ``TriccOperation``. See ``feature/20260909-display-message-ast.md``.
"""

from __future__ import annotations

from typing import Any, List, Optional, Union

from pydantic import BaseModel
from strenum import StrEnum

from tricc_oo.models.base import TriccNodeBaseModel, TriccOperation, TriccReference
from tricc_oo.models.ordered_set import OrderedSet


class TriccMessageMarkKind(StrEnum):
    STRONG = "strong"
    EM = "em"
    U = "u"


def _copy_child(child: Any, keep_node: bool = False, **kwargs) -> Any:
    if child is None:
        return None
    if isinstance(child, (TriccMessage, TriccMessageMark, TriccMessageList, TriccMessageListItem, TriccMessageText)):
        return child.copy(keep_node=keep_node, **kwargs)
    if isinstance(child, TriccMessageBreak):
        return TriccMessageBreak()
    if isinstance(child, TriccOperation):
        return child.copy(keep_node=keep_node, **kwargs)
    if isinstance(child, TriccReference):
        return child.copy()
    if keep_node:
        return child
    if hasattr(child, "name"):
        return TriccReference(child.name)
    return child


def _walk_refs(child: Any, predecessor: OrderedSet) -> None:
    if child is None:
        return
    if isinstance(child, TriccReference):
        predecessor.add(child)
        return
    if issubclass(child.__class__, TriccNodeBaseModel):
        predecessor.add(child)
        return
    if isinstance(child, TriccOperation):
        for ref in child.get_references() or []:
            predecessor.add(ref)
        return
    if hasattr(child, "get_references"):
        for ref in child.get_references() or []:
            predecessor.add(ref)


def _replace_child(child: Any, old_node: Any, new_node: Any) -> Any:
    if child is None:
        return None
    if isinstance(child, (TriccMessage, TriccMessageMark, TriccMessageList, TriccMessageListItem)):
        child.replace_node(old_node, new_node)
        return child
    if isinstance(child, TriccOperation):
        child.replace_node(old_node, new_node)
        return child
    if isinstance(child, TriccReference) or issubclass(child.__class__, TriccNodeBaseModel):
        if child == old_node:
            replacement = new_node
            if (
                hasattr(replacement, "select")
                and hasattr(old_node, "select")
                and issubclass(replacement.select.__class__, TriccNodeBaseModel)
            ):
                # Option nodes: also swap the parent select when both sides have one.
                pass
            return replacement
        return child
    return child


def _first_text_leaf(node: Any) -> Optional[str]:
    if node is None:
        return None
    if isinstance(node, TriccMessageText):
        return node.value if node.value else None
    if isinstance(node, str):
        return node if node else None
    if isinstance(node, TriccMessageList):
        for item in node.items or []:
            text = _first_text_leaf(item)
            if text:
                return text
        return None
    children = getattr(node, "children", None)
    if children:
        for child in children:
            text = _first_text_leaf(child)
            if text:
                return text
    return None


class TriccMessageText(BaseModel):
    value: str = ""

    def get_references(self) -> OrderedSet:
        return OrderedSet()

    def replace_node(self, old_node, new_node) -> None:
        return None

    def copy(self, keep_node: bool = False, **kwargs) -> TriccMessageText:
        return TriccMessageText(value=self.value)

    def __str__(self) -> str:
        return self.value


class TriccMessageBreak(BaseModel):
    def get_references(self) -> OrderedSet:
        return OrderedSet()

    def replace_node(self, old_node, new_node) -> None:
        return None

    def copy(self, keep_node: bool = False, **kwargs) -> TriccMessageBreak:
        return TriccMessageBreak()

    def __str__(self) -> str:
        return "\n"


class TriccMessageMark(BaseModel):
    kind: TriccMessageMarkKind = TriccMessageMarkKind.STRONG
    children: List[Any] = []

    def get_references(self) -> OrderedSet:
        predecessor = OrderedSet()
        for child in self.children or []:
            _walk_refs(child, predecessor)
        return predecessor

    def replace_node(self, old_node, new_node) -> None:
        self.children = [_replace_child(c, old_node, new_node) for c in self.children or []]

    def copy(self, keep_node: bool = False, **kwargs) -> TriccMessageMark:
        return TriccMessageMark(
            kind=self.kind,
            children=[_copy_child(c, keep_node=keep_node, **kwargs) for c in self.children or []],
        )


class TriccMessageListItem(BaseModel):
    children: List[Any] = []

    def get_references(self) -> OrderedSet:
        predecessor = OrderedSet()
        for child in self.children or []:
            _walk_refs(child, predecessor)
        return predecessor

    def replace_node(self, old_node, new_node) -> None:
        self.children = [_replace_child(c, old_node, new_node) for c in self.children or []]

    def copy(self, keep_node: bool = False, **kwargs) -> TriccMessageListItem:
        return TriccMessageListItem(
            children=[_copy_child(c, keep_node=keep_node, **kwargs) for c in self.children or []],
        )


class TriccMessageList(BaseModel):
    ordered: bool = False
    items: List[TriccMessageListItem] = []

    def get_references(self) -> OrderedSet:
        predecessor = OrderedSet()
        for item in self.items or []:
            for ref in item.get_references():
                predecessor.add(ref)
        return predecessor

    def replace_node(self, old_node, new_node) -> None:
        for item in self.items or []:
            item.replace_node(old_node, new_node)

    def copy(self, keep_node: bool = False, **kwargs) -> TriccMessageList:
        return TriccMessageList(
            ordered=self.ordered,
            items=[item.copy(keep_node=keep_node, **kwargs) for item in self.items or []],
        )


class TriccMessage(BaseModel):
    """Root of a display-text tree (one locale value)."""

    children: List[Any] = []

    def get_references(self) -> OrderedSet:
        predecessor = OrderedSet()
        for child in self.children or []:
            _walk_refs(child, predecessor)
        return predecessor

    def replace_node(self, old_node, new_node) -> None:
        self.children = [_replace_child(c, old_node, new_node) for c in self.children or []]

    def __copy__(self, keep_node: bool = False, **kwargs) -> TriccMessage:
        return TriccMessage(
            children=[_copy_child(c, keep_node=keep_node, **kwargs) for c in self.children or []],
        )

    def copy(self, keep_node: bool = False, **kwargs) -> TriccMessage:
        return self.__copy__(keep_node=keep_node, **kwargs)

    def first_text(self) -> Optional[str]:
        return _first_text_leaf(self)

    def __str__(self) -> str:
        from tricc_oo.visitors.text_injection import serialize_injection_for_js_text

        return serialize_injection_for_js_text(self)


TriccMessageNode = Union[
    TriccMessageText,
    TriccReference,
    TriccNodeBaseModel,
    TriccMessageBreak,
    TriccMessageMark,
    TriccMessageList,
    TriccMessageListItem,
    TriccMessage,
]

# So DisplayText forward refs on TriccNodeBaseModel.resolve when calculate rebuilds.
import tricc_oo.models.base as _base_mod

_base_mod.TriccMessage = TriccMessage
