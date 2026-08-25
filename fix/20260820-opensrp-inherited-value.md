# `GET_INHERITED_VALUE` is not exportable to openSRP (FHIRPath / CQL)

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `feature/advanced-merge-calc.md`, `feature/20260812-intervention-order-and-dedup.md`, `fix/20260817-choice-membership-and-group-relevance.md`, `fix/20260821-output-pass-calculate-readiness.md`, `fix/20260821-merge-input-into-populate.md`, `docs/desing/FHIRcore.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## 1. What went wrong

When the same question or calculate is reachable through several paths of a guideline, the
transformation engine keeps one item per occurrence ("versions") and merges their values with
the `GET_INHERITED_VALUE` operator (`tricc_oo/visitors/tricc.py` — `get_version_inheritance`
and `process_reference`). ODK and CHT serialise it as `coalesce(…)`; the FHIR/openSRP strategy
has **no handler for the operator at all**, so the generic dispatcher
(`fhir_form.py:1206-1217`) raises `NotImplementedError`.

Observed on the global almanach (`L2/child` + `L2/common`, `-O OpenSRPStrategy`):

```
File "tricc_oo/strategies/output/fhir_form.py", line 591, in generate_relevance
    fhirpath_expr = self.convert_expression_to_fhirpath(relevance)
NotImplementedError: This type of operation 'get_inherited_value' is not supported
```

| Where | Current behaviour |
|-------|-------------------|
| `generate_relevance` | Unguarded call → the exception **aborts the whole export**. |
| `generate_calculate` | The FHIRPath attempt is caught (debug log), the CQL attempt is swallowed by `except Exception` → the item gets **neither** `calculatedExpression` nor `initialExpression`; the value silently never computes. |
| `_attach_option_toggles` | Caught → the option toggle is dropped (option always offered). |

`demo.drawio` has no multi-version content, so the demo export looks healthy; real content
does not.

## 2. What the operator actually looks like (census, not assumption)

Instrumented run of the global almanach OpenSRP build, operator stubbed so every occurrence is
recorded — **187 occurrences**:

| Shape | Count | Detail |
|-------|-------|--------|
| FHIRPath, from `relevance` | 160 | the crash site |
| CQL, from `calculate` | 27 | silently value-less today |
| 2 operands: two `select_one` **versions of another node** | 177 | `CHE_B24_G_DE44_Vv_2` then `_Vv_1` — **newest first** (`version` 2/1, `path_len` 138/118); **both are items of the same Questionnaire** (`diagnostic-testing`) |
| 1 operand: the node's own local formula (nested `TriccOperation`) | 5 | self-contribution; an outer `coalesce`/`or` from `merge_expressions` joins it to the prior versions |
| 1 operand: a single prior version node | 5 | e.g. `CHE_B27_G_DE04_Vv_1`, `CHE_B23_DE03_Vv_1` (Questionnaire `registration`) |
| First operand **is** the node being serialised | **0** | never occurs in this content |

Two consequences for the fix:

- The dominant case is *"all versions of a referenced concept live in the current
  Questionnaire"* — exactly the case that can stay live FHIRPath.
- The ODK-style `coalesce(., …)` shape (current node first, replaced by `$this`) does **not**
  appear as one `GET_INHERITED_VALUE`; self-inheritance arrives as separate single-operand ops
  that an outer operator already combines. The `$this` rule is therefore specified below but
  unexercised by current content — see the open question in §10.
- `node.segment` is `None` for the nodes carrying these expressions, so "the current process"
  must be resolved from the Questionnaire that actually holds the node's item
  (`_segment_for_item`), not from `node.segment`.

## 3. Expected behaviour

A question or calculate that exists in several versions exports **one** value expression that
resolves to the value the health worker actually entered, whichever version was reached — and
the export does not crash.

## 4. Why openSRP cannot reuse the ODK `coalesce` as-is

1. **One Questionnaire per process.** Versions living in another process's Questionnaire are
   invisible to `%resource` (the current QuestionnaireResponse); no FHIRPath can read them.
2. **Every Observation/Condition item already deduplicates.** A dedup `initialExpression`
   prefills each item from the concept's value already recorded in this encounter
   (`feature/20260812-intervention-order-and-dedup.md`), so an out-of-form version's answer is
   already visible without a coalesce.
3. **CQL access is concept-keyed.** In the Helper library every version of a node collapses to
   the same accessor string, so a `Coalesce` of them is `Coalesce(x, x)`.

## 5. Out of scope

- ODK / CHT semantics (`coalesce(., …)`) — unchanged.
- How the visitor *builds* `GET_INHERITED_VALUE` (origin-signature grouping, `repeat = -1`
  exclusion) — unchanged; only serialisation changes.
- `GET_HISTORY_VALUE` / `GET_REPEATED_VALUE` — already handled by the populate/repeat helpers.
- Pre-existing, recorded here because the same run surfaces it: one CQL define serialises an
  operand as a bare `.` (`. != 'no_height_no_weight' or "CHE_B6_DE20" != '1'`) → CQL grammar
  error. Separate `fix/` once this one lands.

---

# Part II — Fix approach

## 6. Root cause

`FHIRStrategy` implements `tricc_operation_coalesce` / `tricc_operation_fhirpath_coalesce` but
no `…_get_inherited_value` variant, and the operator is not reducible to plain `coalesce` for
this target (§4).

## 7. Emission rules

**R0 — recency never comes from list position.** The two construction sites order operands
differently by design (`process_reference` sorts newest-first; `get_version_inheritance` bucket
lists are append-ordered). Rank operands by `(path_len, version)` descending; a nested
`TriccOperation` operand is the node's own local formula and ranks newest.

**R1 — FHIRPath, at least one operand is in the current process.**
Keep the operands whose `linkId` is an item of the *current* Questionnaire, ordered newest-first,
and emit their union as one scalar:

```
(%resource.repeat(item).where(linkId='CHE_B24_G_DE44_Vv_2').answer |
 %resource.repeat(item).where(linkId='CHE_B24_G_DE44_Vv_1').answer)
  .where($this.exists()).first().value.code
```

- Value suffix follows the referenced item type, as elsewhere in this strategy: `.value.code`
  for `choice` / `open-choice`, `.value` otherwise (`_answer_value_suffix`).
- Emitting a **scalar** is what keeps composition working: the parent operator treats a nested
  `TriccOperation` as already-scalar (`_wrap_operand_if_needed`), so `> 5` / `.empty()` compose
  directly, and `SELECTED` / `CONTAINS` strip the `.value.code` suffix
  (`_choice_answer_collection`) and re-append `.where(value.code = 'x').exists()`.
- Operands outside the current Questionnaire are dropped from the union (unreachable), and the
  drop is logged at debug with the linkId.

**R1b — self operand → `$this`.** If an operand *is* the node carrying the expression, emit
`$this` for it instead of a self `linkId` reference (the FHIR analogue of ODK's `coalesce(., …)`,
and it avoids a self-referencing `calculatedExpression`). Unexercised by current content — §10.

**R2 — single operand.** No union, no `.first()` wrapper: serialise the operand exactly as it
would be outside the operator (unwrap). Covers the 10 single-operand occurrences.

**R3 — FHIRPath, no operand in the current process.**
Raise `NotImplementedError` with an explicit message.
- `generate_calculate` already reads that as "fall back to CQL `initialExpression`" (R4).
- `generate_relevance` must catch it: warn, emit **no** `enableWhenExpression` (fail open — item
  shown) instead of aborting the export.

**R4 — CQL `initialExpression`.** Deduplicate operand strings preserving order (concept-keyed
Helper access makes all versions identical); one distinct operand → emit it bare (the
current-encounter dedup `initialExpression` is the value source); several distinct → `Coalesce(…)`.

## 8. Code checklist

- `tricc_oo/strategies/output/fhir_form.py`
  - [ ] `self._current_segment` — set in `generate_calculate`, `generate_relevance`,
        `_attach_option_toggles` from `_segment_for_item(node, get_export_name(node))`
        (**not** `node.segment`, which is `None` here); cleared afterwards.
  - [ ] `_inherited_operands_in_segment(original_references)` — split operands into
        in-current-Questionnaire / elsewhere, newest-first (R0), handling node,
        `TriccReference` and nested `TriccOperation` operands.
  - [ ] `tricc_operation_fhirpath_get_inherited_value()` — R1 / R1b / R2 / R3.
  - [ ] `tricc_operation_get_inherited_value()` — R4.
  - [ ] `generate_relevance` — `try/except NotImplementedError` → warn + skip.
- Docs
  - [ ] `AGENTS.md` "FHIR CQL / Library Generation" — one bullet on inherited values.
  - [ ] `docs/desing/FHIRcore.md` — R0–R4.
  - [ ] `docs/open-srp-export.md` — author-facing: a question asked on several paths exports as
        the union of its versions in the same form, and as encounter dedup across processes.

## 9. Tests (`tests/test_strategies/test_fhir_inherited_value.py`)

- [ ] Two versions of a choice item, both in this Questionnaire → `enableWhenExpression` unions
      both `linkId`s newest-first and ends in `.where(value.code = '…').exists()`; no
      `NotImplementedError`.
- [ ] Scalar comparison over an inherited value → `…first().value > 5` (value suffix present,
      no double wrap).
- [ ] Mixed → out-of-process version dropped from the union, in-process ones kept.
- [ ] No version in this Questionnaire, calculate → no `calculatedExpression`; one CQL define
      with a single Helper accessor and **no** `Coalesce(x, x)`.
- [ ] No version in this Questionnaire, relevance → export does not raise; item gets no
      `enableWhenExpression`.
- [ ] Single operand → serialised without union/`.first()`.
- [ ] Distinct CQL operands → `Coalesce(…)` still emitted.
- [ ] `python -m pytest tests/` stays green (ODK/CHT untouched).

## 10. Open question (needs an answer before implementation)

`$this` (R1b): in the Android FHIR SDK / openSRP, `calculatedExpression` and
`enableWhenExpression` are evaluated with the QuestionnaireResponse as context, so `$this` may
resolve to the *resource*, not to the item's own answer — in which case a `$this` operand would
make the whole union non-empty and return garbage. Options: (a) `$this` as specified,
(b) explicit self `linkId` (risks the SDK's cyclic-dependency check on
`calculatedExpression`), (c) drop the self operand and rely on the dedup `initialExpression`.
No current content exercises it (0/187), so it can also be deferred with a `NotImplementedError`.

## 11. Acceptance criteria — verified 2026-08-20

| Criterion | Result |
|---|---|
| Global almanach OpenSRP export completes | **Pass** — 8 Questionnaires, 7 CQL libraries, 8 FML mappings written; no `NotImplementedError`, no `Traceback`, no "Could not convert calculate expression" |
| No in-process version → calculate uses CQL, relevance emits nothing and warns | **Pass** — 85 warnings, each naming the process and the out-of-process versions (`… no version in the current process 'dispense-medications' (CHE_B24_G_DE44_Vv_2, CHE_B24_G_DE44_Vv_1) …`) |
| In-process versions → one FHIRPath union naming only in-process `linkId`s, newest first | **Pass in unit tests** (`test_fhir_inherited_value.py`); **not observable in the global export** — blocked by follow-up 1 below: the attachment step resolves the target Questionnaire from `node.segment`, which is never set, so nothing is attached outside `main` regardless of this operator |
| No expression references a `linkId` absent from its own Questionnaire | **Pass** — out-of-process operands are dropped from the union by construction |
| `python -m pytest tests/` | **Pass** — 225 passed (9 new) |
| `flake8 tricc_oo` | **Pass** — 17 findings before and after this change, all pre-existing |

The exported Questionnaires still show `enableWhenExpression` only in `main` (2), and no
`calculatedExpression` anywhere: that is follow-up 1, not this operator.

## 12. Follow-ups found while implementing (separate `fix/` each — not done here)

1. **`node.segment` is never assigned anywhere in the codebase.** `generate_relevance`
   (`getattr(node, "segment", None) or "main"`) and `generate_calculate`
   (`getattr(node, "segment", "main")`) therefore always resolve to `main`, so an
   `enableWhenExpression` / `calculatedExpression` is only ever *attached* to items that live in
   the `main` Questionnaire — in the global export that is 13 items out of ~99 000, and 7 of the
   8 Questionnaires had zero `enableWhenExpression`. This fix resolves "the current process" for
   the operator through `_segment_for_item` (the Questionnaire that actually holds the item), so
   the operator side is already correct; the *attachment* side still needs the same treatment.
2. **Cross-process relevance is structurally inexpressible.** Where a condition depends on a
   question answered in an earlier process (`dispense-medications` item gated on a
   `diagnostic-testing` answer), `enableWhenExpression` is FHIRPath-only and cannot reach it, so
   the item now shows unconditionally (fail open). Making these work needs the value mirrored
   into the current Questionnaire as a hidden CQL-populated item, then referenced by `linkId`.
3. **Duplicate CQL defines / constant-`true` calculates** — now `fix/20260821-output-pass-calculate-readiness.md`.
4. **`input` nodes exported as nothing** — now `fix/20260821-merge-input-into-populate.md`.
5. **Invalid CQL operands.** The same run emits `define`s containing a bare `.`
   (`. != 'no_height_no_weight' or "CHE_B6_DE20" != '1'`) and bare version identifiers
   (`fever_Vv_2`) that no library defines — the CQL grammar check in the run log rejects them.
