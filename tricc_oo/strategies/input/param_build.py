"""Build the pages of an input: one copy of each page per distinct set of parameter values.

Shared by the YAML and draw.io inputs (feature/20261102-block-params-and-start-node.md §3,
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
  strategy's normal page build).

``ParamBuild.run`` then computes the effective parameters, binds the intervention ``args`` at
the root pages and each call's ``args`` below, builds every instance once, and registers the
parameter concepts. The models and rules it uses are in ``tricc_oo.models.params``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from tricc_oo.models.params import (
    CONCEPT_DATA_TYPES,
    E_PARAM_UNKNOWN,
    PRIMITIVE_TYPES,
    W_PARAM_UNREFERENCED,
    CallSite,
    Env,
    ParamSpec,
    Template,
    TriccParamError,
    bind,
    compute_effective,
    env_key,
    env_suffix,
    param_concept_code,
    unreferenced,
)

logger = logging.getLogger("default")

#: key of the calculate dictionary when the project has none (draw.io's name for it)
CALCULATE_SYSTEM = "calculate"

#: a call of a rendered page, and the setter pointing it at the instance it must use
RenderedCall = Tuple[CallSite, Callable[[str], None]]


def _matches(key, code_system, ref: str) -> bool:
    """Whether ``ref`` names ``code_system`` by its project key, url, id or name."""
    return ref in (key, getattr(code_system, "url", None), getattr(code_system, "id", None),
                   getattr(code_system, "name", None))


def role_code_system_key(codesystems, role: str, configured: Optional[str] = None,
                         setting: Optional[str] = None) -> Optional[str]:
    """Find the project CodeSystem playing ``role`` (``calculate``, ``retrieve``).

    The first found of:

    1. the CodeSystem tagged ``meta.tag`` ``codesystem-role|<role>``
       (``datadictionnary.CODESYSTEM_ROLE_SYSTEM``);
    2. ``configured``, the tricc.yaml ``<role>_code_system`` (url, id or name);
    3. one whose key, id or name is ``<role>`` (draw.io) or ends in ``-<role>`` (the
       frontend's ``<default>-<role>``).

    Several tagged CodeSystems (the first by url is used, as in the frontend), or a
    ``configured`` one that is not the tagged one or is not a project CodeSystem, are warnings.

    Args:
        codesystems: The project CodeSystems, by key (``TriccIntervention.code_systems``).
        role: The role tag code.
        configured: The tricc.yaml setting, if any.
        setting: The setting name, for messages (default ``<role>_code_system``).

    Returns:
        The key in ``codesystems``, or None when none fits.
    """
    from tricc_oo.converters.datadictionnary import has_role

    setting = setting or f"{role}_code_system"
    # several tagged: the first by url, as the frontend picks it
    tagged = sorted(
        (key for key, cs in codesystems.items() if has_role(cs, role)),
        key=lambda k: str(getattr(codesystems[k], "url", None) or k),
    )
    if len(tagged) > 1:
        logger.warning(f"several CodeSystems are tagged as the {role} dictionary: {tagged}; using {tagged[0]}")
    if configured:
        named = next((key for key, cs in codesystems.items() if _matches(key, cs, configured)), None)
        if named is None:
            logger.warning(f"{setting} {configured!r} is not a project CodeSystem")
        elif tagged and named != tagged[0]:
            logger.warning(f"{setting} {configured!r} differs from the tagged CodeSystem {tagged[0]!r}")
        if not tagged and named is not None:
            return named
    if tagged:
        return tagged[0]
    for key, cs in codesystems.items():
        for label in (key, getattr(cs, "id", None), getattr(cs, "name", None)):
            if label and (label == role or str(label).endswith(f"-{role}")):
                return key
    return None


def calculate_code_system_key(codesystems, configured: Optional[str] = None) -> str:
    """Find the calculate dictionary, where parameter concepts go.

    ``role_code_system_key`` with role ``calculate``; when none fits, ``calculate``, created
    on first use (``init_codesystem`` tags it).

    Args:
        codesystems: The project CodeSystems, by key (``TriccIntervention.code_systems``).
        configured: tricc.yaml ``calculate_code_system``, if any.

    Returns:
        The key in ``codesystems``, or ``calculate`` when none fits (``add_concept`` then
        creates it).
    """
    from tricc_oo.converters.datadictionnary import CALCULATE_ROLE

    return role_code_system_key(codesystems, CALCULATE_ROLE, configured) or CALCULATE_SYSTEM


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


class ParamBuild:
    """Build every page instance of one input, once each.

    Instances are keyed by ``(page id, env_key(values))``: two uses of a page with the same
    values share one instance. Ids:

    - an activity's instance with the values its intervention gives (its *base* instance)
      keeps the page id, so a page without parameters is built exactly as before;
    - any other instance is the page id plus ``env_suffix`` (``__p`` + a stable digest);
    - a block without parameters keeps its id too. A block is never built on its own: only
      when a call uses it (linking then inlines one copy per use).

    Attributes:
        templates: Every page, by id.
        resolve: See the module docstring.
        project: The ``TriccIntervention`` being loaded (its ``config`` gives the
            intervention ``args``).
        render: See the module docstring.
        build: See the module docstring.
        effective: Each page's effective parameters, set by ``run``.
        base_env: Each activity's values from its intervention, or None when only its
            callers can bind it (a required parameter the intervention does not give).
    """

    def __init__(
        self,
        templates: Dict[str, Template],
        resolve: Callable[[CallSite], Optional[str]],
        project,
        render: Callable[[Template, Env, str], Tuple[Any, List[RenderedCall]]],
        build: Callable[[Template, Any], None],
    ):
        self.templates = templates
        self.resolve = resolve
        self.project = project
        self.render = render
        self.build = build
        self.effective: Dict[str, Dict[str, ParamSpec]] = {}
        self.base_env: Dict[str, Optional[Env]] = {}
        # (page id, env key) -> instance id
        self._memo: Dict[Tuple[str, Any], str] = {}
        # instances waiting to be rendered and built: (page id, env, instance id, chain)
        self._queue: List[Tuple[str, Env, str, List[str]]] = []

    def run(self) -> None:
        """Build every page instance of the input.

        1. Compute the effective parameters; warn on declarations nothing uses.
        2. Check the intervention ``args``: each must reach a parameter of some activity.
        3. Bind each activity's base values from the intervention ``args`` and defaults.
           An activity whose required parameter only its callers set waits for them.
        4. Build the base instances in page order, then, breadth first, every instance
           their calls need: rendering a page gives its calls, each call's values are
           bound from the calling instance (``bind``) and the call is pointed at its
           callee's instance (queued on first use).
        5. Register the parameter concepts.

        Raises:
            TriccParamError: From ``compute_effective`` and ``bind`` (conflicts, unknown or
                missing values, wrong types, block cycles), from the strategy's ``render``
                (placeholders), and ``E_PARAM_UNKNOWN`` for an intervention argument that
                no activity has.
        """
        self.effective = compute_effective(self.templates, self.resolve)
        for tid, template in self.templates.items():
            for name in unreferenced(template, self.effective[tid]):
                logger.warning(f"{W_PARAM_UNREFERENCED}: page {tid} declares {name!r} but nothing uses it")
        config = getattr(self.project, "config", None)
        args = dict(getattr(config, "args", None) or {})
        roots = [tid for tid, t in self.templates.items() if not t.is_block]
        known = {name for tid in roots for name in self.effective[tid]}
        for name in args:
            if name not in known:
                raise TriccParamError(
                    E_PARAM_UNKNOWN,
                    f"intervention {getattr(config, 'id', '?')}: argument {name!r} reaches no activity parameter",
                )
        called = {self.resolve(c) for t in self.templates.values() for c in t.calls}
        for tid in roots:
            params = self.effective[tid]
            try:
                root_args = {k: v for k, v in args.items() if k in params}
                self.base_env[tid] = bind(params, root_args, {}, f"intervention > {tid}")
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
                callee_env = bind(self.effective[callee], call.args, env, where)
                callee_id = self.instantiate(callee, callee_env, chain + [call.describe()])
                set_link(callee_id)
            self.build(template, rendered)
        register_param_concepts(self.templates, self.project)

    def instantiate(self, tid: str, env: Env, chain: List[str]) -> str:
        """The id of page ``tid``'s instance for ``env``; queued for building on first use.

        The id is known before the instance is built, so a call can point at it right away
        (and a goto cycle between activities ends on the memo instead of looping).

        Args:
            tid: The page id.
            env: The instance's bound values.
            chain: The calls from the root to this instance, for later error messages.

        Returns:
            The instance id (see the class docstring for when it is the page id itself).
        """
        key = (tid, env_key(env))
        if key in self._memo:
            return self._memo[key]
        template = self.templates[tid]
        base = self.base_env.get(tid)
        if template.is_block:
            suffix = env_suffix(env) if self.effective[tid] else ""
        else:
            suffix = "" if base is not None and env_key(base) == env_key(env) else env_suffix(env)
        new_id = tid + suffix
        self._memo[key] = new_id
        self._queue.append((tid, env, new_id, chain))
        return new_id
