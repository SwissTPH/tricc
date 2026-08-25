# FHIRPath choice check fails on `select_multiple`

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260813-fhirpath-choice-answers.md`, `fix/20260817-choice-membership-and-group-relevance.md`, `fix/20260824-fhirpath-choice-equality.md`, `fix/20260824-fhirpath-nested-item-path.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |
| **Approval** | 2026-08-24 conversation (user: FHIRPath to check a choice works for `select_one` but not for `select_multiple`). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability).

---

# Part I — Issue analysis

## 1. Symptom

Picking an option on a `select_one` makes gated notes / calculates / relevance true.

Picking the same kind of option on a `select_multiple` (checkbox) does not. The
membership FHIRPath stays false.

## 2. Why it happens

`select_one` and `select_multiple` both emit the HAPI-safe membership test:

```
…item.where(linkId='<q>').answer.where(value.code = '<code>').exists()
```

That is enough when there is **one** QuestionnaireResponse item with **one**
answer (radio). `select_multiple` is exported as `choice` with `repeats=true`
(Android FHIR requires `repeats` to allow more than one answer). At runtime
that means:

- several answers on one item, and/or
- several QR items with the same `linkId` (siblings, or nested under a
  repeating wrapper).

Two gaps then hide the selected code:

1. **Nested item path** (`fix/20260824-fhirpath-nested-item-path.md`) walks a
   precise `item.where(linkId=…)` chain. That finds the Questionnaire *definition*
   slot. It does not walk descendants of a repeating wrapper, so `.answer` can
   be empty even though a copy of the item further down holds the answers.
2. **`.where(value.code = 'x')` on a collection of answers.** Inside `.where()`,
   some engines resolve unqualified `value` against the whole answer list.
   `('a' | 'b') = 'a'` is empty, so the test is never true once two boxes are
   ticked. A singleton `select_one` answer still works.

`SELECTED` / `CONTAINS` / rewritten `EQUAL` all share that membership helper,
so every “is this option ticked?” check on a multi-select is affected. Authors
do not change how they draw selects.

## 3. What authors and implementers should see after the fix

Ticking one or several options on a `select_multiple` makes the matching notes,
option flags, and relevance true — same as `select_one`. No diagram change.

## 4. Out of scope

- Changing checkbox vs radio itemControl.
- Dropping `repeats=true` (Android FHIR rejects multiple answers on a
  non-repeating question).
- CQL `initialExpression` membership (Helper accessors, not QR item walks).

---

# Part II — Fix approach

## 5. Formal rules

**R1 — repeating items use a parent-scoped `repeat(item)`.** When the
Questionnaire item has `repeats=true` and a nested path `g1/g2/q` is known,
item lookup is:

```
%resource.item.where(linkId='g1').item.where(linkId='g2').repeat(item).where(linkId='q')
```

Top-level repeating items use `%resource.repeat(item).where(linkId='q')`.
Non-repeating items keep the precise nested path from
`fix/20260824-fhirpath-nested-item-path.md`.

**R2 — membership tests `$this`.** `SELECTED` / `CONTAINS` / rewritten choice
`EQUAL` emit:

```
<answer-collection>.where($this.value.code = '<code>').exists()
```

`$this` is the current Answer so `value.code` is not compared as a collection.

**R3 — non-choice paths unchanged.** Boolean / integer / string items still
use `.answer.where($this.exists()).value`.

## 6. Code checklist

- [x] `FHIRStrategy._fhirpath_item` — parent-scoped `repeat(item)` when `repeats`
- [x] `FHIRStrategy._choice_membership_expr` / `_rewrite_choice_code_equality`
- [x] Tests: `tests/test_strategies/test_fhir_relevance_fhirpath.py`
- [x] Docs: this file, `docs/open-srp-export.md`

## 7. Acceptance

1. Nested `select_multiple` membership uses
   `…item.where(linkId='<parent>').repeat(item).where(linkId='<q>').answer.where($this.value.code = '…').exists()`.
2. Nested `select_one` membership still uses the precise
   `…item.where(linkId='<parent>').item.where(linkId='<q>').answer…` path (no
   `repeat(item)` on that chain).
3. Unknown `linkId` still falls back to `%resource.repeat(item).where(linkId=…)`.
4. `EQUAL(select_one, 'code')` still rewrites to membership (no
   `.where($this.exists()).value.code =`).
5. Ticking a `select_multiple` option shows the gated items.
