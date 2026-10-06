# FHIRPath `calculatedExpression` crashes: `.round()` on an empty collection

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260824-fhirpath-numeric-arithmetic.md`, `fix/20260821-fhirpath-numeric-compare.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## 1. Symptom

The registration Questionnaire never renders in openSRP FHIR Data Capture — the
form is dead on open, before the user can answer anything:

```
Failed to render questionnaire 50fb25b1-3951-5661-b807-aa5654307ae5
org.hl7.fhir.exceptions.PathEngineException: Error evaluating FHIRPath expression:
focus for 0 can only have one value, but has 0 values (@char 9)
    at FHIRPathEngine.funcRound(FHIRPathEngine.java:4002)
    at ExpressionEvaluator.evaluateCalculatedExpression
    at QuestionnaireViewModel.initializeCalculatedExpressions(QuestionnaireViewModel.kt:734)
```

Unlike `fix/20260824-fhirpath-numeric-arithmetic.md` (which fired when the user
answered a question), this one fires in `initializeCalculatedExpressions` — at
**render time, with every answer still empty** — so the whole questionnaire
fails, not just one calculate.

## 2. Offending expression

`tests/output/cohort_fup/questionnaire/Questionnaire-questionnaire-registration.json`,
hidden decimal item `bmi`:

```
((%resource.item.where(linkId='id_…093c').item.where(linkId='weight').answer.where($this.exists()).value).toDecimal()
 / (…height…/100.0 * …height…/100.0).toDecimal()).round()
```

At render time `weight` and `height` have no answers:

- `…answer.where($this.exists()).value` → empty
- `empty.toDecimal()` → empty (HAPI is spec-conformant here)
- `empty / empty` → empty (HAPI `opDivide` returns empty when either side is empty)
- `empty.round()` → **throws** instead of returning empty

## 3. Why `.round()` throws

FHIRPath ("if the input collection is empty, the result is empty") and HAPI
disagree: HAPI's `funcRound` starts with a `focus.size() != 1` guard and raises
`makeExceptionPlural(…FHIRPATH_FOCUS…)` — the exact message in the trace, with
`0` values. The sibling math functions added in the same HAPI batch (`abs`,
`sqrt`, `truncate`, `exp`, `ln`, `log`, `power`, `ceiling`, `floor`) carry the
same guard.

So *any* generated expression that ends in a HAPI math function is a
render-time crash whenever its operand is unanswered — i.e. always, on form
open. Empty-tolerant emission is the exporter's job; the author cannot express
"round, but only once weight and height exist" in the source graph.

Functions we emit that are **not** affected (verified against HAPI R4):
`toDecimal()` / `toInteger()` (empty focus → `convertToString` → empty),
`length()` (guarded with `if (focus.size() == 1)`, returns empty), `first()`,
`where()`, `exists()`, `iif()` (empty condition → else branch).

## 4. Who is affected

Every FHIR/openSRP form with a `ROUND` (or `ABS`) calculate over in-form
answers — currently `cohort_fup` registration (BMI). The failure is total: no
item renders, so no data can be captured at all.

## 5. Out of scope

- The dropped precision argument: `ROUND(x, 2)` emits `x.round()` and silently
  loses `2` (`base_output_strategy.tricc_operation_round` documents
  `round(r[0], r[1])`; `xls_form` drops it too). Tracked separately.
- Whether BMI *should* be rounded to an integer — author content.
- CQL `initialExpression` emission (`Round(x)`) — CQL returns null on null, no crash.
- The other unimplemented FHIRPath math operators (`ZSCORE`, `MIN`/`MAX`/`SUM`)
  which still raise `NotImplementedError`.

---

# Part II — Fix approach

## 6. Emission rules

**R1 — Single-value FHIRPath math functions are emitted empty-safely.**
Instead of `X.round()`, emit the operand-projected form:

```
X.select($this.round())
```

`select()` over an empty collection yields empty without evaluating the body;
over a one-item collection the body runs with `$this` as a single-item focus, so
`round()` sees exactly one value. No engine-level `iif` is needed and — unlike
`iif(X.exists(), X.round(), {})` — `X` is **not duplicated**, which matters
because `X` is already a long nested-item path (see commit 48c5b2c, real-path
perf).

Applies to `ROUND` and `ABS`. `LENGTH` gets the same treatment for consistency
(HAPI already returns empty there; the emitted form is equivalent for a
one-item focus).

**R2 — The math operand is a numeric scalar.**
`ROUND` / `ABS` route their operand through `_fhirpath_numeric_operand`
(`_wrap_operand_if_needed` + `.toDecimal()` unless already cast / boolean /
choice), same as arithmetic operands under
`fix/20260824-fhirpath-numeric-arithmetic.md`. `LENGTH` keeps
`_wrap_operand_if_needed` only — its operand is a string.

Expected `bmi`:

```
((…weight….answer.where($this.exists()).value).toDecimal()
 / (…).toDecimal()).select($this.round())
```

**R3 — No bare single-value math call may reach a `text/fhirpath` extension.**
A generated Questionnaire must not contain `.round()` or `.abs()` outside a
`select($this.…)` body.

## 7. Code checklist

- [x] `_fhirpath_single_value_call(expr, call)` helper in `fhir_form.py` emitting
      `{expr}.select($this.{call})`
- [x] `tricc_operation_fhirpath_round` uses `_fhirpath_numeric_operand` + helper
- [x] `tricc_operation_fhirpath_abs` uses `_fhirpath_numeric_operand` + helper
- [x] `tricc_operation_fhirpath_length` uses `_wrap_operand_if_needed` + helper
- [x] docstring on the helper explaining the HAPI `focus.size() != 1` guard and
      pointing at this fix
- [x] tests (below)
- [x] `docs/open-srp-export.md` — FHIRPath emission section
- [x] regenerate `tests/output/cohort_fup` and confirm R3 on the registration
      Questionnaire

## 8. Tests

`tests/test_strategies/test_fhir_calculate_expression.py` —
`TestEmptySafeMathCalculatedExpression`:

- `ROUND(weight / (height/100 * height/100))` emits `.select($this.round())`,
  and the expression does not match `(?<!\$this)\.(round|abs)\(\)`.
- `ABS(a - b)` emits `.select($this.abs())`.
- Operand still carries `.answer.where($this.exists()).value` and `.toDecimal()` (R2).

`tests/test_strategies/test_fhir_questionnaire_hygiene.py` —
`TestEmptySafeMathExpressions`: walks every `text/fhirpath` extension of a
generated Questionnaire (calculate **and** relevance) and asserts no bare
`.round()` / `.abs()`.

`tests/test_strategies/test_fhir_relevance_fhirpath.py`: `ROUND` / `ABS` /
`LENGTH` assertions tightened to the projected form; `LENGTH` keeps no
`.toDecimal()`.

Result: 372 passed (full suite), no new flake8 findings.

Regenerated `tests/output/cohort_fup`: the `bmi` calculatedExpression ends
`… .toDecimal().select($this.round())`, and neither Questionnaire contains a bare
math call. (Sibling order of the `load_*` items shifts between runs — pre-existing
export nondeterminism, unrelated to this fix.)

## 9. Acceptance criteria

1. `cohort_fup` registration Questionnaire renders in openSRP with all answers
   empty — no `PathEngineException` from `funcRound` in logcat.
2. Once weight and height are answered, `bmi` computes the same rounded value as
   before the fix.
3. Full suite green (`python -m pytest tests/`).
