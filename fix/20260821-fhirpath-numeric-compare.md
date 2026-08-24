# FHIRPath `calculatedExpression` crashes: string compared to integer

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260821-sdc-singleton-expressions.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## 1. Symptom

openSRP FHIR Data Capture fails while initialising calculated expressions:

```
Failed to render questionnaire e43806d7-67e0-5792-8622-f10ac9404f8a
org.hl7.fhir.exceptions.PathEngineException: Error evaluating FHIRPath expression:
Unable to compare values of type string and integer (@char 55)
    at FHIRPathEngine.opGreaterOrEqual
    at ExpressionEvaluator.evaluateCalculatedExpression
```

Thrown on `Dispatchers.Main.immediate` inside the SDK ViewModel (same uncaught
path as a duplicate `calculatedExpression`).

## 2. Offending expression

Registration item `child_Vv_1`:

```
%resource.repeat(item).where(linkId='age_in_months').answer.where($this.exists()).value >= 2
```

Character 55 is `.value >= 2`. `age_in_months` is a hidden **calculate emitted
as `type: string`** with CQL `initialExpression` `Calc_age_in_months`. `$populate`
stores a string; HAPI then compares that string to the integer `2`.

The same pattern is widespread: `age_in_days`, `age_in_years`, `WFA`/`WFL` (also
string calculates) used in `>=` / `<` / `<=` in both `calculatedExpression` and
`enableWhenExpression`. `>` / `<` currently skip the `.value` wrap as well
(`.answer < 2`).

## 3. Why the item is a string

`TriccNodeType.calculate` maps to FHIR `string`. `generate_base` /
`generate_calculate` already coerce to `boolean` when the expression is in
`RETURNS_BOOLEAN`. Numeric operators (`AGE_MONTH`, `PLUS`, `COUNT`, …) stay
`string`.

## 4. Out of scope

- Implementing z-score in FHIRPath (`WFA` currently serialises as `'Zscore'`).
- Changing CQL age helpers.

---

# Part II — Fix approach

## 5. Emission rules

**R1 — Numeric calculate items are `integer` or `decimal`, not `string`.**
If the calculate's expression operator is in `RETURNS_NUMBER`, set the
Questionnaire item type to `integer` (age in days/months/years, `COUNT`,
`CAST_INTEGER`, `GET_NUMBER_OF_REPEAT`) or `decimal` (the rest). Same coerce
path as boolean.

**R2 — Relational FHIRPath compares decimals.**
`>`, `>=`, `<`, `<=`, and `BETWEEN` wrap each operand with `.where($this.exists()).value`
when it is an item, then `.toDecimal()` (numeric literals become `2.0`). Boolean
and choice operands are not cast.

## 6. Code checklist

- [x] `_expression_fhir_number_type` + apply in `generate_base` / `generate_calculate`
- [x] `_fhirpath_numeric_operand` used by more/less/more_or_equal/less_or_equal/between
- [x] tests: `age >= 2` emits `.toDecimal()`; `AGE_MONTH` calculate is `integer`
- [x] `docs/open-srp-export.md`
