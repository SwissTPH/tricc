# A suffix call binds to the last operand (`Length(a & b)` → `a & b.length()`)

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260831-fhirpath-empty-safe-math.md`, `fix/20260824-fhirpath-numeric-arithmetic.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |
| **Approval** | 2026-09-02 conversation (cohort_fup crashed on the device; GlitchTip issue 97 "Failed to render questionnaire 50fb25b1-…"). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## 1. Symptom

`cohort_fup` renders on open, then dies as soon as the clinician answers
anything on the symptom page. fhircore logs
`Failed to render questionnaire 50fb25b1-3951-5661-b807-aa5654307ae5` and
reports the coroutine cancellation (`JobCancellationException`) that follows —
the real exception is swallowed.

Reproduced against HAPI `org.hl7.fhir.r4` 6.0.22 (the version OpenSRP 2.2.2-qa
ships) on the exported Questionnaire: with any answer present,

```
RAISE[symptom_l:calculatedExpression] PathEngineException:
  right operand to & has the wrong type integer
```

Nothing raises while the form is empty, which is why the crash looks like "it
breaks when I select symptoms".

## 2. Why it happens

`symptom_l` builds a comma-joined symptom label list. The author guards each
separator with "is anything in the list yet", i.e. `LENGTH(CONCATENATE(a, b)) > 0`.
That was exported as:

```
(a.toString() & b.toString().select($this.length())).toDecimal() > 0.0
```

FHIRPath path navigation binds tighter than `&`, so `.select($this.length())`
applies to `b` alone and the expression evaluates `string & integer`. HAPI
raises instead of returning empty, the exception leaves
`initializeCalculatedExpressions`, and the whole Questionnaire fails to render.

The generator appended the call with a plain f-string
(`f"{expr}.select($this.{call})"`), which is only correct when `expr` is a
single path or an already-parenthesised group. The same shape predates
`fix/20260831-fhirpath-empty-safe-math.md` (`f"{expr}.length()"` mis-bound
identically), so this is not a regression from that fix — it is the same
missing-parentheses bug, still present after it.

## 3. What authors should see after the fix

`LENGTH(CONCATENATE(…))`, `ROUND(a + b)`, `ABS(a - b)` and the existence tests
work on composite operands. No diagram change.

## 4. Out of scope

- The `&`-vs-`+` choice for concatenation (unchanged).
- Whether a 42 KB `calculatedExpression` is a good idea (it is what the authored
  label list produces; it evaluates fine).

---

# Part II — Fix approach

## 5. Formal rules

**R1 — parenthesise a composite operand before appending a call.** Emitting
`X.f()` where `X` contains a binary operator (`&`, `+`, `-`, `*`, `/`,
comparison, `and`/`or`/`xor`/`implies`, `div`/`mod`, `in`, `contains`) at the
top level — outside quotes and brackets — must emit `(X).f()`. A single path,
literal or already-parenthesised group is left alone.

**R2 — applies to every suffix emitter.** `ROUND` / `ABS` / `LENGTH` (through
`_fhirpath_single_value_call`) and `EXISTS` / `NOTEXISTS` / `ISNULL` /
`ISNOTNULL`. `NOT` already parenthesised.

## 6. Code checklist

- [x] `_FHIRPATH_BINARY_OP` + `_fhirpath_has_top_level_operator` +
      `_fhirpath_atom` in `tricc_oo/strategies/output/fhir_form.py`.
- [x] `_fhirpath_single_value_call` parenthesises through `_fhirpath_atom`.
- [x] `tricc_operation_fhirpath_exists` / `_notexists` / `_isnull` / `_isnotnull`.
- [x] Tests: `tests/test_strategies/test_fhir_suffix_precedence.py` +
      `tests/data/yaml/length_of_concatenation.yaml`.
- [x] Docs: this file + `docs/open-srp-export.md`.

## 7. Acceptance

1. `LENGTH(CONCATENATE(a, b))` emits `((a).toString() & (b).toString()).select($this.length())`,
   never `… & (b).toString().select($this.length())`.
2. `ROUND(a + b)` / `ABS(a - b)` parenthesise the arithmetic before the call.
3. `LENGTH(a)` on a plain reference gains no redundant parentheses.
4. The exported `cohort_fup` registration Questionnaire evaluates with **0**
   raises under HAPI 6.0.22 with 0, 1, 2 and 3 answers per repeating choice
   (verified by repairing the 18 mis-bound sites in the pushed artifact).
5. `python -m pytest tests/` passes.
