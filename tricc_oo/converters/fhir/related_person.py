"""
RelatedPerson helpers for openSRP / TRICC client register contract.

Invariant: RelatedPerson.patient always references the **child**.
Parent/mother/father/guardian is a full Patient client, linked via identifier (PI, secondary).

See ``feature/opensrp-register.md`` and android ``feature/register-tricc.md``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

# ---------------------------------------------------------------------------
# Constants (shared with openSRP Android enrichment)
# ---------------------------------------------------------------------------

RELATED_PERSON_PATIENT_IDENTIFIER_SYSTEM = "urn:ietf:rfc:3986"
IDENTIFIER_TYPE_SYSTEM_V2_0203 = "http://terminology.hl7.org/CodeSystem/v2-0203"
IDENTIFIER_TYPE_PI = "PI"
IDENTIFIER_USE_SECONDARY = "secondary"

ROLE_CODE_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-RoleCode"
ROLE_CLASS_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-RoleClass"

# role key → (system, code, display)
RELATIONSHIP_ROLES = {
    "mother": (ROLE_CODE_SYSTEM, "MTH", "mother"),
    "mth": (ROLE_CODE_SYSTEM, "MTH", "mother"),
    "father": (ROLE_CODE_SYSTEM, "FTH", "father"),
    "fth": (ROLE_CODE_SYSTEM, "FTH", "father"),
    "guardian": (ROLE_CLASS_SYSTEM, "GUARD", "guardian"),
    "guard": (ROLE_CLASS_SYSTEM, "GUARD", "guardian"),
}

AVAILABLE_CARE_NAMED_EVENT = "available-care"

RELATED_PERSON_CONTRACT: Dict[str, Any] = {
    "version": "1.0.0",
    "identifier": {
        "use": IDENTIFIER_USE_SECONDARY,
        "type_system": IDENTIFIER_TYPE_SYSTEM_V2_0203,
        "type_code": IDENTIFIER_TYPE_PI,
        "system": RELATED_PERSON_PATIENT_IDENTIFIER_SYSTEM,
        "value_pattern": "Patient/{id} | absolute Patient URL",
    },
    "relationship_roles": {
        "mother": {"system": ROLE_CODE_SYSTEM, "code": "MTH"},
        "father": {"system": ROLE_CODE_SYSTEM, "code": "FTH"},
        "guardian": {"system": ROLE_CLASS_SYSTEM, "code": "GUARD"},
    },
}


def _normalize_patient_ref(patient_id_or_ref: str) -> str:
    """Normalize to ``Patient/{id}`` when possible."""
    value = (patient_id_or_ref or "").strip()
    if not value:
        raise ValueError("patient id/reference must be non-empty")
    if "Patient/" in value:
        logical = value.split("Patient/", 1)[1].split("/")[0].split("?")[0].split("#")[0]
        if not logical:
            raise ValueError(f"invalid Patient reference: {patient_id_or_ref!r}")
        return f"Patient/{logical}"
    return f"Patient/{value}"


def patient_url_identifier(
    patient_id_or_ref: str,
    *,
    use: str = IDENTIFIER_USE_SECONDARY,
    type_code: str = IDENTIFIER_TYPE_PI,
    absolute_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Build RelatedPerson.identifier entry linking to a guardian/parent Patient.

    Args:
        patient_id_or_ref: Patient logical id or ``Patient/{id}``.
        use: Identifier.use (default ``secondary``).
        type_code: v2-0203 type (default ``PI``).
        absolute_url: If set, used as identifier.value instead of relative ref.
    """
    relative = _normalize_patient_ref(patient_id_or_ref)
    display = (
        "Patient internal identifier"
        if type_code.upper() == IDENTIFIER_TYPE_PI
        else "Patient external identifier"
    )
    return {
        "use": use,
        "type": {
            "coding": [
                {
                    "system": IDENTIFIER_TYPE_SYSTEM_V2_0203,
                    "code": type_code,
                    "display": display,
                }
            ]
        },
        "system": RELATED_PERSON_PATIENT_IDENTIFIER_SYSTEM,
        "value": absolute_url or relative,
    }


def relationship_coding(role: str) -> Dict[str, Any]:
    """Build a CodeableConcept for mother / father / guardian."""
    key = (role or "").strip().lower()
    if key not in RELATIONSHIP_ROLES:
        raise ValueError(
            f"Unknown relationship role {role!r}; "
            f"expected one of {sorted(set(RELATIONSHIP_ROLES))}"
        )
    system, code, display = RELATIONSHIP_ROLES[key]
    return {
        "coding": [
            {
                "system": system,
                "code": code,
                "display": display,
            }
        ],
        "text": display,
    }


def build_related_person(
    *,
    child_patient_id_or_ref: str,
    guardian_patient_id_or_ref: str,
    role: str,
    related_person_id: Optional[str] = None,
    guardian_display_name: Optional[str] = None,
    absolute_guardian_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a RelatedPerson resource dict (patient always = child).

    Args:
        child_patient_id_or_ref: Child Patient id or reference.
        guardian_patient_id_or_ref: Mother/father/guardian Patient id or reference.
        role: ``mother`` | ``father`` | ``guardian`` (or MTH/FTH/GUARD aliases).
        related_person_id: Optional resource id.
        guardian_display_name: Optional HumanName text for the related person.
        absolute_guardian_url: Optional absolute Patient URL for identifier.value.
    """
    child_ref = _normalize_patient_ref(child_patient_id_or_ref)
    rp: Dict[str, Any] = {
        "resourceType": "RelatedPerson",
        "identifier": [
            patient_url_identifier(
                guardian_patient_id_or_ref,
                absolute_url=absolute_guardian_url,
            )
        ],
        "patient": {"reference": child_ref},
        "relationship": [relationship_coding(role)],
        "active": True,
    }
    if related_person_id:
        rp["id"] = related_person_id
    if guardian_display_name:
        rp["name"] = [{"text": guardian_display_name}]
    return rp


def structure_map_related_person_hints() -> List[str]:
    """FML comment lines for StructureMap authors extracting RelatedPerson."""
    return [
        "// TRICC RelatedPerson contract (feature/opensrp-register.md):",
        "//   RelatedPerson.patient = child Patient (always)",
        "//   RelatedPerson.relationship = MTH | FTH | GUARD",
        f"//   RelatedPerson.identifier.use = {IDENTIFIER_USE_SECONDARY}",
        f"//   RelatedPerson.identifier.type = {IDENTIFIER_TYPE_PI} ({IDENTIFIER_TYPE_SYSTEM_V2_0203})",
        f"//   RelatedPerson.identifier.system = {RELATED_PERSON_PATIENT_IDENTIFIER_SYSTEM}",
        "//   RelatedPerson.identifier.value = Patient/{{guardianId}}",
        "// Never set RelatedPerson.patient to the parent/guardian.",
    ]
