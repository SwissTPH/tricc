# In-form FHIRPath: nested `item.where(linkId)` instead of `repeat(item)`

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260813-fhirpath-choice-answers.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |
| **Approval** | 2026-08-24 conversation (user: OpenSRP is slow; emit precise group/`linkId` paths). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability).

---

# Part I — Issue analysis

## 1. Symptom

Live `enableWhenExpression` / `calculatedExpression` / option toggles all look up
answers with:

```
%resource.repeat(item).where(linkId='CHE_B3_DE06')
```

`repeat(item)` walks **every** QuestionnaireResponse item. OpenSRP re-evaluates
those expressions on each answer change. On a nested IMCI form that is a full
tree walk per expression, per keystroke.

## 2. Why `repeat(item)` was added

`%resource.item.where(linkId=…)` only sees **top-level** items. Questions sit
under start / page / activity groups, so the 2026-08-13 fix switched to
`repeat(item)` rather than recording the nest.

StructureMap already walks `item.item` and matches `linkId` on the current node.
It does not use `repeat()`. FHIRPath can do the equivalent with an explicit path.

## 3. What authors and implementers should see after the fix

Same behaviour (nested questions still found). Forms should evaluate live
expressions faster. No diagram change.

## 4. Out of scope

- StructureMap FML (keep recursive `item.item` + `item as q where(linkId=…)`;
  HAPI FML still rejects `item.where(…)` as a path).
- CQL Helper accessors (not QR item walks).
- Flattened QuestionnaireResponse trees (SDC / OpenSRP keep Questionnaire
  nesting; if a client flattened QR, `repeat(item)` was the fallback).

---

# Part II — Fix approach

## 5. Formal rules

**R1 — precise path when the item is on a Questionnaire.** Index each
`linkId` to its root-to-item list of `linkId`s. Emit:

```
%resource.item.where(linkId='<g1>').item.where(linkId='<g2>').item.where(linkId='<item>')
```

Top-level items are `%resource.item.where(linkId='<item>')` (no `repeat`).

**R2 — fallback.** If the `linkId` is not on any Questionnaire (or not yet
indexed), keep `%resource.repeat(item).where(linkId='<item>')`.

**R3 — current Questionnaire wins.** When the same `linkId` exists on more than
one process, use `_current_segment` from serialisation context.

**R4 — `descendants()` stays forbidden** (walks non-item children).

## 6. Code checklist

- [x] `FHIRStrategy._fhirpath_answer` / item-path index
- [x] Tests: nested path, top-level path, unknown `linkId` fallback
- [x] Docs: this file, `docs/open-srp-export.md`, `docs/desing/FHIRcore.md`

## 7. Acceptance

1. A question under two groups emits
   `%resource.item.where(linkId='g1').item.where(linkId='g2').item.where(linkId='q')`.
2. A top-level item emits `%resource.item.where(linkId='q')`, not `repeat(item)`.
3. A reference with no Questionnaire item still uses `repeat(item)`.
4. Choice membership / inherited-value unions still work; each `linkId` has its
   own path.
