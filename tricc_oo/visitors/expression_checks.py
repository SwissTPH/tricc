"""Load-time checks over every expression of a loaded project, before the walk.

* ``W_CQL_UNKNOWN_FUNCTION`` (feature/20261125-expression-languages.md §2): a call to a function
  that is neither in the catalogue (``tricc_oo/lang/functions.json``), nor declared in a project
  CQL library, nor a decision-table alias. It is still passed through as written (``native``).
* The output capability check (feature/20261125-output-capabilities.md) walks the same nodes
  (:mod:`tricc_oo.converters.capabilities`).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional, Tuple

from tricc_oo.converters.decision_table import EXPRESSION_ATTRIBUTES, iter_activity_nodes
from tricc_oo.converters.lang import error_code, load_lang_json
from tricc_oo.models.base import TriccOperation, TriccOperator, TriccStatic

logger = logging.getLogger("default")


def catalogue_names() -> Dict[str, Dict[str, Any]]:
    """The catalogue functions by name."""
    return {entry["name"]: entry for entry in load_lang_json("functions.json")["functions"]}


def iter_operations(expr: Any) -> Iterator[TriccOperation]:
    """Every operation of an expression, the expression itself included, depth first."""
    stack = [expr]
    while stack:
        item = stack.pop()
        if isinstance(item, (list, tuple)):
            stack.extend(reversed(item))
        elif isinstance(item, TriccOperation):
            yield item
            stack.extend(reversed(list(item.reference or [])))


def project_nodes(project: Any) -> List[Any]:
    """Every node of the project's pages and library calculates, each once."""
    pages = list((getattr(project, "pages", None) or {}).values())
    return list(iter_activity_nodes(pages + list(getattr(project, "library_calculates", None) or [])))


def iter_node_expressions(project: Any) -> Iterator[Tuple[Any, str, Any]]:
    """``(node, attribute, expression)`` for every expression attribute of every node."""
    for node in project_nodes(project):
        for attribute in EXPRESSION_ATTRIBUTES + ("reference",):
            expr = getattr(node, attribute, None)
            if isinstance(expr, TriccOperation):
                yield node, attribute, expr


def native_name(op: TriccOperation) -> Optional[str]:
    """The function name of a call passed through as written (``native``), else None."""
    if op.operator != TriccOperator.NATIVE or not op.reference:
        return None
    head = op.reference[0]
    name = head.value if isinstance(head, TriccStatic) else head
    return name.strip("'`") if isinstance(name, str) else None


def node_label(node: Any) -> str:
    """``'name' (activity)`` for messages."""
    name = getattr(node, "name", None) or getattr(node, "label", None) or getattr(node, "id", "?")
    activity = getattr(getattr(node, "activity", None), "name", None)
    return f"{name!r}" + (f" ({activity})" if activity else "")


def check_unknown_functions(project: Any) -> Dict[str, List[str]]:
    """Log ``W_CQL_UNKNOWN_FUNCTION`` once per unknown function name.

    Args:
        project: The loaded project (before the decision-table expansion).

    Returns:
        ``{function name: [node labels]}`` of the unknown functions.
    """
    from tricc_oo.converters.cql_library import BUILTIN_FUNCTION_TYPES, function_signature

    known = catalogue_names()
    aliases = getattr(project, "aliases", None) or {}
    unknown: Dict[str, List[str]] = {}
    for node, _attribute, expr in iter_node_expressions(project):
        for op in iter_operations(expr):
            name = native_name(op)
            if (
                name is None
                or name in known
                or name in aliases
                or name.lower() in BUILTIN_FUNCTION_TYPES
                or function_signature(project, name) is not None
            ):
                continue
            labels = unknown.setdefault(name, [])
            if node_label(node) not in labels:
                labels.append(node_label(node))
    code = error_code("unknown_function")
    for name, labels in unknown.items():
        logger.warning(
            f"{code}: {name}() is not a TRICC function nor declared in a project library "
            f"(used by {', '.join(labels[:5])}{'…' if len(labels) > 5 else ''}); it is passed through as written"
        )
    return unknown
