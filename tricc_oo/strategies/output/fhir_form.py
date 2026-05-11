"""
FHIRStrategy: standard FHIR SDC output strategy for TRICC.

Generates:
- FHIR Questionnaire (one per process, with SDC extensions)
- CQL Libraries (helper + per-resource)
- FHIR StructureMap / FLM (data extraction)
- FHIR ValueSets (from TRICC CodeSystems)
- FHIR Binary (images)
- FSH files (via fsh_serializer)

This is the reusable FHIR base layer. openSRP/fhircore-specific resources
(Composition, PlanDefinition, Binary config manifest) are added by
``OpenSRPStrategy`` which inherits from this class.
"""

from __future__ import annotations

import base64
import datetime
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from tricc_oo.converters.fhir.concept_mapper import get_fhir_resource, get_fhir_value_field

from tricc_oo.converters.fhir.questionnaire_item_mapper import (
    CALCULATE_NODE_TYPES,
    SDC_EXT_CALCULATED_EXPR,
    SDC_EXT_ENABLE_WHEN_EXPR,
    SDC_EXT_HIDDEN,
    SDC_EXT_INITIAL_EXPR,
    build_enable_when_expression,
    build_hidden_extension,
    build_initial_expression,
    build_calculated_expression,
    get_display_type_extensions,
    get_fhir_item_type,
    is_default_or_odk_input,
    is_hidden,
    is_repeating,
    should_skip,
)
from tricc_oo.converters.tricc_to_xls_form import get_export_name
from tricc_oo.models.base import (
    TriccOperation,
    TriccOperator,
    TriccReference,
    TriccStatic,
)
from tricc_oo.models.tricc import (
    TriccNodeBaseModel,
    TriccNodeInputModel,
    TriccNodeSelect,
    TriccNodeSelectOption,
)
from tricc_oo.strategies.output.base_output_strategy import BaseOutPutStrategy
from tricc_oo.visitors.tricc import get_process

logger = logging.getLogger("default")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_BASE_URL = "https://fhir.tricc.io"
FHIR_VERSION = "4.0.1"
QUESTIONNAIRE_PROFILE = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire"
LIBRARY_PROFILE = "http://hl7.org/fhir/StructureDefinition/Library"
STRUCTUREMAP_PROFILE = "http://hl7.org/fhir/StructureDefinition/StructureMap"
VALUESET_PROFILE = "http://hl7.org/fhir/StructureDefinition/ValueSet"
CODESYSTEM_PROFILE = "http://hl7.org/fhir/StructureDefinition/CodeSystem"

# List-context operators that work on collections without needing .first().value
LIST_CONTEXT_OPERATORS = {"contains", "selected", "has_qualifier", "count"}

# CQL helper library template (based on pyfhirsdc/core_fhir/cql/pyfhirsdc.cql patterns)
CQL_HELPER_TEMPLATE = """\
library {library_id}Helper version '1.0.0'

using FHIR version '{fhir_version}'

include FHIRHelpers version '{fhir_version}' called FHIRHelpers

context Patient

// ── Observation helpers ──────────────────────────────────────────────────────

define function GetObservation(code String):
  First(
    [Observation: Code code from "http://snomed.info/sct"] O
      where O.status in {{'final', 'amended', 'corrected'}}
      sort by effective desc
  )

define function GetObservationValue(code String):
  GetObservation(code).value

// ── Condition helpers ─────────────────────────────────────────────────────────

define function HasCondition(code String):
  exists(
    [Condition: Code code from "http://snomed.info/sct"] C
      where C.clinicalStatus ~ "active"
  )

// ── Age helpers ───────────────────────────────────────────────────────────────

define AgeInDays:
  duration in days between Patient.birthDate and Today()

define AgeInMonths:
  duration in months between Patient.birthDate and Today()

define AgeInYears:
  AgeInYears()
"""

# CQL child library template (per Questionnaire / PlanDefinition)
CQL_CHILD_TEMPLATE = """\
library {library_id} version '1.0.0'

using FHIR version '{fhir_version}'

include FHIRHelpers version '{fhir_version}' called FHIRHelpers
include {helper_library_id}Helper version '1.0.0' called Helper

context Patient

"""


class FHIRStrategy(BaseOutPutStrategy):
    """Standard FHIR SDC output strategy.

    Generates Questionnaire, Library+CQL, StructureMap/FLM, ValueSet, Binary,
    and FSH files from a TRICC project graph.

    Attributes:
        processes: List of process names to handle (default ``["main"]``).
        base_url: Canonical base URL for generated resources.
        questionnaires: Dict mapping process name → Questionnaire resource dict.
        cql_defines: Dict mapping process name → list of CQL define strings.
        structuremaps: Dict mapping process name → StructureMap resource dict.
        valuesets: Dict mapping list_name → ValueSet resource dict.
        binaries: List of Binary resource dicts (images).
        cur_group: Current group context for nesting items (Optional[dict]).
    """

    processes = ["main"]

    def __init__(self, project, output_path: str, base_url: str = DEFAULT_BASE_URL, use_value_sets: bool = False):
        """Initialise the FHIRStrategy.

        Args:
            project: The TRICC project object.
            output_path: Directory path for output files.
            base_url: Canonical base URL for FHIR resources.
            use_value_sets: If True, generate external ValueSets and reference them via answerValueSet.
                            If False (default), hardcode options directly in the Questionnaire as answerOption
                            (easier for standalone testing).
        """
        super().__init__(project, output_path)
        self.base_url = base_url.rstrip("/")
        self.use_value_sets = use_value_sets
        self.questionnaires: Dict[str, dict] = {}
        self.cql_defines: Dict[str, List[str]] = {}
        self.structuremaps: Dict[str, dict] = {}
        self.valuesets: Dict[str, dict] = {}
        self.binaries: List[dict] = []
        self._form_id: Optional[str] = None
        self.cur_group: Optional[dict] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def execute(self):
        """Run the full FHIR export pipeline."""
        version = datetime.datetime.now().strftime("%Y%m%d%H%M")
        logger.info(f"FHIRStrategy: build version {version}")

        if "main" not in self.project.start_pages:
            logger.critical("Main process required")
            return

        self._form_id = getattr(self.project.start_pages["main"].root, "form_id", None) or "tricc_form"

        self.process_base(self.project.start_pages, pages=self.project.pages, version=version)
        logger.info("FHIRStrategy: generating relevance (enableWhenExpression)")
        self.process_relevance(self.project.start_pages, pages=self.project.pages)
        logger.info("FHIRStrategy: generating calculate (initialExpression / CQL)")
        self.process_calculate(self.project.start_pages, pages=self.project.pages)
        logger.info("FHIRStrategy: generating export (StructureMap)")
        self.process_export(self.project.start_pages, pages=self.project.pages)
        logger.info("FHIRStrategy: writing output files")
        self.export(self.project.start_pages, version=version)
        logger.info("FHIRStrategy: validating")
        self.validate()

    # ── Node callbacks ────────────────────────────────────────────────────────

    def generate_base(self, node, **kwargs) -> bool:
        """Build a Questionnaire item for the given node.

        Manages group nesting: groups set cur_group context, non-groups append to cur_group or root.

        Args:
            node: TRICC node being processed.
            **kwargs: Additional keyword arguments from the walker.

        Returns:
            True if the node was processed, False to defer.
        """
        tricc_type = str(getattr(node, "tricc_type", ""))
        if should_skip(tricc_type):
            return True

        process = get_process(node) or "main"
        q = self._get_or_create_questionnaire(process)

        link_id = get_export_name(node)
        if not link_id:
            return True

        # Avoid duplicate items (check recursively if nested)
        if self._find_item(q, link_id) is not None:
            return True

        fhir_type = get_fhir_item_type(tricc_type)

        item: dict = {
            "linkId": link_id,
            "type": fhir_type,
        }

        # Handle group nesting
        if fhir_type == "group":
            # Special case: ignore "main" process root group (matches PD semantics)
            if process == "main" and tricc_type in ("start", "activity_start"):
                return True  # Skip emitting the root group
            # Initialize group with items list
            item["item"] = []
           
            # Append to current group or questionnaire root
            parent_target = self.cur_group["item"] if self.cur_group else q.setdefault("item", [])
            parent_target.append(item)
            # Set as current group context and append to parent
            self.cur_group = item
            return True

        # Label / text
        label = getattr(node, "label", None)
        if label:
            item["text"] = label if isinstance(label, str) else next(iter(label.values()), "")

        # Repeats
        if is_repeating(tricc_type):
            item["repeats"] = True

        # Hidden items
        extensions = []
        if is_hidden(tricc_type):
            extensions.append(build_hidden_extension())

        # display_type → SDC extensions
        display_type = getattr(node, "display_type", None)
        extensions.extend(get_display_type_extensions(display_type, tricc_type))

        # Image / media
        image = getattr(node, "image", None)
        if image:
            binary_id = self._add_binary(image, link_id)
            extensions.append({
                "url": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-itemMedia",
                "valueAttachment": {"url": f"Binary/{binary_id}"},
            })

        if extensions:
            item["extension"] = extensions

        # Answer options for select questions
        if isinstance(node, TriccNodeSelect) and hasattr(node, "options"):
            if self.use_value_sets:
                vs_id = self._get_or_create_valueset(node)
                if vs_id:
                    item["answerValueSet"] = f"{self.base_url}/ValueSet/{vs_id}"
            else:
                # Hardcode options directly in the Questionnaire (default for easier testing)
                answer_options = []
                for opt in getattr(node, "options", {}).values():
                    label = opt.label if isinstance(opt.label, str) else next(iter(opt.label.values()), opt.name)
                    answer_options.append({
                        "valueCoding": {
                            "code": opt.name,
                            "display": label,
                        }
                    })
                if answer_options:
                    item["answerOption"] = answer_options

        # Required flag
        required = getattr(node, "required", None)
        if required and not is_hidden(tricc_type):
            item["required"] = True

        # Append to current group or questionnaire root
        target = self.cur_group["item"] if self.cur_group else q.setdefault("item", [])
        target.append(item)
        return True

    def generate_relevance(self, node, **kwargs) -> bool:
        """Add enableWhenExpression (FHIRPath) to the Questionnaire item.

        Args:
            node: TRICC node being processed.
            **kwargs: Additional keyword arguments from the walker.

        Returns:
            True always (relevance is best-effort).
        """
        relevance = getattr(node, "relevance", None)
        if not relevance:
            return True

        process = get_process(node) or "main"
        q = self._get_or_create_questionnaire(process)
        link_id = get_export_name(node)
        item = self._find_item(q, link_id)
        if item is None:
            return True

        try:
            fhirpath_expr = self.convert_expression_to_fhirpath(relevance)
            if fhirpath_expr:
                item.setdefault("extension", []).append(
                    build_enable_when_expression(fhirpath_expr)
                )
        except NotImplementedError as exc:
            logger.warning(f"FHIRPath conversion not supported for node {link_id}: {exc}")
        return True

    def generate_calculate(self, node, **kwargs) -> bool:
        """Add initialExpression / calculatedExpression (CQL) to the item.

        Rhombus (sequence/logic) nodes use ``initialExpression`` with inline
        ``text/cql`` so that the full CQL expression is embedded directly in
        the extension rather than referencing a named CQL identifier.  All
        other calculate-type nodes continue to use ``calculatedExpression``
        with ``text/cql-identifier``, and non-calculate nodes use
        ``initialExpression`` with ``text/cql-identifier``.

        Args:
            node: TRICC node being processed.
            **kwargs: Additional keyword arguments from the walker.

        Returns:
            True always.
        """
        expression = getattr(node, "expression", None) or getattr(node, "expression_reference", None)
        if not expression:
            return True

        process = get_process(node) or "main"
        q = self._get_or_create_questionnaire(process)
        link_id = get_export_name(node)
        item = self._find_item(q, link_id)


        tricc_type = str(getattr(node, "tricc_type", ""))
        is_calc = tricc_type in CALCULATE_NODE_TYPES
        is_input = is_default_or_odk_input(node)

        try:
            if is_input or is_calc:
                cql_expr = self.convert_expression_to_cql(expression)
                if cql_expr:
                    define_name = link_id.replace(".", "_").replace("-", "_")
                    self.cql_defines.setdefault(process, []).append(
                        f'define "{define_name}":\n  {cql_expr}'
                    )
                    if is_calc:
                        ext = build_calculated_expression(
                            define_name, library_name=f"{self._form_id}_{process}"
                        )
                    else:
                        ext = build_initial_expression(
                            define_name, library_name=f"{self._form_id}_{process}"
                        )
                    if item is not None:
                        item.setdefault("extension", []).append(ext)
            else:
                fhirpath_expr = self.convert_expression_to_fhirpath(expression)
                if fhirpath_expr and item is not None:
                    ext = {
                        "url": SDC_EXT_INITIAL_EXPR,
                        "valueExpression": {
                            "language": "text/fhirpath",
                            "expression": fhirpath_expr,
                        },
                    }
                    item.setdefault("extension", []).append(ext)
        except NotImplementedError as exc:
            logger.warning(f"Expression conversion not supported for node {link_id}: {exc}")
        return True

    def generate_export(self, node, **kwargs) -> bool:
        """Build StructureMap / FLM rules for data extraction.

        Args:
            node: TRICC node being processed.
            **kwargs: Additional keyword arguments from the walker.

        Returns:
            True always.
        """
        tricc_type = str(getattr(node, "tricc_type", ""))
        concept_type = getattr(node, "concept_type", None)
        if not concept_type and tricc_type not in ("diagnosis", "proposed_diagnosis"):
            return True

        process = get_process(node) or "main"
        link_id = get_export_name(node)
        if not link_id:
            return True

        fhir_resource, profile_url, data_field = get_fhir_resource(concept_type, tricc_type)
        data_type = getattr(node, "datatype", None) or getattr(node, "get_datatype", lambda: "string")()
        value_field = get_fhir_value_field(data_type)

        sm = self._get_or_create_structuremap(process)
        rule = {
            "name": f"rule_{link_id.replace('.', '_')}",
            "source": [{"context": "src", "element": link_id, "variable": "v"}],
            "target": [
                {
                    "context": "tgt",
                    "contextType": "variable",
                    "element": data_field,
                    "transform": "copy",
                    "parameter": [{"valueId": "v"}],
                }
            ],
        }
        sm.setdefault("group", [{}])[0].setdefault("rule", []).append(rule)
        return True

    # ── Export ────────────────────────────────────────────────────────────────

    def export(self, start_pages, version: str = ""):
        """Write all generated FHIR resources to the output directory.

        Args:
            start_pages: Dict of start pages from the project.
            version: Build version string.
        """
        # Prune empty groups before writing
        for q in self.questionnaires.values():
            self._prune_empty_groups(q)
        
        base = Path(self.output_path) / self._form_id
        self._write_questionnaires(base, version)
        self._write_libraries(base, version)
        self._write_structuremaps(base)
        self._write_valuesets(base)
        self._write_binaries(base)
        logger.info(f"FHIRStrategy: exported FHIR resources to {base}")

    def validate(self):
        """Validate the generated FHIR resources (basic checks).

        Raises:
            Warning logs for any detected issues.
        """
        for process, q in self.questionnaires.items():
            if not q.get("item"):
                logger.warning(f"Questionnaire for process '{process}' has no items")
            if not q.get("url"):
                logger.warning(f"Questionnaire for process '{process}' has no URL")
        logger.info("FHIRStrategy: validation complete")

    # ── Resource builders ─────────────────────────────────────────────────────

    def _get_or_create_questionnaire(self, process: str) -> dict:
        """Get or create the Questionnaire resource dict for a process.

        Args:
            process: The cpg-common-process name.

        Returns:
            Questionnaire resource dict.
        """
        if process not in self.questionnaires:
            q_id = f"{self._form_id}-{process}"
            self.questionnaires[process] = {
                "resourceType": "Questionnaire",
                "id": q_id,
                "meta": {"profile": [QUESTIONNAIRE_PROFILE]},
                "url": f"{self.base_url}/Questionnaire/{q_id}",
                "name": q_id,
                "title": f"{self._form_id} – {process}",
                "status": "draft",
                "experimental": True,
                "subjectType": ["Patient"],
                "item": [],
            }
            # Reset group context per questionnaire
            self.cur_group = None
        return self.questionnaires[process]

    def _get_or_create_structuremap(self, process: str) -> dict:
        """Get or create the StructureMap resource dict for a process.

        Args:
            process: The cpg-common-process name.

        Returns:
            StructureMap resource dict.
        """
        if process not in self.structuremaps:
            sm_id = f"{self._form_id}-{process}-extract"
            self.structuremaps[process] = {
                "resourceType": "StructureMap",
                "id": sm_id,
                "meta": {"profile": [STRUCTUREMAP_PROFILE]},
                "url": f"{self.base_url}/StructureMap/{sm_id}",
                "name": sm_id,
                "status": "draft",
                "structure": [
                    {
                        "url": f"{self.base_url}/Questionnaire/{self._form_id}-{process}",
                        "mode": "source",
                        "alias": "src",
                    }
                ],
                "group": [
                    {
                        "name": f"Extract{process.replace('-', '')}",
                        "typeMode": "none",
                        "input": [
                            {"name": "src", "type": "QuestionnaireResponse", "mode": "source"},
                            {"name": "tgt", "type": "Bundle", "mode": "target"},
                        ],
                        "rule": [],
                    }
                ],
            }
        return self.structuremaps[process]

    def _get_or_create_valueset(self, node) -> Optional[str]:
        """Get or create a ValueSet for a select node's options.

        Args:
            node: A TRICC select node with options.

        Returns:
            ValueSet ID string, or None if no options.
        """
        list_name = getattr(node, "list_name", None) or get_export_name(node)
        if not list_name:
            return None
        if list_name in self.valuesets:
            return list_name

        concepts = []
        for opt in getattr(node, "options", {}).values():
            label = opt.label if isinstance(opt.label, str) else next(iter(opt.label.values()), opt.name)
            concepts.append({"code": opt.name, "display": label})

        if not concepts:
            return None

        cs_id = f"{self._form_id}-{list_name}"
        vs_id = list_name
        self.valuesets[vs_id] = {
            "resourceType": "ValueSet",
            "id": vs_id,
            "meta": {"profile": [VALUESET_PROFILE]},
            "url": f"{self.base_url}/ValueSet/{vs_id}",
            "name": vs_id,
            "status": "draft",
            "compose": {
                "include": [
                    {
                        "system": f"{self.base_url}/CodeSystem/{cs_id}",
                        "concept": concepts,
                    }
                ]
            },
        }
        return vs_id

    def _add_binary(self, image_data: str, node_id: str) -> str:
        """Add a Binary resource for an image.

        Args:
            image_data: Base64-encoded image data.
            node_id: Node identifier used to name the binary.

        Returns:
            Binary resource ID string.
        """
        binary_id = f"img-{node_id}"
        self.binaries.append({
            "resourceType": "Binary",
            "id": binary_id,
            "contentType": "image/png",
            "data": image_data,
        })
        return binary_id

    def generate_library(self, process: str, version: str) -> dict:
        """Build a CQL Library resource for a process.

        Args:
            process: The cpg-common-process name.
            version: Build version string.

        Returns:
            Library resource dict.
        """
        lib_id = f"{self._form_id}-{process}"
        helper_id = f"{self._form_id}"
        cql_header = CQL_CHILD_TEMPLATE.format(
            library_id=lib_id,
            fhir_version=FHIR_VERSION,
            helper_library_id=helper_id,
        )
        defines = self.cql_defines.get(process, [])
        cql_content = cql_header + "\n\n".join(defines)
        cql_b64 = base64.b64encode(cql_content.encode()).decode()

        return {
            "resourceType": "Library",
            "id": lib_id,
            "meta": {"profile": [LIBRARY_PROFILE]},
            "url": f"{self.base_url}/Library/{lib_id}",
            "name": lib_id,
            "version": version or "1.0.0",
            "status": "draft",
            "type": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/library-type", "code": "logic-library"}]
            },
            "content": [{"contentType": "text/cql", "data": cql_b64}],
        }

    def generate_helper_library(self, version: str) -> dict:
        """Build the shared CQL helper Library resource.

        Args:
            version: Build version string.

        Returns:
            Library resource dict.
        """
        lib_id = f"{self._form_id}Helper"
        cql_content = CQL_HELPER_TEMPLATE.format(
            library_id=self._form_id,
            fhir_version=FHIR_VERSION,
        )
        cql_b64 = base64.b64encode(cql_content.encode()).decode()
        return {
            "resourceType": "Library",
            "id": lib_id,
            "meta": {"profile": [LIBRARY_PROFILE]},
            "url": f"{self.base_url}/Library/{lib_id}",
            "name": lib_id,
            "version": version or "1.0.0",
            "status": "draft",
            "type": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/library-type", "code": "logic-library"}]
            },
            "content": [{"contentType": "text/cql", "data": cql_b64}],
        }

    # ── File writers ──────────────────────────────────────────────────────────

    def _write_questionnaires(self, base: Path, version: str):
        """Write Questionnaire JSON files and attach library references.

        Args:
            base: Base output directory path.
            version: Build version string.
        """
        q_dir = base / "questionnaire"
        q_dir.mkdir(parents=True, exist_ok=True)
        for process, q in self.questionnaires.items():
            lib_id = f"{self._form_id}-{process}"
            q["version"] = version
            # Wire cqlInputResources
            q.setdefault("extension", []).append({
                "url": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-launchContext",
                "extension": [
                    {"url": "name", "valueCoding": {"system": "http://hl7.org/fhir/uv/sdc/CodeSystem/launchContext", "code": "patient"}},
                    {"url": "type", "valueCode": "Patient"},
                ],
            })
            path = q_dir / f"{q['id']}.json"
            path.write_text(json.dumps(q, indent=2, ensure_ascii=False))
            logger.debug(f"Wrote Questionnaire: {path}")

    def _write_libraries(self, base: Path, version: str):
        """Write CQL Library JSON and .cql files.

        Args:
            base: Base output directory path.
            version: Build version string.
        """
        lib_dir = base / "library"
        lib_dir.mkdir(parents=True, exist_ok=True)
        # Helper library
        helper = self.generate_helper_library(version)
        (lib_dir / f"{helper['id']}.json").write_text(json.dumps(helper, indent=2, ensure_ascii=False))
        # Per-process libraries
        for process in self.questionnaires:
            lib = self.generate_library(process, version)
            (lib_dir / f"{lib['id']}.json").write_text(json.dumps(lib, indent=2, ensure_ascii=False))
            # Also write raw .cql for readability
            cql_content = base64.b64decode(lib["content"][0]["data"]).decode()
            (lib_dir / f"{lib['id']}.cql").write_text(cql_content)
            logger.debug(f"Wrote Library: {lib['id']}")

    def _write_structuremaps(self, base: Path):
        """Write StructureMap JSON files.

        Args:
            base: Base output directory path.
        """
        sm_dir = base / "structure-map"
        sm_dir.mkdir(parents=True, exist_ok=True)
        for process, sm in self.structuremaps.items():
            path = sm_dir / f"{sm['id']}.json"
            path.write_text(json.dumps(sm, indent=2, ensure_ascii=False))
            logger.debug(f"Wrote StructureMap: {path}")

    def _write_valuesets(self, base: Path):
        """Write ValueSet JSON files.

        Args:
            base: Base output directory path.
        """
        vs_dir = base / "ValueSet"
        vs_dir.mkdir(parents=True, exist_ok=True)
        for vs_id, vs in self.valuesets.items():
            path = vs_dir / f"{vs_id}.json"
            path.write_text(json.dumps(vs, indent=2, ensure_ascii=False))
            logger.debug(f"Wrote ValueSet: {path}")

    def _write_binaries(self, base: Path):
        """Write Binary JSON files (images).

        Args:
            base: Base output directory path.
        """
        bin_dir = base / "binary"
        bin_dir.mkdir(parents=True, exist_ok=True)
        for binary in self.binaries:
            path = bin_dir / f"{binary['id']}.json"
            path.write_text(json.dumps(binary, indent=2, ensure_ascii=False))
            logger.debug(f"Wrote Binary: {path}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _prune_empty_groups(self, questionnaire: dict) -> None:
        """Recursively remove empty groups from a Questionnaire.

        Args:
            questionnaire: Questionnaire resource dict to prune.
        """
        def prune_items(items: List[dict]) -> None:
            to_remove = []
            for item in items:
                if item.get("type") == "group":
                    g_items = item.get("item", [])
                    prune_items(g_items)
                    if g_items == []:
                        to_remove.append(item)
            for item in to_remove:
                items.remove(item)

        prune_items(questionnaire.get("item", []))

    def _find_item(self, questionnaire: dict, link_id: str) -> Optional[dict]:
        """Find a Questionnaire item by linkId (recursive).

        Args:
            questionnaire: Questionnaire resource dict.
            link_id: The linkId to search for.

        Returns:
            Item dict if found, else None.
        """
        for item in questionnaire.get("item", []):
            if item.get("linkId") == link_id:
                return item
            sub = self._find_item(item, link_id)
            if sub:
                return sub
        return None

    # ── Expression conversion ─────────────────────────────────────────────────

    def get_tricc_operation_expression(self, operation) -> str:
        """Convert a TriccOperation to a CQL expression string.

        Args:
            operation: TriccOperation or operand to convert.

        Returns:
            CQL expression string.

        Raises:
            NotImplementedError: If the operator is not supported.
        """
        if not hasattr(operation, "reference"):
            return self._operand_to_cql(operation)
        ref_expressions = []
        original_references = []
        for r in operation.reference:
            if isinstance(r, list):
                ref_expressions.append([
                    self.get_tricc_operation_expression(sr) if isinstance(sr, TriccOperation)
                    else self._operand_to_cql(sr)
                    for sr in r
                ])
                original_references.append(r)
            elif isinstance(r, TriccOperation):
                ref_expressions.append(self.get_tricc_operation_expression(r))
                original_references.append(r)
            else:
                ref_expressions.append(self._operand_to_cql(r))
                original_references.append(r)

        method = f"tricc_operation_{operation.operator}"
        if hasattr(self, method):
            return getattr(self, method)(ref_expressions, original_references)
        raise NotImplementedError(f"CQL: operator '{operation.operator}' not implemented")

    def convert_expression_to_cql(self, expression) -> str:
        """Convert a TRICC expression to CQL.

        Args:
            expression: TriccOperation, TriccStatic, TriccReference, or node.

        Returns:
            CQL expression string.
        """
        if isinstance(expression, TriccOperation):
            return self.get_tricc_operation_expression(expression)
        return self._operand_to_cql(expression)

    def convert_expression_to_fhirpath(self, expression) -> str:
        """Convert a TRICC expression to FHIRPath.

        Args:
            expression: TriccOperation, TriccStatic, TriccReference, or node.

        Returns:
            FHIRPath expression string.
        """
        if isinstance(expression, TriccOperation):
            return self._operation_to_fhirpath(expression)
        return self._operand_to_fhirpath(expression)

    def _operation_to_fhirpath(self, operation, add_first_value: bool = True, is_cql: bool = False) -> str:
        """Recursively convert a TriccOperation to FHIRPath.

        Args:
            operation: TriccOperation to convert.
            add_first_value: If True (default), append .first().value to reference/node
                            operands for scalar contexts. If False, emit just the
                            .answer list reference for list-aware operations.
            is_cql: If True, this conversion is for CQL context (no .first().value).

        Returns:
            FHIRPath expression string.
        """
        if not hasattr(operation, "reference"):
            return self._operand_to_fhirpath(operation, add_first_value=add_first_value and not is_cql)

        # Determine context for operands: list-aware operators don't add .first().value
        operand_context = (add_first_value and operation.operator not in LIST_CONTEXT_OPERATORS) and not is_cql

        ref_expressions = []
        original_references = []
        for r in operation.reference:
            if isinstance(r, list):
                ref_expressions.append([
                    self._operation_to_fhirpath(sr, add_first_value=operand_context, is_cql=is_cql) if isinstance(sr, TriccOperation)
                    else self._operand_to_fhirpath(sr, add_first_value=operand_context)
                    for sr in r
                ])
                original_references.append(r)
            elif isinstance(r, TriccOperation):
                ref_expressions.append(self._operation_to_fhirpath(r, add_first_value=operand_context, is_cql=is_cql))
                original_references.append(r)
            else:
                ref_expressions.append(self._operand_to_fhirpath(r, add_first_value=operand_context))
                original_references.append(r)

        fp_method = f"tricc_operation_fhirpath_{operation.operator}"
        cql_method = f"tricc_operation_{operation.operator}"
        if hasattr(self, fp_method):
            return getattr(self, fp_method)(ref_expressions, original_references, is_cql=is_cql)
        if hasattr(self, cql_method):
            return getattr(self, cql_method)(ref_expressions, original_references)
        raise NotImplementedError(f"FHIRPath: operator '{operation.operator}' not implemented")

    def _operand_to_fhirpath(self, r, add_first_value: bool = True) -> str:
        """Convert a single operand to a FHIRPath string.

        Handles nested references via repeat(item) which walks groups automatically.

        Args:
            r: Operand (TriccReference, TriccStatic, node, or primitive).
            add_first_value: If True (default), append .first().value to reference/node
                            expressions for scalar contexts. If False, emit just the
                            .answer list reference for list-aware operations.

        Returns:
            FHIRPath string representation.
        """
        if isinstance(r, TriccOperation):
            return self._operation_to_fhirpath(r, add_first_value=add_first_value)
        if isinstance(r, TriccReference):
            link_id = r.value
            base_expr = f"%resource.repeat(item).where(linkId='{link_id}').answer"
            return f"{base_expr}.first().value" if add_first_value else base_expr
        if isinstance(r, TriccStatic):
            return f"'{r.value}'" if isinstance(r.value, str) else str(r.value)
        if isinstance(r, str):
            return f"'{r}'"
        if isinstance(r, (int, float, bool)):
            return str(r).lower() if isinstance(r, bool) else str(r)
        if isinstance(r, TriccNodeSelectOption):
            return f"'{r.name}'"
        if issubclass(r.__class__, TriccNodeBaseModel):
            link_id = get_export_name(r)
            base_expr = f"%resource.repeat(item).where(linkId='{link_id}').answer"
            return f"{base_expr}.first().value" if add_first_value else base_expr
        raise NotImplementedError(f"FHIRPath operand type not supported: {r.__class__}")

    def _operand_to_cql(self, r) -> str:
        """Convert a single operand to a CQL string.

        Args:
            r: Operand (TriccReference, TriccStatic, node, or primitive).

        Returns:
            CQL string representation.
        """
        if isinstance(r, TriccOperation):
            return self.get_tricc_operation_expression(r)
        if isinstance(r, TriccReference):
            return f'"{r.value}"'
        if isinstance(r, TriccStatic):
            return f"'{r.value}'" if isinstance(r.value, str) else str(r.value)
        if isinstance(r, str):
            return f"'{r}'"
        if isinstance(r, (int, float, bool)):
            return str(r).lower() if isinstance(r, bool) else str(r)
        if isinstance(r, TriccNodeSelectOption):
            return f"'{r.name}'"
        if issubclass(r.__class__, TriccNodeBaseModel):
            return f'"{get_export_name(r)}"'
        raise NotImplementedError(f"CQL operand type not supported: {r.__class__}")

    # ── CQL operator implementations ──────────────────────────────────────────

    def tricc_operation_equal(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_equal(ref_expressions, original_references, is_cql=True)

    def tricc_operation_not_equal(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_not_equal(ref_expressions, original_references, is_cql=True)

    def tricc_operation_and(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_and(ref_expressions, original_references, is_cql=True)

    def tricc_operation_and_or(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]}) and ({' or '.join(ref_expressions[1:])})"

    def tricc_operation_or(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_or(ref_expressions, original_references, is_cql=True)

    def tricc_operation_not(self, ref_expressions, original_references=None):
        return f"not({ref_expressions[0]})"

    def tricc_operation_istrue(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_istrue(ref_expressions, original_references, is_cql=True)

    def tricc_operation_isnottrue(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_isnottrue(ref_expressions, original_references, is_cql=True)

    def tricc_operation_isfalse(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_isfalse(ref_expressions, original_references, is_cql=True)

    def tricc_operation_isnotfalse(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_isnotfalse(ref_expressions, original_references, is_cql=True)

    def tricc_operation_isnull(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} is null"

    def tricc_operation_isnotnull(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} is not null"

    def tricc_operation_exists(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_exists(ref_expressions, original_references, is_cql=True)

    def tricc_operation_notexists(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_notexists(ref_expressions, original_references, is_cql=True)

    def tricc_operation_more(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_more(ref_expressions, original_references, is_cql=True)

    def tricc_operation_less(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_less(ref_expressions, original_references, is_cql=True)

    def tricc_operation_more_or_equal(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_more_or_equal(ref_expressions, original_references, is_cql=True)

    def tricc_operation_less_or_equal(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_less_or_equal(ref_expressions, original_references, is_cql=True)

    def tricc_operation_between(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} >= {ref_expressions[1]} and {ref_expressions[0]} <= {ref_expressions[2]}"

    def tricc_operation_plus(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_plus(ref_expressions, original_references, is_cql=True)

    def tricc_operation_minus(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_minus(ref_expressions, original_references, is_cql=True)

    def tricc_operation_multiplied(self, ref_expressions, original_references=None):
        return " * ".join(ref_expressions)

    def tricc_operation_divided(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} / {ref_expressions[1]}"

    def tricc_operation_modulo(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} mod {ref_expressions[1]}"

    def tricc_operation_round(self, ref_expressions, original_references=None):
        return f"Round({ref_expressions[0]}, {ref_expressions[1] if len(ref_expressions) > 1 else '0'})"

    def tricc_operation_abs(self, ref_expressions, original_references=None):
        return f"Abs({ref_expressions[0]})"

    def tricc_operation_min(self, ref_expressions, original_references=None):
        return f"Min({{{', '.join(ref_expressions)}}})"

    def tricc_operation_max(self, ref_expressions, original_references=None):
        return f"Max({{{', '.join(ref_expressions)}}})"

    def tricc_operation_sum(self, ref_expressions, original_references=None):
        return f"Sum({{{', '.join(ref_expressions)}}})"

    def tricc_operation_count(self, ref_expressions, original_references=None):
        return f"Count({ref_expressions[0]})"

    def tricc_operation_coalesce(self, ref_expressions, original_references=None):
        return f"Coalesce({', '.join(ref_expressions)})"

    def tricc_operation_cast_number(self, ref_expressions, original_references=None):
        return f"ToDecimal({ref_expressions[0]})"

    def tricc_operation_cast_integer(self, ref_expressions, original_references=None):
        return f"ToInteger({ref_expressions[0]})"

    def tricc_operation_cast_string(self, ref_expressions, original_references=None):
        return f"ToString({ref_expressions[0]})"

    def tricc_operation_cast_boolean(self, ref_expressions, original_references=None):
        return f"ToBoolean({ref_expressions[0]})"

    def tricc_operation_cast_date(self, ref_expressions, original_references=None):
        return f"ToDate({ref_expressions[0]})"

    def tricc_operation_concatenate(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_plus(ref_expressions, original_references, is_cql=True)

    def tricc_operation_contains(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} contains {ref_expressions[1]}"

    def tricc_operation_selected(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} contains {ref_expressions[1]}"

    def tricc_operation_native(self, ref_expressions, original_references=None):
        return ref_expressions[0] if ref_expressions else ""

    def tricc_operation_parenthesis(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]})"

    def tricc_operation_if(self, ref_expressions, original_references=None):
        # if cond then val_true else val_false
        if len(ref_expressions) >= 2:
            return f"if {ref_expressions[0]} then {ref_expressions[1]} else {ref_expressions[2] if len(ref_expressions) > 2 else 'null'}"
        return ref_expressions[0] if ref_expressions else "null"

    def tricc_operation_ifs(self, ref_expressions, original_references=None):
        parts = []
        for pair in ref_expressions:
            if isinstance(pair, list) and len(pair) == 2:
                parts.append(f"if {pair[0]} then {pair[1]}")
        return " else ".join(parts) + " else null" if parts else "null"

    def tricc_operation_case(self, ref_expressions, original_references=None):
        parts = []
        for pair in ref_expressions:
            if isinstance(pair, list) and len(pair) == 2:
                parts.append(f"when {pair[0]} then {pair[1]}")
        return f"case {' '.join(parts)} else null end" if parts else "null"

    def tricc_operation_age_day(self, ref_expressions, original_references=None):
        return "duration in days between Patient.birthDate and Today()"

    def tricc_operation_age_month(self, ref_expressions, original_references=None):
        return "duration in months between Patient.birthDate and Today()"

    def tricc_operation_age_year(self, ref_expressions, original_references=None):
        return "AgeInYears()"

    def tricc_operation_today(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_today(ref_expressions, original_references, is_cql=True)

    def tricc_operation_now(self, ref_expressions, original_references=None):
        return self.tricc_operation_fhirpath_now(ref_expressions, original_references, is_cql=True)

    def tricc_operation_length(self, ref_expressions, original_references=None):
        return f"Length({ref_expressions[0]})"

    def tricc_operation_format_date(self, ref_expressions, original_references=None):
        return f"ToString({ref_expressions[0]})"

    def tricc_operation_datetime_to_decimal(self, ref_expressions, original_references=None):
        return f"ToDecimal(duration in days between {ref_expressions[0]} and Today())"

    def tricc_operation_zscore(self, ref_expressions, original_references=None):
        return f"Helper.ZScore({', '.join(ref_expressions)})"

    def tricc_operation_izscore(self, ref_expressions, original_references=None):
        return f"Helper.IZScore({', '.join(ref_expressions)})"

    def tricc_operation_drug_dosage(self, ref_expressions, original_references=None):
        return f"Helper.DrugDosage({', '.join(ref_expressions)})"

    def tricc_operation_has_qualifier(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]}.qualifier contains {ref_expressions[1]}"

    def tricc_operation_diagnosis_list(self, ref_expressions, original_references=None):
        return f"Combine({', '.join(ref_expressions)}, ', ')"

    # ── FHIRPath operator implementations ──────────────────────────────────────



    def tricc_operation_fhirpath_count(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"{ref_expressions[0]}.count())"

    def tricc_operation_fhirpath_equal(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"{ref_expressions[0]} = {ref_expressions[1]}"

    def tricc_operation_fhirpath_not_equal(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"{ref_expressions[0]} != {ref_expressions[1]}"

    def tricc_operation_fhirpath_and(self, ref_expressions, original_references=None, is_cql: bool = False):
        return " and ".join(ref_expressions)

    def tricc_operation_fhirpath_or(self, ref_expressions, original_references=None, is_cql: bool = False):
        return " or ".join(ref_expressions)

    def tricc_operation_fhirpath_not(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"({ref_expressions[0]}).not()"

    def tricc_operation_fhirpath_istrue(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"({ref_expressions[0]}) = true"

    def tricc_operation_fhirpath_isnottrue(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"({ref_expressions[0]}) != true"

    def tricc_operation_fhirpath_isfalse(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"({ref_expressions[0]}) = false"

    def tricc_operation_fhirpath_isnotfalse(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"({ref_expressions[0]}) != false"

    def tricc_operation_fhirpath_isnull(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"({ref_expressions[0]}).empty()"

    def tricc_operation_fhirpath_isnotnull(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"({ref_expressions[0]}).exists()"

    def tricc_operation_fhirpath_exists(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"({ref_expressions[0]}).exists()"

    def tricc_operation_fhirpath_notexists(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"({ref_expressions[0]}).empty()"

    def tricc_operation_fhirpath_more(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"{ref_expressions[0]} > {ref_expressions[1]}"

    def tricc_operation_fhirpath_less(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"{ref_expressions[0]} < {ref_expressions[1]}"

    def tricc_operation_fhirpath_more_or_equal(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"{ref_expressions[0]} >= {ref_expressions[1]}"

    def tricc_operation_fhirpath_less_or_equal(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"{ref_expressions[0]} <= {ref_expressions[1]}"

    def tricc_operation_fhirpath_selected(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"({ref_expressions[0]}).where($this = {ref_expressions[1]}).exists()"

    def tricc_operation_fhirpath_contains(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"({ref_expressions[0]}).contains({ref_expressions[1]})"

    def tricc_operation_fhirpath_plus(self, ref_expressions, original_references=None, is_cql: bool = False):
        return " + ".join(ref_expressions)

    def tricc_operation_fhirpath_minus(self, ref_expressions, original_references=None, is_cql: bool = False):
        return " - ".join(ref_expressions) if len(ref_expressions) > 1 else f"-{ref_expressions[0]}"

    def tricc_operation_fhirpath_coalesce(self, ref_expressions, original_references=None, is_cql: bool = False):
        return f"iif({ref_expressions[0]}.exists(), {ref_expressions[0]}, {', '.join(ref_expressions[1:])})" if len(ref_expressions) > 1 else ref_expressions[0]

    def tricc_operation_fhirpath_age_day(self, ref_expressions, original_references=None, is_cql: bool = False):
        return "(today() - Patient.birthDate).value"

    def tricc_operation_fhirpath_age_month(self, ref_expressions, original_references=None, is_cql: bool = False):
        return "Patient.birthDate.memberOf('http://hl7.org/fhir/ValueSet/age-units')"

    def tricc_operation_fhirpath_today(self, ref_expressions, original_references=None, is_cql: bool = False):
        return "today()"

    def tricc_operation_fhirpath_now(self, ref_expressions, original_references=None, is_cql: bool = False):
        return "now()"

    def get_kwargs(self) -> dict:
        """Return extra kwargs passed to node callbacks."""
        return {}

