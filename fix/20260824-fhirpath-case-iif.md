# `CASE` has no FHIRPath, so `age_in_months` never gets `calculatedExpression`

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260824-fhirpath-numeric-arithmetic.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## 1. Symptom

Registration `age_in_months` is a hidden calculate with only CQL
`initialExpression` `Calc_age_in_months`. `calculatedExpression` is empty, so
the value does not update live when `p_age_years` / `p_age_months` are answered.

Log:

```
Falling back to CQL for age_in_months: CASE is not supported by FHIRPath 2.0 – use CQL instead
```

Authored formula (searched `case` / XLSForm `if`):

```
case
when "p_age_months" >= 0 then Coalesce("p_age_months", 0) + Coalesce(("p_age_years" * 12), 0)
else 0
end
```

The CQL define is also wrong (list-pair CASE dumped as a Python list):

```
define Calc_age_in_months: ['p_age_months >= 0', 'Coalesce(p_age_months, 0) + Coalesce((p_age_years * 12), 0)']
```

## 2. Why FHIRPath failed

`tricc_operation_fhirpath_case` / `_ifs` raise `NotImplementedError`.
XLSForm already expands the same operator to nested `if(cond, then, else)`.
FHIRPath’s equivalent is nested `iif()` (already used for `IF`).

## 3. Out of scope

- Implementing `AGE_MONTH` / `AGE_DAY` in FHIRPath (DOB helpers stay CQL).
- Changing the authored age formula.

---

# Part II — Fix approach

## 4. Emission rules

**R1 — Searched CASE / IFS → nested `iif`.**
`[[cond, val], …, default]` becomes `iif(cond, val, iif(…, default))`. Missing
default is `{}` (empty). Same structure as XLSForm nested `if()`.

**R2 — Value CASE → nested `iif` on equality.**
`[x, [a, va], [b, vb], default]` → `iif(x = a, va, iif(x = b, vb, default))`.

**R3 — In-form CASE uses `calculatedExpression`.**
When every referenced item is in this Questionnaire, attach FHIRPath
`calculatedExpression` (not CQL `initialExpression`).

**R4 — Numeric CASE item type.**
If every value branch (and default) is integer/decimal, the item is `integer`
or `decimal`, not `string`.

**R5 — CQL fallback** for searched CASE emits `if … then … else …`, not a
Python list repr.

## 5. Code checklist

- [x] `tricc_operation_fhirpath_case` / `_ifs` nested `iif`
- [x] `_expression_fhir_number_type` for CASE / IFS / IF
- [x] CQL searched CASE → if/then/else
- [x] tests: age_in_months CASE → FHIRPath `iif` + `calculatedExpression`
- [x] `docs/open-srp-export.md`
