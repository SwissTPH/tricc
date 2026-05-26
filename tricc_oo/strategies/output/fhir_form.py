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
    build_initial_expression_cql,
    build_calculated_expression,
    get_display_type_extensions,
    get_fhir_item_type,
    is_hidden,
    is_repeating,
    should_skip,
)
from tricc_oo.converters.tricc_to_xls_form import get_export_name
from tricc_oo.converters.datadictionnary import lookup_codesystems_code
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
    TriccNodeDisplayModel, 
)
from tricc_oo.models.calculate import TriccNodeDisplayCalculateBase
from tricc_oo.converters.tricc_to_xls_form import get_export_name
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
    project = None
    output_path = None

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
        self.base_url = (base_url or "https://fhir.tricc").rstrip("/")
        self.use_value_sets = use_value_sets
        self.questionnaires: Dict[str, dict] = {}
        self.cql_defines: Dict[str, List[str]] = {}
        self.structuremaps: Dict[str, dict] = {}
        self.valuesets: Dict[str, dict] = {}
        self.binaries: List[dict] = []
        self._form_id: Optional[str] = None
        self.cur_group: Optional[dict] = None
        self.cql_libraries = {} # FIXME
        self.fml_mappings = {}

    def get_tricc_operation_expression(self, operation):
        # For CQL
        ref_expressions = []
        original_references = []
        if not hasattr(operation, "reference"):
            return self.get_tricc_operation_operand(operation)
        for r in operation.reference:
            if isinstance(r, list):
                r_expr = [
                    (
                        self.get_tricc_operation_expression(sr)
                        if isinstance(sr, TriccOperation)
                        else self.get_tricc_operation_operand(sr)
                    )
                    for sr in r
                ]
                original_references.append(r)
            elif isinstance(r, TriccOperation):
                r_expr = self.get_tricc_operation_expression(r)
                original_references.append(r)
            else:
                r_expr = self.get_tricc_operation_operand(r)
                original_references.append(r)
            if isinstance(r_expr, TriccReference):
                r_expr = self.get_tricc_operation_operand(r_expr)
            ref_expressions.append(r_expr)

        # build lower level
        if hasattr(self, f"tricc_operation_{operation.operator}"):
            callable = getattr(self, f"tricc_operation_{operation.operator}")
            return callable(ref_expressions, original_references)
        else:
            raise NotImplementedError(
                f"This type of operation '{operation.operator}' is not supported in this strategy"
            )

    def execute(self):
        """Run the full FHIR export pipeline."""
        version = datetime.datetime.now().strftime("%Y%m%d%H%M")
        logger.info(f"FHIRStrategy: build version {version}")
        if "main" in self.project.start_pages:
            self.process_base(self.project.start_pages, pages=self.project.pages, version=version)
        else:
            logger.critical("Main process required")
            return


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

    def generate_base(self, node, **kwargs):
        if (
            not issubclass(node.__class__, (TriccNodeDisplayModel, TriccNodeDisplayCalculateBase)) 
            or isinstance(node, TriccNodeSelectOption)
        ):
            return True
        # Generate Questionnaire items per segment
        segment = getattr(node, 'segment', 'main')
        if segment not in self.questionnaires:
            self.questionnaires[segment] = {
                "resourceType": "Questionnaire",
                "id": f"questionnaire-{segment}",
                "url": f"http://example.com/Questionnaire/{segment}",
                "status": "draft",
                "item": []
            }
        item = {
            "linkId": get_export_name(node),
            "text": getattr(node, 'label', ''),
            "type": self.map_tricc_type_to_fhir(node.tricc_type if hasattr(node, 'tricc_type') else 'text')
        }
        item["extension"] = []
        if isinstance(node, TriccNodeDisplayCalculateBase):
            item["extension"] = [
                self.get_hidden_extention()
            ]
        if hasattr(node, 'options') and node.options:
            item["answerOption"] = []
            for opt in node.options.values():
                concept = lookup_codesystems_code(self.project.code_systems, opt.name)
                if concept:
                    item["answerOption"].append(
                        {
                            "valueCoding": {
                                "code": concept.code,
                                "display": concept.display
                            }
                        } 
                    )
                else:
                    item["answerOption"].append(
                        {
                            "valueCoding": {
                                "code": opt.name,
                                "display": getattr(opt, 'label', opt.name)
                            }
                        }
                    )

        self.questionnaires[segment]["item"].append(item)
        return True

    def get_hidden_extention(self):
        return {
            "url": "http://hl7.org/fhir/StructureDefinition/questionnaire-hidden",
            "valueBoolean": True
        }


    def get_enable_when_extention(self, expr, language="text/fhirpath"):
        return {
                "url": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-enableWhenExpression",
                "valueExpression": {
                    "language": language,
                    "expression": expr
                }
            }

    def generate_relevance(self, node, **kwargs):
        # Add enableWhen to Questionnaire item with FHIRPath
        if hasattr(node, 'relevance') and node.relevance:
            segment = getattr(node, 'segment', 'main')
            if segment in self.questionnaires:
                for item in self.questionnaires[segment]["item"]:
                    if item["linkId"] == get_export_name(node):
                        # Use FHIRPath expression
                        fhirpath_expr = self.convert_expression_to_fhirpath(node.relevance)
                        # Alternatively, use expression for complex logic
                        if fhirpath_expr == 'false':
                            item["extension"].append(self.get_hidden_extention())
                        elif fhirpath_expr != 'true':
                            item["extension"].append(self.get_enable_when_extention(fhirpath_expr) )
                        break
        return True

    def generate_calculate(self, node, **kwargs):
        segment = getattr(node, "segment", "main")
        q = self.questionnaires.get(segment)
        if q:
            for item in q.get("item", []):
                if item.get("linkId") == get_export_name(node):
                    build_calculated_expression(item, node)
                    break
        return True

    def generate_export(self, node, **kwargs):
        # Generate FML for saving based on content_type
        content_type = getattr(node, 'content_type', 'Observation')
        if content_type not in self.fml_mappings:
            self.fml_mappings[content_type] = f"map \"{content_type}\" {{\n"
        # Add mapping rules
        self.fml_mappings[content_type] += f"  {get_export_name(node)} -> {content_type}.{get_export_name(node)}\n"
        return True

    def export(self, start_pages, version):
        form_id = start_pages["main"].root.form_id or "fhir_form"
        base_path = os.path.join(self.output_path, form_id)
        if not os.path.exists(base_path):
            os.makedirs(base_path)

        # Export Questionnaires
        for segment, q in self.questionnaires.items():
            file_name = f"{segment}.json"
            path = os.path.join(base_path, file_name)
            with open(path, 'w') as f:
                json.dump(q, f, indent=2)

        # Export CQL
        for segment, cql in self.cql_libraries.items():
            file_name = f"{segment}.cql"
            path = os.path.join(base_path, file_name)
            with open(path, 'w') as f:
                f.write(cql)

        # Export FML
        for content_type, fml in self.fml_mappings.items():
            fml += "}\n"
            file_name = f"{content_type}.map"
            path = os.path.join(base_path, file_name)
            with open(path, 'w') as f:
                f.write(fml)

        logger.info(f"Exported FHIR resources to {base_path}")

    def map_tricc_type_to_fhir(self, tricc_type):
        mapping = {
            'text': 'string',
            'integer': 'integer',
            'decimal': 'decimal',
            'select_one': 'choice',
            'select_multiple': 'choice',
            'date': 'date',
            'time': 'time',
            'datetime': 'dateTime',
            'boolean': 'boolean'
        }
        return mapping.get(tricc_type, 'string')

    def get_question_link(self, expression):
        # Simplified, assume first reference
        if isinstance(expression, TriccOperation) and hasattr(expression, 'reference'):
            for r in expression.reference:
                if isinstance(r, TriccReference):
                    return get_export_name(r.value)
        return ""

    def get_answer_value(self, expression):
        # Simplified
        return "true"

    def get_tricc_operation_operand(self, r):
        if isinstance(r, TriccOperation):
            return self.get_tricc_operation_expression(r)
        elif isinstance(r, TriccReference):
            return get_export_name(r.value)
        elif isinstance(r, TriccStatic):
            if isinstance(r.value, str):
                value = f"'{r.value}'"
            else:
                value = str(r.value)
            if value == "True":
                return "true"
            elif value == "False":
                return "false"
            else:
                return value
        elif isinstance(r, bool):
            return 'true' if r else 'false'
        elif isinstance(r, str):
            return f"'{r}'"
        elif isinstance(r, (int, float)):
            return str(r)
        elif isinstance(r, TriccNodeSelectOption):
            return f"'{r.name}'"
        elif issubclass(r.__class__, TriccNodeInputModel):
            return get_export_name(r)
        elif issubclass(r.__class__, TriccNodeBaseModel):
            return get_export_name(r)
        else:
            raise NotImplementedError(f"This type of node {r.__class__} is not supported within an operation")

    def convert_expression_to_cql(self, expression):
        if isinstance(expression, TriccOperation):
            return self.get_tricc_operation_expression(expression)
        else:
            return self.get_tricc_operation_operand(expression)

    def convert_expression_to_fhirpath(self, expression):
        # For FHIRPath, similar to CQL but in FHIR context
        # For questionnaire, references to other questions
        if isinstance(expression, TriccOperation):
            return self.get_tricc_operation_expression_fhirpath(expression)
        else:
            return self.get_tricc_operation_operand_fhirpath(expression)

    def _wrap_operand_if_needed(self, r_expr, original_ref) -> str:
        """Wrap a single operand expression with .where($this.exists()).first()
        if the original reference is a Questionnaire answer collection.

        - TriccOperation references are *not* wrapped (the inner operation
          already handles its own scalar output).
        - List sub-references are wrapped element-by-element.
        - TriccReference / TriccNodeInputModel / TriccNodeBaseModel references
          produce answer collections and therefore need the wrapper.
        """
        if isinstance(original_ref, TriccOperation):
            # Inner operation already returns a scalar – do not double-wrap.
            return r_expr

        if isinstance(original_ref, list):
            # Each element in the list is an independent sub-reference.
            for o_r in original_ref:
                r_expr = self._wrap_operand_if_needed(r_expr, o_r)
            # Fallback: treat the whole list expression as a single item.
            return r_expr

        if self._should_wrap_first(original_ref):
            search = self.get_tricc_operation_operand_fhirpath(original_ref)
            replace = f"{search}.where($this.exists()).value"
            return r_expr.replace(search, replace)

        return r_expr

    def get_tricc_operation_expression_fhirpath(self, operation):
        ref_expressions = []
        original_references = []
        if not hasattr(operation, "reference"):
            return self.get_tricc_operation_operand_fhirpath(operation)
        for r in operation.reference:
            if isinstance(r, list):
                r_expr = [
                    (
                        self.get_tricc_operation_expression_fhirpath(sr)
                        if isinstance(sr, TriccOperation)
                        else self.get_tricc_operation_operand_fhirpath(sr)
                    )
                    for sr in r
                ]
                original_references.append(r)
            elif isinstance(r, TriccOperation):
                r_expr = self.get_tricc_operation_expression_fhirpath(r)
                original_references.append(r)
            else:
                r_expr = self.get_tricc_operation_operand_fhirpath(r)
                original_references.append(r)
            if isinstance(r_expr, TriccReference):
                r_expr = self.get_tricc_operation_operand_fhirpath(r_expr)
            # ───────────────────────────────────────────────────────────────
            ref_expressions.append(r_expr)

        if hasattr(self, f"tricc_operation_fhirpath_{operation.operator}"):
            callable = getattr(self, f"tricc_operation_fhirpath_{operation.operator}")
            return callable(ref_expressions, original_references)
        else:
            # Fallback to CQL operations
            if hasattr(self, f"tricc_operation_{operation.operator}"):
                callable = getattr(self, f"tricc_operation_{operation.operator}")
                return callable(ref_expressions, original_references)
            else:
                raise NotImplementedError(
                    f"This type of operation '{operation.operator}' is not supported"
                )

    def get_tricc_operation_operand_fhirpath(self, r):
        if isinstance(r, TriccOperation):
            return self.get_tricc_operation_expression_fhirpath(r)
        elif isinstance(r, TriccReference):
            # In FHIRPath, reference to another question's answer
            return f"%resource.item.where(linkId='{get_export_name(r.value)}').answer"
        elif isinstance(r, TriccStatic):
            if isinstance(r.value, str):
                value = f"'{r.value}'"
            else:
                value = str(r.value)
            if value == "True":
                return "true"
            elif value == "False":
                return "false"
            else:
                return value
        elif isinstance(r, bool):
            return 'true' if r else 'false'
        elif isinstance(r, str):
            return f"'{r}'"
        elif isinstance(r, (int, float)):
            return str(r)
        elif isinstance(r, TriccNodeSelectOption):
            return f"'{r.name}'"
        elif issubclass(r.__class__, TriccNodeInputModel):
            return f"%resource.item.where(linkId='{get_export_name(r)}').answer"
        elif issubclass(r.__class__, TriccNodeBaseModel):
            return f"%resource.item.where(linkId='{get_export_name(r)}').answer"
        else:
            raise NotImplementedError(f"This type of node {r.__class__} is not supported within an operation")

    # FHIRPath operations, same as CQL for now
    def tricc_operation_fhirpath_equal(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} = {ref_expressions[1]}"

    def tricc_operation_fhirpath_not_equal(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} != {ref_expressions[1]}"

    def tricc_operation_fhirpath_and(self, ref_expressions, original_references=None):
        return " and ".join(ref_expressions)

    def tricc_operation_fhirpath_or(self, ref_expressions, original_references=None):
        return " or ".join(ref_expressions)

    def tricc_operation_fhirpath_not(self, ref_expressions, original_references=None):
        return f"not {ref_expressions[0]}"

    def tricc_operation_fhirpath_plus(self, ref_expressions, original_references=None):
        return " + ".join(ref_expressions)

    def tricc_operation_fhirpath_minus(self, ref_expressions, original_references=None):
        if len(ref_expressions) > 1:
            return " - ".join(ref_expressions)
        return f"-{ref_expressions[0]}"

    def tricc_operation_fhirpath_more(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} > {ref_expressions[1]}"

    def tricc_operation_fhirpath_less(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} < {ref_expressions[1]}"

    def tricc_operation_fhirpath_more_or_equal(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} >= {ref_expressions[1]}"

    def tricc_operation_fhirpath_less_or_equal(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} <= {ref_expressions[1]}"

    # Operation methods for CQL
    def tricc_operation_equal(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} = {ref_expressions[1]}"

    def tricc_operation_not_equal(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} != {ref_expressions[1]}"

    def tricc_operation_and(self, ref_expressions, original_references=None):
        return " and ".join(ref_expressions)

    def tricc_operation_or(self, ref_expressions, original_references=None):
        return " or ".join(ref_expressions)

    def tricc_operation_not(self, ref_expressions, original_references=None):
        return f"not {ref_expressions[0]}"

    def tricc_operation_plus(self, ref_expressions, original_references=None):
        return " + ".join(ref_expressions)

    def tricc_operation_minus(self, ref_expressions, original_references=None):
        if len(ref_expressions) > 1:
            return " - ".join(ref_expressions)
        return f"-{ref_expressions[0]}"

    def tricc_operation_more(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} > {ref_expressions[1]}"

    def tricc_operation_less(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} < {ref_expressions[1]}"

    def tricc_operation_more_or_equal(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} >= {ref_expressions[1]}"

    def tricc_operation_less_or_equal(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]} <= {ref_expressions[1]}"

    # ============================================================
    # HELPER: Flexible .first() for FHIRPath only (per operation level)
    # ============================================================
    def _should_wrap_first(self, original_ref) -> bool:
        """Return True if the original reference is known to produce a collection
        that needs .first() in FHIRPath."""
        if original_ref is None:
            return False
        if isinstance(original_ref,  (TriccStatic, str, TriccOperation, TriccNodeSelectOption)):
            return False
        if isinstance(original_ref, TriccReference):
            return True
        if isinstance(original_ref, (TriccNodeInputModel, TriccNodeBaseModel)):
            return True
        return False


    # ============================================================
    # BOOLEAN / LOGICAL OPERATORS
    # ============================================================
    def tricc_operation_istrue(self, ref_expressions, original_references=None):
        # CQL: treat as identity or explicit comparison
        return f"({ref_expressions[0]} is true)"

    def tricc_operation_isnottrue(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]} is not true)"

    def tricc_operation_isfalse(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]} is false)"

    def tricc_operation_isnotfalse(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]} is not false)"

    def tricc_operation_isnull(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]} is null)"

    def tricc_operation_isnotnull(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]} is not null)"

    def tricc_operation_selected(self, ref_expressions, original_references=None):
        # ref[0] is the select field, remaining refs are the option values

        return f"({ref_expressions[1]} in {ref_expressions[0]})"

    def tricc_operation_between(self, ref_expressions, original_references=None):
        # ref[0] between low and high
        if len(ref_expressions) >= 3:
            return f"({ref_expressions[0]} between {ref_expressions[1]} and {ref_expressions[2]})"
        return ref_expressions[0]

    def tricc_operation_contains(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]} contains {ref_expressions[1]})"

    def tricc_operation_exists(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]} is not null)"

    def tricc_operation_notexists(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]} is null)"

    def tricc_operation_has_qualifier(self, ref_expressions, original_references=None):
        # Not implemented for now (CDSS specific)
        raise NotImplementedError("HAS_QUALIFIER is not supported yet")

    # ============================================================
    # ARITHMETIC OPERATORS
    # ============================================================
    def tricc_operation_divided(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]} / {ref_expressions[1]})"

    def tricc_operation_multiplied(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]} * {ref_expressions[1]})"

    def tricc_operation_modulo(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]} mod {ref_expressions[1]})"

    def tricc_operation_round(self, ref_expressions, original_references=None):
        return f"Round({ref_expressions[0]})"

    def tricc_operation_abs(self, ref_expressions, original_references=None):
        return f"Abs({ref_expressions[0]})"

    def tricc_operation_min(self, ref_expressions, original_references=None):
        # MIN of a list -> use Min() aggregate
        items = ", ".join(ref_expressions)
        return f"Min({{{items}}})"

    def tricc_operation_max(self, ref_expressions, original_references=None):
        items = ", ".join(ref_expressions)
        return f"Max({{{items}}})"

    def tricc_operation_sum(self, ref_expressions, original_references=None):
        items = ", ".join(ref_expressions)
        return f"Sum({{{items}}})"

    def tricc_operation_count(self, ref_expressions, original_references=None):
        items = ", ".join(ref_expressions)
        return f"Count({{{items}}})"

    # ============================================================
    # CASTING & CONVERSION
    # ============================================================
    def tricc_operation_cast_number(self, ref_expressions, original_references=None):
        return f"ToDecimal({ref_expressions[0]})"

    def tricc_operation_cast_integer(self, ref_expressions, original_references=None):
        return f"ToInteger({ref_expressions[0]})"

    def tricc_operation_cast_date(self, ref_expressions, original_references=None):
        return f"ToDate({ref_expressions[0]})"

    def tricc_operation_cast_string(self, ref_expressions, original_references=None):
        return f"ToString({ref_expressions[0]})"

    def tricc_operation_cast_boolean(self, ref_expressions, original_references=None):
        return f"ToBoolean({ref_expressions[0]})"

    def tricc_operation_datetime_to_decimal(self, ref_expressions, original_references=None):
        return f"ToDecimal({ref_expressions[0]})"

    # ============================================================
    # STRING OPERATORS
    # ============================================================
    def tricc_operation_concatenate(self, ref_expressions, original_references=None):
        return " + ".join(ref_expressions)

    def tricc_operation_length(self, ref_expressions, original_references=None):
        return f"Length({ref_expressions[0]})"

    def tricc_operation_diagnosis_list(self, ref_expressions, original_references=None):
        # Return as-is (string list)
        return ref_expressions[0] if ref_expressions else "''"

    # ============================================================
    # DATE / TIME OPERATORS
    # ============================================================
    def tricc_operation_today(self, ref_expressions, original_references=None):
        return "Today()"

    def tricc_operation_now(self, ref_expressions, original_references=None):
        return "Now()"

    def tricc_operation_age_day(self, ref_expressions, original_references=None):
        return f"AgeInDays({ref_expressions[0]})"

    def tricc_operation_age_month(self, ref_expressions, original_references=None):
        return f"AgeInMonths({ref_expressions[0]})"

    def tricc_operation_age_year(self, ref_expressions, original_references=None):
        return f"AgeInYears({ref_expressions[0]})"

    def tricc_operation_format_date(self, ref_expressions, original_references=None):
        # ref[0] = date, ref[1] = format string (optional)
        if len(ref_expressions) > 1:
            return f"ToString({ref_expressions[0]}, {ref_expressions[1]})"
        return f"ToString({ref_expressions[0]})"

    # ============================================================
    # CONDITIONAL / FLOW CONTROL
    # ============================================================
    def tricc_operation_if(self, ref_expressions, original_references=None):
        # if cond then true_val else false_val
        if len(ref_expressions) >= 3:
            return f"if {ref_expressions[0]} then {ref_expressions[1]} else {ref_expressions[2]}"
        return ref_expressions[0]

    def tricc_operation_ifs(self, ref_expressions, original_references=None):
        # Build nested if-then-else chain
        # ref_expressions layout: [cond1, res1, cond2, res2, ..., default]
        if len(ref_expressions) < 2:
            return ref_expressions[0] if ref_expressions else "null"
        parts = []
        i = 0
        while i < len(ref_expressions) - 1:
            cond = ref_expressions[i]
            res = ref_expressions[i + 1]
            parts.append(f"if {cond} then {res}")
            i += 2
        if i < len(ref_expressions):
            parts.append(f"else {ref_expressions[-1]}")
        return " ".join(parts)

    def tricc_operation_case(self, ref_expressions, original_references=None):
        # Similar to IFS but value-based matching
        # Layout: [value, (match1, res1), (match2, res2), ..., default]
        if len(ref_expressions) < 3:
            return ref_expressions[0] if ref_expressions else "null"
        value = ref_expressions[0]
        parts = []
        i = 1
        while i < len(ref_expressions) - 1:
            match_val = ref_expressions[i]
            res = ref_expressions[i + 1]
            parts.append(f"when {match_val} then {res}")
            i += 2
        if i < len(ref_expressions):
            parts.append(f"else {ref_expressions[-1]}")
        return f"case {value} {' '.join(parts)} end"

    def tricc_operation_coalesce(self, ref_expressions, original_references=None):
        # CQL coalesce
        items = ", ".join(ref_expressions)
        return f"Coalesce({items})"

    def tricc_operation_parenthesis(self, ref_expressions, original_references=None):
        # Simple wrapper
        return f"({ref_expressions[0]})" if ref_expressions else "()"

    # ============================================================
    # CDSS-SPECIFIC (NOT IMPLEMENTED)
    # ============================================================
    def tricc_operation_zscore(self, ref_expressions, original_references=None):
        raise NotImplementedError("ZSCORE is not supported yet")

    def tricc_operation_izscore(self, ref_expressions, original_references=None):
        raise NotImplementedError("IZSCORE is not supported yet")

    def tricc_operation_drug_dosage(self, ref_expressions, original_references=None):
        raise NotImplementedError("DRUG_DOSAGE is not supported yet")

    # ============================================================
    # ADDITIONAL / FALLBACK
    # ============================================================
    def tricc_operation_native(self, ref_expressions, original_references=None):
        # Raw expression passthrough
        return ref_expressions[0] if ref_expressions else ""

    def tricc_operation_add_or(self, ref_expressions, original_references=None):
        # left AND (right1 OR right2 OR ...)
        if len(ref_expressions) <= 1:
            return ref_expressions[0] if ref_expressions else ""
        left = ref_expressions[0]
        rights = " or ".join(ref_expressions[1:])
        return f"({left} and ({rights}))"

    # ============================================================
    # FHIRPath variants – delegate to CQL handlers.
    # ============================================================
    def tricc_operation_fhirpath_equal(self, ref_expressions, original_references=None):
        # Operands are already scalar-wrapped; just build the comparison.
        r_expr =  self.tricc_operation_equal(ref_expressions)
        return self._wrap_operand_if_needed(r_expr, original_references)

    def tricc_operation_fhirpath_not_equal(self, ref_expressions, original_references=None):
        # Operands are already scalar-wrapped; just build the comparison.
        r_expr =  self.tricc_operation_not_equal(ref_expressions)
        return self._wrap_operand_if_needed(r_expr, original_references)

    def tricc_operation_fhirpath_less_or_equal(self, ref_expressions, original_references=None):
        # Operands are already scalar-wrapped; just build the comparison.
        r_expr =  self.tricc_operation_less_or_equal(ref_expressions)
        return self._wrap_operand_if_needed(r_expr, original_references)

    def tricc_operation_fhirpath_more_or_equal(self, ref_expressions, original_references=None):
        # Operands are already scalar-wrapped; just build the comparison.
        r_expr =  self.tricc_operation__more_or_equal(ref_expressions)
        return self._wrap_operand_if_needed(r_expr, original_references)


    def tricc_operation_fhirpath_istrue(self, ref_expressions, original_references=None):
        # Operands are already scalar-wrapped; just build the comparison.
        r_expr =  self.tricc_operation_istrue(ref_expressions)
        return self._wrap_operand_if_needed(r_expr, original_references)

    def tricc_operation_fhirpath_isnottrue(self, ref_expressions, original_references=None):
        r_expr =  self.tricc_operation_isnottrue(ref_expressions)
        return self._wrap_operand_if_needed(r_expr, original_references)

    def tricc_operation_fhirpath_isfalse(self, ref_expressions, original_references=None):
        r_expr =  self.tricc_operation_isfalse(ref_expressions)
        return self._wrap_operand_if_needed(r_expr, original_references)

    def tricc_operation_fhirpath_isnotfalse(self, ref_expressions, original_references=None):
        r_expr =  self.tricc_operation_isnotfalse(ref_expressions)
        return self._wrap_operand_if_needed(r_expr, original_references)

    def tricc_operation_fhirpath_isnull(self, ref_expressions, original_references=None):
        return self.tricc_operation_isnull(ref_expressions)

    def tricc_operation_fhirpath_isnotnull(self, ref_expressions, original_references=None):
        return self.tricc_operation_isnotnull(ref_expressions)

    def tricc_operation_fhirpath_selected(self, ref_expressions, original_references=None):
        return self.tricc_operation_selected(ref_expressions)

    def tricc_operation_fhirpath_between(self, ref_expressions, original_references=None):
        r_expr =  self.tricc_operation_between(ref_expressions)
        return self._wrap_operand_if_needed(r_expr, original_references)

    def tricc_operation_fhirpath_contains(self, ref_expressions, original_references=None):
        return self.tricc_operation_contains(ref_expressions)

    def tricc_operation_fhirpath_exists(self, ref_expressions, original_references=None):
        return self.tricc_operation_exists(ref_expressions)

    def tricc_operation_fhirpath_notexists(self, ref_expressions, original_references=None):
        return self.tricc_operation_notexists(ref_expressions)

    def tricc_operation_fhirpath_coalesce(self, ref_expressions, original_references=None):
        return f"({ref_expressions.join("|")}).where($this.exists()).first())"

    def tricc_operation_fhirpath_if(self, ref_expressions, original_references=None):
        r_expr =  self.tricc_operation_if(ref_expressions)
        return self._wrap_operand_if_needed(r_expr, original_references)

    def tricc_operation_fhirpath_ifs(self, ref_expressions, original_references=None):
        # IFS/CASE not supported in FHIRPath 2.0 – raise explicit error
        raise NotImplementedError("IFS is not supported by FHIRPath 2.0 – use CQL instead")

    def tricc_operation_fhirpath_case(self, ref_expressions, original_references=None):
        raise NotImplementedError("CASE is not supported by FHIRPath 2.0 – use CQL instead")

    def tricc_operation_fhirpath_zscore(self, ref_expressions, original_references=None):
        raise NotImplementedError("ZSCORE is not supported by FHIRPath 2.0")

    def tricc_operation_fhirpath_izscore(self, ref_expressions, original_references=None):
        raise NotImplementedError("IZSCORE is not supported by FHIRPath 2.0")

    def tricc_operation_fhirpath_drug_dosage(self, ref_expressions, original_references=None):
        raise NotImplementedError("DRUG_DOSAGE is not supported by FHIRPath 2.0")

    def tricc_operation_fhirpath_has_qualifier(self, ref_expressions, original_references=None):
        raise NotImplementedError("HAS_QUALIFIER is not supported by FHIRPath 2.0")


    def tricc_operation_fhirpath_istrue(self, ref_expressions, original_references=None):
        # CQL: treat as identity or explicit comparison
        return self._wrap_operand_if_needed(f"({ref_expressions[0]} = true)", original_references)

    def tricc_operation_fhirpath_isnottrue(self, ref_expressions, original_references=None):
        return self._wrap_operand_if_needed(f"({ref_expressions[0]} != true)", original_references) 

    def tricc_operation_fhirpath_isfalse(self, ref_expressions, original_references=None):
        return self._wrap_operand_if_needed(f"({ref_expressions[0]} = false)", original_references)

    def tricc_operation_fhirpath_isnotfalse(self, ref_expressions, original_references=None):
        return self._wrap_operand_if_needed(f"({ref_expressions[0]} != false)", original_references)

    def tricc_operation_fhirpath_isnull(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]}.empty())"

    def tricc_operation_fhirpath_isnotnull(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]}.exists())"

    def tricc_operation_fhirpath_count(self, ref_expressions, original_references=None):
        if len(ref_expressions)>1:
            items = ", ".join(ref_expressions)
            return f"{{{items}}}.count()"
        else:
            return f"{ref_expressions[0]}.count()"
    # ============================================================
    # CASTING & CONVERSION
    # ============================================================
    def tricc_operation_fhirpath_cast_number(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]}.toDecimal()"

    def tricc_operation_fhirpath_cast_integer(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]}.toInteger()"

    def tricc_operation_fhirpath_cast_date(self, ref_expressions, original_references=None):
        return f"({ref_expressions[0]}.toDate()"

    def tricc_operation_fhirpath_cast_string(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]}.toString()"

    def tricc_operation_fhirpath_cast_boolean(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]}.toBoolean()"

    def tricc_operation_fhirpath_datetime_to_decimal(self, ref_expressions, original_references=None):
        return f"{ref_expressions[0]}.toDecimal()"
    # For any other fhirpath_* not explicitly defined above, the fallback in
    # get_tricc_operation_expression_fhirpath will call the CQL handler directly.
    # Per-operand .first() wrapping has already been applied before reaching here.
