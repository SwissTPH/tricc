"""draw.io surface of block and activity parameters.

feature/20261111-block-params-and-start-node.md §2 to §4. In a drawing:

- a ``parameters`` shape (at most one per page) declares the page's parameters, one
  attribute ``param.<name>`` each, holding JSON or the shorthand ``type[(a|b)][!][=default]``
  (see ``models.params.parse_param_shorthand``). It is not a flow node: it is removed from
  the rendered copy before the page is built;
- a ``block`` shape uses a block (``link``: the block's ``block_start`` name, or
  ``data:page/id,<diagram id>``); a ``goto`` shape calls an activity as before. Either may
  carry ``param.<name>`` attributes: the values for that use;
- ``{{param}}`` / ``{{param|raw}}`` placeholders may appear in node attributes (rendered as
  text or as an expression, see ``_context``), in edge labels and in the page name;
- a call argument may be an expression, ``param.age = {"expression": "AgeInDays()"}``: a
  calculate of the calling page, added by ``drawio_add_calculate`` (§18.8 point 1);
- an input or calculate of a block marked ``output = true`` is an output; when no field of
  the block is marked, every input and calculate is an output.

This module gives ``strategies.input.param_build.ParamBuild`` what it needs from a drawing:
``drawio_template`` reads a diagram as a ``Template``, ``drawio_resolver`` resolves its calls,
and ``drawio_render`` makes the copy of a diagram for one instance, which the strategy then
builds with the normal ``create_activity``. (``param:<name>`` is not used: in XML a ``:``
starts a namespace prefix, so such a drawing does not parse.)
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from tricc_oo.converters.xml_to_tricc import clean_link, get_id
from tricc_oo.models.params import (
    E_OUTPUT_UNKNOWN,
    E_PARAM_CONFLICT,
    E_PARAM_PLACEHOLDER,
    E_PARAM_UNKNOWN,
    EXPRESSION,
    TEXT,
    CallSite,
    Template,
    TriccParamError,
    has_placeholder,
    literal_arg_names,
    parse_param_shorthand,
    placeholder_names,
    raw_placeholder_names,
    substitute,
)
from tricc_oo.parsers.xml import type_name

logger = logging.getLogger("default")

#: prefix of the parameter attributes, on a ``parameters`` shape and on ``block`` / ``goto``
PARAM_PREFIX = "param."
#: the elements that carry TRICC attributes (``odk_type``, ``name``, ...) in draw.io
SHAPES = ("object", "UserObject")
#: page roots, in the order ``create_root_node`` looks for them
ROOT_TYPES = ("start", "activity_start", "block_start")
#: shapes that call another page
CALL_TYPES = ("block", "goto")
#: the inputs and calculates of a block: its outputs unless some are marked ``output = true`` (§18.2)
FIELD_TYPES = (
    "integer", "decimal", "quantity", "text", "date", "select_one", "select_multiple", "select_yesno",
    "calculate", "add", "count", "diagnosis", "proposed_diagnosis",
)
#: first names of block_start / block, still read
TYPE_ALIASES = {"snippet_start": "block_start", "snippet": "block"}

#: attributes a placeholder renders into as an expression (quoted literals, §4)
EXPRESSION_ATTRIBUTES = {"relevance", "calculate", "expression", "constraint", "min", "max", "reference", "trigger"}
#: attributes a placeholder renders into as plain text
TEXT_ATTRIBUTES = {"name", "label", "hint", "help", "save", "constraint_message"}
#: cell references: suffixed in each copy, never holding a placeholder. Any other attribute
#: (``odk_type``, ``link``, ``process``, ``instance``, ``style``, ...) refuses placeholders.
ID_ATTRIBUTES = ("id", "parent", "source", "target")

#: a call of a rendered diagram, and the setter pointing it at the instance it must use
RenderedCall = Tuple[CallSite, Callable[[str], None]]


def _shapes(diagram):
    """Every TRICC shape (``object`` / ``UserObject`` element) of ``diagram``."""
    for tag in SHAPES:
        yield from diagram.iter(tag)


def normalize_types(diagram) -> None:
    """Rewrite the first names ``snippet_start`` / ``snippet`` to ``block_start`` / ``block``.

    Args:
        diagram: A ``<diagram>`` element, changed in place.
    """
    for shape in _shapes(diagram):
        if shape.attrib.get(type_name) in TYPE_ALIASES:
            shape.attrib[type_name] = TYPE_ALIASES[shape.attrib[type_name]]


def page_id(diagram) -> str:
    """The id of the page built from ``diagram`` (as ``create_activity`` computes it)."""
    did = diagram.attrib.get("id")
    return get_id(did, did)


def _root(diagram):
    """The page's root shape: a ``start``, else an ``activity_start``, else a ``block_start``."""
    shapes = list(_shapes(diagram))
    for kind in ROOT_TYPES:
        for shape in shapes:
            if shape.attrib.get(type_name) == kind:
                return shape
    return None


def _arg_value(text: str) -> Any:
    """A ``param.<name>`` value of a call: JSON when it is an object (a concept
    ``{"system", "code"}``), else the text (a literal, or ``{{ref}}``)."""
    text = text.strip()
    if text.startswith("{") and not text.startswith("{{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def call_args(shape) -> Dict[str, Any]:
    """The values a ``block`` / ``goto`` shape gives: its ``param.<name>`` attributes.

    Args:
        shape: The shape element.

    Returns:
        ``{name: value}``; values are checked against the callee's parameters later, by
        ``models.params.bind``.
    """
    return {k[len(PARAM_PREFIX):]: _arg_value(v) for k, v in shape.attrib.items() if k.startswith(PARAM_PREFIX)}


def drawio_template(diagram) -> Template:
    """Read a diagram as a ``Template``: declarations, calls and placeholders used.

    Args:
        diagram: A ``<diagram>`` element (kept, unchanged, as ``Template.raw``).

    Returns:
        The template. Its ``name`` is the root shape's ``name`` (for a block, what a
        ``block`` shape's ``link`` may use); ``is_block`` when the root is ``block_start``.
        A goto call's ``link`` is the target page id; a block call's is the block name or
        page id as written.

    Raises:
        TriccParamError: ``E_PARAM_CONFLICT`` for two ``parameters`` shapes on the page, or
            one name declared twice; errors of ``parse_param_shorthand``.
    """
    tid = page_id(diagram)
    root = _root(diagram)
    is_block = root is not None and root.attrib.get(type_name) == "block_start"
    name = root.attrib.get("name") if root is not None else None
    template = Template(id=tid, name=name, is_block=is_block, raw=diagram)
    declared = {}
    holders = [s for s in _shapes(diagram) if s.attrib.get(type_name) == "parameters"]
    if len(holders) > 1:
        raise TriccParamError(E_PARAM_CONFLICT, f"page {tid} has {len(holders)} parameters shapes (one at most)")
    for holder in holders:
        for key, value in holder.attrib.items():
            if not key.startswith(PARAM_PREFIX):
                continue
            pname = key[len(PARAM_PREFIX):]
            if pname in declared:
                raise TriccParamError(E_PARAM_CONFLICT, f"page {tid} declares {pname!r} twice")
            spec = parse_param_shorthand(pname, value)
            declared[pname] = spec.model_copy(update={"owner": template.owner})
    template.declared = declared
    calls = []
    for shape in _shapes(diagram):
        kind = shape.attrib.get(type_name)
        if kind in CALL_TYPES and shape.attrib.get("link"):
            link = clean_link(shape.attrib["link"]) or shape.attrib["link"]
            if kind == "goto":
                link = get_id(link, link)
            calls.append(CallSite(caller=tid, node_id=shape.attrib.get("id"), link=link, kind=kind,
                                  args=call_args(shape)))
    template.calls = calls
    used = set()
    for element in diagram.iter():
        for key, value in element.attrib.items():
            if not key.startswith(PARAM_PREFIX):
                used.update(placeholder_names(value))
    template.used = sorted(used)
    template.static_used = sorted(_static_used(diagram))
    shapes = list(_shapes(diagram))
    template.fields = [
        s.attrib["name"] for s in shapes if s.attrib.get(type_name) in FIELD_TYPES and s.attrib.get("name")
    ]
    template.outputs = _outputs(shapes, type_name) if is_block else None
    template.templated_names = [s.attrib["name"] for s in shapes if has_placeholder(s.attrib.get("name"))]
    return template


def _outputs(shapes, type_name) -> Optional[List[str]]:
    """The names of the block's fields marked ``output = true``; None when none is marked
    (every input and calculate is an output). A marked shape that is not a named input or
    calculate is ``E_OUTPUT_UNKNOWN``."""
    marked = [s for s in shapes if str(s.attrib.get("output", "")).strip().lower() in ("true", "1", "yes")]
    if not marked:
        return None
    outputs = []
    for shape in marked:
        if shape.attrib.get(type_name) not in FIELD_TYPES or not shape.attrib.get("name"):
            raise TriccParamError(
                E_OUTPUT_UNKNOWN,
                f"shape {shape.attrib.get('id')!r} is marked output but is not a named input or calculate",
            )
        outputs.append(shape.attrib["name"])
    return outputs


def _static_used(diagram) -> set:
    """Parameters a diagram uses where only a fixed value fits (§18.8 point 1): the page name,
    shape ``name`` / ``save``, ``{{p|raw}}``, static decisions, literal call arguments."""
    names = set(placeholder_names(diagram.attrib.get("name")))
    for element in diagram.iter():
        for key, value in element.attrib.items():
            if not key.startswith(PARAM_PREFIX):
                names.update(raw_placeholder_names(value))
    for shape in _shapes(diagram):
        for key in ("name", "save"):
            names.update(placeholder_names(shape.attrib.get(key)))
        if str(shape.attrib.get("static", "")).lower() == "true":
            for key in EXPRESSION_ATTRIBUTES:
                names.update(placeholder_names(shape.attrib.get(key)))
        if shape.attrib.get(type_name) in CALL_TYPES:
            names.update(literal_arg_names(call_args(shape)))
    return names


def drawio_add_calculate(diagram, call: CallSite, name: str, expression: str, label: str) -> None:
    """Add to a rendered diagram the calculate of an expression argument (§18.8 point 1).

    A calculate shape with no incoming edge, beside the call shape: evaluated once its
    references are, like any free calculate of the page, and read in the block through
    ``{{param}}``.
    """
    from lxml import etree

    call_shape = next(
        (s for s in _shapes(diagram) if s.attrib.get("id", "").startswith(call.node_id)
         and s.attrib.get(type_name) in CALL_TYPES),
        None,
    )
    cell = call_shape.find("mxCell") if call_shape is not None else None
    parent = cell.attrib.get("parent", "1") if cell is not None else "1"
    container = call_shape.getparent() if call_shape is not None else next(diagram.iter("root"))
    shape = etree.SubElement(container, "object")
    shape.attrib.update({
        type_name: "calculate", "label": label, "name": name, "reference": expression,
        "id": f"{call.node_id}-{name}",
    })
    geometry = etree.SubElement(etree.SubElement(shape, "mxCell", parent=parent, vertex="1"), "mxGeometry")
    geometry.attrib["as"] = "geometry"


def _context(element, key: str, edge_ids) -> Optional[str]:
    """How a placeholder in ``element``'s attribute ``key`` renders.

    Args:
        element: The XML element holding the attribute.
        key: The attribute name.
        edge_ids: Ids of the diagram's edge cells.

    Returns:
        ``EXPRESSION`` for the expression attributes and for an edge label (``value`` of an
        edge cell, or of a label cell on an edge); ``TEXT`` for the text attributes and the
        ``value`` (text) of any other cell; None when placeholders are not allowed there.
    """
    if key in EXPRESSION_ATTRIBUTES:
        return EXPRESSION
    if key == "value" and element.tag == "mxCell":
        is_edge = element.attrib.get("edge") or element.attrib.get("parent") in edge_ids
        return EXPRESSION if is_edge else TEXT
    if key in TEXT_ATTRIBUTES:
        return TEXT
    return None


def drawio_render(template: Template, env, new_id: str) -> Tuple[Any, List[RenderedCall]]:
    """Make the copy of a diagram for one instance.

    In the copy: the diagram id becomes ``new_id``; when ``new_id`` has a suffix, every
    ``id`` / ``parent`` / ``source`` / ``target`` gets it too, so node and edge ids stay
    unique across instances; placeholders are rendered from ``env`` (``_context`` decides
    how); the ``parameters`` shape is removed. ``param.<name>`` attributes are left as they
    are: ``ParamBuild`` binds them.

    Args:
        template: The page (``drawio_template``).
        env: The instance's values (``models.params.Env``).
        new_id: The instance id: the page id, plus a suffix for any instance other than the
            page's own (see ``ParamBuild``).

    Returns:
        ``(diagram copy, calls)``; each call comes with a setter that points the copy's shape
        at the instance it must use (``link = data:page/id,<instance id>``).

    Raises:
        TriccParamError: ``E_PARAM_PLACEHOLDER`` for a placeholder in an id, or in an
            attribute that allows none; errors of ``models.params.substitute``.
    """
    suffix = new_id[len(template.id):]
    diagram = copy.deepcopy(template.raw)
    diagram.attrib["id"] = new_id
    if "name" in diagram.attrib:
        diagram.attrib["name"] = substitute(diagram.attrib["name"], env, TEXT, template.id)
    edge_ids = {c.attrib.get("id") for c in diagram.iter("mxCell") if c.attrib.get("edge")}
    calls = []
    for element in diagram.iter():
        if element is diagram:
            continue
        where = f"{template.id}/{element.attrib.get('id', element.tag)}"
        for key, value in list(element.attrib.items()):
            if key.startswith(PARAM_PREFIX):
                continue
            if key in ID_ATTRIBUTES:
                if has_placeholder(value):
                    raise TriccParamError(E_PARAM_PLACEHOLDER, f"{where}: placeholders are not allowed in {key!r}")
                if suffix:
                    element.attrib[key] = value + suffix
                continue
            context = _context(element, key, edge_ids)
            if context is None:
                if has_placeholder(value):
                    raise TriccParamError(E_PARAM_PLACEHOLDER, f"{where}: placeholders are not allowed in {key!r}")
                continue
            element.attrib[key] = substitute(value, env, context, where)
        kind = element.attrib.get(type_name)
        if element.tag in SHAPES and kind in CALL_TYPES and element.attrib.get("link"):
            original_id = element.attrib["id"]
            if suffix:
                original_id = original_id[: len(original_id) - len(suffix)]
            call = next(c for c in template.calls if c.node_id == original_id)
            calls.append((call, _link_setter(element)))
    for holder in [s for s in _shapes(diagram) if s.attrib.get(type_name) == "parameters"]:
        holder.getparent().remove(holder)
    return diagram, calls


def _link_setter(element) -> Callable[[str], None]:
    """Point a call shape at a page instance, in draw.io's link format."""

    def set_link(instance_id: str) -> None:
        element.attrib["link"] = f"data:page/id,{instance_id}"

    return set_link


def drawio_resolver(templates: Dict[str, Template]) -> Callable[[CallSite], Optional[str]]:
    """The ``resolve`` callback of ``ParamBuild`` for a set of diagrams.

    Args:
        templates: Every page of the input, by id.

    Returns:
        A function mapping a call to the template id it targets:

        - a ``block`` call: the block whose ``block_start`` name is the link, else the block
          page with that id;
        - a ``goto`` call: the activity page with that id, or None when the page is not in
          this input (linked as before).

        It raises ``TriccParamError`` (``E_PARAM_UNKNOWN``) for a ``block`` call to no block.
    """
    blocks_by_name = {}
    for tid, template in templates.items():
        if template.is_block and template.name:
            blocks_by_name.setdefault(template.name, tid)

    def resolve(call: CallSite) -> Optional[str]:
        if call.kind == "block":
            tid = blocks_by_name.get(call.link) or (call.link if call.link in templates else None)
            if tid is None or not templates[tid].is_block:
                raise TriccParamError(E_PARAM_UNKNOWN, f"{call.describe()}: no block {call.link!r}")
            return tid
        if call.link in templates and not templates[call.link].is_block:
            return call.link
        return None

    return resolve
