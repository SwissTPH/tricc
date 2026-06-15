"""
Mapping from TRICC node types to FHIR Questionnaire item types and SDC extensions.

This module implements the node-type → FHIR item mapping table documented in
``docs/tricc-elements.md`` and required by the FHIRcore.md v4 specification.

Reuses patterns from pyfhirsdc/converters/questionnaireItemConverter.py.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple


from tricc_oo.models.base import TriccNodeType
from tricc_oo.models.calculate import TriccNodeInput

logger = logging.getLogger("default")

# ---------------------------------------------------------------------------
# FHIR Questionnaire item type constants
# ---------------------------------------------------------------------------
FHIR_TYPE_STRING = "string"
FHIR_TYPE_INTEGER = "integer"
FHIR_TYPE_DECIMAL = "decimal"
FHIR_TYPE_DATE = "date"
FHIR_TYPE_DATETIME = "dateTime"
FHIR_TYPE_BOOLEAN = "boolean"
FHIR_TYPE_CHOICE = "choice"
FHIR_TYPE_DISPLAY = "display"
FHIR_TYPE_GROUP = "group"
FHIR_TYPE_QUANTITY = "quantity"

# ---------------------------------------------------------------------------
# SDC extension URLs (openSRP profile)
# ---------------------------------------------------------------------------
SDC_EXT_ENABLE_WHEN_EXPR = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-enableWhenExpression"
SDC_EXT_INITIAL_EXPR = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression"
SDC_EXT_CALCULATED_EXPR = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-calculatedExpression"
SDC_EXT_ITEM_MEDIA = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-itemMedia"
SDC_EXT_HIDDEN = "http://hl7.org/fhir/StructureDefinition/questionnaire-hidden"
SDC_EXT_CHOICE_ORIENTATION = "http://hl7.org/fhir/StructureDefinition/questionnaire-choiceOrientation"
SDC_EXT_ITEM_CONTROL = "http://hl7.org/fhir/StructureDefinition/questionnaire-itemControl"
OPENSRP_EXT_POPULATE = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-itemPopulationContext"

# ---------------------------------------------------------------------------
# Mapping table: TriccNodeType → (fhir_item_type, repeats, hidden, notes)
# ---------------------------------------------------------------------------
# Format: TriccNodeType → (fhir_type, repeats, hidden)
# hidden=True means the item should not be displayed to the user
NODE_TYPE_TO_FHIR: Dict[str, Tuple[str, bool, bool]] = {
    # Primitive inputs
    TriccNodeType.integer:          (FHIR_TYPE_INTEGER,  False, False),
    TriccNodeType.decimal:          (FHIR_TYPE_DECIMAL,  False, False),
    TriccNodeType.text:             (FHIR_TYPE_STRING,   False, False),
    TriccNodeType.date:             (FHIR_TYPE_DATE,     False, False),
    TriccNodeType.quantity:         (FHIR_TYPE_QUANTITY, False, False),
    # Select questions
    TriccNodeType.select_one:       (FHIR_TYPE_CHOICE,   False, False),
    TriccNodeType.select_yesno:     (FHIR_TYPE_BOOLEAN,  False, False),
    TriccNodeType.select_multiple:  (FHIR_TYPE_CHOICE,   True,  False),
    # Display / note
    TriccNodeType.note:             (FHIR_TYPE_DISPLAY,  False, False),
    TriccNodeType.help:             (FHIR_TYPE_DISPLAY,  False, False),
    TriccNodeType.hint:             (FHIR_TYPE_DISPLAY,  False, False),
    # Calculate (hidden, populated via CQL initialExpression)
    TriccNodeType.calculate:        (FHIR_TYPE_STRING,   False, True),
    TriccNodeType.count:            (FHIR_TYPE_INTEGER,  False, True),
    TriccNodeType.add:              (FHIR_TYPE_DECIMAL,  False, True),
    # Diagnosis nodes (hidden, extracted to Condition)
    TriccNodeType.diagnosis:        (FHIR_TYPE_BOOLEAN,  False, True),
    TriccNodeType.proposed_diagnosis: (FHIR_TYPE_BOOLEAN, False, True),
    # Navigation / structural (not rendered as items)
    TriccNodeType.start:            (FHIR_TYPE_GROUP,    False, True),
    TriccNodeType.activity_start:   (FHIR_TYPE_GROUP,    False, True),
    TriccNodeType.activity_end:     (FHIR_TYPE_GROUP,    False, True),
    TriccNodeType.end:              (FHIR_TYPE_GROUP,    False, True),
    TriccNodeType.rhombus:          (FHIR_TYPE_BOOLEAN,  False, True),
    TriccNodeType.factor:           (FHIR_TYPE_DECIMAL,  False, True),
    TriccNodeType.bridge:           (FHIR_TYPE_BOOLEAN,  False, True),
    TriccNodeType.wait:             (FHIR_TYPE_BOOLEAN,  False, True),
    TriccNodeType.goto:             (FHIR_TYPE_GROUP,    False, True),
    TriccNodeType.link_in:          (FHIR_TYPE_GROUP,    False, True),
    TriccNodeType.link_out:         (FHIR_TYPE_GROUP,    False, True),
}

# Node types that should be skipped entirely (not added to Questionnaire)
SKIP_NODE_TYPES = {
    TriccNodeType.page,
    TriccNodeType.activity,
    TriccNodeType.edge,
    TriccNodeType.select_option,
    TriccNodeType.not_available,
    TriccNodeType.context,
    TriccNodeType.input,
    TriccNodeType.remote_reference,
    TriccNodeType.operation,
}

# Node types that produce hidden calculate items (populated via CQL calculatedExpression)
CALCULATE_NODE_TYPES = {
    TriccNodeType.calculate,
    TriccNodeType.count,
    TriccNodeType.add,
    TriccNodeType.bridge,
    TriccNodeType.wait,
    TriccNodeType.diagnosis,
    TriccNodeType.proposed_diagnosis,
}


def is_default_or_odk_input(node) -> bool:
    """Return True only for real TriccNodeInput instances (primitive odk inputs)."""
    return isinstance(node, TriccNodeInput)


def get_fhir_item_type(tricc_type: str) -> str:
    """Return the FHIR Questionnaire item type for a given TRICC node type.

    Args:
        tricc_type: A ``TriccNodeType`` value (string).

    Returns:
        FHIR item type string (e.g. ``"choice"``, ``"string"``).
    """
    mapping = NODE_TYPE_TO_FHIR.get(tricc_type)
    if mapping:
        return mapping[0]
    logger.warning(f"No FHIR item type mapping for TRICC type '{tricc_type}', defaulting to 'string'")
    return FHIR_TYPE_STRING


def is_repeating(tricc_type: str) -> bool:
    """Return True if the FHIR item should have ``repeats=true``.

    Args:
        tricc_type: A ``TriccNodeType`` value (string).

    Returns:
        Boolean indicating whether the item repeats.
    """
    mapping = NODE_TYPE_TO_FHIR.get(tricc_type)
    return mapping[1] if mapping else False


def is_hidden(tricc_type: str) -> bool:
    """Return True if the FHIR item should be hidden from the user.

    Args:
        tricc_type: A ``TriccNodeType`` value (string).

    Returns:
        Boolean indicating whether the item is hidden.
    """
    mapping = NODE_TYPE_TO_FHIR.get(tricc_type)
    return mapping[2] if mapping else False


def should_skip(tricc_type: str) -> bool:
    """Return True if this node type should not produce a Questionnaire item.

    Args:
        tricc_type: A ``TriccNodeType`` value (string).

    Returns:
        Boolean indicating whether to skip this node.
    """
    return tricc_type in SKIP_NODE_TYPES


def is_calculate_type(tricc_type: str) -> bool:
    """Return True if this node type is a hidden calculate item.

    Args:
        tricc_type: A ``TriccNodeType`` value (string).

    Returns:
        Boolean indicating whether this is a calculate-type node.
    """
    return tricc_type in CALCULATE_NODE_TYPES


def build_item_control_extension(control_code: str) -> dict:
    """Build a questionnaire-itemControl extension dict.

    Args:
        control_code: The item control code (e.g. ``"drop-down"``, ``"check-box"``).

    Returns:
        FHIR extension dict.
    """
    return {
        "url": SDC_EXT_ITEM_CONTROL,
        "valueCodeableConcept": {
            "coding": [
                {
                    "system": "http://hl7.org/fhir/questionnaire-item-control",
                    "code": control_code,
                }
            ]
        },
    }


def build_hidden_extension() -> dict:
    """Build a questionnaire-hidden extension dict.

    Returns:
        FHIR extension dict marking the item as hidden.
    """
    return {"url": SDC_EXT_HIDDEN, "valueBoolean": True}


def build_enable_when_expression(fhirpath_expr: str) -> dict:
    """Build an SDC enableWhenExpression extension dict.

    Args:
        fhirpath_expr: FHIRPath expression string.

    Returns:
        FHIR extension dict.
    """
    return {
        "url": SDC_EXT_ENABLE_WHEN_EXPR,
        "valueExpression": {
            "language": "text/fhirpath",
            "expression": fhirpath_expr,
        },
    }


def build_initial_expression(cql_expr: str, library_name: Optional[str] = None) -> dict:
    """Build an SDC initialExpression extension dict using a CQL identifier reference.

    Args:
        cql_expr: CQL define name (identifier) to reference.
        library_name: Optional CQL library name for qualified reference.

    Returns:
        FHIR extension dict with ``text/cql-identifier`` language.
    """
    expr = f"{library_name}.{cql_expr}" if library_name else cql_expr
    return {
        "url": SDC_EXT_INITIAL_EXPR,
        "valueExpression": {
            "language": "text/cql-identifier",
            "expression": expr,
        },
    }


def build_initial_expression_cql(cql_expr: str) -> dict:
    """Build an SDC initialExpression extension dict using an inline CQL expression.

    Use this for rhombus (sequence/logic) nodes where the expression must be
    expressed as inline CQL (``text/cql``) rather than a named CQL identifier
    reference (``text/cql-identifier``).  Only ``initialExpression`` supports
    ``text/cql``; ``calculatedExpression`` must use ``text/cql-identifier``.

    Args:
        cql_expr: Inline CQL expression string.

    Returns:
        FHIR extension dict with ``text/cql`` language.
    """
    return {
        "url": SDC_EXT_INITIAL_EXPR,
        "valueExpression": {
            "language": "text/cql",
            "expression": cql_expr,
        },
    }


def build_calculated_expression(cql_expr: str, library_name: Optional[str] = None) -> dict:
    """Build an SDC calculatedExpression extension dict (CQL-based).

    Args:
        cql_expr: CQL expression string.
        library_name: Optional CQL library name for qualified reference.

    Returns:
        FHIR extension dict.
    """
    expr = f"{library_name}.{cql_expr}" if library_name else cql_expr
    return {
        "url": SDC_EXT_CALCULATED_EXPR,
        "valueExpression": {
            "language": "text/cql-identifier",
            "expression": expr,
        },
    }


def get_display_type_extensions(display_type: Optional[str], tricc_type: str) -> list:
    """Return SDC extensions based on the node's display_type attribute.

    Reuses pyfhirsdc display_type → SDC extension mapping patterns.

    Args:
        display_type: The display_type string from the TRICC node (may be None).
        tricc_type: The TRICC node type string.

    Returns:
        List of FHIR extension dicts.
    """
    extensions = []
    if not display_type:
        # Apply defaults based on node type
        if tricc_type == TriccNodeType.select_multiple:
            extensions.append(build_item_control_extension("check-box"))
        elif tricc_type == TriccNodeType.select_one:
            extensions.append(build_item_control_extension("radio-button"))
        # select_yesno is now boolean — no itemControl needed
        return extensions

    dt = display_type.lower().strip()
    if dt in ("dropdown", "drop-down", "select"):
        extensions.append(build_item_control_extension("drop-down"))
    elif dt in ("radio", "radio-button"):
        # Only apply to choice-based selects (not yesno, which is now boolean)
        if tricc_type != TriccNodeType.select_yesno:
            extensions.append(build_item_control_extension("radio-button"))
    elif dt in ("checkbox", "check-box"):
        extensions.append(build_item_control_extension("check-box"))
    elif dt in ("slider",):
        extensions.append(build_item_control_extension("slider"))
    elif dt in ("autocomplete",):
        extensions.append(build_item_control_extension("autocomplete"))
    elif dt in ("hidden",):
        extensions.append(build_hidden_extension())
    else:
        logger.debug(f"Unknown display_type '{display_type}', no SDC extension added")

    return extensions
