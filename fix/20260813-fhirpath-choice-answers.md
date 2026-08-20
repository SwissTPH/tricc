# FHIRPath choice answers, nested item lookup, and calculate types

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `feature/zscore` / `develop` |
| **Related** | `docs/desing/FHIRcore.md`, `docs/open-srp-export.md`, `feature/opensrp-export-hygiene.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |
| **Approval** | Requested in the 2026-08-13 conversation (user asked to analyse the generated demo Questionnaire and fix the FHIR/OpenSRP emitters in the same turn). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability). Same two-part shape and status gate; see `AGENTS.md`.

---

# Part I — Issue analysis

*Audience: clinical authors, guideline developers, implementers reviewing an OpenSRP / FHIR-Core package.*

## 1. What went wrong

The generated Questionnaire for the demo form looked structurally fine (groups, choice lists, hidden calculates, `$populate` identifiers) but several **live expressions would not evaluate as intended** once a clinician filled the form.

The most visible symptom: display notes that should appear when a reason is ticked on **Why?** (`select_why`) — “Now eat !”, “Sorry for the bad presentation”, “Next time we could present with a snack”, the GoTo/path hidden flags, and the “You selected at least one choice” note — stay hidden even after the matching choice is selected.

## 2. Why it happens (plain language)

Choice answers in a FHIR `QuestionnaireResponse` are **codings** (code + optional display), not bare strings.

TRICC was writing expressions such as:

- “is the string `demo.hungry` in the list of answers?”
- “does the answer list contain the string `demo.hungry`?”

The runtime compares that string to the whole answer object. The test is almost always false, so relevance and live calculates never fire.

A second, quieter problem: those expressions only looked at **top-level** form items. The demo questions sit several groups deep (page → activity → …). Engines that do not walk descendants miss the item entirely.

A third problem: the hidden “this option was selected” flags (`demo_hungry`, `demo_bad_p`, …) were declared as **text** fields while the expression returns **yes/no**. Downstream extraction and type-sensitive engines can then mis-store the value.

## 3. What authors and implementers should see after the fix

- Ticking a reason on a multi-select shows the matching notes and path flags.
- “At least one real choice” (anything other than “None of the above”) still works, without mixing collection operators incorrectly.
- Hidden option-flags are yes/no, not text.
- Expressions find questions even when they live inside nested groups.

No new draw.io attributes. Authors do not change how they draw selects.

## 4. Out of scope (author content, not the exporter)

These showed up on the same Questionnaire but are **source labels**, not expression bugs:

| Item | Issue |
|------|--------|
| Option `demo.angry` | Display “Angy” (typo in the diagram) |
| Note `demo.sorry` | “presentiation” (typo in the diagram) |
| Hidden rhombus | Text `>0` leftover from the condition label |
| Empty `text` on some hidden booleans | Allowed by FHIR; not ideal, not a runtime failure |
| Path/GoTo hidden items | `text` carried internal routing (`path: GoTo\|…`) |

The exporter **does** stop copying internal `path:` / `contains:` / `save:` labels onto hidden items (use the concept name instead). Diagram typos are corrected in the demo fixture only.

## 5. Limitations

- CQL `initialExpression` identifiers (`Dedup_demo_is_happy`, …) still require the generated Library to define them. This fix does not re-validate that Library.
- StructureMap / FML `item.where(linkId=…)` nesting is a separate extraction concern and is **not** changed here.
- Target-engine confirmation (fhirpath.js, HAPI, Smart Register) is recommended after deploy; unit tests cover the emitted strings.

---

# Part II — Technical specification

*Audience: TRICC developers.*

## 6. Root cause

All in-form FHIRPath is built in `FHIRStrategy`:

| Site | Current (broken) | Required |
|------|------------------|----------|
| `get_tricc_operation_operand_fhirpath` | `%resource.item.where(linkId='X').answer` | `%resource.repeat(item).where(linkId='X').answer` |
| `tricc_operation_fhirpath_selected` | `('code' in …answer)` | `('code' in …answer.valueCoding.code)` |
| `tricc_operation_fhirpath_contains` | `(…answer contains 'code')` | same membership as SELECTED |
| `_wrap_operand_if_needed` | always `.value` | `.valueCoding.code` for choice items |
| `tricc_operation_fhirpath_cast_number` | `boolean.toDecimal()` | `iif(boolean, 1, 0)` when the operand is boolean |
| `generate_base` / `NODE_TYPE_TO_FHIR[calculate]` | always `string` | `boolean` when the expression’s datatype is boolean |

The demo `demo_m_select_1` enableWhen is:

```text
…answer.count() - ('opt_none' in …answer).toDecimal() > 0
```

That is `COUNT(select) - CAST_NUMBER(SELECTED(select, opt_none)) > 0` from `get_count_terms_details`. Fixing SELECTED + CAST_NUMBER is enough; do **not** special-case this shape in the visitor.

## 7. Formal emission rules

### 7.1 Item lookup

Every Questionnaire item reference in FHIRPath uses descendant walk:

```text
%resource.repeat(item).where(linkId='<export-name>')
```

`repeat(item)` is FHIRPath (not CQL). Do not use `descendants()` (too broad).

CQL / Helper paths are unchanged: they must not embed `%resource…` item walks.

### 7.2 Answer value access

| Questionnaire item type | Scalar value path | Collection of codes |
|-------------------------|-------------------|---------------------|
| `choice` / `open-choice` | `.answer.where($this.exists()).valueCoding.code` | `.answer.valueCoding.code` |
| `boolean`, `integer`, `decimal`, `string`, `date`, … | `.answer.where($this.exists()).value` | n/a |

`answer.value` on a choice returns a `Coding`, not a string. Never compare it to a code literal.

### 7.3 SELECTED / CONTAINS

- **SELECTED(select, code)** and **CONTAINS(select, code)** on a choice item:

  ```text
  ('<code>' in %resource.repeat(item).where(linkId='<select>').answer.valueCoding.code)
  ```

- **SELECTED** on a native boolean (`select_yesno` / yes-no `select_one`):

  ```text
  (%resource.repeat(item).where(linkId='<q>').answer.where($this.exists()).value = <true|false>)
  ```

- **CONTAINS** on a string/text item keeps substring `contains` (rare; not used by the option-flag generator).

`in` is preferred over `contains` for code membership (works for 0..n answers).

### 7.4 Boolean → number

`CAST_NUMBER` / `CAST_INTEGER` of a boolean operation (`SELECTED`, `CONTAINS`, comparisons, `AND`/`OR`/`NOT`, …) emits `iif(<expr>, 1, 0)`, not `.toDecimal()`. FHIRPath `toDecimal()` is not reliably defined on boolean.

### 7.5 Calculate item type

If a `calculate` node’s `expression` / `expression_reference` has `get_datatype() == "boolean"`, the Questionnaire item type is `boolean` (not `string`). Apply in `generate_base` and re-assert in `generate_calculate` for expressions that only exist after calculate load.

Boolean calculate typing uses `RETURNS_BOOLEAN` plus `ISNULL` / `CAST_BOOLEAN` in the FHIR
emitter only — do **not** widen the shared `RETURNS_BOOLEAN` list (it feeds skip/relevance).

### 7.6 Hidden item text

For hidden non-group items, if `text` is empty or starts with `path:`, `contains:`, or `save:` (case-insensitive), replace with `node.name` (or `""`). Do not rewrite author-facing display/note labels.

## 8. Code checklist

- [x] `tricc_oo/strategies/output/fhir_form.py` — path, SELECTED/CONTAINS, wrap, cast, type, hidden text
- [x] FHIR emitter treats `ISNULL` / `CAST_BOOLEAN` as boolean without widening shared `RETURNS_BOOLEAN`
- [x] Tests in `tests/test_strategies/test_fhir_relevance_fhirpath.py` (+ calculate type)
- [x] Docs: `docs/open-srp-export.md`, `docs/desing/FHIRcore.md`, `docs/troubleshooting.md`
- [x] `AGENTS.md` — `fix/` workflow + FHIRPath rules
- [x] Demo fixture typos only (`tests/data/demo.drawio`)

## 9. Tests

1. `SELECTED(TriccReference('select_why'), 'demo.hungry')` → `repeat(item)` + `valueCoding.code` + `in`.
2. `CONTAINS(select_multiple_node, 'demo.bad_p')` → same membership pattern.
3. `NOT(SELECTED(...))` still uses suffix `.not()`.
4. `ISTRUE` / equality on a boolean item still use `.value`, not `.valueCoding`.
5. `COUNT - CAST_NUMBER(SELECTED(opt_none))` uses `iif(..., 1, 0)` and choice codes.
6. Existing relevance tests updated from `%resource.item.where` → `%resource.repeat(item).where`.
7. A `TriccNodeCalculate` whose expression is `CONTAINS` is emitted as `type: boolean`.

## 10. Acceptance criteria

- Demo Questionnaire `enableWhenExpression` / `calculatedExpression` that test `select_why` membership use `'<code>' in %resource.repeat(item).where(linkId='select_why').answer.valueCoding.code`.
- `demo_m_select_1` enableWhen uses that membership test (or `iif`) rather than `in …answer` / `.toDecimal()`.
- `demo_hungry` / `demo_bad_p` / `demo_bored` / `demo_angry` are `boolean`.
- Hidden path/contains items no longer expose `path:` / `contains:` as `text`.
- `python -m pytest tests/test_strategies/test_fhir_relevance_fhirpath.py tests/test_strategies/test_fhir_calculate_expression.py` passes.

## 11. Implementation phases

1. Spec (`fix/`) + AGENTS.md `fix/` workflow.
2. Emitter + `RETURNS_BOOLEAN` + unit tests.
3. Docs + demo fixture typos.
4. Status → Implemented.
