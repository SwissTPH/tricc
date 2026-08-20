"""FHIR resource id helpers.

FHIR R4 ``id`` type: 1–64 characters matching ``[A-Za-z0-9\\-\\.]``
(see https://hl7.org/fhir/R4/datatypes.html#id). Underscores and other
characters are rejected by HAPI (HAPI-0521).

openSRP content packages typically use **UUID** resource ids for REST
addressing (e.g. Binary). TRICC follows that for server-facing ``id`` values
via deterministic UUID5 keys so re-exports stay stable for PUT upserts.
"""

from __future__ import annotations

import re
import uuid
from typing import Optional

# FHIR id character class + length
_INVALID = re.compile(r"[^A-Za-z0-9.\-]+")
_MULTI_DASH = re.compile(r"-{2,}")
_FHIR_ID = re.compile(r"^[A-Za-z0-9.\-]{1,64}$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Namespace for deterministic FHIR resource UUIDs (TRICC export).
# Distinct from concept UUID namespace in datadictionnary.py.
TRICC_FHIR_ID_NAMESPACE = uuid.UUID("7c3f9e2a-4b1d-5e8f-a0c6-d2e4f6a8b0c1")


def to_fhir_id(*parts: Optional[str], max_length: int = 64) -> str:
    """Join parts into a valid human-readable FHIR token (name / file stem).

    Non-allowed characters (including ``_``) become ``-``. Prefer
    :func:`fhir_resource_id` for server resource ``id`` fields.

    Args:
        *parts: Name fragments (form id, process, resource role, …).
        max_length: Maximum length (FHIR max 64).

    Returns:
        A string matching ``[A-Za-z0-9.-]{1,64}``.
    """
    raw = "-".join(str(p).strip() for p in parts if p is not None and str(p).strip())
    if not raw:
        return "resource"
    cleaned = _INVALID.sub("-", raw)
    cleaned = _MULTI_DASH.sub("-", cleaned).strip("-.")
    if not cleaned:
        cleaned = "resource"
    if cleaned[0] in ".-":
        cleaned = f"id{cleaned}"
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip("-.")
    if not cleaned:
        cleaned = "resource"
    return cleaned


def fhir_resource_id(*parts: Optional[str]) -> str:
    """Return a stable UUID FHIR resource id (openSRP-style REST id).

    Uses UUID5 over a fixed TRICC namespace and the joined logical key so the
    same form/process/role always maps to the same id across re-exports
    (idempotent PUT). Random UUID4 would orphan server resources on each build.

    Args:
        *parts: Logical key fragments (form id, resourceType, process, role, …).

    Returns:
        Lowercase UUID string (36 chars, valid FHIR id).
    """
    key = "|".join(str(p).strip() for p in parts if p is not None and str(p).strip())
    if not key:
        key = "resource"
    return str(uuid.uuid5(TRICC_FHIR_ID_NAMESPACE, key))


def is_valid_fhir_id(value: str) -> bool:
    """Return True if ``value`` is a legal FHIR id.

    Args:
        value: Candidate id string.

    Returns:
        Whether the value matches the FHIR id pattern.
    """
    if not value or not isinstance(value, str):
        return False
    return bool(_FHIR_ID.match(value))


def is_uuid_id(value: str) -> bool:
    """Return True if ``value`` looks like a UUID resource id.

    Args:
        value: Candidate id string.

    Returns:
        Whether the value is a UUID string.
    """
    if not value or not isinstance(value, str):
        return False
    return bool(_UUID_RE.match(value))


def readable_resource_filename(
    resource: dict,
    *,
    prefix: Optional[str] = None,
    fallback: str = "resource",
    ext: str = ".json",
) -> str:
    """Build a human-readable on-disk filename for a FHIR resource.

    Uses ``name`` (preferred) or ``title``, never the UUID ``id``. The REST
    ``id`` stays inside the JSON; only the package file stem is readable.

    Args:
        resource: FHIR resource dict (must not rely on ``id`` for naming).
        prefix: Optional prefix such as ``Library`` or ``PlanDefinition``.
        fallback: Stem when name/title are missing.
        ext: File extension including the dot.

    Returns:
        Filename like ``PlanDefinition-demo-tricc-main-PD.json``.
    """
    stem_src = resource.get("name") or resource.get("title") or fallback
    stem = to_fhir_id(str(stem_src))
    if prefix:
        stem = f"{to_fhir_id(prefix)}-{stem}"
    if not ext.startswith("."):
        ext = f".{ext}"
    return f"{stem}{ext}"
