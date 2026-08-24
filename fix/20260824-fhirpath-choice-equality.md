# Choice `=` never true (`CHE_B3_DE06` = `CHE.B3.DE04`)

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260813-fhirpath-choice-answers.md`, `fix/20260817-choice-membership-and-group-relevance.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |
| **Approval** | 2026-08-24 conversation (user: enableWhen `%resource…CHE_B3_DE06…value.code = 'CHE.B3.DE04'` never true when the option is picked). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability).

---

# Part I — Issue analysis

## 1. Symptom

A relevance or live calculate that means “Type of Consultation is Initial visit”
is exported as:

```
%resource.repeat(item).where(linkId='CHE_B3_DE06').answer.where($this.exists()).value.code = 'CHE.B3.DE04'
```

The clinician picks that option. The expression stays false, so the gated
questions never appear.

## 2. Why it happens

`SELECTED` / `CONTAINS` already use the HAPI-safe membership test
(`fix/20260817-choice-membership-and-group-relevance.md`):

```
…answer.where(value.code = 'CHE.B3.DE04').exists()
```

`EQUAL` / `NOT_EQUAL` do not. They wrap the choice operand as a scalar
(`.where($this.exists()).value.code`) and compare with `=`.

On QuestionnaireResponse.answer, HAPI FHIRPath exposes polymorphic `value`,
not `valueCoding`. Chaining `.value.code` after `.where($this.exists())` does
not yield the coding’s code (the collection is empty, or `=` on that collection
is empty). `empty = 'CHE.B3.DE04'` is not true.

Inside `.where(value.code = '…')`, `value` is resolved as a child of the
current Answer, which does work.

Authors write `select_one = option` in the diagram. That is `EQUAL`, not
`SELECTED`, so the 2026-08-17 membership fix never applied.

## 3. What authors and implementers should see after the fix

Picking the matching answer on a `select_one` / `select_multiple` makes
`question = option` relevance and calculates true. No diagram change.

## 4. Out of scope

- Comparing two choice items to each other (not reported).
- CQL `initialExpression` equality (Helper accessors, not QR item walks).

---

# Part II — Fix approach

## 5. Formal rules

**R1 — choice vs code uses membership.** FHIRPath `EQUAL` / `NOT_EQUAL` when
one operand is a choice / open-choice answer (including an inherited-value
union that already ends in `.value.code`) and the other is a code literal
(`'CHE.B3.DE04'`, option name, `TriccStatic` string) emit:

```
<answer-collection>.where(value.code = '<code>').exists()
```

`NOT_EQUAL` adds `.not()`.

**R2 — do not compare `.value.code = '…'`.** That chain is the broken form.
Strip `.where($this.exists()).value.code` / `.value.code` back to the answer
collection, then apply R1.

**R3 — non-choice equality unchanged.** Integer / boolean / string items still
use `.where($this.exists()).value = …`.

## 6. Code checklist

- [x] `FHIRStrategy.tricc_operation_fhirpath_equal` / `not_equal`
- [x] Tests: `tests/test_strategies/test_fhir_relevance_fhirpath.py`
- [x] Docs: this file, `docs/open-srp-export.md`

## 7. Acceptance

1. `EQUAL(CHE_B3_DE06, 'CHE.B3.DE04')` emits
   `…linkId='CHE_B3_DE06').answer.where(value.code = 'CHE.B3.DE04').exists()`.
2. That string does **not** contain `.where($this.exists()).value.code =`.
3. `NOT_EQUAL` of the same shape ends with `.exists().not()`.
4. `EQUAL(age, 5)` still uses `.value`.
5. Picking Initial visit on Type of Consultation makes the gated items show.
