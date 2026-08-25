"""QuestionnaireResponse → Bundle extraction StructureMaps.

Driven by the CodeSystem ``conceptType`` (and node-type fallbacks in
``concept_mapper``):

* Symptom-Finding / Question / finding → ``Observation``
* proposed_diagnosis → ``Condition`` (verificationStatus = provisional)
* AcceptDiag → ``Condition`` (confirmed when accepted, refuted when rejected)
* ``repeat != 1`` → Observation repeat-index extension
* Calculation / InteractSet / Value / ``final.{code}`` calculates are not extracted
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from tricc_oo.converters.datadictionnary import lookup_codesystems_code
from tricc_oo.converters.fhir.concept_mapper import (
    classify_extraction,
    diagnosis_concept_code,
    get_qr_value_field,
    resolve_concept_type,
)
from tricc_oo.converters.fhir.ids import fhir_resource_id, to_fhir_id
from tricc_oo.converters.fhir.questionnaire_item_mapper import (
    get_fhir_item_type,
    is_calculate_type,
    is_hidden,
)
from tricc_oo.converters.fhir.repeat_helper import (
    TRICC_OBSERVATION_REPEAT_EXT,
    fml_repeat_extension_on_target,
    should_emit_repeat_metadata,
)
from tricc_oo.converters.tricc_to_xls_form import get_export_name
from tricc_oo.models.base import RETURNS_BOOLEAN, TriccOperation, TriccOperator, get_repeat

logger = logging.getLogger("default")

_YESNO_MARKERS = {"true", "yes", "1", "y", "false", "no", "0", "n"}

CONDITION_CLINICAL_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-clinical"
CONDITION_VERIFICATION_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
CONDITION_CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-category"
DEFAULT_CODE_SYSTEM = "https://fhir.tricc.io/CodeSystem/tricc"
SDC_EXT_TARGET_STRUCTUREMAP = (
    "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-targetStructureMap"
)

_GROUP_SAFE = re.compile(r"[^A-Za-z0-9]+")


@dataclass
class ExtractionRule:
    """One extractable concept/repeat slot → FHIR resource mapping.

    ``link_ids`` lists Questionnaire ``linkId``s for this concept and repeat
    (newest first). Extraction writes one resource from the first non-null
    answer among those items.
    """

    link_id: str
    concept_code: str
    display: str
    concept_type: str
    kind: str
    qr_value_field: str
    item_type: str
    repeat: Optional[int]
    code_system_url: str
    group_name: str
    only_when_true: bool = False
    link_ids: List[str] = field(default_factory=list)
    version: int = 1
    path_len: int = 0


def _expression_is_boolean(node) -> bool:
    """True when the node's calculate expression is a boolean operation.

    Matches FHIRStrategy._expression_returns_boolean (CONTAINS / SELECTED / …)
    so option-flag calculates stay boolean in extraction as well as the Questionnaire.
    """
    expr = getattr(node, "expression_reference", None) or getattr(node, "expression", None)
    return _operation_is_boolean(expr)


def _operation_is_boolean(expr) -> bool:
    if not isinstance(expr, TriccOperation):
        return False
    if expr.operator == TriccOperator.PARENTHESIS and expr.reference:
        return _operation_is_boolean(expr.reference[0])
    return expr.operator in RETURNS_BOOLEAN or expr.operator in (
        TriccOperator.ISNULL,
        TriccOperator.CAST_BOOLEAN,
    )


def _is_hidden_boolean_flag(node, item_type: str) -> bool:
    """Hidden/calculate boolean (option-selected flags) — persist only when true."""
    if item_type != "boolean":
        return False
    tricc_type = getattr(node, "tricc_type", None)
    return bool(is_hidden(tricc_type) or is_calculate_type(tricc_type))


def _is_yesno_boolean_select(node) -> bool:
    options = getattr(node, "options", None) or {}
    if len(options) != 2:
        return False
    opt_names = {str(o.name).lower() for o in options.values()}
    opt_codes = {str(getattr(o, "code", "")).lower() for o in options.values()}
    return bool(opt_names & _YESNO_MARKERS or opt_codes & _YESNO_MARKERS)


def _fml_escape(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace("'", "\\'")


def _xml_escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _group_name(prefix: str, link_id: str) -> str:
    cleaned = _GROUP_SAFE.sub("_", link_id or "item").strip("_")
    if not cleaned:
        cleaned = "item"
    if cleaned[0].isdigit():
        cleaned = f"n_{cleaned}"
    return f"{prefix}_{cleaned}"


def _repeat_slot(repeat: Optional[int]) -> int:
    """Default capture slot is 1 (``None`` and ``1`` are the same Observation)."""
    return 1 if repeat is None else int(repeat)


def _extract_group_name(concept_code: str, repeat: Optional[int]) -> str:
    """StructureMap group name: one per concept + repeat, never a ``_Vv_`` version."""
    base = concept_code or "item"
    slot = _repeat_slot(repeat)
    if slot != 1:
        base = f"{base}_Rr_{str(slot).replace('-', 'n')}"
    return _group_name("extract", str(base))


def _rule_rank(rule: ExtractionRule) -> tuple:
    """Newest-first rank, same as GET_INHERITED_VALUE: (path_len, version)."""
    return (int(rule.path_len or 0), int(rule.version or 0))


def extraction_rule_link_ids(rule) -> List[str]:
    """Questionnaire ``linkId``s this rule reads, newest first."""
    ids: List[str] = []
    for lid in list(getattr(rule, "link_ids", None) or []):
        if lid and lid not in ids:
            ids.append(str(lid))
    lid = getattr(rule, "link_id", None)
    if lid and str(lid) not in ids:
        ids.insert(0, str(lid))
    return ids


def extraction_rules_conflict(left: ExtractionRule, right: ExtractionRule) -> bool:
    """True when two rules share a concept/repeat key but would extract differently."""
    return (
        left.kind,
        left.item_type,
        left.only_when_true,
        left.qr_value_field,
    ) != (
        right.kind,
        right.item_type,
        right.only_when_true,
        right.qr_value_field,
    )


def _merge_key(rule: ExtractionRule) -> tuple:
    return (rule.kind, str(rule.concept_code), _repeat_slot(rule.repeat))


def merge_extraction_rules(rules: List[ExtractionRule]) -> List[ExtractionRule]:
    """One rule per concept + repeat; ``link_ids`` newest first.

    HAPI ``resolveGroupReference`` requires a unique group name. Versions of
    the same concept (``p_age_years``, ``p_age_years_Vv_1``) share one group
    and extract the first non-null answer. See
    fix/20260824-structuremap-duplicate-extract-groups.md.
    """
    buckets: dict = {}
    order: List[tuple] = []
    for rule in rules or []:
        key = _merge_key(rule)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(rule)
    out: List[ExtractionRule] = []
    for key in order:
        members = sorted(buckets[key], key=_rule_rank, reverse=True)
        winner = members[0]
        for other in members[1:]:
            if extraction_rules_conflict(winner, other):
                logger.warning(
                    "StructureMap: merging extract group '%s' despite mismatched "
                    "kind/type (kept %s/%s, skipped %s/%s from linkId %s)",
                    winner.group_name,
                    winner.kind,
                    winner.item_type,
                    other.kind,
                    other.item_type,
                    other.link_id,
                )
        seen_ids: List[str] = []
        for member in members:
            for lid in extraction_rule_link_ids(member):
                if lid not in seen_ids:
                    seen_ids.append(lid)
        winner.link_ids = seen_ids
        winner.link_id = seen_ids[0]
        winner.group_name = _extract_group_name(winner.concept_code, winner.repeat)
        out.append(winner)
    return out


def dedupe_extraction_rules(rules: List[ExtractionRule]) -> List[ExtractionRule]:
    """Alias for ``merge_extraction_rules`` (unique group per concept/repeat)."""
    return merge_extraction_rules(rules)


def _concept_system_url(codesystems, code: str, default_url: str) -> str:
    if not codesystems or not code:
        return default_url
    concept = lookup_codesystems_code(codesystems, code)
    if concept is None:
        return default_url
    for cs in codesystems.values():
        for item in cs.concept or []:
            if item is concept or getattr(item, "code", None) == code:
                return getattr(cs, "url", None) or default_url
    return default_url


def build_extraction_rule(
    node,
    codesystems=None,
    default_code_system: str = DEFAULT_CODE_SYSTEM,
) -> Optional[ExtractionRule]:
    """Build an extraction rule for ``node``, or None when it should not be persisted."""
    kind = classify_extraction(node, codesystems)
    if kind is None:
        return None
    try:
        link_id = get_export_name(node)
    except Exception:
        link_id = getattr(node, "name", None) or getattr(node, "id", None)
    if not link_id:
        return None

    if kind in ("proposed_condition", "accept_condition"):
        concept_code = diagnosis_concept_code(node)
    else:
        concept_code = getattr(node, "save", None) or getattr(node, "name", None) or link_id

    display = getattr(node, "label", None) or concept_code or link_id
    if not isinstance(display, str):
        display = str(concept_code or link_id)

    tricc_type = getattr(node, "tricc_type", None)
    item_type = get_fhir_item_type(tricc_type) or "string"
    if item_type == "choice" and _is_yesno_boolean_select(node):
        item_type = "boolean"
    if item_type in ("string", "choice") and _expression_is_boolean(node):
        item_type = "boolean"
    if kind in ("proposed_condition", "accept_condition"):
        item_type = "boolean"

    only_when_true = kind == "observation" and _is_hidden_boolean_flag(node, item_type)

    repeat = get_repeat(node) if should_emit_repeat_metadata(node) and kind == "observation" else None
    export_id = str(link_id)
    return ExtractionRule(
        link_id=export_id,
        concept_code=str(concept_code),
        display=display,
        concept_type=resolve_concept_type(node, codesystems),
        kind=kind,
        qr_value_field=get_qr_value_field(item_type),
        item_type=item_type,
        repeat=repeat,
        code_system_url=_concept_system_url(codesystems, concept_code, default_code_system),
        group_name=_extract_group_name(str(concept_code), repeat),
        only_when_true=only_when_true,
        link_ids=[export_id],
        version=int(getattr(node, "version", None) or 1),
        path_len=int(getattr(node, "path_len", None) or 0),
    )


SDC_QUESTIONNAIRE_HIDDEN = "http://hl7.org/fhir/StructureDefinition/questionnaire-hidden"


def apply_questionnaire_item_to_rule(rule: ExtractionRule, item: Optional[dict]) -> ExtractionRule:
    """Align an extraction rule with the Questionnaire item that will actually be answered.

    Hidden boolean items (option-selected flags) extract only when the answer is
    true and write ``Observation.valueBoolean = true``.
    """
    if not item or rule.kind != "observation":
        return rule
    if item.get("type") == "boolean":
        rule.item_type = "boolean"
        rule.qr_value_field = "valueBoolean"
        hidden = any(
            (ext or {}).get("url") == SDC_QUESTIONNAIRE_HIDDEN
            for ext in (item.get("extension") or [])
        )
        if hidden:
            rule.only_when_true = True
    return rule


def _cc(system: str, code: str, display: str) -> str:
    return (
        f"cc('{_fml_escape(system)}', '{_fml_escape(code)}', '{_fml_escape(display)}')"
    )


def _obs_value_rules(rule: ExtractionRule) -> List[str]:
    """Copy QuestionnaireResponse.answer.value[x] onto Observation.value[x].

    HAPI ``getProperty`` only exposes the polymorphic ``value`` child on Answer
    and Observation — ``valueBoolean`` / ``valueString`` / ``valueCoding`` throw
    ``Attempt to read invalid property``. FML must use ``answer.value : <type>``
    and write ``tgt.value``.
    """
    if rule.only_when_true:
        # Option / hidden flag: presence of a true answer is the finding.
        return ['      src -> tgt.value = true "value";']
    field = rule.qr_value_field
    if field == "valueCoding":
        return [
            "      answer.value : Coding as coding -> tgt.value = create('CodeableConcept') as cc then {",
            '        coding -> cc.coding = coding "coding";',
            '      } "value";',
        ]
    if field == "valueDecimal":
        return [
            "      answer.value : decimal as val -> tgt.value = create('Quantity') as qty then {",
            '        val -> qty.value = val "qtyValue";',
            '      } "value";',
        ]
    if field == "valueQuantity":
        return [
            '      answer.value : Quantity as qty -> tgt.value = qty "value";',
        ]
    if field == "valueDate":
        return [
            '      answer.value : date as val -> tgt.value = val "value";',
        ]
    type_name = {
        "valueBoolean": "boolean",
        "valueInteger": "integer",
        "valueString": "string",
        "valueDateTime": "dateTime",
    }.get(field, "string")
    return [f'      answer.value : {type_name} as val -> tgt.value = val "value";']


def _condition_status_fml(target: str, clinical: str, verification: str) -> List[str]:
    return [
        f"      src -> {target}.clinicalStatus = "
        f"{_cc(CONDITION_CLINICAL_SYSTEM, clinical, clinical)} \"clinical\";",
        f"      src -> {target}.verificationStatus = "
        f"{_cc(CONDITION_VERIFICATION_SYSTEM, verification, verification)} \"verification\";",
        f"      src -> {target}.category = "
        f"{_cc(CONDITION_CATEGORY_SYSTEM, 'encounter-diagnosis', 'Encounter Diagnosis')} "
        f"\"category\";",
    ]


def _create_resource_entry(resource_type: str, inner: Iterable[str]) -> List[str]:
    lines = [
        "  src -> bundle.entry as entry then {",
        "    src -> entry.request as req then {",
        "      src -> req.method = 'POST' \"method\";",
        f"      src -> req.url = '{resource_type}' \"url\";",
        '    } "req";',
        f"    src -> entry.resource = create('{resource_type}') as tgt then {{",
        '      src.subject as subject -> tgt.subject = subject "subject";',
        '      src.encounter as enc -> tgt.encounter = enc "encounter";',
    ]
    lines.extend(inner)
    lines.append('    } "resource";')
    lines.append('  } "entry";')
    return lines


def _observation_group(rule: ExtractionRule) -> str:
    inner = [
        "      src -> tgt.status = 'final' \"status\";",
        f"      src -> tgt.code = {_cc(rule.code_system_url, rule.concept_code, rule.display)} \"code\";",
        '      src.authored as authored -> tgt.effective = authored "effective";',
    ]
    inner.extend(_obs_value_rules(rule))
    if rule.repeat is not None:
        inner.append(
            fml_repeat_extension_on_target("tgt", rule.repeat, rule.group_name).rstrip("\n")
        )
    body = "\n".join(_create_resource_entry("Observation", inner))
    return (
        f"group {rule.group_name}"
        f"(source answer, source src : QuestionnaireResponse, target bundle : Bundle) {{\n"
        f"{body}\n"
        f"}}\n"
    )


def _condition_group(rule: ExtractionRule, verification: str, clinical: str, group_name: str) -> str:
    inner = [
        *_condition_status_fml("tgt", clinical, verification),
        f"      src -> tgt.code = {_cc(rule.code_system_url, rule.concept_code, rule.display)} \"code\";",
        '      src.authored as authored -> tgt.recordedDate = authored "recordedDate";',
    ]
    body = "\n".join(_create_resource_entry("Condition", inner))
    return (
        f"group {group_name}"
        f"(source answer, source src : QuestionnaireResponse, target bundle : Bundle) {{\n"
        f"{body}\n"
        f"}}\n"
    )


def _and_where(*parts: str) -> str:
    return " and ".join(p for p in parts if p)


def _preferred_unanswered_where(preferred_link_ids: List[str]) -> str:
    """True when every newer version of this concept has no answer.

    Evaluated against the current item; ``src`` is the QuestionnaireResponse
    StructureMap variable (HAPI FHIRPath ``resolveConstant``).
    """
    return " and ".join(
        f"src.repeat(item).where(linkId = '{_fml_escape(lid)}').answer.empty()"
        for lid in preferred_link_ids
        if lid
    )


def _dispatch_block(
    link_id: str,
    group_name: str,
    extra_where: str = "",
    rule_name: Optional[str] = None,
) -> str:
    """HAPI FML ``where`` clause (not FHIRPath ``item.where()``).

    OpenSRP compiles FML with ``StructureMapUtilities.parse``. The parser
    accepts ``item as q where(linkId = 'x')`` the same way
    ``cdss-client-registration.map`` does, and rejects ``item.where(...)``.
    """
    where = _and_where(f"linkId = '{link_id}'", extra_where)
    name = rule_name or group_name
    return (
        f"  item as q where({where}) then {{\n"
        f"    q.answer as answer then {group_name}(answer, src, bundle) \"answer\";\n"
        f'  }} "{name}";'
    )


def _item_dispatch_rule(rule: ExtractionRule) -> str:
    """Dispatch each version ``linkId`` to one group; older only if newer is empty."""
    ids = extraction_rule_link_ids(rule)
    if not ids:
        return ""
    multi = len(ids) > 1
    lines: List[str] = []
    for index, lid in enumerate(ids):
        preferred = _preferred_unanswered_where(ids[:index])
        suffix = f"_{index}" if multi else ""
        escaped = _fml_escape(lid)
        if rule.kind == "observation" and rule.only_when_true:
            extra = _and_where(preferred, "answer.valueBoolean = true")
            lines.append(
                _dispatch_block(escaped, rule.group_name, extra, rule.group_name + suffix)
            )
        elif rule.kind == "proposed_condition":
            extra = _and_where(preferred, "answer.valueBoolean = true")
            lines.append(
                _dispatch_block(escaped, rule.group_name, extra, rule.group_name + suffix)
            )
        elif rule.kind == "accept_condition":
            yes = f"{rule.group_name}_confirmed"
            no = f"{rule.group_name}_refuted"
            lines.append(
                _dispatch_block(
                    escaped, yes, _and_where(preferred, "answer.valueBoolean = true"), yes + suffix
                )
            )
            lines.append(
                _dispatch_block(
                    escaped, no, _and_where(preferred, "answer.valueBoolean = false"), no + suffix
                )
            )
        else:
            lines.append(
                _dispatch_block(escaped, rule.group_name, preferred, rule.group_name + suffix)
            )
    return "\n".join(lines)


def build_extraction_fml(
    rules: List[ExtractionRule],
    url: str,
    name: str,
) -> str:
    """Return FML source for a QuestionnaireResponse → transaction Bundle map."""
    rules = merge_extraction_rules(rules)
    uses = [
        f'map "{url}" = \'{name}\'',
        "",
        'uses "http://hl7.org/fhir/StructureDefinition/QuestionnaireResponse" as source',
        'uses "http://hl7.org/fhir/StructureDefinition/Bundle" as target',
        'uses "http://hl7.org/fhir/StructureDefinition/Observation" as target',
        'uses "http://hl7.org/fhir/StructureDefinition/Condition" as target',
        "",
        "// Extraction driven by CodeSystem conceptType (Symptom-Finding → Observation,",
        "// Diagnosis / proposed_diagnosis → Condition provisional, AcceptDiag → confirmed/refuted).",
        f"// Repeat slot (when repeat != 1) is written to {TRICC_OBSERVATION_REPEAT_EXT}.",
        "",
        "group extract(source src : QuestionnaireResponse, target bundle : Bundle) {",
        "  src -> bundle.type = 'transaction' \"type\";",
        '  src.item as item then extractItems(item, src, bundle) "walkItems";',
        "}",
        "",
        "group extractItems(source item, source src : QuestionnaireResponse, target bundle : Bundle) {",
        '  item.item as child then extractItems(child, src, bundle) "walkChildren";',
    ]
    for rule in rules:
        uses.append(_item_dispatch_rule(rule))
    uses.append("}")
    uses.append("")

    groups: List[str] = []
    for rule in rules:
        if rule.kind == "observation":
            groups.append(_observation_group(rule))
        elif rule.kind == "proposed_condition":
            groups.append(_condition_group(rule, "provisional", "active", rule.group_name))
        elif rule.kind == "accept_condition":
            groups.append(_condition_group(rule, "confirmed", "active", f"{rule.group_name}_confirmed"))
            groups.append(_condition_group(rule, "refuted", "inactive", f"{rule.group_name}_refuted"))
    return "\n".join(uses) + "\n" + "\n".join(groups)


def _structure_group_json(name: str, rules: List[dict], documentation: str = "") -> dict:
    group = {
        "name": name,
        "typeMode": "none",
        "input": [
            {
                "name": "src" if name == "extract" else "item",
                "type": "QuestionnaireResponse" if name == "extract" else None,
                "mode": "source",
            },
            {"name": "bundle", "type": "Bundle", "mode": "target"},
        ],
        "rule": rules,
    }
    if name != "extract":
        group["input"] = [
            {"name": "item", "mode": "source"},
            {"name": "src", "type": "QuestionnaireResponse", "mode": "source"},
            {"name": "bundle", "type": "Bundle", "mode": "target"},
        ]
    if documentation:
        group["documentation"] = documentation
    # drop None types
    for inp in group["input"]:
        if inp.get("type") is None:
            inp.pop("type", None)
    return group


def build_extraction_structuremap(
    rules: List[ExtractionRule],
    form_id: str,
    process: str,
    base_url: str,
    version: str = "1.0.0",
) -> dict:
    """Build a FHIR StructureMap resource (JSON + ``_fml`` companion text)."""
    rules = merge_extraction_rules(rules)
    sm_id = fhir_resource_id(form_id, "StructureMap", process, "extract")
    sm_name = to_fhir_id(form_id, process, "extract").replace("-", "_")
    url = f"{base_url.rstrip('/')}/StructureMap/{sm_id}"
    fml = build_extraction_fml(rules, url, sm_id)

    dispatch_rules = []
    for rule in rules:
        ids = extraction_rule_link_ids(rule)
        multi = len(ids) > 1
        for index, lid in enumerate(ids):
            preferred = _preferred_unanswered_where(ids[:index])
            condition = _and_where(f"linkId = '{_fml_escape(lid)}'", preferred)
            suffix = f"_{index}" if multi else ""
            dispatch_rules.append(
                {
                    "name": rule.group_name + suffix,
                    "source": [{"context": "item", "condition": condition}],
                    "dependent": [
                        {"name": rule.group_name, "variable": ["answer", "src", "bundle"]}
                    ],
                }
            )

    structuremap = {
        "resourceType": "StructureMap",
        "id": sm_id,
        "url": url,
        "name": sm_name,
        "title": f"Extract {process} QuestionnaireResponse",
        "version": version or "1.0.0",
        "status": "active",
        "description": (
            f"QuestionnaireResponse → transaction Bundle for process '{process}'. "
            "conceptType Symptom-Finding/Question → Observation; proposed_diagnosis → "
            "Condition (provisional); AcceptDiag → Condition confirmed or refuted. "
            "Repeat != 1 writes the observation-repeat-index extension."
        ),
        "structure": [
            {"url": "http://hl7.org/fhir/StructureDefinition/QuestionnaireResponse", "mode": "source"},
            {"url": "http://hl7.org/fhir/StructureDefinition/Bundle", "mode": "target"},
        ],
        "group": [
            _structure_group_json(
                "extract",
                [
                    {
                        "name": "bundleType",
                        "source": [{"context": "src"}],
                        "target": [
                            {
                                "context": "bundle",
                                "contextType": "variable",
                                "element": "type",
                                "transform": "copy",
                                "parameter": [{"valueString": "transaction"}],
                            }
                        ],
                    }
                ],
                "Create a transaction Bundle and walk QuestionnaireResponse items.",
            ),
            _structure_group_json("extractItems", dispatch_rules),
        ],
        "text": {
            "status": "generated",
            "div": (
                f'<div xmlns="http://www.w3.org/1999/xhtml"><pre>{_xml_escape(fml)}</pre></div>'
            ),
        },
        "_fml": fml,
    }
    return structuremap


def target_structuremap_extension(canonical_url: str) -> dict:
    """SDC targetStructureMap extension pointing at an extraction StructureMap."""
    return {
        "url": SDC_EXT_TARGET_STRUCTUREMAP,
        "valueCanonical": canonical_url,
    }
