"""Block and activity parameters: declaration, binding and placeholder substitution.

Input-agnostic part of feature/20261111-block-params-and-start-node.md (§2 to §5). The input
strategies use it in four steps:

1. **Read** each page as a ``Template``: its declared parameters (``ParamSpec``), its calls
   to other pages (``CallSite``, from ``block`` and ``goto`` nodes) and its raw source, with
   the ``{{param}}`` placeholders still in it.
2. **Compute** every page's effective parameters (``compute_effective``): what it declares,
   plus what the pages it calls need and the call leaves unbound.
3. **Bind** values from the top down (``bind``): for each parameter of a called page, the
   call's argument, else the caller's value of the same name, else the default. The result
   is an environment (``Env``): parameter name to ``(spec, value)``.
4. **Render** the raw source with that environment (``substitute``), then build the page as
   any other. One copy is built per distinct environment (``env_key`` / ``env_suffix``).

The driver that runs these steps is ``tricc_oo.strategies.input.param_build.ParamBuild``.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from tricc_oo.converters.utils import quoted_literal

#: every parameter type (§2)
PARAM_TYPES = ("boolean", "number", "string", "choice", "name", "concept", "expression")
#: the types the authoring tool offers, registered as dictionary concepts (§5)
PRIMITIVE_TYPES = ("boolean", "number", "string", "choice")
#: ``dataType`` property of a parameter concept, by parameter type
CONCEPT_DATA_TYPES = {"boolean": "boolean", "number": "decimal", "string": "string", "choice": "coded"}

#: a parameter name
PARAM_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: a ``name`` value, and what ``{{p|raw}}`` may render to inside an expression
NAME_FRAGMENT = re.compile(r"^[a-z0-9_]+$")
#: a placeholder anywhere in a text: group 1 the name, group 2 the ``|raw`` flag
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*(\|\s*raw\s*)?\}\}")
#: an argument that is only a placeholder, ``{{caller_param}}``: passes a caller parameter on
REFERENCE = re.compile(r"^\s*\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}\s*$")
#: draw.io shorthand declaration ``type[(a|b)][!][=default]``
SHORTHAND = re.compile(r"^\s*([a-z]+)\s*(?:\(([^)]*)\))?\s*(!)?\s*(?:=(.*))?$", re.S)

#: rendering contexts of a placeholder (§4): a label or name, or an expression
TEXT = "text"
EXPRESSION = "expression"

# Error / warning codes named by the spec.
E_PARAM_CONFLICT = "E_PARAM_CONFLICT"  # one name, two types (or option lists) along a chain
E_PARAM_REQUIRED = "E_PARAM_REQUIRED"  # a required parameter gets no value
E_PARAM_UNKNOWN = "E_PARAM_UNKNOWN"  # an argument, placeholder or reference names no parameter
E_PARAM_TYPE = "E_PARAM_TYPE"  # a value or declaration of the wrong type
E_PARAM_PLACEHOLDER = "E_PARAM_PLACEHOLDER"  # a placeholder where none is allowed
E_BLOCK_CYCLE = "E_BLOCK_CYCLE"  # a block that uses itself, directly or not
W_PARAM_UNREFERENCED = "W_PARAM_UNREFERENCED"  # a declared parameter nothing uses
# §18.8 (expression arguments, abstract concepts, outputs)
E_ARG_DYNAMIC_STATIC = "E_ARG_DYNAMIC_STATIC"  # an expression argument for a parameter that shapes the drawing
E_BLOCK_PRIVATE = "E_BLOCK_PRIVATE"  # a reference from outside a block to one of its private nodes
E_OUTPUT_UNKNOWN = "E_OUTPUT_UNKNOWN"  # ``outputs`` lists a name no inner input or calculate has
E_ABSTRACT_SELECTED = "E_ABSTRACT_SELECTED"  # an abstract (template) concept used outside its block
E_BLOCK_SCOPE = "E_BLOCK_SCOPE"  # a block reads stored data (it must come in as an argument)

#: parameter types whose value is only ever static (§18.8 point 1)
STATIC_ONLY_TYPES = ("name", "concept")
#: key of a bound dynamic value: ``{"dynamic": <name of the calculate holding it>}``
DYNAMIC = "dynamic"


class TriccParamError(ValueError):
    """A parameter, argument or placeholder problem that stops the build.

    Attributes:
        code: The rule broken, one of the ``E_*`` constants of this module. The message
            starts with it too, and names the page, node or call chain involved.
    """

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


class ParamSpec(BaseModel):
    """One parameter of a page: declared on it, or computed from the pages it calls.

    A computed entry is a copy of the callee's declaration (``owner`` and
    ``declared_name`` keep pointing at it), renamed when a ``{{ref}}`` argument passes it on
    under another name, and with ``via`` recording the calls it came up through.

    Attributes:
        name: The name on this page (what ``{{name}}`` and arguments use).
        type: One of ``PARAM_TYPES``.
        options: The allowed values of a ``choice``; only for that type.
        default: Used when no argument and no inherited value gives one. Checked and
            converted to ``type`` at construction.
        required: Without a value from anywhere, the build fails (``E_PARAM_REQUIRED``).
        label: Display text (draw.io and tests only: the frontend keeps texts on the
            parameter's concept, §5). A string or ``{lang: text}``.
        description: Definition text, same form as ``label``.
        owner: The page holding the declaration, as ``Template.owner``.
        declared_name: The name in that declaration. With ``owner`` it gives the concept
            code (``param_concept_code``). Defaults to ``name``.
        via: For a computed entry, the calls it came up through, nearest first. Error
            messages append it to the chain, down to the use that needs the value.
    """

    model_config = ConfigDict(extra="ignore")

    name: str
    type: str
    options: Optional[List[str]] = None
    default: Any = None
    required: bool = False
    label: Any = None
    description: Any = None
    owner: Optional[str] = None
    declared_name: Optional[str] = None
    via: List[str] = []

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not PARAM_NAME.match(value or ""):
            raise ValueError(f"parameter name {value!r} is not an identifier")
        return value

    @field_validator("type")
    @classmethod
    def _type(cls, value: str) -> str:
        if value not in PARAM_TYPES:
            raise ValueError(f"parameter type {value!r} is not one of {', '.join(PARAM_TYPES)}")
        return value

    @model_validator(mode="after")
    def _check(self) -> "ParamSpec":
        """Options only (and always) for ``choice``; the default converted to the type."""
        if self.type == "choice" and not self.options:
            raise ValueError(f"choice parameter {self.name!r} has no options")
        if self.type != "choice" and self.options:
            raise ValueError(f"parameter {self.name!r}: options are only for type choice")
        if self.default is not None:
            self.default = coerce_value(self, self.default, f"default of {self.name!r}")
        if self.declared_name is None:
            self.declared_name = self.name
        return self

    def signature(self) -> Tuple[str, Tuple[str, ...]]:
        """What two declarations of the same name along a chain must agree on.

        Returns:
            ``(type, options)``. The default may differ: the deepest declaration's wins.
        """
        return self.type, tuple(self.options or ())


def parse_param_shorthand(name: str, text: str) -> ParamSpec:
    """Read a draw.io ``param.<name>`` declaration of a ``parameters`` shape.

    Args:
        name: The parameter name (the attribute name without ``param.``).
        text: The attribute value: JSON (``{"type": "string", "label": {...}}``) or the
            shorthand ``type[(a|b)][!][=default]``, where ``!`` means required.
            Examples: ``choice(axillary|rectal)!``, ``number=37.5``, ``boolean=false``.

    Returns:
        The declaration (its ``owner`` is set by the caller).

    Raises:
        TriccParamError: ``E_PARAM_TYPE`` when the text is neither JSON nor shorthand.
        pydantic.ValidationError: when the declaration itself is invalid (unknown type,
            choice without options, default of the wrong type).
    """
    text = (text or "").strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TriccParamError(E_PARAM_TYPE, f"parameter {name!r}: invalid JSON ({exc})") from exc
        return ParamSpec(**{**data, "name": name})
    match = SHORTHAND.match(text)
    if not match:
        raise TriccParamError(E_PARAM_TYPE, f"parameter {name!r}: cannot read {text!r}")
    ptype, options, required, default = match.groups()
    data: Dict[str, Any] = {"name": name, "type": ptype, "required": bool(required)}
    if options is not None:
        data["options"] = [o.strip() for o in options.split("|") if o.strip()]
    if default is not None:
        data["default"] = default.strip()
    return ParamSpec(**data)


def coerce_value(spec: ParamSpec, value: Any, where: str) -> Any:
    """Check a value against a parameter's type and convert it.

    Values often arrive as text (draw.io attributes, YAML strings), so ``"true"``, ``"38"``
    or a bare concept code are accepted for their types.

    Args:
        spec: The parameter the value is for.
        value: The value as written (an argument, a default, an inherited value).
        where: Context for the error message (the call chain, or ``default of 'x'``).

    Returns:
        ``bool`` for boolean, ``int`` / ``float`` for number, ``{"system", "code"}`` for
        concept, ``str`` for the other types.

    Raises:
        TriccParamError: ``E_PARAM_TYPE`` when the value does not fit: not ``true`` /
            ``false``, not a number, not one of the ``choice`` options, not a name fragment,
            or a structure where text is expected.
    """

    def bad(why: str):
        return TriccParamError(E_PARAM_TYPE, f"{where}: {value!r} {why} (parameter {spec.name}: {spec.type})")

    if spec.type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
        raise bad("is not true or false")
    if spec.type == "number":
        if isinstance(value, bool):
            raise bad("is not a number")
        if isinstance(value, (int, float)):
            return value
        try:
            number = float(str(value).strip())
        except ValueError:
            raise bad("is not a number") from None
        return int(number) if number.is_integer() and "." not in str(value) else number
    if spec.type == "concept":
        if isinstance(value, dict) and value.get("code"):
            return {"system": value.get("system"), "code": str(value["code"])}
        if isinstance(value, str) and value.strip():
            return {"system": None, "code": value.strip()}
        raise bad("is not a concept ({system, code} or a code)")
    if isinstance(value, (dict, list)):
        raise bad("is not a text value")
    text = str(value).lower() if isinstance(value, bool) else str(value)
    if spec.type == "choice" and text not in (spec.options or []):
        raise bad(f"is not one of the options {spec.options}")
    if spec.type == "name" and not NAME_FRAGMENT.match(text):
        raise bad("is not a name fragment ([a-z0-9_]+)")
    return text


def is_expression_arg(arg: Any) -> bool:
    """Whether a call argument, as written, is a dynamic one: ``{expression, intent?}``.

    A bare string is always a literal; a concept is ``{system, code}``, never this form.
    """
    return isinstance(arg, dict) and "expression" in arg and "code" not in arg


def is_dynamic(value: Any) -> bool:
    """Whether a bound value is dynamic: ``{"dynamic": <calculate name>}`` (``bind``)."""
    return isinstance(value, dict) and DYNAMIC in value


def _number_text(value) -> str:
    """A number as text, ``38.0`` written ``38``."""
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)


def render_value(spec: ParamSpec, value: Any, context: str, raw: bool, where: str) -> str:
    """The text one placeholder becomes (§4).

    | type | text context | expression context |
    |------|--------------|--------------------|
    | string, choice | the text | quoted literal: ``'axillary'`` |
    | number, boolean | the value | the literal: ``37.5``, ``true`` |
    | name | the fragment | the fragment |
    | concept | the code | a reference: ``"body_temperature"`` |
    | expression | not allowed | parenthesized: ``(a + b)`` |

    ``raw`` (``{{p|raw}}``) gives the plain text in an expression too, to build a name
    inside one (``"temp_{{site|raw}}"``); it must then be a name fragment.

    A dynamic value (an expression argument, §18.8) is the calculate evaluated at the use:
    a reference to it in an expression (``"arg_age_1a2b3c4d"``), its display injection in a
    text (``${arg_age_1a2b3c4d}``). It never renders raw: it cannot build a name.

    Args:
        spec: The parameter.
        value: Its bound value (``coerce_value`` output); None when nothing bound it.
        context: ``TEXT`` or ``EXPRESSION``, from the field holding the placeholder.
        raw: Whether the placeholder has ``|raw``.
        where: Context for the error message (page / node / field).

    Returns:
        The rendered text.

    Raises:
        TriccParamError: ``E_PARAM_REQUIRED`` when the value is None; ``E_PARAM_TYPE`` when
            a ``|raw`` value is not a name fragment; ``E_PARAM_PLACEHOLDER`` for an
            ``expression`` parameter in a text field.
    """
    if value is None:
        raise TriccParamError(E_PARAM_REQUIRED, f"{where}: parameter {spec.name!r} has no value")
    if is_dynamic(value):
        if raw:
            raise TriccParamError(
                E_ARG_DYNAMIC_STATIC,
                f"{where}: {{{{{spec.name}|raw}}}} builds a name, so {spec.name!r} needs a fixed value",
            )
        return f'"{value[DYNAMIC]}"' if context == EXPRESSION else f"${{{value[DYNAMIC]}}}"
    if spec.type == "boolean":
        text = "true" if value else "false"
    elif spec.type == "number":
        text = _number_text(value)
    elif spec.type == "concept":
        text = value["code"]
    else:
        text = str(value)
    if raw and context == EXPRESSION:
        if not NAME_FRAGMENT.match(text):
            raise TriccParamError(
                E_PARAM_TYPE, f"{where}: {{{{{spec.name}|raw}}}} needs a name fragment, got {text!r}"
            )
        return text
    if context == TEXT:
        if spec.type == "expression":
            raise TriccParamError(E_PARAM_PLACEHOLDER, f"{where}: expression parameter {spec.name!r} in a text field")
        return text
    if spec.type in ("string", "choice"):
        return quoted_literal(text)
    if spec.type == "concept":
        return '"' + text + '"'
    if spec.type == "expression":
        return f"({text})"
    return text


#: an environment: parameter name to ``(declaration, bound value)``; the value is None when
#: nothing bound an optional parameter
Env = Dict[str, Tuple[ParamSpec, Any]]


def has_placeholder(text: Any) -> bool:
    """Whether ``text`` is a string holding at least one ``{{param}}``."""
    return isinstance(text, str) and bool(PLACEHOLDER.search(text))


def substitute(text: Any, env: Env, context: str, where: str) -> Any:
    """Render every placeholder of one field.

    Args:
        text: The field value as written; anything that is not a string is returned as is.
        env: The page instance's environment.
        context: ``TEXT`` or ``EXPRESSION`` (see ``render_value``).
        where: Context for error messages (page / node / field).

    Returns:
        ``text`` with each ``{{p}}`` / ``{{p|raw}}`` replaced by ``render_value``.

    Raises:
        TriccParamError: ``E_PARAM_UNKNOWN`` for a placeholder naming no parameter of the
            page, or any error of ``render_value``.
    """
    if not has_placeholder(text):
        return text

    def one(match):
        name, raw = match.group(1), bool(match.group(2))
        if name not in env:
            raise TriccParamError(E_PARAM_UNKNOWN, f"{where}: {{{{{name}}}}} is not a parameter of this page")
        spec, value = env[name]
        return render_value(spec, value, context, raw, where)

    return PLACEHOLDER.sub(one, text)


def placeholder_names(text: Any) -> List[str]:
    """The parameter names used in ``text``'s placeholders, in order (empty for non-strings)."""
    return [m.group(1) for m in PLACEHOLDER.finditer(text)] if isinstance(text, str) else []


def raw_placeholder_names(text: Any) -> List[str]:
    """The parameter names used as ``{{name|raw}}`` in ``text`` (they build a name)."""
    return [m.group(1) for m in PLACEHOLDER.finditer(text) if m.group(2)] if isinstance(text, str) else []


def literal_arg_names(args: Dict[str, Any]) -> Set[str]:
    """Caller parameters rendered as text into a literal call argument (``"x_{{site}}"``).

    Such a value is fixed when the call is bound, so these parameters need a fixed value
    (``Template.static_used``). A plain ``{{x}}`` passes the value on instead: not counted.
    """
    names: Set[str] = set()
    for arg in args.values():
        if isinstance(arg, str) and not REFERENCE.match(arg):
            names.update(placeholder_names(arg))
    return names


class CallSite(BaseModel):
    """A use of another page: a ``block`` or ``goto`` node, read from the raw source.

    Attributes:
        caller: Id of the page holding the node.
        node_id: Id of the node, as written.
        link: The page it calls, as written: for a block its ``block_start`` name or page
            id, for a goto the page id. The input strategy resolves it.
        kind: ``"block"`` or ``"goto"``.
        args: The parameter values given at this use, as written: literals,
            ``{system, code}``, or ``"{{caller_param}}"`` (see ``bind``).
    """

    caller: str
    node_id: str
    link: str
    kind: str
    args: Dict[str, Any] = {}

    def describe(self) -> str:
        """The use in error messages, e.g. ``block t-ax in triage``."""
        return f"{self.kind} {self.node_id} in {self.caller}"


class Template(BaseModel):
    """A page as written, before any instance of it is built.

    Attributes:
        id: The page id; instances are ``id`` plus an ``env_suffix`` (none for the
            instance an activity gets from its intervention).
        name: The page name (activity name, or the block's ``block_start`` name).
        is_block: Rooted by ``block_start``: only built when used, never a start page.
        declared: Its own parameters, by name.
        calls: Its ``block`` and ``goto`` nodes.
        used: Parameter names its placeholders use (for ``W_PARAM_UNREFERENCED``).
        static_used: Parameter names it uses where only a fixed value fits (§18.8 point 1):
            in a node or option ``name``, a ``save``, a ``{{p|raw}}``, the page name, a static
            decision, or inside a literal call argument. ``compute_static_only`` adds the
            ones the pages it calls need.
        fields: Template names of its inputs and calculates: a block's default outputs.
        outputs: A block's ``outputs`` as written (template names); None when the key is
            absent (every field is an output), ``[]`` for none (§18.8 point 3).
        templated_names: Node names holding a placeholder (``fever_{{site}}``): each may
            have an abstract concept (§18.8 point 2).
        raw: The source the input strategy renders: a YAML dict, or a draw.io diagram.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    name: Optional[str] = None
    is_block: bool = False
    declared: Dict[str, ParamSpec] = {}
    calls: List[CallSite] = []
    used: List[str] = []
    static_used: List[str] = []
    fields: List[str] = []
    outputs: Optional[List[str]] = None
    templated_names: List[str] = []
    raw: Any = None

    def private_fields(self) -> List[str]:
        """Template names of the fields that are not outputs (none without ``outputs``)."""
        if self.outputs is None:
            return []
        return [name for name in self.fields if name not in self.outputs]

    def check_outputs(self) -> None:
        """Check ``outputs`` names fields of the block.

        Raises:
            TriccParamError: ``E_OUTPUT_UNKNOWN`` for a listed name no inner input or
                calculate has, or ``outputs`` on a page that is not a block.
        """
        if self.outputs is None:
            return
        if not self.is_block:
            raise TriccParamError(E_OUTPUT_UNKNOWN, f"page {self.id}: only a block has outputs")
        for name in self.outputs:
            if name not in self.fields:
                raise TriccParamError(
                    E_OUTPUT_UNKNOWN, f"block {self.id} lists an output {name!r} that it does not have"
                )

    @property
    def owner(self) -> str:
        """``<owner>`` of the parameter concept codes: the page name, else its id, with
        every character outside ``[A-Za-z0-9_]`` turned into ``_``."""
        return re.sub(r"[^A-Za-z0-9_]", "_", self.name or self.id)


def param_concept_code(spec: ParamSpec) -> str:
    """The dictionary concept of a parameter: ``param_<owner>_<name>`` of its declaration."""
    return f"param_{spec.owner}_{spec.declared_name}"


def _merge(result: Dict[str, ParamSpec], spec: ParamSpec, where: str, deeper: bool) -> None:
    """Add ``spec`` to a page's parameters, checking a same-name entry agrees with it.

    Args:
        result: The page's parameters being collected.
        spec: The entry to add.
        where: Context for the conflict message.
        deeper: ``spec`` comes from a called page. The deepest declaration carries the
            type, options and default (§3.3), so it replaces an entry from this page.

    Raises:
        TriccParamError: ``E_PARAM_CONFLICT`` when the two entries differ in type or options.
    """
    current = result.get(spec.name)
    if current is None:
        result[spec.name] = spec
        return
    if current.signature() != spec.signature():
        raise TriccParamError(
            E_PARAM_CONFLICT,
            f"parameter {spec.name!r} is {current.type}{current.options or ''} in {current.owner} "
            f"and {spec.type}{spec.options or ''} in {spec.owner} ({where})",
        )
    if deeper:
        result[spec.name] = spec


def compute_effective(
    templates: Dict[str, Template], resolve: Callable[[CallSite], Optional[str]]
) -> Dict[str, Dict[str, ParamSpec]]:
    """Compute every page's effective parameters (§3.3).

    A page's effective parameters are its declarations, plus, for each page it calls,
    the callee's effective parameters that the call does not bind:

    - not in the call's ``args``: the parameter goes up unchanged (it is inherited);
    - bound by a literal: it stops at this call;
    - bound by ``{{x}}``: ``x`` becomes a parameter of the caller, with the callee
      parameter's type.

    The result depends on the calls only, never on values, so it is the same whatever
    branches a later pruning removes.

    Args:
        templates: Every page, by id.
        resolve: Maps a call to the id of the page it calls, or None when that page is not
            a template here (a page of another input: it has no parameters to compute).
            May raise for a call to an unknown block.

    Returns:
        ``{page id: {parameter name: ParamSpec}}`` for every template. Computed entries
        carry ``via``, the calls they came up through.

    Raises:
        TriccParamError: ``E_PARAM_UNKNOWN`` for an argument the callee does not have;
            ``E_PARAM_CONFLICT`` for one name with two types along a chain;
            ``E_BLOCK_CYCLE`` when a block uses itself (a goto cycle between activities is
            allowed and simply stops the walk).
    """
    effective: Dict[str, Dict[str, ParamSpec]] = {}
    stack: List[str] = []

    def visit(tid: str) -> Dict[str, ParamSpec]:
        if tid in effective:
            return effective[tid]
        if tid in stack:
            cycle = stack[stack.index(tid):] + [tid]
            if any(templates[t].is_block for t in cycle):
                raise TriccParamError(E_BLOCK_CYCLE, "block calls itself: " + " -> ".join(cycle))
            return {}  # a goto cycle between activities: no parameters flow around it
        stack.append(tid)
        template = templates[tid]
        result: Dict[str, ParamSpec] = {}
        for spec in template.declared.values():
            _merge(result, spec, f"page {tid}", deeper=False)
        for call in template.calls:
            callee = resolve(call)
            if callee is None:
                continue
            below = visit(callee)
            for arg in call.args:
                if arg not in below:
                    raise TriccParamError(
                        E_PARAM_UNKNOWN,
                        f"{call.describe()}: {callee} has no parameter {arg!r}",
                    )
            for name, spec in below.items():
                via = [call.describe()] + list(spec.via)
                if name not in call.args:
                    _merge(result, spec.model_copy(update={"via": via}), call.describe(), deeper=True)
                    continue
                ref = REFERENCE.match(str(call.args[name])) if isinstance(call.args[name], str) else None
                if ref:
                    renamed = spec.model_copy(update={"name": ref.group(1), "via": via})
                    _merge(result, renamed, call.describe(), deeper=True)
        stack.pop()
        effective[tid] = result
        return result

    for tid in templates:
        visit(tid)
    return effective


def compute_static_only(
    templates: Dict[str, Template], resolve: Callable[[CallSite], Optional[str]]
) -> Dict[str, Set[str]]:
    """The parameters of each page that may not receive an expression argument (§18.8 point 1).

    A parameter is static-only on a page when the page uses it where only a fixed value fits
    (``Template.static_used``), or passes it to a page below that needs it fixed: by
    ``{{name}}`` in an argument, or by leaving the argument out (it is then inherited). The
    ``name`` and ``concept`` types are static-only too; ``bind`` checks those by type.

    Args:
        templates: Every page, by id.
        resolve: As for ``compute_effective`` (already checked there).

    Returns:
        ``{page id: parameter names}`` for every template.
    """
    static: Dict[str, Set[str]] = {tid: set(t.static_used) for tid, t in templates.items()}
    callees = {tid: [(call, resolve(call)) for call in t.calls] for tid, t in templates.items()}
    changed = True
    while changed:  # a fixpoint: goto cycles between activities are allowed
        changed = False
        for tid, calls in callees.items():
            for call, callee in calls:
                if callee is None:
                    continue
                for name in static[callee]:
                    if name not in call.args:
                        found = {name}
                    else:
                        arg = call.args[name]
                        ref = REFERENCE.match(arg) if isinstance(arg, str) else None
                        found = {ref.group(1)} if ref else set()
                    if not found <= static[tid]:
                        static[tid] |= found
                        changed = True
    return static


def bind(
    callee_params: Dict[str, ParamSpec],
    args: Dict[str, Any],
    caller_env: Env,
    chain: str,
    static_only: Iterable[str] = (),
    add_dynamic: Optional[Callable[[str, Dict[str, Any], Env], str]] = None,
) -> Env:
    """Bind the parameters of a called page (§3.2).

    Each parameter takes the first value found among:

    1. the call's argument: a literal (a placeholder inside it is rendered as text from
       the caller's environment), ``{{x}}``, the caller's value of ``x``, or an expression
       ``{expression, intent?}`` (dynamic, §18.8 point 1);
    2. the caller's value of the same name (inheritance), unless that value is dynamic: a
       dynamic value is only ever passed on explicitly, by ``{{x}}``;
    3. the parameter's default.

    A value set at the call replaces the inherited one for the callee only: the caller's
    environment is not changed.

    An expression argument is evaluated once, at the use, in the caller's scope:
    ``add_dynamic`` creates that calculate and names it, and the bound value is
    ``{"dynamic": <its name>}``. Passed on to a page below by ``{{x}}``, the same calculate
    is used: it is not evaluated again.

    Args:
        callee_params: The callee's effective parameters (``compute_effective``).
        args: The call's arguments (``CallSite.args``); the intervention's ``args`` for a
            page at the root.
        caller_env: The calling instance's environment; empty at the root.
        chain: The calls from the root to this one, for error messages
            (``intervention > triage > block t-ax in triage``).
        static_only: The callee's parameters that need a fixed value
            (``compute_static_only``).
        add_dynamic: ``(parameter name, argument, caller_env) -> calculate name``: adds the
            calculate of an expression argument to the calling page. None where no
            expression argument is allowed (the intervention's ``args``).

    Returns:
        The callee's environment, one entry per parameter of ``callee_params``. An
        optional parameter nothing binds gets None.

    Raises:
        TriccParamError: ``E_PARAM_REQUIRED`` for a required parameter with no value (the
            message extends ``chain`` with the parameter's ``via``, down to the use that
            needs it); ``E_PARAM_UNKNOWN`` for ``{{x}}`` naming no caller parameter;
            ``E_PARAM_TYPE`` from ``coerce_value``; ``E_ARG_DYNAMIC_STATIC`` for an
            expression argument where none is allowed, or for a parameter that needs a
            fixed value.
    """
    static_only = set(static_only)
    env: Env = {}
    for name, spec in callee_params.items():
        where = f"{chain}: parameter {name!r}"
        value = None
        if name in args:
            arg = args[name]
            ref = REFERENCE.match(arg) if isinstance(arg, str) else None
            if ref:
                if ref.group(1) not in caller_env:
                    raise TriccParamError(E_PARAM_UNKNOWN, f"{where}: {{{{{ref.group(1)}}}}} is not a caller parameter")
                value = caller_env[ref.group(1)][1]
                if value is not None and not is_dynamic(value):
                    value = coerce_value(spec, value, where)
            elif is_expression_arg(arg):
                if add_dynamic is None:
                    raise TriccParamError(
                        E_ARG_DYNAMIC_STATIC, f"{where}: an intervention argument is a fixed value, not an expression"
                    )
                if not str(arg.get("expression") or "").strip():
                    raise TriccParamError(E_PARAM_TYPE, f"{where}: expression argument with no expression")
                _check_dynamic_allowed(spec, static_only, where)
                value = {DYNAMIC: add_dynamic(name, arg, caller_env)}
            else:
                if isinstance(arg, str) and has_placeholder(arg):
                    arg = substitute(arg, caller_env, TEXT, where)
                value = coerce_value(spec, arg, where)
        elif name in caller_env and caller_env[name][1] is not None and not is_dynamic(caller_env[name][1]):
            value = coerce_value(spec, caller_env[name][1], where)
        if is_dynamic(value):
            _check_dynamic_allowed(spec, static_only, where)
        if value is None and spec.default is not None:
            value = spec.default
        if value is None and spec.required:
            needed = " > ".join([chain] + list(spec.via))
            raise TriccParamError(
                E_PARAM_REQUIRED,
                f"{needed}: parameter {name!r} of {spec.owner} is required and has no value",
            )
        env[name] = (spec, value)
    return env


def _check_dynamic_allowed(spec: ParamSpec, static_only: Set[str], where: str) -> None:
    """Refuse a dynamic value for a parameter that shapes the drawing (§18.8 point 1).

    Raises:
        TriccParamError: ``E_ARG_DYNAMIC_STATIC`` for a ``name`` / ``concept`` parameter,
            or one in ``static_only``.
    """
    if spec.type in STATIC_ONLY_TYPES or spec.name in static_only:
        why = f"is of type {spec.type}" if spec.type in STATIC_ONLY_TYPES else "shapes the drawing (a name, a save "
        if spec.type not in STATIC_ONLY_TYPES:
            why += "or a configuration choice uses it)"
        raise TriccParamError(E_ARG_DYNAMIC_STATIC, f"{where}: {spec.name!r} {why}, so it needs a fixed value")


def env_key(env: Env) -> Tuple[Tuple[str, str], ...]:
    """An environment's values as a hashable, order-independent key.

    Two uses of a page with equal keys share one instance (``ParamBuild.instantiate``).
    """
    return tuple(sorted((name, json.dumps(value, sort_keys=True)) for name, (_, value) in env.items()))


def env_suffix(env: Env) -> str:
    """The id suffix of the page instance built with ``env``: ``__p`` + 8 hex digits.

    A digest of ``env_key``, so the same values give the same ids on every build.
    """
    digest = hashlib.sha1(json.dumps(env_key(env)).encode("utf-8")).hexdigest()[:8]
    return f"__p{digest}"


def unreferenced(template: Template, effective: Dict[str, ParamSpec]) -> Iterable[str]:
    """The declared parameters of a page that nothing uses (``W_PARAM_UNREFERENCED``).

    A declaration is used when a placeholder of the page names it, a call's argument
    passes it on (``{{name}}`` or inside a literal), or a page below needs it (the
    effective entry then comes from that page's declaration).

    Args:
        template: The page.
        effective: Its effective parameters (``compute_effective``).

    Yields:
        The unused names, in declaration order.
    """
    fed = set()
    for call in template.calls:
        for arg in call.args.values():
            if is_expression_arg(arg):
                arg = arg.get("expression")
            if isinstance(arg, str):
                fed.update(placeholder_names(arg))
    for name in template.declared:
        needed_below = name in effective and effective[name].owner != template.owner
        if name not in template.used and name not in fed and not needed_below:
            yield name
