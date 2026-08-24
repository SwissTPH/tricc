# FHIRPath `calculatedExpression` crashes: `*` on `QuestionnaireResponse.item.answer`

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260821-fhirpath-numeric-compare.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## 1. Symptom

openSRP FHIR Data Capture fails while evaluating calculated expressions (same
uncaught SDK path as `fix/20260821-fhirpath-numeric-compare.md`):

```
Failed to render questionnaire e43806d7-67e0-5792-8622-f10ac9404f8a
org.hl7.fhir.exceptions.PathEngineException: Error evaluating FHIRPath expression:
left operand to * has the wrong type QuestionnaireResponse.item.answer (@char 7)
    at FHIRPathEngine.opTimes
    at ExpressionEvaluator.evaluateAllAffectedCalculatedExpressions
```

Triggered when the registration age questions (`p_age_years` / `p_age_months`)
are answered — those answers feed the hidden `age_in_days` calculate.

## 2. Offending expression

Registration item `age_in_days`:

```
((%resource.repeat(item).where(linkId='p_age_months').answer|0).where($this.exists()).first() * 30)
 + (365 * (%resource.repeat(item).where(linkId='p_age_years').answer|0).where($this.exists()).first())
```

HAPI `*` requires numbers. The left operand is a `QuestionnaireResponse.item.answer`
(the union of the months item’s answer collection with `0`, then `.first()`), not
`.answer.value`.

The same COALESCE-without-value pattern is on `age_in_years`:

```
(%resource.repeat(item).where(linkId='p_age_years').answer|0).where($this.exists()).first()
```

`fix/20260821-fhirpath-numeric-compare.md` wrapped **relational** operands
(`>`, `>=`, `<`, `<=`, `BETWEEN`) with `.value` / `.toDecimal()`. Arithmetic
(`+`, `-`, `*`, `/`, `mod`) and `COALESCE` were left emitting raw `.answer`
collections.

## 3. Why this is an Answer object

1. **COALESCE** serialises as FHIRPath union: `(a|b).where($this.exists()).first()`.
   Each item operand is currently the `.answer` collection, so `.first()` is an
   Answer, not a number. (`|` is union, not SQL coalesce; the `.first()` after
   `exists` is the analogue, and it only yields a number when the members are
   scalars.)
2. **MULTIPLIED / DIVIDED / MODULO** have no FHIRPath handler, so they fall
   through to the CQL join (`a * b`) with no `.value` wrap. **PLUS / MINUS**
   have FHIRPath handlers that also join unwrapped operands.

The engine builds age-in-days as
`COALESCE(p_age_months, 0) * 30 + 365 * COALESCE(p_age_years, 0)`.

## 4. Out of scope

- Implementing `AGE_MONTH` / `AGE_DAY` in FHIRPath (still CQL `initialExpression`).
- Changing how the visitor builds the age formula.
- `GET_INHERITED_VALUE` (already has its own value-suffix union).

---

# Part II — Technical specification

## 5. Emission rules

**R1 — Arithmetic FHIRPath uses numeric scalars.**
`+`, `-`, `*`, `/`, and `mod` wrap each operand with `_fhirpath_numeric_operand`
(item → `.where($this.exists()).value` then `.toDecimal()`; numeric literals →
`2.0`; nested operations → `.toDecimal()` unless already cast). Boolean / choice
operands are not cast (same skip list as relational).

**R2 — COALESCE of item references reads scalar values.**
Each operand is wrapped with `_wrap_operand_if_needed` *before* the `|` union, so
the collection is values (or `0`), not Answer objects:

```
(%resource.repeat(item).where(linkId='p_age_months').answer.where($this.exists()).value | 0).where($this.exists()).first()
```

Choice operands keep `_answer_value_suffix` (`.value.code`). Do **not** apply
`.toDecimal()` inside COALESCE — the result may be assigned to an integer item;
arithmetic consumers add `.toDecimal()` via R1.

**R3 — COALESCE of numeric inputs is a numeric calculate.**
If every non-static COALESCE operand is integer/decimal (node or numeric
operation), the Questionnaire item type is `integer` (all integer) or `decimal`.
`COALESCE(p_age_years, 0)` must not stay `string`.

Expected `age_in_days`:

```
(((%resource.repeat(item).where(linkId='p_age_months').answer.where($this.exists()).value|0).where($this.exists()).first()).toDecimal() * 30.0)
 + (365.0 * (%resource.repeat(item).where(linkId='p_age_years').answer.where($this.exists()).value|0).where($this.exists()).first()).toDecimal()
```

(Exact extra `.toDecimal()` wrapping on nested operations is allowed.)

## 6. Code checklist

- [x] `_fhirpath_numeric_operand` used by plus / minus / multiplied / divided / modulo
- [x] `tricc_operation_fhirpath_coalesce` wraps each operand
- [x] `_expression_fhir_number_type` treats numeric COALESCE as integer/decimal
- [x] tests: age-in-days formula emits `.value` and does not multiply `.answer`;
      `COALESCE(integer, 0)` calculate is `integer`
- [x] `docs/open-srp-export.md`

## 7. Tests

- `convert_expression_to_fhirpath(COALESCE(p_age_months, 0) * 30 + 365 * COALESCE(p_age_years, 0))`
  contains `.value`, `30.0` / `365.0` (or `.toDecimal()`), and does **not** contain
  `.answer *` or `.answer|0)` without `.value`.
- `generate_calculate` on `COALESCE(p_age_years, 0)` sets item `type` to `integer`.
- Existing `COUNT - CAST_NUMBER(SELECTED)` still uses `iif` for the boolean;
  outer `.toDecimal()` on the minus operands is allowed.
