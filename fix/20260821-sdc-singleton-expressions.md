# FHIR Data Capture crashes when an item has two `calculatedExpression`s

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260821-opensrp-questionnaire-duplicate-calculates.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## 1. Symptom

openSRP FHIR Data Capture throws while rendering a Questionnaire (uncaught,
`Dispatchers.Main.immediate` inside the SDK ViewModel —
`isQuestionnaireRenderingException` matches datacapture frames). SDC allows
**at most one** `calculatedExpression` / `initialExpression` /
`enableWhenExpression` per item. A second copy is a hard error, not a warning.

## 2. TRICC does emit duplicates for a single item

The output walk re-stashes a node on every incoming path. `_record_cql_define`
already replaces a define of the same name; the Questionnaire item path
**appended**:

```python
item.setdefault("extension", []).append(build_calculated_expression_fhirpath(...))
```

`_find_item_by_link_id` returns the first item with that `linkId`, so every
revisit of the same node — and every clone that shares the export name after
`fix/20260821-opensrp-questionnaire-duplicate-calculates.md` collapsed items —
adds another extension to the **same** item.

Census of the global IMCI child package (identical expression text in every
case — not two different computations):

| Questionnaire | `calculatedExpression` dups | `enableWhenExpression` dups | `initialExpression` dups |
|---|---:|---:|---:|
| registration | 8 items (all identical copies) | 40 | 1 |
| dispense-medications | 1 | 49 | 0 |
| main | 0 | 14 | 0 |
| diagnostic-testing | 0 | 0 | 1 |

Example: `CHE_B23_DE59_Vv_1` carried four copies of the same FHIRPath
`calculatedExpression`.

## 3. Out of scope

- Merging two *different* computations onto one item (does not occur in current
  content; if it did, they belong on two `linkId`s).
- `answerOptionsToggleExpression` — SDC allows several (one group of options
  per expression).

---

# Part II — Fix approach

## 4. Emission rules

**R1 — Singleton SDC expression extensions.**
`calculatedExpression`, `initialExpression`, and `enableWhenExpression` are
0..1 per item. Setting one replaces any existing extension with that URL.

**R2 — Identical re-visits are a no-op.**
The walk may attach the same expression twice; replacement keeps one copy.

**R3 — Last-line sanitizer.**
Before write, collapse any remaining duplicate singleton expression URLs on
an item (keep the last). Same role as `strip_illegal_initials`.

## 5. Code checklist

- [x] `set_item_extension` / `dedupe_singleton_item_extensions` in
      `questionnaire_item_mapper.py`
- [x] `generate_calculate` / `generate_relevance` / dedup attach use the setter
- [x] `_sanitize_questionnaires` runs the deduper
- [x] tests: two `generate_calculate` visits → one `calculatedExpression`;
      two `generate_relevance` visits → one `enableWhenExpression`;
      sanitizer collapses a hand-built duplicate
- [x] `docs/open-srp-export.md`
