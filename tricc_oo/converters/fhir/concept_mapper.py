"""
Mapping from TRICC concept_type / node types to target FHIR resources.

Reuses the manual openMRS concept_type → FHIR resource mapping from pyfhirsdc.
Explicit rule per FHIRcore.md v4: Diagnosis → Condition.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger("default")

# ---------------------------------------------------------------------------
# concept_type → (fhir_resource, fhir_profile_url, data_type_field)
# Reused from pyfhirsdc openMRS manual mapping + Diagnosis→Condition rule
# ---------------------------------------------------------------------------
CONCEPT_TYPE_TO_FHIR: Dict[str, Tuple[str, str, str]] = {
    # Diagnosis / classification → Condition (explicit FHIRcore.md rule)
    "diagnosis":            ("Condition",       "http://hl7.org/fhir/StructureDefinition/Condition",       "code"),
    "proposed_diagnosis":   ("Condition",       "http://hl7.org/fhir/StructureDefinition/Condition",       "code"),
    # Observations (numeric, coded, text) — includes OpenMRS/codesystem classes
    "observation":          ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
    "finding":              ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
    "symptom":              ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
    "symptom-finding":      ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
    "question":             ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
    "sign":                 ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
    "test":                 ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
    "lab":                  ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
    "labset":               ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
    "vital":                ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
    # Medication / treatment
    "drug":                 ("MedicationRequest", "http://hl7.org/fhir/StructureDefinition/MedicationRequest", "medication"),
    "medication":           ("MedicationRequest", "http://hl7.org/fhir/StructureDefinition/MedicationRequest", "medication"),
    "treatment":            ("MedicationRequest", "http://hl7.org/fhir/StructureDefinition/MedicationRequest", "medication"),
    # Procedure
    "procedure":            ("Procedure",       "http://hl7.org/fhir/StructureDefinition/Procedure",       "code"),
    "intervention":         ("Procedure",       "http://hl7.org/fhir/StructureDefinition/Procedure",       "code"),
    # Encounter context
    "encounter":            ("Encounter",       "http://hl7.org/fhir/StructureDefinition/Encounter",       "type"),
    # Patient demographics
    "patient":              ("Patient",         "http://hl7.org/fhir/StructureDefinition/Patient",         "extension"),
    # Service request / referral
    "referral":             ("ServiceRequest",  "http://hl7.org/fhir/StructureDefinition/ServiceRequest",  "code"),
    "service":              ("ServiceRequest",  "http://hl7.org/fhir/StructureDefinition/ServiceRequest",  "code"),
    # Default fallback
    "default":              ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
}

# TRICC node type → concept_type override (when concept_type not set on node)
NODE_TYPE_CONCEPT_OVERRIDE: Dict[str, str] = {
    "diagnosis":          "diagnosis",
    "proposed_diagnosis": "proposed_diagnosis",
}

# FHIR data type for each concept_type field value type
FIELD_DATA_TYPE: Dict[str, str] = {
    "boolean":  "valueBoolean",
    "integer":  "valueInteger",
    "decimal":  "valueQuantity",
    "string":   "valueString",
    "date":     "valueDateTime",
    "code":     "valueCodeableConcept",
    "number":   "valueQuantity",
    "mixed":    "valueString",
}


def get_fhir_resource(concept_type: Optional[str], tricc_type: Optional[str] = None) -> Tuple[str, str, str]:
    """Return the target FHIR resource, profile URL, and field for a concept_type.

    Args:
        concept_type: The concept_type string from the TRICC node (may be None).
        tricc_type: The TRICC node type string (used as fallback).

    Returns:
        Tuple of (fhir_resource, profile_url, data_field).
    """
    # Check node type override first
    if tricc_type and tricc_type in NODE_TYPE_CONCEPT_OVERRIDE:
        ct = NODE_TYPE_CONCEPT_OVERRIDE[tricc_type]
        return CONCEPT_TYPE_TO_FHIR[ct]

    if concept_type:
        ct = concept_type.lower().strip()
        if ct in CONCEPT_TYPE_TO_FHIR:
            return CONCEPT_TYPE_TO_FHIR[ct]
        # Try prefix match (e.g. "diagnosis.icd10" → "diagnosis")
        for key in CONCEPT_TYPE_TO_FHIR:
            if ct.startswith(key):
                return CONCEPT_TYPE_TO_FHIR[key]
        logger.debug(f"No FHIR resource mapping for concept_type '{concept_type}', using Observation")

    return CONCEPT_TYPE_TO_FHIR["default"]


def get_fhir_value_field(data_type: Optional[str]) -> str:
    """Return the FHIR value field name for a given data type.

    Args:
        data_type: The data type string (e.g. ``"boolean"``, ``"integer"``).

    Returns:
        FHIR value field name (e.g. ``"valueBoolean"``).
    """
    if not data_type:
        return "valueString"
    return FIELD_DATA_TYPE.get(data_type.lower(), "valueString")


# Codesystem / OpenMRS classes that extract to Observation.
_OBSERVATION_CONCEPT_TYPES = {
    "observation",
    "finding",
    "symptom",
    "symptom-finding",
    "question",
    "sign",
    "test",
    "lab",
    "labset",
    "vital",
}

# Codesystem classes that must never become extracted resources.
_SKIP_CONCEPT_TYPES = {
    "calculation",
    "interactset",
    "value",
    "misc",
    "n/a",
    "na",
}

# QuestionnaireResponse.answer value[x] for a Questionnaire item type.
QR_VALUE_FIELD: Dict[str, str] = {
    "boolean": "valueBoolean",
    "integer": "valueInteger",
    "decimal": "valueDecimal",
    "date": "valueDate",
    "datetime": "valueDateTime",
    "string": "valueString",
    "text": "valueString",
    "choice": "valueCoding",
    "open-choice": "valueCoding",
    "quantity": "valueQuantity",
}


def _concept_type_key(concept_type: Optional[str]) -> str:
    return (concept_type or "").lower().strip().replace("_", "-")


def lookup_concept_type_from_codesystem(codesystems, name: Optional[str]) -> Optional[str]:
    """Return the ``conceptType`` property for ``name`` from project CodeSystems.

    Args:
        codesystems: Project ``code_systems`` dict (may be None/empty).
        name: Concept code / node name.

    Returns:
        conceptType string, or None when not found.
    """
    if not codesystems or not name:
        return None
    from tricc_oo.converters.datadictionnary import lookup_codesystems_code

    concept = lookup_codesystems_code(codesystems, name)
    if concept is None:
        return None
    for prop in concept.property or []:
        if getattr(prop, "code", None) in ("conceptType", "concept_type"):
            value = getattr(prop, "valueString", None)
            if value:
                return value
    return None


def infer_concept_type(node) -> str:
    """Infer the codesystem-style concept class when the node does not set one.

    Mirrors ``xml_to_tricc.get_concept_type`` so StructureMap classification
    matches the CodeSystem ``conceptType`` property written at input load.
    """
    from tricc_oo.models.base import TriccNodeType

    tricc_type = str(getattr(node, "tricc_type", None) or "")
    if tricc_type in (TriccNodeType.proposed_diagnosis, TriccNodeType.diagnosis):
        return "Diagnosis"
    if tricc_type in (
        TriccNodeType.calculate,
        TriccNodeType.count,
        TriccNodeType.add,
        TriccNodeType.rhombus,
        TriccNodeType.wait,
        TriccNodeType.bridge,
        TriccNodeType.factor,
        TriccNodeType.populate,
    ):
        return "Calculation"
    if tricc_type in (TriccNodeType.note, TriccNodeType.help, TriccNodeType.hint):
        return "InteractSet"
    if tricc_type == TriccNodeType.select_option:
        return "Value"
    if tricc_type == TriccNodeType.select_multiple:
        return "Question"
    if tricc_type in (
        TriccNodeType.integer,
        TriccNodeType.decimal,
        TriccNodeType.text,
        TriccNodeType.date,
        TriccNodeType.quantity,
        TriccNodeType.select_one,
        TriccNodeType.select_yesno,
        TriccNodeType.input,
    ):
        return "Symptom-Finding"
    return "Misc"


def resolve_concept_type(node, codesystems=None) -> str:
    """Resolve the concept class used to pick an extraction target.

    Order: explicit ``node.concept_type`` → CodeSystem ``conceptType`` → node-type fallback.
    """
    explicit = getattr(node, "concept_type", None)
    if explicit:
        return explicit
    from_cs = lookup_concept_type_from_codesystem(codesystems, getattr(node, "name", None))
    if from_cs:
        return from_cs
    return infer_concept_type(node)


def diagnosis_concept_code(node) -> str:
    """Return the clinical concept code for a diagnosis / accept-diag node.

    Accept/reject items are named ``pre_final.{code}``; confirmed calculates
    are ``final.{code}``. The Condition uses the bare concept code.
    """
    name = getattr(node, "save", None) or getattr(node, "name", None) or ""
    for prefix in ("pre_final.", "final.", "anchor."):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def get_qr_value_field(item_type: Optional[str]) -> str:
    """Return the QuestionnaireResponse.answer value[x] field for an item type."""
    if not item_type:
        return "valueString"
    return QR_VALUE_FIELD.get(item_type.lower(), "valueString")


def classify_extraction(node, codesystems=None) -> Optional[str]:
    """Return the StructureMap extraction kind, or None when the node is not persisted.

    Kinds:
        ``observation`` — Symptom-Finding / Question / finding → Observation
        ``proposed_condition`` — proposed_diagnosis → Condition (provisional)
        ``accept_condition`` — AcceptDiag → Condition confirmed or refuted

    ``final.{code}`` calculates and ``TriccNodeDiagnosis`` anchors are not extracted:
    confirmation is the AcceptDiag answer (and CQL ``HasConfirmedCondition``).
    """
    from tricc_oo.models.base import TriccNodeType
    from tricc_oo.models.calculate import TriccNodeProposedDiagnosis
    from tricc_oo.models.tricc import TriccNodeAcceptDiagnostic, TriccNodeSelectOption

    if isinstance(node, TriccNodeSelectOption):
        return None
    if isinstance(node, TriccNodeAcceptDiagnostic):
        return "accept_condition"
    if isinstance(node, TriccNodeProposedDiagnosis):
        return "proposed_condition"

    tricc_type = getattr(node, "tricc_type", None)
    # Display/group nodes have no QuestionnaireResponse.answer and SDC forbids
    # initialExpression on them — they are never persisted as Observation/Condition.
    if tricc_type in (
        TriccNodeType.note,
        TriccNodeType.help,
        TriccNodeType.hint,
        TriccNodeType.start,
        TriccNodeType.activity_start,
        TriccNodeType.activity,
        TriccNodeType.page,
    ):
        return None
    # Diagnosis nodes are wait-anchors (``anchor.{code}``), not persistable Conditions.
    if tricc_type == TriccNodeType.diagnosis:
        return None
    if tricc_type == TriccNodeType.proposed_diagnosis:
        return "proposed_condition"

    ct = resolve_concept_type(node, codesystems)
    key = _concept_type_key(ct)
    if key in _SKIP_CONCEPT_TYPES:
        return None
    if key in _OBSERVATION_CONCEPT_TYPES:
        return "observation"
    resource, _, _ = get_fhir_resource(ct, tricc_type)
    if resource == "Condition":
        return "proposed_condition"
    if resource == "Observation" and key not in _SKIP_CONCEPT_TYPES and key != "default":
        return "observation"
    return None
