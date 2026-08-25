# FHIR / OpenSRP: help-message → `itemControl` help, hint-message → `entryFormat`

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `feature/repeat-inheritance` |
| **Related** | `docs/tricc-elements.md` (hint-message / help-message enrichment), `docs/open-srp-export.md`, `fix/20260814-questionnaire-item-media.md` (same edge-enrichment pattern), `feature/20260819-boolean-choice-orientation.md` (`questionnaire-itemControl`) |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |
| **Authoring surface** | Existing draw.io `help-message` / `hint-message` boxes (and YAML `help` / `hint` on capture nodes). No new attributes. |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business description

*Audience: clinical authors, guideline developers, implementers reviewing OpenSRP forms.*

## 1. Overview

Authors already attach two kinds of extra text to a question in the flowchart:

| Box in the diagram | What the clinician should see |
|--------------------|-------------------------------|
| **help-message** | Explicit help for that question (help icon / expandable help in the app) |
| **hint-message** | A short format / placeholder hint on the question (e.g. `e.g. 12.5`) |

In ODK/XLSForm this already works (`hint` column; help as a more-info note). In the OpenSRP / FHIR Questionnaire those texts are currently **dropped**. This change emits them the way FHIR expects: a nested **display** child with `questionnaire-itemControl` **`help`**, and the official FHIR core **`entryFormat`** extension (`http://hl7.org/fhir/StructureDefinition/entryFormat`) for the hint.

No change to how diagrams are drawn. The captured answer is unchanged.

## 2. What authors see in the app

On a question “Weight (kg)” with a help box “Enter the weight in kilograms” and a hint box “e.g. 12.5”:

- The input shows **e.g. 12.5** as the entry-format / placeholder hint.
- The help control shows **Enter the weight in kilograms**.

Hidden logic (calculates, diagnoses, waits) does not show help or hint — those items are not rendered.

## 3. Benefits

- Help and hint authored in draw.io appear in OpenSRP, not only in ODK.
- Uses the standard FHIR `itemControl` **help** child and the official `entryFormat` extension.

## 4. Limitations

- Help and hint stay **display-only**. They are not extracted as Observations.
- There is no authoring control to pick a different item-control code.
- Generic XLSForm / CHT export is unchanged.

## 5. Out of scope

- Changing how help is written in XLSForm (more-info note).
- New draw.io node types.
- Putting `itemControl` **help** on the **question** itself (that code is for a child display item). Hint uses `entryFormat` on the question, not a nested display.

---

# Part II — Technical specification

## 6. Authoring → node fields (already implemented)

`hint-message` / `help-message` boxes are not graph nodes (`drawio_type_map` `model: None`). `enrich_node` copies the box label onto the target’s `hint` / `help` (`TriccNodeDisplayModel`). FHIR must read those attributes in `generate_base`.

YAML fixtures get `hint` and `help` on capture / note nodes so tests do not need draw.io.

## 7. Emission rules

`help` is a **display** code in `http://hl7.org/fhir/questionnaire-item-control`. It is emitted as a **child** `Questionnaire.item`. Hint is **not** a display child: it is the official FHIR core `entryFormat` extension on the parent item.

**R1 — help-message.** If the parent item is emitted, is not hidden, and `node.help` has a non-empty text, append a child:

```json
{
  "linkId": "<parentLinkId>-help",
  "type": "display",
  "text": "<help text>",
  "extension": [{
    "url": "http://hl7.org/fhir/StructureDefinition/questionnaire-itemControl",
    "valueCodeableConcept": {
      "coding": [{
        "system": "http://hl7.org/fhir/questionnaire-item-control",
        "code": "help"
      }]
    }
  }]
}
```

**R2 — hint-message.** If the parent item is emitted, is not hidden, and `node.hint` has a non-empty text, set this extension on the **parent** item (`valueString`):

```json
{
  "url": "http://hl7.org/fhir/StructureDefinition/entryFormat",
  "valueString": "<hint text>"
}
```

Do **not** emit a nested display / `flyover` child for hint.

**R3 — order.** The help child is prepended to the parent’s `item` list (before any later nested questions). `entryFormat` is an extension on the parent, not an item.

**R4 — skip.** Do not emit help child or `entryFormat` when:

- the parent is not written (skipped / no FHIR type / already in `processed_nodes`);
- the parent is hidden (`questionnaire-hidden`, calculates, diagnoses, waits, bridges, …);
- the corresponding `help` / `hint` is missing or blank after text rendering.

**R5 — standalone `help` / `hint` node types.** If a node with `tricc_type` `help-message` / `hint-message` is walked (should not happen after enrichment), **skip** it. The parent attributes are the source of truth.

**R6 — not extracted.** The help child is synthesised in `generate_base` only. It is not a graph node, so `generate_export` does not create a StructureMap rule for it. It must not receive `initial` / `initialExpression` (already illegal on `display`). `entryFormat` is display-only and is not extracted.

**R7 — text rendering.** Same as the parent `text`: `TriccOperation` via `get_tricc_operation_expression`; multi-lang dict → first non-empty locale; otherwise `str`. Empty result → skip (R4).

Reuse `build_item_control_extension` / `build_entry_format_extension` in `questionnaire_item_mapper.py`.

## 8. Code checklist

| File | Change |
|------|--------|
| `tricc_oo/converters/fhir/questionnaire_item_mapper.py` | [x] `build_item_control_display_item`; `build_entry_format_extension`; skip standalone `help`/`hint` node types. |
| `tricc_oo/strategies/output/fhir_form.py` | [x] After appending a visible item in `generate_base`, attach help child + `entryFormat` (R1–R4, R7). |
| `tricc_oo/strategies/input/yaml.py` | [x] `hint`, `help` on `YamlNode` and capture / note `attrs`. |
| `docs/open-srp-export.md` | [x] Help → nested `itemControl` help; hint → `entryFormat`. |
| `docs/tricc-elements.md` | [x] FHIR/OpenSRP row for hint-message / help-message. |
| `tests/test_strategies/test_fhir_help_hint_itemcontrol.py` | [x] Unit + YAML walk tests. |

`OpenSRPStrategy` inherits `generate_base`; no override required.

## 9. Tests

| Case | Assert |
|------|--------|
| Integer with `help` and `hint` | One `display` child with `itemControl` `help` (`<export>-help`); parent has `entryFormat` `valueString` matching the hint. |
| Only `help` | One child, code `help`; no `entryFormat`. |
| Only `hint` | No children; parent has `entryFormat`. |
| Hidden calculate with `help` / `hint` | No child items; no `entryFormat`. |
| Blank `help` / missing `hint` | No children; no `entryFormat`. |
| Parent widget `itemControl` (e.g. radio-button) | Still present on the **parent**; help only on the child. |
| YAML fixture integer with `help`/`hint`, `process_base` | Same after a real walk. |

## 10. Acceptance criteria

1. OpenSRP Questionnaire shows authored help as a nested `itemControl` **help** child and authored hint as **`entryFormat`** on the question.
2. Hidden items and blank texts emit nothing extra.
3. XLSForm/CHT hint column and more-info help are unchanged.
4. Authors draw the same boxes as today.

## 11. Implementation phases

1. Mapper helpers (`itemControl` help child, `entryFormat` for hint) + `generate_base` attach + skip standalone types.
2. YAML `hint`/`help` attrs.
3. Tests + docs.

Implemented 2026-08-24.
