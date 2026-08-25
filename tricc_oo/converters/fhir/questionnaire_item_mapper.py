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
SDC_EXT_ANSWER_OPTIONS_TOGGLE = (
    "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-answerOptionsToggleExpression"
)
SDC_EXT_INITIAL_EXPR = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression"
SDC_EXT_CALCULATED_EXPR = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-calculatedExpression"
SDC_EXT_ITEM_MEDIA = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-itemMedia"
SDC_EXT_ITEM_ANSWER_MEDIA = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-itemAnswerMedia"
SDC_EXT_HIDDEN = "http://hl7.org/fhir/StructureDefinition/questionnaire-hidden"
SDC_EXT_CHOICE_ORIENTATION = "http://hl7.org/fhir/StructureDefinition/questionnaire-choiceOrientation"
SDC_EXT_ITEM_CONTROL = "http://hl7.org/fhir/StructureDefinition/questionnaire-itemControl"
SDC_EXT_ENTRY_FORMAT = "http://hl7.org/fhir/StructureDefinition/entryFormat"
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
    TriccNodeType.activity_end:     (None,    False, True),
    TriccNodeType.end:              (None,    False, True),
    TriccNodeType.rhombus:          (FHIR_TYPE_BOOLEAN,  False, True),
    TriccNodeType.factor:           (FHIR_TYPE_DECIMAL,  False, True),
    TriccNodeType.populate:         (FHIR_TYPE_STRING,   False, True),
    TriccNodeType.bridge:           (FHIR_TYPE_BOOLEAN,  False, True),
    TriccNodeType.wait:             (FHIR_TYPE_BOOLEAN,  False, True),
    TriccNodeType.goto:             (None,    False, True),
    TriccNodeType.link_in:          (None, False, True),
    TriccNodeType.link_out:         (None,    False, True),
    TriccNodeType.activity:         (FHIR_TYPE_GROUP, False, False),
    TriccNodeType.exclusive:         (None, False, False),
}

# Node types that should be skipped entirely (not added to Questionnaire)
SKIP_NODE_TYPES = {
    TriccNodeType.page,
    TriccNodeType.activity,
    TriccNodeType.edge,
    TriccNodeType.select_option,
    TriccNodeType.not_available,
    TriccNodeType.context,
    TriccNodeType.remote_reference,
    TriccNodeType.operation,
    # Enrichment boxes are copied onto the target node's help/hint; they are not items.
    TriccNodeType.help,
    TriccNodeType.hint,
}

# SDC forbids Questionnaire.item.initial and sdc-questionnaire-initialExpression on
# these types (http://build.fhir.org/ig/HL7/sdc/expressions.html#initialExpression).
# openSRP FHIR Data Capture throws IllegalStateException at $populate if they appear.
FHIR_TYPES_WITHOUT_INITIAL = frozenset({FHIR_TYPE_DISPLAY, FHIR_TYPE_GROUP})

# SDC 0..1 on Questionnaire.item. A second copy crashes openSRP FHIR Data Capture
# at render time (fix/20260821-sdc-singleton-expressions.md).
SDC_SINGLETON_ITEM_EXPRESSION_URLS = frozenset(
    {
        SDC_EXT_CALCULATED_EXPR,
        SDC_EXT_INITIAL_EXPR,
        SDC_EXT_ENABLE_WHEN_EXPR,
    }
)


def item_allows_initial(item: Optional[dict]) -> bool:
    """Return True if SDC allows ``initial`` / ``initialExpression`` on this item.

    Args:
        item: A Questionnaire.item dict (may be None).

    Returns:
        False for ``group`` and ``display`` items (and when ``item`` is missing).
    """
    if not item:
        return False
    return item.get("type") not in FHIR_TYPES_WITHOUT_INITIAL


def strip_illegal_initials(items: Optional[list]) -> int:
    """Remove ``initial`` and ``initialExpression`` from group/display items.

    Walks ``items`` (and nested ``item`` children) in place. Used as a last-line
    export sanitizer so a future attachment path cannot ship a Questionnaire
    that openSRP refuses to render.

    Args:
        items: Questionnaire.item list (may be None).

    Returns:
        Number of items that had an illegal initial / initialExpression removed.
    """
    stripped = 0
    for item in items or []:
        if not item_allows_initial(item):
            had_initial = bool(item.pop("initial", None))
            kept = []
            removed_ext = False
            for ext in item.get("extension") or []:
                if ext.get("url") == SDC_EXT_INITIAL_EXPR:
                    removed_ext = True
                    continue
                kept.append(ext)
            if removed_ext:
                if kept:
                    item["extension"] = kept
                else:
                    item.pop("extension", None)
            if had_initial or removed_ext:
                stripped += 1
                logger.warning(
                    "Removed illegal initial/initialExpression from %s item '%s' "
                    "(SDC forbids them on group/display; openSRP $populate crashes)",
                    item.get("type"),
                    item.get("linkId"),
                )
        stripped += strip_illegal_initials(item.get("item"))
    return stripped


def set_item_extension(item: Optional[dict], extension: dict) -> None:
    """Set one item extension, replacing any existing entry with the same URL.

    Used for SDC 0..1 expression extensions (``calculatedExpression``,
    ``initialExpression``, ``enableWhenExpression``) so a walkthrough re-visit
    cannot append a second copy. ``answerOptionsToggleExpression`` is 0..*
    and should be appended with ``item.setdefault("extension", []).append``.

    Args:
        item: A Questionnaire.item dict (no-op if None).
        extension: The extension dict to store (must include ``url``).
    """
    if not item:
        return
    url = extension.get("url")
    existing = item.setdefault("extension", [])
    if url:
        for index, ext in enumerate(existing):
            if ext.get("url") == url:
                existing[index] = extension
                return
    existing.append(extension)


def dedupe_singleton_item_extensions(items: Optional[list]) -> int:
    """Keep the last ``calculatedExpression`` / ``initialExpression`` /
    ``enableWhenExpression`` on each item.

    Last-line defence for any attach path that still appended. Nested ``item``
    children are walked in place.

    Args:
        items: Questionnaire.item list (may be None).

    Returns:
        Number of extra singleton extensions removed.
    """
    removed = 0
    for item in items or []:
        exts = item.get("extension") or []
        last_index = {}
        kept = []
        for ext in exts:
            url = ext.get("url")
            if url in SDC_SINGLETON_ITEM_EXPRESSION_URLS and url in last_index:
                kept[last_index[url]] = ext
                removed += 1
                continue
            if url in SDC_SINGLETON_ITEM_EXPRESSION_URLS:
                last_index[url] = len(kept)
            kept.append(ext)
        if kept:
            item["extension"] = kept
        elif "extension" in item:
            item.pop("extension", None)
        removed += dedupe_singleton_item_extensions(item.get("item"))
    return removed


# Node types that produce hidden calculate items (populated via CQL calculatedExpression)
CALCULATE_NODE_TYPES = {
    TriccNodeType.calculate,
    TriccNodeType.count,
    TriccNodeType.add,
    TriccNodeType.bridge,
    TriccNodeType.wait,
    TriccNodeType.diagnosis,
    TriccNodeType.proposed_diagnosis,
    TriccNodeType.populate,
}


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


def build_item_control_display_item(link_id: str, text: str, control_code: str) -> dict:
    """Build a nested display item that carries a questionnaire-itemControl code.

    ``help`` is a display code: it belongs on a child ``display`` item of the
    question, not on the question itself. Hint text uses ``entryFormat`` on the
    parent (see ``build_entry_format_extension`` and
    ``feature/20260824-fhir-help-hint-itemcontrol.md``).

    Args:
        link_id: Child item linkId (e.g. ``weight-help``).
        text: Display text.
        control_code: Item-control code (``help``, …).

    Returns:
        FHIR Questionnaire.item dict.
    """
    return {
        "linkId": link_id,
        "type": FHIR_TYPE_DISPLAY,
        "text": text,
        "extension": [build_item_control_extension(control_code)],
    }


def build_entry_format_extension(text: str) -> dict:
    """Build an entryFormat extension from authored hint-message text.

    Official FHIR core extension ``http://hl7.org/fhir/StructureDefinition/entryFormat``
    (valueString) is the placeholder / format hint on ``Questionnaire.item``.
    See ``feature/20260824-fhir-help-hint-itemcontrol.md``.

    Args:
        text: Hint text to show as the entry format (e.g. ``e.g. 12.5``).

    Returns:
        FHIR extension dict.
    """
    return {"url": SDC_EXT_ENTRY_FORMAT, "valueString": text}


def build_hidden_extension() -> dict:
    """Build a questionnaire-hidden extension dict.

    Returns:
        FHIR extension dict marking the item as hidden.
    """
    return {"url": SDC_EXT_HIDDEN, "valueBoolean": True}


def build_choice_orientation_extension(orientation: str = "horizontal") -> dict:
    """Build a questionnaire-choiceOrientation extension dict.

    Rendering hint for yes/no (boolean) and choice lists. OpenSRP uses
    ``horizontal`` on visible boolean items so Yes/No sit side by side.
    See ``feature/20260819-boolean-choice-orientation.md``.

    Args:
        orientation: FHIR ChoiceOrientation code (``horizontal`` or ``vertical``).

    Returns:
        FHIR extension dict.
    """
    return {"url": SDC_EXT_CHOICE_ORIENTATION, "valueCode": orientation}


# Extension aliases for MIME subtypes that don't match the file extension
_IMAGE_EXT_TO_SUBTYPE = {"jpg": "jpeg", "svg": "svg+xml"}


def image_content_type(file_name: Optional[str]) -> Optional[str]:
    """Derive an ``image/<subtype>`` content type from an image file name.

    The extension was originally taken verbatim from the draw.io embedded
    ``image=data:image/<subtype>,<payload>`` style fragment (see
    ``add_image_from_style`` in ``converters/xml_to_tricc.py``), so it already
    is a valid IANA image subtype in the vast majority of cases; this only
    normalizes the handful of aliases (``jpg`` → ``jpeg``, ``svg`` → ``svg+xml``).

    Args:
        file_name: Image file name, e.g. ``"3f9a1c...c2.png"``.

    Returns:
        A content type string such as ``"image/png"``, or ``None`` if
        ``file_name`` has no extension.
    """
    if not file_name or "." not in file_name:
        return None
    ext = file_name.rsplit(".", 1)[-1].lower()
    if not ext:
        return None
    return f"image/{_IMAGE_EXT_TO_SUBTYPE.get(ext, ext)}"


def _image_attachment(binary_id: str, content_type: str) -> dict:
    """Build an Attachment that references a shared Binary, without inline bytes.

    The same picture can appear on several questionnaires. Bytes live once on
    the package ``Binary/{id}``; the Questionnaire only keeps ``contentType``
    and a relative ``Binary/{id}`` URL. openSRP rewrites that URL to an
    absolute FHIR URL at render time. ``itemAnswerMedia`` is inlined from the
    local Binary by the app, because the SDK never follows a URL there.

    Args:
        binary_id: The id of the matching Binary resource.
        content_type: The image content type (e.g. ``"image/png"``).

    Returns:
        FHIR Attachment dict.
    """
    return {
        "contentType": content_type,
        "url": f"Binary/{binary_id}",
    }


def build_item_media_extension(binary_id: str, content_type: str) -> dict:
    """Build an SDC itemMedia extension referencing a Binary resource.

    Illustrates the *question* itself (attaches to a Questionnaire.item).

    Args:
        binary_id: The id of the Binary resource holding the image bytes.
        content_type: The image content type (e.g. ``"image/png"``).

    Returns:
        FHIR extension dict.
    """
    return {
        "url": SDC_EXT_ITEM_MEDIA,
        "valueAttachment": _image_attachment(binary_id, content_type),
    }


def build_item_answer_media_extension(binary_id: str, content_type: str) -> dict:
    """Build an SDC itemAnswerMedia extension referencing a Binary resource.

    Illustrates a single *answer option* (attaches to an answerOption entry).

    Args:
        binary_id: The id of the Binary resource holding the image bytes.
        content_type: The image content type (e.g. ``"image/png"``).

    Returns:
        FHIR extension dict.
    """
    return {
        "url": SDC_EXT_ITEM_ANSWER_MEDIA,
        "valueAttachment": _image_attachment(binary_id, content_type),
    }


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


def build_answer_options_toggle_expression(option_codings, fhirpath_expr: str) -> dict:
    """Build an SDC answerOptionsToggleExpression extension dict.

    When ``fhirpath_expr`` evaluates to true the listed options are enabled;
    otherwise they are disabled. Unlisted options stay enabled (SDC default).

    Args:
        option_codings: One ``valueCoding`` dict, or a list of them.
        fhirpath_expr: FHIRPath boolean expression.

    Returns:
        FHIR extension dict attached to the parent Questionnaire item.
    """
    if isinstance(option_codings, dict):
        option_codings = [option_codings]
    option_exts = [{"url": "option", "valueCoding": coding} for coding in option_codings]
    return {
        "url": SDC_EXT_ANSWER_OPTIONS_TOGGLE,
        "extension": option_exts
        + [
            {
                "url": "expression",
                "valueExpression": {
                    "language": "text/fhirpath",
                    "expression": fhirpath_expr,
                },
            }
        ],
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


def build_calculated_expression_fhirpath(fhirpath_expr: str) -> dict:
    """Build an SDC calculatedExpression extension dict (FHIRPath-based).

    calculatedExpression must be FHIRPath, not CQL — only initialExpression
    supports a CQL identifier reference (``text/cql-identifier``). A
    calculation whose references live outside the current Questionnaire
    (e.g. observation history reachable only through the CQL Helper library)
    should be computed once via initialExpression instead of forced in here.

    Args:
        fhirpath_expr: FHIRPath expression string.

    Returns:
        FHIR extension dict.
    """
    return {
        "url": SDC_EXT_CALCULATED_EXPR,
        "valueExpression": {
            "language": "text/fhirpath",
            "expression": fhirpath_expr,
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
