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

import logging
from typing import Any, Dict, List, Optional, Type, Union

import yaml
from pydantic import BaseModel, Field, ValidationError

from tricc_oo.strategies.input.base_input_strategy import BaseInputStrategy
from tricc_oo.converters.utils import generate_id
from tricc_oo.converters.xml_to_tricc import parse_expression, load_expressions, propagate_activity_repeat
from tricc_oo.visitors.tricc import set_prev_next_node
from tricc_oo.strategies.registry import register_input_strategy

# Core models
from tricc_oo.models.tricc import (
    TriccProject,
    TriccNodeActivity,
    TriccEdge,
    TriccNodeMainStart,
    TriccNodeNote,
    TriccNodeSelectOne,
    TriccNodeSelectMultiple,
    TriccNodeSelectYesNo,
    TriccNodeSelectOption,
    TriccNodeInteger,
    TriccNodeDecimal,
    TriccNodeText,
    TriccNodeGoTo,
)
from tricc_oo.models.base import TriccNodeType

# Nodes defined in calculate.py
from tricc_oo.models.calculate import (
    TriccNodeCalculate,
    TriccNodeRhombus,
    TriccNodeActivityStart,
    TriccNodeActivityEnd,
    TriccNodeEnd,
    TriccNodePopulate,
)

logger = logging.getLogger("default")


# ---------------------------------------------------------------------------
# YAML Test Format Schema (Pydantic)
# ---------------------------------------------------------------------------

class YamlOption(BaseModel):
    """Option for select_one / select_multiple / select_yesno."""
    id: str
    name: str
    label: str
    relevance: Optional[str] = None


class YamlNode(BaseModel):
    """
    Declarative representation of a TRICC node in YAML.

    Only a subset of fields is supported in the initial implementation.
    Add fields here as needed for more advanced test scenarios.
    """
    id: str
    type: str  # e.g. "integer", "select_one", "calculate", "rhombus", ...
    name: Optional[str] = None
    label: Optional[str] = None
    process: Optional[str] = None
    required: Optional[bool] = None
    relevance: Optional[str] = None
    calculate: Optional[str] = None          # for calculate nodes
    expression: Optional[str] = None         # for rhombus / some calculates
    reference: Optional[str] = None          # for rhombus / some calculates
    save: Optional[str] = None
    min: Optional[Union[int, float]] = None
    max: Optional[Union[int, float]] = None
    options: List[YamlOption] = Field(default_factory=list)
    # For goto / link nodes
    link: Optional[str] = None
    instance: Optional[int] = 1
    repeat: Optional[int] = None
    context: Optional[str] = None
    period: Optional[str] = None
    form_id: Optional[str] = None            # start node only; required by XLSForm export


class YamlEdge(BaseModel):
    """Edge between two nodes. 'value' is used for conditional (rhombus) edges."""
    source: str
    target: str
    value: Optional[str] = None


class YamlActivity(BaseModel):
    """
    One activity (equivalent to one draw.io page/tab).
    """
    id: str
    title: str
    process: str = "main"
    nodes: List[YamlNode]
    edges: List[YamlEdge] = Field(default_factory=list)
    applicability: Optional[str] = None


# Mapping from YAML "type" string to (model class, extra attributes to copy)
# Extend this map as you add support for more node types in tests.
NODE_TYPE_MAP: Dict[str, Dict[str, Any]] = {
    "start": {
        "model": TriccNodeMainStart,
        # form_id is required by the XLSForm export, so fixtures can drive a full export
        "attrs": ["process", "label", "relevance", "form_id"],
        "tricc_type": TriccNodeType.start,
    },
    "activity_start": {
        "model": TriccNodeActivityStart,
        "attrs": ["label", "name", "relevance", "instance", "repeat"],
        "tricc_type": TriccNodeType.activity_start,
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
        "attrs": ["label", "name", "relevance"],
        "tricc_type": TriccNodeType.note,
    },
    "integer": {
        "model": TriccNodeInteger,
        "attrs": ["label", "name", "required", "min", "max", "relevance", "save", "repeat"],
        "tricc_type": TriccNodeType.integer,
    },
    "decimal": {
        "model": TriccNodeDecimal,
        "attrs": ["label", "name", "required", "min", "max", "relevance", "save", "repeat"],
        "tricc_type": TriccNodeType.decimal,
    },
    "text": {
        "model": TriccNodeText,
        "attrs": ["label", "name", "required", "relevance", "save", "repeat"],
        "tricc_type": TriccNodeType.text,
    },
    "select_one": {
        "model": TriccNodeSelectOne,
        "attrs": ["label", "name", "required", "relevance", "save", "repeat"],
        "has_options": True,
        "tricc_type": TriccNodeType.select_one,
    },
    "select_multiple": {
        "model": TriccNodeSelectMultiple,
        "attrs": ["label", "name", "required", "relevance", "save", "repeat"],
        "has_options": True,
        "tricc_type": TriccNodeType.select_multiple,
    },
    "select_yesno": {
        "model": TriccNodeSelectYesNo,
        "attrs": ["label", "name", "required", "relevance", "save", "repeat"],
        "has_options": True,
        "tricc_type": TriccNodeType.select_yesno,
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
        "attrs": ["label", "name", "context", "period", "repeat", "data_type", "concept_type"],
        "tricc_type": TriccNodeType.populate,
    },
    "goto": {
        "model": TriccNodeGoTo,
        "attrs": ["label", "name", "link", "instance", "repeat"],
        "tricc_type": TriccNodeType.goto,
    },
}

# Map YAML type strings to TriccNodeType (for nodes where the map above does not list it)
YAML_TYPE_TO_TRICC_TYPE = {
    "start": TriccNodeType.start,
    "activity_start": TriccNodeType.activity_start,
    "activity_end": TriccNodeType.activity_end,
    "end": TriccNodeType.end,
    "goto": TriccNodeType.goto,
    "note": TriccNodeType.note,
    "integer": TriccNodeType.integer,
    "decimal": TriccNodeType.decimal,
    "text": TriccNodeType.text,
    "select_one": TriccNodeType.select_one,
    "select_multiple": TriccNodeType.select_multiple,
    "select_yesno": TriccNodeType.select_yesno,
    "calculate": TriccNodeType.calculate,
    "rhombus": TriccNodeType.rhombus,
    "populate": TriccNodeType.populate,
}


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

    processes = ["main"]

    def __init__(self, input_path: Union[str, List[str]]):
        super().__init__(input_path)
        self._node_cache: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Main entry point (matches DrawioStrategy contract)
    # ------------------------------------------------------------------
    def execute(self, file_content: List[str], media_path: str) -> Optional[TriccProject]:
        project = TriccProject()

        for raw_content in file_content:
            if not raw_content or not raw_content.strip():
                continue

            try:
                loaded_docs = list(yaml.safe_load_all(raw_content))
            except yaml.YAMLError as exc:
                logger.error(f"Failed to parse YAML content: {exc}")
                continue

            for loaded in loaded_docs:
                if not loaded:
                    continue
                # Support either a single activity dict or a list of activities
                activities_data: List[Dict[str, Any]] = (
                    loaded if isinstance(loaded, list) else [loaded]
                )

                for act_dict in activities_data:
                    if not act_dict:
                        continue
                    try:
                        yaml_activity = YamlActivity(**act_dict)
                    except ValidationError as exc:
                        logger.error(f"Invalid YAML activity definition: {exc}")
                        continue

                    activity = self._build_activity(yaml_activity, project)
                    if activity is not None:
                        project.pages[activity.id] = activity
                        self._assign_start_page(activity, project)

        # Re-use the sophisticated linking / inheritance / calculate logic
        # already present in the base class and DrawioStrategy.
        app = self.execute_linked_process(project)
        if app:
            project.start_pages["main"] = app
            project.pages[app.id] = app
            self.process_pages(app, project)
            return project

        # Fallback for projects that only have non-main processes
        if project.start_pages:
            for process, pages in project.start_pages.items():
                targets = pages if isinstance(pages, list) else [pages]
                for page in targets:
                    self.process_pages(page, project)
            return project

        return project if project.pages else None

    # ------------------------------------------------------------------
    # Activity construction
    # ------------------------------------------------------------------
    def _build_activity(
        self, yaml_act: YamlActivity, project: TriccProject
    ) -> Optional[TriccNodeActivity]:
        root_node = None
        nodes: Dict[str, Any] = {}
        edges: List[TriccEdge] = []

        # 1. Create all nodes
        for ynode in yaml_act.nodes:
            node = self._create_node(ynode, yaml_act, project)
            if node is None:
                logger.warning(f"Skipping unknown or unsupported node type: {ynode.type}")
                continue
            nodes[ynode.id] = node
            if ynode.type in ("start", "activity_start"):
                root_node = node

        if root_node is None:
            logger.error(f"Activity '{yaml_act.id}' has no start/activity_start node")
            return None

        # 2. Create edges
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

        # 3. Assemble the activity
        activity = TriccNodeActivity(
            id=yaml_act.id,
            label=yaml_act.title,
            name=yaml_act.title.lower().replace(" ", "_"),
            root=root_node,
            nodes=nodes,
            edges=edges,
            process=yaml_act.process,
        )

        # Wire root to activity
        root_node.activity = activity
        root_node.group = activity
        if getattr(root_node, "process", None) is None:
            root_node.process = yaml_act.process
        for node in nodes.values():
            node.activity = activity
            node.group = activity

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

        logger.info(f"Loaded YAML activity: {yaml_act.id} ({yaml_act.title})")
        return activity

    def _create_node(
        self, ynode: YamlNode, yaml_act: YamlActivity, project: TriccProject
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

        # Copy supported attributes from YAML (with some normalization)
        for attr in allowed_attrs:
            val = getattr(ynode, attr, None)
            if val is not None:
                # "required" in the domain model is an expression-like thing, not a bare bool
                if attr == "required":
                    data[attr] = "1" if val else "0"
                else:
                    data[attr] = val

        # Ensure we have at least a label or name for nodes that require it
        if "label" not in data and ynode.label:
            data["label"] = ynode.label
        if "name" not in data and ynode.name:
            data["name"] = ynode.name

        # Special handling for select nodes: create parent first (no options yet),
        # then create options with a reference back to the parent select.
        list_name = None
        if type_info.get("has_options"):
            list_name = ynode.name or f"list_{ynode.id}"
            data["list_name"] = list_name
            # We will attach options after the parent node is created
            data["options"] = {}

        try:
            node = model_cls(**data)
        except Exception as exc:
            logger.error(f"Failed to instantiate {ynode.type} node '{ynode.id}': {exc}")
            return None

        # Post-creation wiring for select options (now that the parent exists)
        if type_info.get("has_options"):
            node.options = {}
            # Integer keys (0, 1, …) match draw.io and Dict[int, TriccNodeSelectOption].
            for i, opt in enumerate(ynode.options):
                opt_node = TriccNodeSelectOption(
                    id=opt.id,
                    name=opt.name,
                    label=opt.label,
                    list_name=list_name or (ynode.name or f"list_{ynode.id}"),
                    select=node,
                    relevance=parse_expression("", opt.relevance) if opt.relevance else None,
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
        from tricc_oo.converters.utils import remove_html

        if isinstance(node, TriccNodeDisplayModel):
            try:
                apply_display_text_injections(node, clean_fn=remove_html)
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

    def _assign_start_page(self, activity: TriccNodeActivity, project: TriccProject) -> None:
        """Replicate the start page assignment logic from xml_to_tricc."""
        root = activity.root
        if root is None:
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
