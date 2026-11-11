"""Build the pages of an input: one copy of each page per distinct set of parameter values.

Shared by the YAML and draw.io inputs (feature/20261111-block-params-and-start-node.md §3,
§5, §11). Every page goes through here, parameterized or not: a page without parameters gets
one copy identical to the original (same ids), so outputs do not change.

An input strategy gives:

- ``templates``: every page read as a ``Template`` (raw source, declared parameters, calls);
- ``resolve(call)``: the template id a ``block`` / ``goto`` call targets, or None when the
  target is not a template of this input (it is then linked as before);
- ``render(template, env, new_id)``: the page's source with its placeholders rendered from
  ``env`` and its ids made unique for ``new_id``, plus its calls as ``[(CallSite,
  set_link)]``; ``set_link(id)`` points that call at the instance it must use;
- ``build(template, rendered)``: turn a rendered source into a page of the project (the
  strategy's normal page build);
- ``add_calculate(rendered, call, name, expression, label)`` (optional): add to a rendered
  page the calculate holding an expression argument of one of its calls (§18.8 point 1).

``ParamBuild.run`` then computes the effective parameters, binds the intervention ``args`` at
the root pages and each call's ``args`` below, builds every instance once, and registers the
parameter concepts. Around the build of each instance it also gives the use's concrete
concepts from the abstract ones (§18.8 point 2), makes a block's private fields private
(§18.8 point 3) and refuses stored data inside a block (§18.1, §18.8 decisions). The models
and rules it uses are in ``tricc_oo.models.params``.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import uuid
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from tricc_oo.models.params import (
    CONCEPT_DATA_TYPES,
    E_ARG_DYNAMIC_STATIC,
    E_BLOCK_PRIVATE,
    E_BLOCK_SCOPE,
    E_PARAM_UNKNOWN,
    EXPRESSION,
    PRIMITIVE_TYPES,
    TEXT,
    W_PARAM_UNREFERENCED,
    CallSite,
    Env,
    ParamSpec,
    Template,
    TriccParamError,
    bind,
    compute_effective,
    compute_static_only,
    env_key,
    env_suffix,
    is_dynamic,
    is_expression_arg,
    param_concept_code,
    PLACEHOLDER,
    render_value,
    substitute,
    unreferenced,
)

logger = logging.getLogger("default")

#: key of the calculate dictionary when the project has none (draw.io's name for it)
CALCULATE_SYSTEM = "calculate"

#: a call of a rendered page, and the setter pointing it at the instance it must use
RenderedCall = Tuple[CallSite, Callable[[str], None]]

#: node attributes holding a parsed expression (references are read and renamed there)
EXPRESSION_ATTRS = (
    "relevance", "expression", "expression_reference", "reference", "constraint", "applicability",
    "trigger", "calculate",
)
#: concept properties that make a concept abstract; not copied to its concrete concepts
ABSTRACT_PROPERTIES = ("notSelectable", "kind", "owner")


def _digest(text: str, length: int = 8) -> str:
    """A short stable hex digest of ``text``."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def _references(value) -> Iterable[Any]:
    """Every ``TriccReference`` inside a node attribute value (an operation, a list, a reference)."""
    from tricc_oo.models.base import TriccOperation, TriccReference

    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, TriccReference):
            yield item
        elif isinstance(item, TriccOperation):
            pending.extend(item.reference or [])
        elif isinstance(item, (list, tuple)):
            pending.extend(item)


def _rename_references(value, renamed: Dict[str, str]) -> Tuple[Any, bool]:
    """``value`` with each ``TriccReference`` to a key of ``renamed`` replaced by one to its value.

    References are replaced, never changed in place: an operation keeps them in an
    ``OrderedSet``, hashed by name.

    Returns:
        ``(new value, whether anything changed)``; an operation is updated in place.
    """
    from tricc_oo.models.base import TriccOperation, TriccReference

    if isinstance(value, TriccReference):
        return (TriccReference(renamed[value.value]), True) if value.value in renamed else (value, False)
    if isinstance(value, list):
        items = [_rename_references(item, renamed) for item in value]
        return ([item for item, _ in items], True) if any(c for _, c in items) else (value, False)
    if isinstance(value, TriccOperation):
        items = [_rename_references(item, renamed) for item in value.reference or []]
        if not any(c for _, c in items):
            return value, False
        value.reference = [item for item, _ in items]
        value._invalidate_identity_cache()
        return value, True
    return value, False


def _expression_values(node) -> Iterable[Tuple[str, Any]]:
    """``(attribute, value)`` of each expression attribute of a node and of its options."""
    options = getattr(node, "options", None)
    for owner in [node] + (list(options.values()) if isinstance(options, dict) else []):
        for attr in EXPRESSION_ATTRS:
            value = getattr(owner, attr, None)
            if value is not None and not isinstance(value, str):
                yield attr, value


def _matches(key, code_system, ref: str) -> bool:
    """Whether ``ref`` names ``code_system`` by its project key, url, id or name."""
    return ref in (key, getattr(code_system, "url", None), getattr(code_system, "id", None),
                   getattr(code_system, "name", None))


def calculate_code_system_key(codesystems, configured: Optional[str] = None) -> str:
    """Find the calculate dictionary, where parameter concepts go.

    The first found of:

    1. the CodeSystem tagged ``meta.tag`` ``codesystem-role|calculate``
       (``datadictionnary.CODESYSTEM_ROLE_SYSTEM``);
    2. ``configured``, tricc.yaml ``calculate_code_system`` (url, id or name);
    3. one whose key, id or name is ``calculate`` (draw.io) or ends in ``-calculate`` (the
       frontend's ``<default>-calculate``);
    4. ``calculate``, created on first use (``init_codesystem`` tags it).

    Several tagged CodeSystems (the first by url is used, as in the frontend), or a
    ``configured`` one that is not the tagged one or is not a project CodeSystem, are warnings.

    Args:
        codesystems: The project CodeSystems, by key (``TriccIntervention.code_systems``).
        configured: tricc.yaml ``calculate_code_system``, if any.

    Returns:
        The key in ``codesystems``, or ``calculate`` when none fits (``add_concept`` then
        creates it).
    """
    from tricc_oo.converters.datadictionnary import CALCULATE_ROLE, has_role

    # several tagged: the first by url, as the frontend picks it
    tagged = sorted(
        (key for key, cs in codesystems.items() if has_role(cs, CALCULATE_ROLE)),
        key=lambda k: str(getattr(codesystems[k], "url", None) or k),
    )
    if len(tagged) > 1:
        logger.warning(f"several CodeSystems are tagged as the calculate dictionary: {tagged}; using {tagged[0]}")
    if configured:
        named = next((key for key, cs in codesystems.items() if _matches(key, cs, configured)), None)
        if named is None:
            logger.warning(f"calculate_code_system {configured!r} is not a project CodeSystem")
        elif tagged and named != tagged[0]:
            logger.warning(f"calculate_code_system {configured!r} differs from the tagged CodeSystem {tagged[0]!r}")
        if not tagged and named is not None:
            return named
    if tagged:
        return tagged[0]
    for key, cs in codesystems.items():
        for label in (key, getattr(cs, "id", None), getattr(cs, "name", None)):
            if label and (label == CALCULATE_SYSTEM or str(label).endswith("-calculate")):
                return key
    return CALCULATE_SYSTEM


def _text(value: Any, lang: str) -> Optional[str]:
    """A display text in ``lang``: ``value`` itself, or its ``lang`` (else first) entry of a
    ``{lang: text}`` dict."""
    if isinstance(value, dict):
        return value.get(lang) or next(iter(value.values()), None)
    return value


def register_param_concepts(templates: Dict[str, Template], project) -> None:
    """Add the parameter concepts (§5) the project dictionary lacks.

    One concept per declared primitive parameter (``PRIMITIVE_TYPES``), code
    ``param_<owner>_<name>``, in the calculate dictionary (``calculate_code_system_key``):

    - display: the declaration's ``label``, else its name; definition: its ``description``;
    - properties ``kind`` = ``parameter``, ``dataType`` (boolean / decimal / string / coded),
      ``option`` per choice option, ``default`` when there is one.

    The project dictionary wins: a concept that already exists, in any project CodeSystem, is
    left as it is (the frontend writes them; the library only fills in for projects without,
    such as draw.io-only ones). Computed parameters reuse their declaration's concept.

    Args:
        templates: Every page of the input, by id.
        project: The ``TriccIntervention``; its ``code_systems`` are updated in place.
    """
    from fhir.resources.codesystem import CodeSystemConceptProperty

    from tricc_oo.converters.datadictionnary import add_concept, find_concept

    lang = getattr(project, "lang_code", None) or "en"
    for template in templates.values():
        for spec in template.declared.values():
            if spec.type not in PRIMITIVE_TYPES:
                continue
            code = param_concept_code(spec)
            if find_concept(project.code_systems, code) is not None:
                continue
            system = calculate_code_system_key(
                project.code_systems, getattr(project, "calculate_code_system", None)
            )
            concept = add_concept(project.code_systems, system, code, _text(spec.label, lang) or spec.name, {})
            definition = _text(spec.description, lang)
            if definition:
                concept.definition = definition
            props = [
                CodeSystemConceptProperty(code="kind", valueCode="parameter"),
                CodeSystemConceptProperty(code="dataType", valueCode=CONCEPT_DATA_TYPES[spec.type]),
            ]
            props += [CodeSystemConceptProperty(code="option", valueCode=o) for o in spec.options or []]
            if spec.default is not None:
                default = spec.default
                text = ("true" if default else "false") if isinstance(default, bool) else str(default)
                props.append(CodeSystemConceptProperty(code="default", valueString=text))
            concept.property = props
            logger.debug(f"parameter concept {code} added to {system}")


def render_concept_text(text: Any, env: Env, language: Optional[str], project) -> Any:
    """Render the placeholders of an abstract concept's text for one use (§18.8 point 2).

    As a text attribute (§4), except a ``choice`` value: the label, in ``language``, of
    the concept coded as the option, else the option code.

    Args:
        text: A display, definition or designation value.
        env: The use's environment.
        language: The text's language (None: the project default).
        project: The ``TriccIntervention`` (its ``code_systems`` hold the option concepts).

    Returns:
        The rendered text; anything that is not a string is returned as is.
    """
    from tricc_oo.converters.datadictionnary import concept_text, find_concept

    if not isinstance(text, str):
        return text
    default = getattr(project, "lang_code", None)

    def one(match):
        name, raw = match.group(1), bool(match.group(2))
        if name not in env:
            return match.group(0)  # not a parameter of this use: kept as written
        spec, value = env[name]
        if spec.type == "choice" and value is not None and not is_dynamic(value):
            option = find_concept(project.code_systems, value)
            label = concept_text(option, "display", language or default, default) if option is not None else None
            return label or str(value)
        return render_value(spec, value, TEXT, raw, f"concept text {text!r}")

    return PLACEHOLDER.sub(one, text)


def concretize_concepts(template: Template, env: Env, project) -> List[str]:
    """Give one use the concrete concepts of its abstract ones (§18.8 point 2).

    For each templated node name of ``template`` (``fever_{{site}}``) that the project
    dictionary has as an abstract concept (``kind = template``), add ``fever_axillary`` to
    the same CodeSystem: a copy of the abstract concept with its texts rendered for ``env``
    (display, definition, each designation in its language) and without the abstract
    properties (``notSelectable``, ``kind``, ``owner``). A concrete concept already in the
    dictionary wins: it is left as it is.

    Args:
        template: The page being built.
        env: The instance's environment.
        project: The ``TriccIntervention``; its ``code_systems`` are updated in place.

    Returns:
        The codes of the concepts added.
    """
    from tricc_oo.converters.datadictionnary import UUID_NAMESPACE, find_concept, is_template_concept

    added = []
    for raw_name in template.templated_names:
        abstract, system = None, None
        for key, code_system in project.code_systems.items():
            abstract = next((c for c in code_system.concept or [] if c.code == raw_name), None)
            if abstract is not None:
                system = key
                break
        if abstract is None or not is_template_concept(abstract):
            continue
        code = substitute(raw_name, env, TEXT, f"{template.id}: name {raw_name!r}")
        if find_concept(project.code_systems, code) is not None:
            continue
        concrete = copy.deepcopy(abstract)
        concrete.code = code
        concrete.id = str(uuid.uuid5(UUID_NAMESPACE, code))
        concrete.display = render_concept_text(abstract.display, env, None, project)
        concrete.definition = render_concept_text(abstract.definition, env, None, project)
        for designation in concrete.designation or []:
            designation.value = render_concept_text(designation.value, env, designation.language, project)
        concrete.property = [p for p in concrete.property or [] if p.code not in ABSTRACT_PROPERTIES] or None
        project.code_systems[system].concept.append(concrete)
        added.append(code)
        logger.debug(f"concept {code} built from abstract concept {raw_name} in {system}")
    return added


class ParamBuild:
    """Build every page instance of one input, once each.

    Instances are keyed by ``(page id, env_key(values))``: two uses of a page with the same
    values share one instance. Ids:

    - an activity's instance with the values its intervention gives (its *base* instance)
      keeps the page id, so a page without parameters is built exactly as before;
    - any other instance is the page id plus ``env_suffix`` (``__p`` + a stable digest);
    - a block without parameters keeps its id too. A block is never built on its own: only
      when a call uses it (linking then inlines one copy per use);
    - a block with private fields (§18.8 point 3) gets one instance per use (``__u`` + a
      digest of its values and of the use), so each use's private fields are its own.

    Attributes:
        templates: Every page, by id.
        resolve: See the module docstring.
        project: The ``TriccIntervention`` being loaded (its ``config`` gives the
            intervention ``args``).
        render: See the module docstring.
        build: See the module docstring.
        add_calculate: See the module docstring; None when the input has no expression
            arguments.
        effective: Each page's effective parameters, set by ``run``.
        static_only: Each page's parameters that need a fixed value, set by ``run``.
        base_env: Each activity's values from its intervention, or None when only its
            callers can bind it (a required parameter the intervention does not give).
        private: Rendered name of each private field (before its per-use suffix) to the
            block instance holding it, for ``E_BLOCK_PRIVATE``.
    """

    def __init__(
        self,
        templates: Dict[str, Template],
        resolve: Callable[[CallSite], Optional[str]],
        project,
        render: Callable[[Template, Env, str], Tuple[Any, List[RenderedCall]]],
        build: Callable[[Template, Any], None],
        add_calculate: Optional[Callable[[Any, CallSite, str, str, str], None]] = None,
    ):
        self.templates = templates
        self.resolve = resolve
        self.project = project
        self.render = render
        self.build = build
        self.add_calculate = add_calculate
        self.effective: Dict[str, Dict[str, ParamSpec]] = {}
        self.static_only: Dict[str, Set[str]] = {}
        self.base_env: Dict[str, Optional[Env]] = {}
        self.private: Dict[str, str] = {}
        # (page id, env key, use) -> instance id
        self._memo: Dict[Tuple[str, Any, Optional[str]], str] = {}
        # instances waiting to be rendered and built: (page id, env, instance id, chain)
        self._queue: List[Tuple[str, Env, str, List[str]]] = []

    def run(self) -> None:
        """Build every page instance of the input.

        1. Compute the effective and the static-only parameters; check block ``outputs``;
           warn on declarations nothing uses.
        2. Check the intervention ``args``: each must reach a parameter of some activity,
           and be a fixed value.
        3. Bind each activity's base values from the intervention ``args`` and defaults.
           An activity whose required parameter only its callers set waits for them.
        4. Build the base instances in page order, then, breadth first, every instance
           their calls need: rendering a page gives its calls, each call's values are
           bound from the calling instance (``bind``; an expression argument adds its
           calculate to the calling page) and the call is pointed at its callee's instance
           (queued on first use). Each instance gets its concrete concepts before it is
           built; a block instance is checked for stored data and has its private fields
           renamed after.
        5. Refuse references to private fields from outside their block; register the
           parameter concepts.

        Raises:
            TriccParamError: From ``compute_effective`` and ``bind`` (conflicts, unknown or
                missing values, wrong types, block cycles, expression arguments where a
                fixed value is needed), from the strategy's ``render`` (placeholders),
                ``E_PARAM_UNKNOWN`` for an intervention argument that no activity has,
                ``E_OUTPUT_UNKNOWN``, ``E_BLOCK_SCOPE`` and ``E_BLOCK_PRIVATE``.
        """
        self.effective = compute_effective(self.templates, self.resolve)
        self.static_only = compute_static_only(self.templates, self.resolve)
        for tid, template in self.templates.items():
            template.check_outputs()
            for name in unreferenced(template, self.effective[tid]):
                logger.warning(f"{W_PARAM_UNREFERENCED}: page {tid} declares {name!r} but nothing uses it")
        config = getattr(self.project, "config", None)
        args = dict(getattr(config, "args", None) or {})
        roots = [tid for tid, t in self.templates.items() if not t.is_block]
        known = {name for tid in roots for name in self.effective[tid]}
        for name, value in args.items():
            if name not in known:
                raise TriccParamError(
                    E_PARAM_UNKNOWN,
                    f"intervention {getattr(config, 'id', '?')}: argument {name!r} reaches no activity parameter",
                )
            if is_expression_arg(value):
                raise TriccParamError(
                    E_ARG_DYNAMIC_STATIC,
                    f"intervention {getattr(config, 'id', '?')}: argument {name!r} is an expression; an "
                    "intervention's arguments are fixed values (nothing is collected yet)",
                )
        called = {self.resolve(c) for t in self.templates.values() for c in t.calls}
        for tid in roots:
            params = self.effective[tid]
            try:
                root_args = {k: v for k, v in args.items() if k in params}
                self.base_env[tid] = bind(params, root_args, {}, f"intervention > {tid}", self.static_only[tid])
            except TriccParamError:
                if tid not in called:
                    raise
                # bound only by its callers
                self.base_env[tid] = None
        for tid in roots:
            if self.base_env[tid] is not None:
                self.instantiate(tid, self.base_env[tid], [tid])
        while self._queue:
            tid, env, new_id, chain = self._queue.pop(0)
            template = self.templates[tid]
            rendered, calls = self.render(template, env, new_id)
            for call, set_link in calls:
                callee = self.resolve(call)
                if callee is None:
                    continue
                where = " > ".join(chain + [call.describe()])
                callee_env = bind(
                    self.effective[callee], call.args, env, where, self.static_only[callee],
                    self._dynamic_adder(rendered, call, new_id, where),
                )
                use = f"{new_id}/{call.node_id}" if self.templates[callee].private_fields() else None
                callee_id = self.instantiate(callee, callee_env, chain + [call.describe()], use)
                set_link(callee_id)
            concretize_concepts(template, env, self.project)
            before = self._concept_codes()
            self.build(template, rendered)
            page = self.project.pages.get(new_id)
            if template.is_block and page is not None:
                check_block_scope(page, " > ".join(chain))
                self._make_private(template, env, page, before)
        self._check_private_references()
        register_param_concepts(self.templates, self.project)

    def instantiate(self, tid: str, env: Env, chain: List[str], use: Optional[str] = None) -> str:
        """The id of page ``tid``'s instance for ``env``; queued for building on first use.

        The id is known before the instance is built, so a call can point at it right away
        (and a goto cycle between activities ends on the memo instead of looping).

        Args:
            tid: The page id.
            env: The instance's bound values.
            chain: The calls from the root to this instance, for later error messages.
            use: For a block with private fields, the use (calling instance and node):
                each use gets its own instance.

        Returns:
            The instance id (see the class docstring for when it is the page id itself).
        """
        key = (tid, env_key(env), use)
        if key in self._memo:
            return self._memo[key]
        template = self.templates[tid]
        base = self.base_env.get(tid)
        if use is not None:
            suffix = "__u" + _digest(repr((env_key(env), use)))
        elif template.is_block:
            suffix = env_suffix(env) if self.effective[tid] else ""
        else:
            suffix = "" if base is not None and env_key(base) == env_key(env) else env_suffix(env)
        new_id = tid + suffix
        self._memo[key] = new_id
        self._queue.append((tid, env, new_id, chain))
        return new_id

    # ------------------------------------------------------------------
    # Expression arguments (§18.8 point 1)
    # ------------------------------------------------------------------
    def _dynamic_adder(self, rendered, call: CallSite, caller_id: str, where: str):
        """The ``add_dynamic`` callback of ``bind`` for one call of a rendered page.

        It renders the argument's expression in the caller's environment, names its
        calculate ``arg_<parameter>_<digest of the use>`` and has the strategy add it to the
        calling page, where it is evaluated once, at the use.
        """

        def add(name: str, arg: Dict[str, Any], caller_env: Env) -> str:
            if self.add_calculate is None:
                raise TriccParamError(E_ARG_DYNAMIC_STATIC, f"{where}: this input has no expression arguments")
            expression = substitute(str(arg["expression"]), caller_env, EXPRESSION, f"{where}: parameter {name!r}")
            calc_name = f"arg_{name}_{_digest(f'{caller_id}/{call.node_id}/{name}')}"
            lang = getattr(self.project, "lang_code", None) or "en"
            label = _text(arg.get("intent"), lang) or name
            self.add_calculate(rendered, call, calc_name, expression, label)
            return calc_name

        return add

    # ------------------------------------------------------------------
    # Private fields (§18.8 point 3)
    # ------------------------------------------------------------------
    def _concept_codes(self) -> Set[Tuple[str, str]]:
        """``(CodeSystem key, code)`` of every concept of the project now."""
        return {(key, c.code) for key, cs in self.project.code_systems.items() for c in cs.concept or []}

    def _make_private(self, template: Template, env: Env, page, before: Set[Tuple[str, str]]) -> None:
        """Give a block instance's private fields their per-use name, and no concept.

        A private field ``score`` becomes ``score_<digest of the instance>``, and every
        reference to it inside the instance follows. The concepts the build added for the
        private names are removed (a project concept is kept).

        Args:
            template: The block.
            env: The instance's environment.
            page: The built instance.
            before: ``_concept_codes()`` before the build.
        """
        privates = {substitute(n, env, TEXT, f"{template.id}: output {n!r}") for n in template.private_fields()}
        if not privates:
            return
        renamed = {name: f"{name}_{_digest(page.id, 6)}" for name in privates}
        for node in page.nodes.values():
            if getattr(node, "name", None) in renamed:
                node.name = renamed[node.name]
            options = getattr(node, "options", None)
            for owner in [node] + (list(options.values()) if isinstance(options, dict) else []):
                for attr in EXPRESSION_ATTRS:
                    value = getattr(owner, attr, None)
                    if value is not None and not isinstance(value, str):
                        new_value, changed = _rename_references(value, renamed)
                        if changed:
                            setattr(owner, attr, new_value)
        for name in privates:
            self.private[name] = page.id
        for key, code_system in self.project.code_systems.items():
            if code_system.concept:
                code_system.concept = [
                    c for c in code_system.concept if c.code not in privates or (key, c.code) in before
                ]

    def _check_private_references(self) -> None:
        """Refuse a reference, from outside its block, to a private field.

        Raises:
            TriccParamError: ``E_BLOCK_PRIVATE`` naming the reference and the block.
        """
        if not self.private:
            return
        names = {getattr(n, "name", None) for page in self.project.pages.values() for n in page.nodes.values()}
        for page in self.project.pages.values():
            for node in page.nodes.values():
                for _, value in _expression_values(node):
                    for ref in _references(value):
                        if ref.value in self.private and ref.value not in names:
                            raise TriccParamError(
                                E_BLOCK_PRIVATE,
                                f"{page.id}/{node.id} reads {ref.value!r}, which is internal to block "
                                f"{self.private[ref.value]}: add it to the block's outputs to use it",
                            )


def check_block_scope(page, where: str) -> None:
    """Refuse stored data inside a block instance (§18.1, §18.8 decisions).

    A block reads no stored data: a ``populate`` node, or an expression calling a function of
    ``converters/cql/stored_data_functions.json`` (``AgeInDays()``, the encounter, history
    and context readers), is an error. ``Today()`` / ``Now()`` are allowed. The value comes
    in as an expression argument, evaluated at the use.

    Args:
        page: The built block instance.
        where: The calls that reached it, for the message.

    Raises:
        TriccParamError: ``E_BLOCK_SCOPE`` naming the node.
    """
    from tricc_oo.models.base import TriccOperation
    from tricc_oo.models.calculate import TriccNodePopulate

    for node in page.nodes.values():
        label = f"{page.id}/{getattr(node, 'name', None) or node.id}"
        if isinstance(node, TriccNodePopulate):
            raise TriccParamError(
                E_BLOCK_SCOPE,
                f"{where}: {label} reads stored data (populate); "
                "pass the value in as an argument calculated at the use",
            )
        for attr, value in _expression_values(node):
            if isinstance(value, TriccOperation) and value.get_stored_data():
                raise TriccParamError(
                    E_BLOCK_SCOPE,
                    f"{where}: {label} {attr} reads stored data; "
                    "pass the value in as an argument calculated at the use",
                )
