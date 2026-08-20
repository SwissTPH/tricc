# Choice membership FHIRPath and page-group relevance

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260813-fhirpath-choice-answers.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |

## What went wrong

1. Option-selected relevance (`SELECTED` / `CONTAINS`) emitted
   `'demo.bad_p' in %resource.repeat(item).where(linkId='select_why').answer.valueCoding.code`.
   HAPI FHIRPath on `QuestionnaireResponse.item.answer` exposes polymorphic `value`,
   not `valueCoding`, so the collection is empty and the test is always false.
2. Page / activity groups (demo **Page-2**) had no `enableWhenExpression`. The
   condition (hungry OR bad_p) lives on `activity.relevance` (same place XLSForm
   begin-group uses). The `activity_start` node's own `relevance` is `true`.

## Fix

- Membership: `…answer.where(value.code = 'demo.bad_p').exists()`
- Group starters (`start` / `activity_start` / `page`) emit `activity.relevance`
  when it is a real expression.

## Acceptance

- Ticking `select_why` options shows notes / flags / Page-2.
- Page-2 group `enableWhenExpression` is hungry OR bad_p membership.
