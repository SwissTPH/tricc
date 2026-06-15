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
    # Observations (numeric, coded, text)
    "observation":          ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
    "finding":              ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
    "symptom":              ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
    "sign":                 ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
    "test":                 ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
    "lab":                  ("Observation",     "http://hl7.org/fhir/StructureDefinition/Observation",     "value"),
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
