"""
FSH (FHIR Shorthand) serializer for TRICC → FHIR SDC resource generation.

Converts FHIR resource dicts into FSH syntax suitable for SUSHI compilation.
Supports: Questionnaire, Library, StructureMap, ValueSet, PlanDefinition,
          Composition, Binary.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def resource_to_fsh(resource: dict) -> str:
    """Convert a FHIR resource dict to FSH (FHIR Shorthand) text.

    Args:
        resource: A FHIR resource represented as a Python dict.

    Returns:
        A string containing the FSH representation of the resource.
        Falls back to a RuleSet-wrapped JSON instance if the resource type
        is not explicitly handled.
    """
    resource_type = resource.get("resourceType", "")
    serializer = _SERIALIZERS.get(resource_type, _generic_instance_fsh)
    try:
        return serializer(resource)
    except Exception as exc:  # pragma: no cover
        logger.warning("FSH serialization failed for %s (%s); using generic fallback", resource_type, exc)
        return _generic_instance_fsh(resource)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fsh_header(keyword: str, name: str, resource_type: str) -> str:
    """Return the FSH keyword + name header line."""
    return f"{keyword}: {name}"


def _meta_lines(resource: dict) -> list[str]:
    """Return common FSH metadata lines (Id, Title, Description, etc.)."""
    lines: list[str] = []
    if "id" in resource:
        lines.append(f"Id: {resource['id']}")
    if "url" in resource:
        lines.append(f"* url = \"{resource['url']}\"")
    if "version" in resource:
        lines.append(f"* version = \"{resource['version']}\"")
    if "name" in resource:
        lines.append(f"* name = \"{resource['name']}\"")
    if "title" in resource:
        lines.append(f"* title = \"{resource['title']}\"")
    if "description" in resource:
        desc = resource["description"].replace('"', '\\"')
        lines.append(f"* description = \"{desc}\"")
    if "status" in resource:
        lines.append(f"* status = #{resource['status']}")
    if "date" in resource:
        lines.append(f"* date = \"{resource['date']}\"")
    if "publisher" in resource:
        lines.append(f"* publisher = \"{resource['publisher']}\"")
    return lines


def _extension_fsh(ext: dict, path_prefix: str = "*") -> list[str]:
    """Render a single FHIR extension as FSH rule lines."""
    lines: list[str] = []
    url = ext.get("url", "")
    # Nested extensions
    if "extension" in ext:
        for sub in ext["extension"]:
            sub_url = sub.get("url", "")
            for vk, vv in sub.items():
                if vk in ("url",):
                    continue
                lines.append(f"{path_prefix}.extension[{_quote(url)}].extension[{_quote(sub_url)}].{vk} = {_fsh_value(vv)}")
        return lines
    # Simple value extension
    for vk, vv in ext.items():
        if vk == "url":
            continue
        lines.append(f"{path_prefix}.extension[{_quote(url)}].{vk} = {_fsh_value(vv)}")
    return lines


def _quote(s: str) -> str:
    return f'"{s}"'


def _fsh_value(v: Any) -> str:
    """Convert a Python value to its FSH literal representation."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        # FHIR code references (e.g. #active) vs plain strings
        return f'"{v}"'
    if isinstance(v, dict):
        # Inline JSON for complex types
        return json.dumps(v)
    if isinstance(v, list):
        return json.dumps(v)
    return f'"{v}"'


# ---------------------------------------------------------------------------
# Questionnaire serializer
# ---------------------------------------------------------------------------

def _questionnaire_fsh(resource: dict) -> str:
    """Serialize a Questionnaire resource to FSH."""
    name = _safe_name(resource.get("id") or resource.get("name") or "Questionnaire")
    lines = [f"Instance: {name}", "InstanceOf: SDCQuestionnaireExtract"]
    lines += _meta_lines(resource)

    # Top-level extensions
    for ext in resource.get("extension", []):
        lines += _extension_fsh(ext)

    # Items
    for item in resource.get("item", []):
        lines += _questionnaire_item_fsh(item, "item")

    return "\n".join(lines) + "\n"


def _questionnaire_item_fsh(item: dict, path: str) -> list[str]:
    """Recursively render a Questionnaire.item as FSH rules."""
    lines: list[str] = []
    link_id = item.get("linkId", "")
    item_path = f"{path}[{_quote(link_id)}]"

    lines.append(f"* {item_path}.linkId = \"{link_id}\"")
    if "type" in item:
        lines.append(f"* {item_path}.type = #{item['type']}")
    if "text" in item:
        lines.append(f"* {item_path}.text = \"{item['text']}\"")
    # Dynamic display text (cqf-expression) hangs off the text element itself.
    for ext in (item.get("_text") or {}).get("extension", []):
        lines += _extension_fsh(ext, f"* {item_path}.text")
    if "required" in item:
        lines.append(f"* {item_path}.required = {str(item['required']).lower()}")
    if "repeats" in item:
        lines.append(f"* {item_path}.repeats = {str(item['repeats']).lower()}")
    if "readOnly" in item:
        lines.append(f"* {item_path}.readOnly = {str(item['readOnly']).lower()}")
    if "answerValueSet" in item:
        lines.append(f"* {item_path}.answerValueSet = \"{item['answerValueSet']}\"")

    for ext in item.get("extension", []):
        lines += _extension_fsh(ext, f"* {item_path}")

    for sub in item.get("item", []):
        lines += _questionnaire_item_fsh(sub, f"{item_path}.item")

    return lines


# ---------------------------------------------------------------------------
# Library serializer
# ---------------------------------------------------------------------------

def _library_fsh(resource: dict) -> str:
    """Serialize a Library resource to FSH."""
    name = _safe_name(resource.get("id") or resource.get("name") or "Library")
    lines = [f"Instance: {name}", "InstanceOf: Library"]
    lines += _meta_lines(resource)

    if "type" in resource:
        coding = resource["type"].get("coding", [{}])[0]
        system = coding.get("system", "")
        code = coding.get("code", "")
        lines.append(f"* type = {_quote(system)}#{code}")

    for content in resource.get("content", []):
        ct = content.get("contentType", "")
        data = content.get("data", "")
        lines.append(f"* content[+].contentType = \"{ct}\"")
        lines.append(f"* content[=].data = \"{data}\"")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# StructureMap serializer
# ---------------------------------------------------------------------------

def _structuremap_fsh(resource: dict) -> str:
    """Serialize a StructureMap resource to FSH (as an Instance)."""
    name = _safe_name(resource.get("id") or resource.get("name") or "StructureMap")
    lines = [f"Instance: {name}", "InstanceOf: StructureMap"]
    lines += _meta_lines(resource)

    # StructureMap groups are complex; embed as JSON content note
    if "group" in resource:
        lines.append("// StructureMap groups are defined in the source FML/map file.")
        lines.append(f"// Full resource: see {name}.json")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# ValueSet serializer
# ---------------------------------------------------------------------------

def _valueset_fsh(resource: dict) -> str:
    """Serialize a ValueSet resource to FSH."""
    name = _safe_name(resource.get("id") or resource.get("name") or "ValueSet")
    lines = [f"ValueSet: {name}"]
    if "id" in resource:
        lines.append(f"Id: {resource['id']}")
    if "url" in resource:
        lines.append(f"* ^url = \"{resource['url']}\"")
    if "version" in resource:
        lines.append(f"* ^version = \"{resource['version']}\"")
    if "name" in resource:
        lines.append(f"* ^name = \"{resource['name']}\"")
    if "title" in resource:
        lines.append(f"* ^title = \"{resource['title']}\"")
    if "status" in resource:
        lines.append(f"* ^status = #{resource['status']}")

    compose = resource.get("compose", {})
    for include in compose.get("include", []):
        system = include.get("system", "")
        for concept in include.get("concept", []):
            code = concept.get("code", "")
            display = concept.get("display", "")
            if display:
                lines.append(f"* {_quote(system)}#{code} \"{display}\"")
            else:
                lines.append(f"* {_quote(system)}#{code}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# PlanDefinition serializer
# ---------------------------------------------------------------------------

def _plandefinition_fsh(resource: dict) -> str:
    """Serialize a PlanDefinition resource to FSH."""
    name = _safe_name(resource.get("id") or resource.get("name") or "PlanDefinition")
    lines = [f"Instance: {name}", "InstanceOf: PlanDefinition"]
    lines += _meta_lines(resource)

    if "type" in resource:
        coding = resource["type"].get("coding", [{}])[0]
        system = coding.get("system", "")
        code = coding.get("code", "")
        lines.append(f"* type = {_quote(system)}#{code}")

    for trigger in resource.get("trigger", []):
        t_type = trigger.get("type", "")
        t_name = trigger.get("name", "")
        lines.append(f"* trigger[+].type = #{t_type}")
        if t_name:
            lines.append(f"* trigger[=].name = \"{t_name}\"")

    for action in resource.get("action", []):
        lines += _plandefinition_action_fsh(action, "action")

    return "\n".join(lines) + "\n"


def _plandefinition_action_fsh(action: dict, path: str) -> list[str]:
    """Render a PlanDefinition.action as FSH rules."""
    lines: list[str] = []
    lines.append(f"* {path}[+].title = \"{action.get('title', '')}\"")
    if "description" in action:
        lines.append(f"* {path}[=].description = \"{action['description']}\"")
    if "definitionCanonical" in action:
        lines.append(f"* {path}[=].definitionCanonical = \"{action['definitionCanonical']}\"")
    for cond in action.get("condition", []):
        kind = cond.get("kind", "")
        expr = cond.get("expression", {})
        lang = expr.get("language", "")
        exp_str = expr.get("expression", "").replace('"', '\\"')
        lines.append(f"* {path}[=].condition[+].kind = #{kind}")
        lines.append(f"* {path}[=].condition[=].expression.language = \"{lang}\"")
        lines.append(f"* {path}[=].condition[=].expression.expression = \"{exp_str}\"")
    return lines


# ---------------------------------------------------------------------------
# Composition serializer
# ---------------------------------------------------------------------------

def _composition_fsh(resource: dict) -> str:
    """Serialize a Composition resource to FSH."""
    name = _safe_name(resource.get("id") or resource.get("title") or "Composition")
    lines = [f"Instance: {name}", "InstanceOf: Composition"]
    lines += _meta_lines(resource)

    if "type" in resource:
        coding = resource["type"].get("coding", [{}])[0]
        system = coding.get("system", "")
        code = coding.get("code", "")
        lines.append(f"* type = {_quote(system)}#{code}")

    if "subject" in resource:
        ref = resource["subject"].get("reference", "")
        lines.append(f"* subject = Reference({ref})")

    for section in resource.get("section", []):
        title = section.get("title", "")
        lines.append(f"* section[+].title = \"{title}\"")
        for entry in section.get("entry", []):
            ref = entry.get("reference", "")
            lines.append(f"* section[=].entry[+] = Reference({ref})")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Binary serializer
# ---------------------------------------------------------------------------

def _binary_fsh(resource: dict) -> str:
    """Serialize a Binary resource to FSH."""
    name = _safe_name(resource.get("id") or "Binary")
    lines = [f"Instance: {name}", "InstanceOf: Binary"]
    if "id" in resource:
        lines.append(f"Id: {resource['id']}")
    if "contentType" in resource:
        lines.append(f"* contentType = \"{resource['contentType']}\"")
    if "data" in resource:
        lines.append(f"* data = \"{resource['data']}\"")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Generic fallback
# ---------------------------------------------------------------------------

def _generic_instance_fsh(resource: dict) -> str:
    """Generic FSH Instance block wrapping the full resource as a comment."""
    resource_type = resource.get("resourceType", "Resource")
    name = _safe_name(resource.get("id") or resource_type)
    lines = [
        f"Instance: {name}",
        f"InstanceOf: {resource_type}",
        "// Auto-generated from TRICC — review before use",
    ]
    lines += _meta_lines(resource)
    # Dump remaining keys as comments for manual review
    skip = {"resourceType", "id", "url", "version", "name", "title", "description", "status", "date", "publisher"}
    for k, v in resource.items():
        if k not in skip:
            lines.append(f"// {k}: {json.dumps(v)}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe_name(raw: str) -> str:
    """Convert an arbitrary string to a valid FSH identifier."""
    import re
    # Replace non-alphanumeric (except hyphens) with underscores
    safe = re.sub(r"[^A-Za-z0-9\-]", "_", raw)
    # FSH identifiers must start with a letter
    if safe and not safe[0].isalpha():
        safe = "R_" + safe
    return safe or "Resource"


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_SERIALIZERS = {
    "Questionnaire": _questionnaire_fsh,
    "Library": _library_fsh,
    "StructureMap": _structuremap_fsh,
    "ValueSet": _valueset_fsh,
    "PlanDefinition": _plandefinition_fsh,
    "Composition": _composition_fsh,
    "Binary": _binary_fsh,
}
