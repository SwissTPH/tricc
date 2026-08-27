# FHIR / OpenSRP: help-message → `itemControl` help, hint-message → flyover

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
| **hint-message** | A short flyover / hover hint on the question text |

In ODK/XLSForm this already works (`hint` column; help as a more-info note). In the OpenSRP / FHIR Questionnaire those texts are currently **dropped**. This change emits them in the way FHIR SDC and the OpenSRP renderer expect: nested **display** children with `questionnaire-itemControl` codes **`help`** and **`flyover`**.

No change to how diagrams are drawn. The captured answer is unchanged.

## 2. What authors see in the app

On a question “Weight (kg)” with a help box “Enter the weight in kilograms” and a hint box “e.g. 12.5”:

- Hovering / focusing the question shows **e.g. 12.5** (flyover).
- The help control shows **Enter the weight in kilograms**.

Hidden logic (calculates, diagnoses, waits) does not show help or hint — those items are not rendered.

## 3. Benefits

- Help and hint authored in draw.io appear in OpenSRP, not only in ODK.
- Uses the standard FHIR item-control codes the OpenSRP FHIR Data Capture library already understands.

## 4. Limitations

- Help and hint stay **display-only**. They are not extracted as Observations.
- There is no authoring control to pick a different item-control code.
- Generic XLSForm / CHT export is unchanged.

## 5. Out of scope

- Changing how help is written in XLSForm (more-info note).
- New draw.io node types.
- Putting `itemControl` help/flyover on the **question** itself (those codes are for child display items).

---

# Part II — Technical specification

## 6. Authoring → node fields (already implemented)

`hint-message` / `help-message` boxes are not graph nodes (`drawio_type_map` `model: None`). `enrich_node` copies the box label onto the target’s `hint` / `help` (`TriccNodeDisplayModel`). FHIR must read those attributes in `generate_base`.

YAML fixtures get `hint` and `help` on capture / note nodes so tests do not need draw.io.

## 7. Emission rules

`help` and `flyover` are **display** codes in `http://hl7.org/fhir/questionnaire-item-control`. They are emitted as **child** `Questionnaire.item` entries of the question (or group), not as extensions on the parent.

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

**R2 — hint-message.** Same, with `linkId` `<parentLinkId>-hint`, `code` **`flyover`**, text from `node.hint`.

**R3 — order.** Children are appended to the parent’s `item` list: help first, then flyover, then any later nested questions (groups).

**R4 — skip.** Do not emit either child when:

- the parent is not written (skipped / no FHIR type / already in `processed_nodes`);
- the parent is hidden (`questionnaire-hidden`, calculates, diagnoses, waits, bridges, …);
- the corresponding `help` / `hint` is missing or blank after text rendering.

**R5 — standalone `help` / `hint` node types.** If a node with `tricc_type` `help-message` / `hint-message` is walked (should not happen after enrichment), **skip** it. The parent attributes are the source of truth.

**R6 — not extracted.** Child display items are synthesised in `generate_base` only. They are not graph nodes, so `generate_export` does not create StructureMap rules for them. They must not receive `initial` / `initialExpression` (already illegal on `display`).

**R7 — text rendering.** Same as the parent `text`: `TriccOperation` via `get_tricc_operation_expression`; multi-lang dict → first non-empty locale; otherwise `str`. Empty result → skip (R4).

Reuse `build_item_control_extension` in `questionnaire_item_mapper.py`.

## 8. Code checklist

| File | Change |
|------|--------|
| `tricc_oo/converters/fhir/questionnaire_item_mapper.py` | [x] `build_item_control_display_item`; skip standalone `help`/`hint` node types. |
| `tricc_oo/strategies/output/fhir_form.py` | [x] After appending a visible item in `generate_base`, attach help/flyover children (R1–R4, R7). |
| `tricc_oo/strategies/input/yaml.py` | [x] `hint`, `help` on `YamlNode` and capture / note `attrs`. |
| `docs/open-srp-export.md` | [x] Help → nested `itemControl` help; hint → flyover. |
| `docs/tricc-elements.md` | [x] FHIR/OpenSRP row for hint-message / help-message. |
| `tests/test_strategies/test_fhir_help_hint_itemcontrol.py` | [x] Unit + YAML walk tests. |

`OpenSRPStrategy` inherits `generate_base`; no override required.

## 9. Tests

| Case | Assert |
|------|--------|
| Integer with `help` and `hint` | Parent item has two `display` children; first `itemControl` `help`, second `flyover`; texts match; linkIds `<export>-help` / `<export>-hint`. |
| Only `help` | One child, code `help`. |
| Only `hint` | One child, code `flyover`. |
| Hidden calculate with `help` | No child items. |
| Blank `help` / missing `hint` | No children. |
| Parent widget `itemControl` (e.g. radio-button) | Still present on the **parent**; help/flyover only on children. |
| YAML fixture integer with `help`/`hint`, `process_base` | Same nesting after a real walk. |

## 10. Acceptance criteria

1. OpenSRP Questionnaire shows authored help as `itemControl` **help** and authored hint as **flyover**, nested under the question.
2. Hidden items and blank texts emit nothing extra.
3. XLSForm/CHT hint column and more-info help are unchanged.
4. Authors draw the same boxes as today.

## 11. Implementation phases

1. Mapper helper + `generate_base` attach + skip standalone types.
2. YAML `hint`/`help` attrs.
3. Tests + docs.

Implemented 2026-08-24.
