"""
YAML Input Strategy for TRICC.

This strategy allows loading a simplified, human-readable YAML representation
of activities instead of draw.io files. It is primarily intended for:

- Focused unit and regression testing of core transformations
  (inheritance/versioning, calculate loading, relevance propagation, etc.)
- Creating minimal reproducible examples for bugs or new features

It is **not** intended as a replacement for draw.io clinical authoring.

The format supports one or more activities per file. Each activity declares
nodes (with options for selects) and edges. Expressions are provided as strings
and parsed using the existing expression infrastructure.
"""

import copy
import logging
from typing import Any, Dict, List, Optional, Type, Union

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, model_validator

from tricc_oo.strategies.input.base_input_strategy import BaseInputStrategy
from tricc_oo.strategies.input.param_build import ParamBuild
from tricc_oo.models.params import (
    E_ABSTRACT_SELECTED,
    E_PARAM_CONFLICT,
    E_PARAM_PLACEHOLDER,
    E_PARAM_TYPE,
    E_PARAM_UNKNOWN,
    EXPRESSION,
    TEXT,
    CallSite,
    ParamSpec,
    Template,
    TriccParamError,
    has_placeholder,
    literal_arg_names,
    placeholder_names,
    raw_placeholder_names,
    substitute,
)
from tricc_oo.converters.utils import generate_id
from tricc_oo.converters.datadictionnary import concept_text, find_concept, is_template_concept
from tricc_oo.converters.xml_to_tricc import (
    _get_name,
    assign_rhombus_path,
    parse_expression,
    load_expressions,
    process_edge_label,
    propagate_activity_repeat,
    shield_required,
)
from tricc_oo.visitors.tricc import get_select_yes_no_options, set_prev_next_node
from tricc_oo.visitors.utils import PROCESSES
from tricc_oo.strategies.registry import register_input_strategy

# Core models
from tricc_oo.models.tricc import (
    TriccIntervention,
    TriccNodeActivity,
    TriccSegment,
    TriccEdge,
    TriccNodeMainStart,
    node_container_for_root,
    TriccNodeNote,
    TriccNodeSelectOne,
    TriccNodeSelectMultiple,
    TriccNodeSelectYesNo,
    TriccNodeSelectNotAvailable,
    TriccNodeSelectOption,
    TriccNodeInteger,
    TriccNodeDecimal,
    TriccNodeQuantity,
    TriccNodeText,
    TriccNodeGoTo,
    TriccNodeBlock,
)
from tricc_oo.models.base import TriccNodeType

# Nodes defined in calculate.py
from tricc_oo.models.calculate import (
    TriccNodeCalculate,
    TriccNodeRhombus,
    TriccNodeActivityStart,
    TriccNodeBlockStart,
    TriccNodeActivityEnd,
    TriccNodeEnd,
    TriccNodePopulate,
    TriccNodeProposedDiagnosis,
    TriccNodeDiagnosis,
    TriccRhombusMixIn,
)

logger = logging.getLogger("default")


# ---------------------------------------------------------------------------
# YAML Test Format Schema (Pydantic)
# ---------------------------------------------------------------------------

class YamlModel(BaseModel):
    """Unknown keys are ignored, e.g. the frontend's presentation-only ``ui`` blocks
    (geometry, viewport, waypoints), edge ``id`` or ``formatVersion``."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class YamlConceptRef(YamlModel):
    """Link to a project CodeSystem concept; ``system`` is a CodeSystem name, id or url."""
    code: str
    system: Optional[str] = None


# A plain string is a concept code in any project CodeSystem.
ConceptRef = Union[str, YamlConceptRef]


class YamlOption(YamlModel):
    """Option for select_one / select_multiple / select_yesno.

    Without ``label`` the text comes from the option's concept (``concept``, else
    ``name``) in the project terminology. ``name`` defaults to the concept code.
    """
    id: str
    name: Optional[str] = None
    label: Optional[str] = None
    concept: Optional[ConceptRef] = None
    relevance: Optional[str] = None
    # the "none of these" answer, as the draw.io ``is_none`` attribute
    is_none: bool = False


class YamlNode(YamlModel):
    """
    Declarative representation of a TRICC node in YAML.

    Only a subset of fields is supported in the initial implementation.
    Add fields here as needed for more advanced test scenarios.

    ``label`` / ``hint`` / ``help`` left out are read from the node's concept
    (``concept``, else ``name``) in the project terminology (tricc.yaml
    ``terminology``): ``display`` and the ``hint`` / ``help`` designations in the
    default language. Inline text wins.
    """
    id: str
    type: str  # e.g. "integer", "select_one", "calculate", "rhombus", ...
    name: Optional[str] = None
    label: Optional[str] = None
    process: Optional[str] = None
    # bool / 1 / "yes" or a boolean expression string. Shielded before the node is built.
    required: Optional[Union[bool, int, float, str]] = None
    relevance: Optional[str] = None
    calculate: Optional[str] = None          # for calculate nodes
    expression: Optional[str] = None         # for rhombus / some calculates
    reference: Optional[str] = None          # for rhombus / some calculates
    save: Optional[str] = None
    # a string only while a {{placeholder}} is unrendered (templates)
    min: Optional[Union[int, float, str]] = None
    max: Optional[Union[int, float, str]] = None
    options: List[YamlOption] = Field(default_factory=list)
    # For goto / link / block nodes
    link: Optional[str] = None
    # block / goto: parameter values for the called page (literals, {system, code}, "{{ref}}")
    args: Optional[Dict[str, Any]] = None
    # decision node: a configuration choice resolved at build time (static pruning: not yet)
    static: Optional[bool] = None
    instance: Optional[int] = 1
    repeat: Optional[int] = None
    context: Optional[str] = None
    period: Optional[str] = None
    # quantity questions (and populate nodes reading one) carry a unit of measure
    unit: Optional[str] = None
    unit_system: Optional[str] = None
    unit_code: Optional[str] = None
    # populate: FHIR item type of the value being read back (e.g. "quantity")
    data_type: Optional[str] = None
    concept_type: Optional[str] = None
    # start node only. Legacy: names the form only without tricc.yaml interventions
    # (use interventions[].name). ``formId`` accepted too.
    form_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("form_id", "formId"))
    hint: Optional[str] = None
    help: Optional[str] = None
    concept: Optional[ConceptRef] = None
    # proposed_diagnosis / diagnosis. Copied only when the node type's attr list names them.
    severity: Optional[str] = None
    remote_reference: Optional[str] = None
    trigger: Optional[str] = None
    priority: Optional[int] = None


ROOT_TYPES = ("start", "activity_start", "block_start")
# the inputs and calculates of a block: its outputs unless ``outputs`` says otherwise (§18.2)
FIELD_TYPES = (
    "integer", "decimal", "quantity", "text", "date", "select_one", "select_multiple", "select_yesno",
    "calculate", "add", "count", "diagnosis", "proposed_diagnosis",
)
CALL_TYPES = ("block", "goto")
# first names of block_start / block, still read
TYPE_ALIASES = {"snippet_start": "block_start", "snippet": "block"}

# Nodes whose label is not display text (it is the parse context of their expression).
NO_CONCEPT_TEXT_TYPES = {"calculate", "rhombus"}
TEXT_FIELD_USES = {"label": "display", "hint": "hint", "help": "help"}


class YamlEdge(YamlModel):
    """Edge between two nodes. 'value' is used for conditional (rhombus) edges."""
    source: str
    target: str
    value: Optional[str] = None


class YamlActivity(YamlModel):
    """
    One activity (equivalent to one draw.io page/tab).
    """
    id: str
    # defaults to the id
    title: Optional[str] = None
    process: str = "main"
    nodes: List[YamlNode]
    edges: List[YamlEdge] = Field(default_factory=list)
    applicability: Optional[str] = None
    # names the activity in outputs (else the title slug)
    name: Optional[str] = None
    # plain-language twin of ``applicability``, a string or {lang: text}; informational
    intent: Optional[Union[str, Dict[str, str]]] = None
    # Legacy: names the form only without tricc.yaml interventions (use
    # interventions[].name). Read for a start node that has none. ``formId`` accepted too.
    form_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("form_id", "formId"))

    # declared and computed parameters, ``{name, type, options?, default?, required?}``
    params: List[Dict[str, Any]] = Field(default_factory=list)
    # a block's outputs (template names of inner inputs / calculates); None: all, []: none
    outputs: Optional[List[str]] = None
    # prerequisite concepts (§8.4) and extension contract (§9): read, not used yet
    requires: List[Any] = Field(default_factory=list)
    extension: Optional[Dict[str, Any]] = None

    # whether ``title`` was written (it defaults to the id)
    _title_given: bool = PrivateAttr(default=False)

    @model_validator(mode="after")
    def _defaults(self) -> "YamlActivity":
        self._title_given = bool(self.title)
        if not self.title:
            self.title = self.id
        if self.name is not None:
            self.name = self.name.strip() or None
        return self


# Mapping from YAML "type" string to (model class, extra attributes to copy)
# Extend this map as you add support for more node types in tests.
NODE_TYPE_MAP: Dict[str, Dict[str, Any]] = {
    "start": {
        "model": TriccNodeMainStart,
        # form_id: legacy form name, read only without tricc.yaml interventions
        "attrs": ["process", "label", "relevance", "form_id"],
        "tricc_type": TriccNodeType.start,
    },
    "activity_start": {
        "model": TriccNodeActivityStart,
        "attrs": ["label", "name", "relevance", "instance", "repeat"],
        "tricc_type": TriccNodeType.activity_start,
    },
    "block_start": {
        "model": TriccNodeBlockStart,
        "attrs": ["label", "name", "relevance"],
        "tricc_type": TriccNodeType.block_start,
    },
    "activity_end": {
        "model": TriccNodeActivityEnd,
        "attrs": [],
        "tricc_type": TriccNodeType.activity_end,
    },
    "end": {
        "model": TriccNodeEnd,
        "attrs": ["process", "label", "name", "hint"],
        "tricc_type": TriccNodeType.end,
    },
    "note": {
        "model": TriccNodeNote,
        "attrs": ["label", "name", "relevance", "hint", "help"],
        "tricc_type": TriccNodeType.note,
    },
    "integer": {
        "model": TriccNodeInteger,
        "attrs": ["label", "name", "required", "min", "max", "relevance", "save", "repeat", "hint", "help"],
        "tricc_type": TriccNodeType.integer,
    },
    "decimal": {
        "model": TriccNodeDecimal,
        "attrs": ["label", "name", "required", "min", "max", "relevance", "save", "repeat", "hint", "help"],
        "tricc_type": TriccNodeType.decimal,
    },
    "quantity": {
        "model": TriccNodeQuantity,
        "attrs": [
            "label", "name", "required", "min", "max", "relevance", "save", "repeat",
            "hint", "help", "unit", "unit_system", "unit_code", "concept_type",
        ],
        "tricc_type": TriccNodeType.quantity,
    },
    "text": {
        "model": TriccNodeText,
        "attrs": ["label", "name", "required", "relevance", "save", "repeat", "hint", "help"],
        "tricc_type": TriccNodeType.text,
    },
    "select_one": {
        "model": TriccNodeSelectOne,
        "attrs": ["label", "name", "required", "relevance", "save", "repeat", "hint", "help"],
        "has_options": True,
        "tricc_type": TriccNodeType.select_one,
    },
    "select_multiple": {
        "model": TriccNodeSelectMultiple,
        "attrs": ["label", "name", "required", "relevance", "save", "repeat", "hint", "help"],
        "has_options": True,
        "tricc_type": TriccNodeType.select_multiple,
    },
    "select_yesno": {
        "model": TriccNodeSelectYesNo,
        "attrs": ["label", "name", "required", "relevance", "save", "repeat", "hint", "help"],
        "has_options": True,
        # Same as the draw.io model: the node keeps select_one (exported as select_one yes_no).
        "tricc_type": TriccNodeType.select_one,
    },
    "not_available": {
        "model": TriccNodeSelectNotAvailable,
        "attrs": ["label", "name", "required", "relevance", "save", "repeat", "hint", "help"],
        "has_options": True,
        # Same as the draw.io model: SelectNotAvailable subclasses SelectOne.
        "tricc_type": TriccNodeType.select_one,
    },
    "calculate": {
        "model": TriccNodeCalculate,
        "attrs": ["label", "name", "calculate", "relevance", "save", "reference", "repeat"],
        "tricc_type": TriccNodeType.calculate,
    },
    "rhombus": {
        "model": TriccNodeRhombus,
        "attrs": ["label", "name", "expression", "reference", "relevance"],
        "tricc_type": TriccNodeType.rhombus,
    },
    "populate": {
        "model": TriccNodePopulate,
        "attrs": [
            "label", "name", "context", "period", "repeat", "data_type", "concept_type",
            "unit", "unit_system", "unit_code",
        ],
        "tricc_type": TriccNodeType.populate,
    },
    "goto": {
        "model": TriccNodeGoTo,
        "attrs": ["label", "name", "link", "instance", "repeat"],
        "tricc_type": TriccNodeType.goto,
    },
    # inlines one copy of the block built for its args (a goto with instance -1)
    "block": {
        "model": TriccNodeBlock,
        "attrs": ["label", "name", "link", "repeat", "args"],
        "tricc_type": TriccNodeType.block,
    },
    # Same attributes the model and the draw.io map actually carry. A missing entry
    # makes _create_node return None, so the node is dropped on YAML load.
    "proposed_diagnosis": {
        "model": TriccNodeProposedDiagnosis,
        "attrs": ["label", "name", "severity", "reference", "remote_reference", "trigger", "repeat", "save"],
        "tricc_type": TriccNodeType.proposed_diagnosis,
    },
    "diagnosis": {
        "model": TriccNodeDiagnosis,
        "attrs": ["label", "name", "severity", "reference", "save", "repeat", "priority"],
        "tricc_type": TriccNodeType.diagnosis,
    },
}

# Map YAML type strings to TriccNodeType (for nodes where the map above does not list it)
YAML_TYPE_TO_TRICC_TYPE = {
    "start": TriccNodeType.start,
    "activity_start": TriccNodeType.activity_start,
    "activity_end": TriccNodeType.activity_end,
    "end": TriccNodeType.end,
    "goto": TriccNodeType.goto,
    "block": TriccNodeType.block,
    "block_start": TriccNodeType.block_start,
    "note": TriccNodeType.note,
    "integer": TriccNodeType.integer,
    "decimal": TriccNodeType.decimal,
    "quantity": TriccNodeType.quantity,
    "text": TriccNodeType.text,
    "select_one": TriccNodeType.select_one,
    "select_multiple": TriccNodeType.select_multiple,
    "select_yesno": TriccNodeType.select_yesno,
    "not_available": TriccNodeType.not_available,
    "calculate": TriccNodeType.calculate,
    "rhombus": TriccNodeType.rhombus,
    "populate": TriccNodeType.populate,
    "proposed_diagnosis": TriccNodeType.proposed_diagnosis,
    "diagnosis": TriccNodeType.diagnosis,
}


# Node fields a placeholder may appear in, and how it renders there (§4).
EXPRESSION_FIELDS = {"relevance", "calculate", "expression", "constraint", "min", "max", "reference", "trigger"}
TEXT_FIELDS = {"name", "label", "hint", "help", "constraint_message", "save"}
# never rendered: ids, structure, and call arguments (bound by the call instead)
RAW_FIELDS = {"id", "type", "process", "instance", "link", "args", "options", "ui"}


def _normalize_types(act_dict: Dict[str, Any]) -> None:
    """``snippet_start`` / ``snippet`` (the first names) read as ``block_start`` / ``block``."""
    for node in act_dict.get("nodes") or []:
        if isinstance(node, dict) and node.get("type") in TYPE_ALIASES:
            node["type"] = TYPE_ALIASES[node["type"]]


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings(v)


def _yaml_template(raw: Dict[str, Any], ya: YamlActivity) -> Template:
    is_block = any(n.type == "block_start" for n in ya.nodes)
    template = Template(id=ya.id, name=ya.name, is_block=is_block, raw=raw)
    declared = {}
    for entry in ya.params:
        try:
            spec = ParamSpec(**entry, owner=template.owner)
        except ValidationError as exc:
            raise TriccParamError(E_PARAM_TYPE, f"page {ya.id}: invalid parameter {entry!r}: {exc}") from exc
        if spec.name in declared:
            raise TriccParamError(E_PARAM_CONFLICT, f"page {ya.id} declares {spec.name!r} twice")
        declared[spec.name] = spec
    template.declared = declared
    template.calls = [
        CallSite(caller=ya.id, node_id=n.id, link=n.link, kind=n.type, args=n.args or {})
        for n in ya.nodes
        if n.type in CALL_TYPES and n.link
    ]
    template.used = sorted({name for text in _walk_strings(raw) for name in placeholder_names(text)})
    template.static_used = sorted(_static_used(raw))
    template.fields = [n.name for n in ya.nodes if n.type in FIELD_TYPES and n.name]
    template.outputs = list(ya.outputs) if ya.outputs is not None else None
    template.templated_names = [n.name for n in ya.nodes if has_placeholder(n.name)]
    return template


def _static_used(raw: Dict[str, Any]) -> set:
    """Parameters a YAML page uses where only a fixed value fits (§18.8 point 1): its name,
    node / option names, ``save``, ``{{p|raw}}``, static decisions, literal call arguments."""
    names = set(placeholder_names(raw.get("name")))
    names.update(n for text in _walk_strings(raw) for n in raw_placeholder_names(text))
    for node in raw.get("nodes") or []:
        for key in ("name", "save"):
            names.update(placeholder_names(node.get(key)))
        for option in node.get("options") or []:
            names.update(placeholder_names(option.get("name")))
        if node.get("static"):
            for key in EXPRESSION_FIELDS:
                names.update(placeholder_names(node.get(key)))
        if node.get("type") in CALL_TYPES and isinstance(node.get("args"), dict):
            names.update(literal_arg_names(node["args"]))
    return names


def _yaml_add_calculate(rendered: Dict[str, Any], call: CallSite, name: str, expression: str, label: str) -> None:
    """Add to a rendered YAML page the calculate of an expression argument (§18.8 point 1).

    A calculate with no incoming edge: evaluated once its references are, like any free
    calculate of the page, and read in the block through ``{{param}}``.
    """
    rendered["nodes"].append({
        "id": f"{call.node_id}__{name}",
        "type": "calculate",
        "name": name,
        "label": label,
        "calculate": expression,
    })


def _render_field(key: str, value: Any, env, where: str) -> Any:
    if key in EXPRESSION_FIELDS:
        context = EXPRESSION
    elif key in TEXT_FIELDS or key in ("title", "intent"):
        context = TEXT
    else:
        if any(has_placeholder(t) for t in _walk_strings(value)):
            raise TriccParamError(E_PARAM_PLACEHOLDER, f"{where}: placeholders are not allowed in {key!r}")
        return value
    if isinstance(value, dict):
        return {k: substitute(v, env, context, f"{where}.{key}") for k, v in value.items()}
    return substitute(value, env, context, f"{where}.{key}")


def _yaml_render(template: Template, env, new_id: str):
    """The page with placeholders rendered and ids suffixed for ``new_id``; its calls."""
    suffix = new_id[len(template.id):]
    raw = template.raw
    out = {k: (_render_field(k, v, env, template.id) if k in ("applicability", "title", "intent", "name") else v)
           for k, v in raw.items() if k not in ("nodes", "edges")}
    out["id"] = new_id
    out["params"] = []
    nodes, calls = [], []
    for node in raw.get("nodes") or []:
        where = f"{template.id}/{node.get('id')}"
        rendered = {}
        for key, value in node.items():
            if key in RAW_FIELDS:
                if key not in ("args", "options", "ui") and any(has_placeholder(t) for t in _walk_strings(value)):
                    raise TriccParamError(E_PARAM_PLACEHOLDER, f"{where}: placeholders are not allowed in {key!r}")
                rendered[key] = copy.deepcopy(value)
            else:
                rendered[key] = _render_field(key, value, env, where)
        rendered["id"] = f"{node['id']}{suffix}"
        rendered["options"] = [
            {
                **{k: _render_field(k, v, env, f"{where}/{opt.get('id')}") if k in ("name", "label", "relevance")
                   else v for k, v in opt.items()},
                "id": f"{opt['id']}{suffix}",
            }
            for opt in node.get("options") or []
        ]
        if node.get("type") in CALL_TYPES and node.get("link"):
            call = CallSite(
                caller=template.id, node_id=node["id"], link=node["link"], kind=node["type"],
                args=node.get("args") or {},
            )
            calls.append((call, lambda new_link, target=rendered: target.__setitem__("link", new_link)))
        nodes.append(rendered)
    out["nodes"] = nodes
    out["edges"] = [
        {
            **edge,
            "source": f"{edge['source']}{suffix}",
            "target": f"{edge['target']}{suffix}",
            **({"value": substitute(edge["value"], env, EXPRESSION, f"{template.id} edge")} if edge.get("value") else {}),
        }
        for edge in raw.get("edges") or []
    ]
    return out, calls


@register_input_strategy("YamlStrategy")
class YamlStrategy(BaseInputStrategy):
    """
    Input strategy that loads activities from a simple YAML format.

    This is especially useful for testing the internal transformation logic
    (inheritance, calculate generation, relevance, diagnosis ordering, etc.)
    without the overhead and noise of draw.io XML files.

    Usage (via CLI):
        python tests/build.py -i my_test.yaml -o out/ -I YamlStrategy -O ...
    """

    # Same cpg-common-process list DrawioStrategy uses, so a fixture can lay out a
    # multi-process flow (one TriccSegment / Questionnaire per process) instead of
    # only the single "main" process. Fixtures that declare `process: main` keep
    # short-circuiting in execute_linked_process and are unaffected.
    processes = PROCESSES
    file_extensions = (".yaml", ".yml")

    def __init__(self, input_path: Union[str, List[str]]):
        super().__init__(input_path)
        self._node_cache: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Main entry point (matches DrawioStrategy contract)
    # ------------------------------------------------------------------
    def execute(
        self,
        file_content: List[str],
        media_path: str,
        project_config=None,
        intervention=None,
    ) -> Optional[TriccIntervention]:
        project = self.new_project(project_config, intervention)
        self.load(file_content, media_path, project)
        return self.finalize(project, media_path)

    def load(self, file_content: List[str], media_path: str, project: TriccIntervention) -> None:
        loaded: List[tuple] = []  # (raw dict, YamlActivity), in file order
        ids = set()
        for raw_content in file_content:
            if not raw_content or not raw_content.strip():
                continue

            try:
                loaded_docs = list(yaml.safe_load_all(raw_content))
            except yaml.YAMLError as exc:
                logger.error(f"Failed to parse YAML content: {exc}")
                continue

            for doc in loaded_docs:
                if not doc:
                    continue
                # Support either a single activity dict or a list of activities
                activities_data: List[Dict[str, Any]] = doc if isinstance(doc, list) else [doc]

                for act_dict in activities_data:
                    if not act_dict:
                        continue
                    _normalize_types(act_dict)
                    try:
                        yaml_activity = YamlActivity(**act_dict)
                    except ValidationError as exc:
                        logger.error(f"Invalid YAML activity definition: {exc}")
                        continue
                    if yaml_activity.id in project.pages or yaml_activity.id in ids:
                        # Same rule as DrawioStrategy; matters when a project mixes
                        # drawio pages and yaml activities sharing one id space.
                        raise ValueError(
                            f"activity id {yaml_activity.id!r} is already loaded (duplicate activity / diagram id)"
                        )
                    ids.add(yaml_activity.id)
                    loaded.append((act_dict, yaml_activity))

        # every activity is a template: one without parameters gets a single copy identical
        # to the original (same ids); a block is built only where it is used
        self._load_pages(loaded, project)

    def _register(self, activity: Optional[TriccNodeActivity], project: TriccIntervention) -> None:
        if activity is None:
            return
        project.pages[activity.id] = activity
        if isinstance(activity.root, TriccNodeBlockStart):
            project.blocks[activity.id] = activity
        else:
            self._assign_start_page(activity, project)

    # ------------------------------------------------------------------
    # Parameters (feature/20261111-block-params-and-start-node.md)
    # ------------------------------------------------------------------
    def _load_pages(self, loaded: List[tuple], project: TriccIntervention) -> None:
        """Build the activities: one copy of each per distinct set of parameter values."""
        templates: Dict[str, Template] = {}
        for raw, ya in loaded:
            templates[ya.id] = _yaml_template(raw, ya)
        blocks_by_name = {}
        for tid, template in templates.items():
            if template.is_block:
                root = next(n for n in template.raw["nodes"] if n.get("type") == "block_start")
                if root.get("name"):
                    blocks_by_name.setdefault(root["name"], tid)

        def resolve(call: CallSite) -> Optional[str]:
            if call.kind == "block":
                tid = blocks_by_name.get(call.link) or (call.link if call.link in templates else None)
                if tid is None or not templates[tid].is_block:
                    raise TriccParamError(E_PARAM_UNKNOWN, f"{call.describe()}: no block {call.link!r}")
                return tid
            if call.link in templates and not templates[call.link].is_block:
                return call.link
            return None  # a page of another input, or not loaded: linked as before

        def build(template: Template, rendered: Dict[str, Any]) -> None:
            self._register(self._build_activity(YamlActivity(**rendered), project), project)

        ParamBuild(templates, resolve, project, _yaml_render, build, _yaml_add_calculate).run()

    def finalize(self, project: TriccIntervention, media_path: str) -> Optional[TriccIntervention]:
        # Project CodeSystems (tricc.yaml ``terminology``) are exported like drawio's;
        # without terminology the yaml input builds none, so nothing is written.
        self.write_terminology(project, media_path)
        # Re-use the sophisticated linking / inheritance / calculate logic
        # already present in the base class and DrawioStrategy.
        return self.link_project(project)

    # ------------------------------------------------------------------
    # Activity construction
    # ------------------------------------------------------------------
    def _build_activity(
        self, yaml_act: YamlActivity, project: TriccIntervention
    ) -> Optional[TriccNodeActivity]:
        root_node = None
        nodes: Dict[str, Any] = {}
        edges: List[TriccEdge] = []
        pending_ends: List[YamlNode] = []

        # 1. Create every node except activity_end. That model names itself from
        # activity.id, so it is created once the container exists.
        for ynode in yaml_act.nodes:
            if ynode.type == "activity_end":
                pending_ends.append(ynode)
                continue
            node = self._create_node(ynode, yaml_act, project)
            if node is None:
                logger.warning(f"Skipping unknown or unsupported node type: {ynode.type}")
                continue
            nodes[ynode.id] = node
            # options are edge sources too (yes / no, Answer('…')), as in draw.io
            for option in (getattr(node, "options", None) or {}).values():
                nodes[option.id] = option
            if ynode.type in ROOT_TYPES:
                root_node = node

        if root_node is None:
            logger.error(f"Activity '{yaml_act.id}' has no start/activity_start/block_start node")
            return None
        if yaml_act.form_id and isinstance(root_node, TriccNodeMainStart) and not root_node.form_id:
            root_node.form_id = yaml_act.form_id
        activity_name = yaml_act.name or yaml_act.title.lower().replace(" ", "_")
        # The start node is the activity: activity-level keys are the single copy, and a
        # value still written on the root (older files) is the fallback / keeps the root's.
        activity_label = yaml_act.title
        if not yaml_act._title_given and getattr(root_node, "label", None):
            activity_label = root_node.label
        if not getattr(root_node, "label", None):
            root_node.label = yaml_act.title

        # 2. Assemble the activity (segment when root is a main start) before ends,
        # so activity_end.__init__ can read activity.id.
        activity = node_container_for_root(
            root_node,
            id=yaml_act.id,
            label=activity_label,
            name=activity_name,
            nodes=nodes,
            edges=edges,
            process=yaml_act.process,
        )
        for ynode in pending_ends:
            node = self._create_node(ynode, yaml_act, project, activity=activity)
            if node is None:
                logger.warning(f"Skipping unknown or unsupported node type: {ynode.type}")
                continue
            nodes[ynode.id] = node

        # 3. Create edges, now that ends exist.
        for yedge in yaml_act.edges:
            if yedge.source not in nodes or yedge.target not in nodes:
                logger.warning(
                    f"Edge references unknown node(s): {yedge.source} -> {yedge.target}"
                )
                continue
            edge = TriccEdge(
                id=generate_id(f"e{yedge.source}{yedge.target}{len(edges)}"),
                source=yedge.source,
                target=yedge.target,
                value=yedge.value,
            )
            edges.append(edge)
        # The model copied both collections on construction; hand it the complete ones.
        activity.nodes = nodes
        activity.edges = edges
        nodes = activity.nodes

        # Wire root to activity
        root_node.activity = activity
        root_node.group = activity
        if getattr(root_node, "process", None) is None:
            root_node.process = yaml_act.process
        for node in nodes.values():
            node.activity = activity
            node.group = activity

        # 3b. Edge labels, as for draw.io: rhombus paths, then yes / no / factor /
        # condition / follow / Answer('…'). Injected nodes and edges land in the activity.
        for node in list(nodes.values()):
            if isinstance(node, TriccRhombusMixIn) and node.path is None:
                calc = assign_rhombus_path(node, nodes, activity)
                if calc:
                    nodes[calc.id] = calc
        for edge in list(activity.edges):
            process_edge_label(edge, nodes, yaml_act.id)
        edges = activity.edges

        # 4. Post-process expressions (relevance, calculate, etc.)
        for node in nodes.values():
            self._apply_expressions(node)

        # 5. Link prev/next using the same helper as drawio path
        self._wire_prev_next(nodes, edges)

        # 6. Handle dangling calculates (important for many test cases)
        self._collect_dangling_calculates(activity)

        propagate_activity_repeat(activity)

        if yaml_act.applicability:
            activity.applicability = parse_expression("", yaml_act.applicability)
        elif getattr(root_node, "relevance", None) is not None:
            activity.applicability = root_node.relevance
        activity.intent = yaml_act.intent

        logger.info(f"Loaded YAML activity: {yaml_act.id} ({yaml_act.title})")
        return activity

    def _create_node(
        self, ynode: YamlNode, yaml_act: YamlActivity, project: TriccIntervention, activity=None
    ) -> Optional[Any]:
        """Create a concrete Tricc* node instance from a YamlNode definition."""
        type_info = NODE_TYPE_MAP.get(ynode.type)
        if not type_info:
            return None

        model_cls: Type[Any] = type_info["model"]
        allowed_attrs = type_info.get("attrs", [])

        # Determine the correct tricc_type enum value
        tricc_type = type_info.get("tricc_type") or YAML_TYPE_TO_TRICC_TYPE.get(ynode.type)

        # Base data passed to the model
        data: Dict[str, Any] = {
            "id": ynode.id,
            "tricc_type": tricc_type,
        }
        # activity_end names itself from activity.id inside __init__. The container
        # is built first and passed in; creating the end before that drops the node.
        if activity is not None:
            data["activity"] = activity
            data["group"] = activity

        # Copy supported attributes from YAML (with some normalization)
        for attr in allowed_attrs:
            val = getattr(ynode, attr, None)
            if attr in ("min", "max") and isinstance(val, str):
                val = float(val)
            if val is not None:
                if attr == "required":
                    data[attr] = shield_required(val)
                else:
                    data[attr] = val

        if ynode.type not in NO_CONCEPT_TEXT_TYPES and any(
            f in allowed_attrs and f not in data for f in TEXT_FIELD_USES
        ):
            concept = self._resolve_concept(ynode.concept, ynode.name, project, f"node {ynode.id}")
            for field, text in self._concept_texts(concept, project).items():
                if field in allowed_attrs and field not in data:
                    data[field] = text

        # Ensure we have at least a label or name for nodes that require it
        if "label" not in data and ynode.label:
            data["label"] = ynode.label
        if "name" not in data and ynode.name:
            data["name"] = ynode.name
        if ynode.type == "end" and "name" not in data:
            # a sequence node: name it from its id, as the activity start
            data["name"] = _get_name("end_", ynode.id, yaml_act.id)

        # Special handling for select nodes: create parent first (no options yet),
        # then create options with a reference back to the parent select.
        list_name = None
        if type_info.get("has_options"):
            list_name = ynode.name or f"list_{ynode.id}"
            if ynode.type == "select_yesno" and not ynode.options:
                list_name = "yes_no"
            data["list_name"] = list_name
            # We will attach options after the parent node is created
            data["options"] = {}

        if ynode.concept is not None and "concept_code" in model_cls.model_fields:
            data["concept_code"], data["concept_system"] = self._concept_ref(ynode.concept)

        try:
            node = model_cls(**data)
        except Exception as exc:
            logger.error(f"Failed to instantiate {ynode.type} node '{ynode.id}': {exc}")
            return None

        # Post-creation wiring for select options (now that the parent exists)
        if ynode.type == "select_yesno" and not ynode.options:
            # as draw.io: the built-in yes / no options
            node.options = get_select_yes_no_options(node, None)
        elif type_info.get("has_options"):
            node.options = {}
            # Integer keys (0, 1, …) match draw.io and Dict[int, TriccNodeSelectOption].
            for i, opt in enumerate(ynode.options):
                opt_code, opt_system = self._concept_ref(opt.concept)
                opt_name = opt.name or opt_code or opt.id
                opt_label = opt.label
                if opt_label is None:
                    concept = self._resolve_concept(opt.concept, opt_name, project, f"option {opt.id}")
                    opt_label = self._concept_texts(concept, project).get("label", opt_name)
                opt_node = TriccNodeSelectOption(
                    id=opt.id,
                    name=opt_name,
                    label=opt_label,
                    list_name=list_name or (ynode.name or f"list_{ynode.id}"),
                    select=node,
                    relevance=parse_expression("", opt.relevance) if opt.relevance else None,
                    concept_code=opt_code,
                    concept_system=opt_system,
                    is_none=opt.is_none,
                )
                node.options[i] = opt_node
                # Also set activity/group if they exist on the parent
                opt_node.activity = getattr(node, "activity", None)
                opt_node.group = getattr(node, "group", None)

        # Special case: calculate nodes often use the 'calculate' field as expression source
        if ynode.type == "calculate" and ynode.calculate:
            node.expression = parse_expression(ynode.label or "", ynode.calculate)

        if isinstance(node, TriccNodePopulate):
            from tricc_oo.converters.fhir.populate_helper import normalize_populate_node

            normalize_populate_node(node)

        return node

    @staticmethod
    def _concept_ref(concept: Optional[ConceptRef]):
        """``(code, system)`` of a YAML concept link (``(None, None)`` when absent)."""
        if concept is None:
            return None, None
        if isinstance(concept, str):
            return concept, None
        return concept.code, concept.system

    @staticmethod
    def _resolve_concept(concept: Optional[ConceptRef], name: Optional[str], project: TriccIntervention, where: str):
        """The CodeSystem concept of a node / option: explicit ``concept``, else ``name``."""
        if not project.code_systems:
            return None
        code, system = YamlStrategy._concept_ref(concept)
        if code is None:
            code = name
        if not code:
            return None
        found = find_concept(project.code_systems, code, system)
        if found is not None and is_template_concept(found):
            raise TriccParamError(
                E_ABSTRACT_SELECTED,
                f"{where}: {code!r} is an abstract concept, only used inside its block",
            )
        if found is None:
            # A missing explicit link is worth noticing; a name without concept is common.
            (logger.info if concept is not None else logger.debug)(
                f"{where}: concept {code!r} not found in the project terminology"
            )
        return found

    @staticmethod
    def _concept_texts(concept, project: TriccIntervention) -> Dict[str, str]:
        if concept is None:
            return {}
        texts = {}
        for field, use in TEXT_FIELD_USES.items():
            text = concept_text(concept, use, project.lang_code, project.lang_code)
            if text:
                texts[field] = text
        return texts

    def _apply_expressions(self, node: Any) -> None:
        """Run the project's expression loader on the newly created node."""
        try:
            load_expressions(node)
        except Exception:
            # load_expressions is defensive; ignore non-fatal issues in test data
            pass

        # Also handle direct string fields that may still be present
        for field in ("relevance", "expression", "calculate"):
            raw = getattr(node, field, None)
            if isinstance(raw, str):
                try:
                    parsed = parse_expression(getattr(node, "label", None), raw)
                    setattr(node, field, parsed)
                except Exception:
                    pass

        # Display-model only: ${REF} injection (load_expressions also does this;
        # re-apply if node was built without going through load_expressions fully)
        from tricc_oo.models.tricc import TriccNodeDisplayModel
        from tricc_oo.visitors.text_injection import apply_display_text_injections

        if isinstance(node, TriccNodeDisplayModel):
            try:
                apply_display_text_injections(node)
            except Exception:
                pass

    def _wire_prev_next(self, nodes: Dict[str, Any], edges: List[TriccEdge]) -> None:
        """Establish prev_nodes / next_nodes relationships."""
        for edge in edges:
            src = nodes.get(edge.source)
            tgt = nodes.get(edge.target)
            if src and tgt:
                set_prev_next_node(src, tgt)

    def _collect_dangling_calculates(self, activity: TriccNodeActivity) -> None:
        """Mirror the logic from xml_to_tricc.manage_dangling_calculate."""
        dangling = []
        for node in activity.nodes.values():
            has_incoming = any(
                e.target == node.id or e.target == node for e in activity.edges
            )
            if not has_incoming and isinstance(node, TriccNodeCalculate):
                dangling.append(node)
        if dangling:
            activity.calculates.extend(dangling)

    def _assign_start_page(self, activity: TriccNodeActivity, project: TriccIntervention) -> None:
        """Replicate the start page assignment logic from xml_to_tricc."""
        root = activity.root
        if root is None or isinstance(root, TriccNodeBlockStart):
            return

        # process lives on the root node (start / activity_start), not on the activity itself
        proc = getattr(root, "process", None) or getattr(activity, "process", None) or "main"

        if proc == "main" or proc is None:
            if "main" not in project.start_pages:
                project.start_pages["main"] = activity
                if hasattr(root, "process"):
                    root.process = "main"
        else:
            if proc not in project.start_pages:
                project.start_pages[proc] = []
            if activity not in project.start_pages[proc]:
                project.start_pages[proc].append(activity)
        if isinstance(activity, TriccSegment):
            project.register_segment(activity)

    # The following two methods are inherited from BaseInputStrategy / DrawioStrategy
    # and are called by execute_linked_process / process_pages.
    # We deliberately reuse the rich logic already present there.

    def process_pages(self, start_page, project):
        """Delegate to the rich implementation in the parent hierarchy."""
        # DrawioStrategy defines this; we can call super if it existed,
        # or simply import and call the same visitors.
        # For simplicity and to avoid duplication we re-use the existing path.
        from tricc_oo.strategies.input.drawio import DrawioStrategy

        # Create a temporary DrawioStrategy just to reuse its process_pages
        # (it only uses self.linking_nodes and the visitor functions)
        temp = DrawioStrategy.__new__(DrawioStrategy)
        temp.processes = self.processes
        temp.linking_nodes = DrawioStrategy.linking_nodes.__get__(temp, DrawioStrategy)
        temp.walkthrough_goto_node = DrawioStrategy.walkthrough_goto_node.__get__(temp, DrawioStrategy)
        temp.walkthrough_link_out_node = DrawioStrategy.walkthrough_link_out_node.__get__(temp, DrawioStrategy)
        temp.process_pages(start_page, project)

    def linking_nodes(self, *args, **kwargs):
        """Provided for compatibility with execute_linked_process."""
        from tricc_oo.strategies.input.drawio import DrawioStrategy
        temp = DrawioStrategy.__new__(DrawioStrategy)
        return DrawioStrategy.linking_nodes(temp, *args, **kwargs)
