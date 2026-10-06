# `GetRepeatedValue(code)` — latest value already collected this consultation

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `develop` |
| **Related** | `feature/20260821-get-repeated-value-operation.md` (mandatory slot), `feature/concept-repeat.md`, `feature/populate-context.md`, `feature/advanced-merge-calc.md`, `feature/display-text-injection.md`, `feature/20260812-intervention-order-and-dedup.md` |
| **Authoring surface** | draw.io calculate expressions + YAML fixtures |
| **Target strategies** | XLSForm / CHT (FHIR deferred — see §12) |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business Description

*Audience: clinical authors, guideline developers, implementers.*

## 1. Overview

Authors can read back a value **already collected earlier in the same consultation**, without
asking the question again:

```text
GetRepeatedValue('etat.r.006')
```

Used in a calculate, this yields the most recent value captured for that concept so far in the
form. The typical use is a **confirm-and-overwrite** step: show the value, ask whether it is still
correct, and only re-ask the question when it is not.

`GetRepeatedValue` already exists with a mandatory repeat-slot argument. This feature makes the
second argument **optional**: when it is omitted, the lookup is no longer restricted to one capture
slot and returns the latest value across slots.

| Form | Meaning |
|------|---------|
| `GetRepeatedValue('weight', 2)` | Value captured in repeat slot 2 specifically |
| `GetRepeatedValue('weight')` | Latest value captured for `weight` so far, any slot |

## 2. Clinical problem

A weight may be measured at triage and then needed again later in the same visit. Asking twice
wastes time and invites transcription differences; trusting the first value blindly is unsafe when
the child has been re-weighed or the first entry was a typo.

The wanted pattern is a confirmation:

> For this child the weight is 8.4 kg. Is this correct?

If the user confirms, the protocol continues with the existing value. If not, the question is asked
again and the new value supersedes it for everything downstream.

## 3. What this is **not**

This is deliberately **within the current consultation**. It is not a look-up into the patient's
chart from earlier visits.

| Need | Use |
|------|-----|
| Value collected earlier **in this consultation** | `GetRepeatedValue('code')` — this feature |
| Value from a **previous consultation** | `populate` `context=history` / `GetHistoryObservationValue` |
| Value known from the **patient record** (age, sex) | `populate` `context=patient` |

## 4. Authoring example

```text
calculate     last_weight_value = GetRepeatedValue('etat.r.006')

note          "For this child the weight is ${last_weight_value}. Is this correct?"
                relevance: last_weight_value is not null

select_yesno  weight_confirmed

decimal       etat.r.006   repeat=2
                relevance: weight_confirmed = 'no'

calculate     weight_effective = GetRepeatedValue('etat.r.006')
```

Reading the flow:

1. `last_weight_value` reads the weight captured earlier in the visit.
2. The note displays it using the existing `${…}` injection, and hides itself when nothing was
   collected.
3. The re-ask is a **second capture slot** (`repeat=2`), so it is genuinely asked rather than
   skipped as a duplicate of slot 1.
4. `weight_effective` reads the latest value again — after the re-ask, so it picks up the
   correction when there is one, and falls back to the original when there is not.

Downstream logic (dosing, z-scores) should use `weight_effective`, not `etat.r.006` directly.

## 5. Position in the flowchart matters

"Latest so far" is evaluated **at the point in the flow where the calculate sits**. A calculate
placed before the re-ask cannot see the re-ask; one placed after it can. This is the same rule that
already governs plain concept references in TRICC, and it is what makes the confirm pattern safe:
the confirmation note cannot depend on the answer it is trying to confirm.

## 6. Limitations

- **Same form only.** If the earlier value was collected in a *different* form of the same
  consultation (a CHT task chain), there is no field in this form to read. Use `populate`
  `context=encounter` for that case.
- **Must have been collected earlier in the flow.** Referencing a concept that is never captured
  before this point is an authoring error and stops the conversion (§10.4) — it is not silently
  treated as empty.
- **`repeat=-1` captures are invisible** to this lookup by design; local-only slots do not
  participate in value inheritance.
- **XLSForm / CHT only in this phase.** FHIR export is deferred (§12).

---

# Part II — Technical Specification

*Audience: TRICC developers. Do not implement until Part I is **Approved**.*

## 7. Formal semantics

```text
GetRepeatedValue(code)      ≡  TriccOperation(GET_REPEATED_VALUE, [TriccReference(code)])
GetRepeatedValue(code, n)   ≡  TriccOperation(GET_REPEATED_VALUE, [TriccReference(code), TriccStatic(n)])
```

Resolution reuses the existing reference machinery with a single knob — the repeat filter:

| Arity | `ref_repeat` | Candidate set |
|-------|--------------|---------------|
| 1 | `None` | All processed versions of `code`, any repeat slot |
| 2 | `int(n)` | Processed versions of `code` in slot `n` only |

`ref_repeat=None` already means "any slot" in `version_filter`:

```107:109:tricc_oo/visitors/tricc.py
        if repeat is not None:
            return _get_repeat(item) == repeat
        return True
```

With `inherit_display_versions=True` the resolver expands multi-version matches to
`GET_INHERITED_VALUE(ordered newest-first)`, which serializes to `coalesce(…)` — that is the
"latest non-empty value" semantics, with no new lookup logic required.

Only **processed** nodes are candidates, so a calculate upstream of the re-ask cannot resolve to it
and no dependency cycle is possible.

## 8. Current state of the code

`GET_REPEATED_VALUE` is **half-wired**: the enum member and the XLSForm handler exist, but nothing
in the codebase ever constructs the operation. That keeps regression risk low, and it also means
the one existing resolver branch has never executed.

| Piece | State |
|-------|-------|
| `TriccOperator.GET_REPEATED_VALUE` (`models/base.py`, value `"get_repeated_value"`) | Exists; in `RETURNS_CONCEPT` |
| `FUNCTION_MAP` entry in `converters/cql_to_operation.py` | Exists (`feature/20260821-get-repeated-value-operation.md`); this overlay adds `as_concept_reference` so `'code'` is not a `TriccStatic` |
| Resolver (`get_repeat_index_arg`) | Exists; omitted slot now returns `None` (any slot) instead of defaulting to `1` |
| `tricc_operation_get_repeated_value` (XLSForm/CHT) | Exists; this overlay hard-fails if the concept did not resolve |

Because `FUNCTION_MAP` has no entry, `GetRepeatedValue('x')` written today parses as `NATIVE` and
`tricc_operation_native` emits the call **verbatim** into the XLSForm `calculation` column, which is
not valid ODK.

## 9. Pipeline

```text
draw.io / YAML calculate:  GetRepeatedValue('etat.r.006')
        │
        ▼  converters/cql_to_operation.py
FUNCTION_MAP → GET_REPEATED_VALUE ; arg 0 normalized to TriccReference
        │
        ▼  visitors/tricc.py :: process_operation_reference
ref_repeat = None (1 arg) | int(n) (2 args)
  → resolves to processed version(s) of the concept
  → multi-version ⇒ GET_INHERITED_VALUE(newest-first)
        │
        ▼  strategies/output/xls_form.py
tricc_operation_get_repeated_value → ${field} | coalesce(${v2}, ${v1})
        │
        ▼  note label
"… is ${last_weight_value}. …"   (existing ${REF} injection)
```

## 10. Code changes

### 10.1 Parse — `tricc_oo/converters/cql_to_operation.py`

Add the mapping:

```python
"GetRepeatedValue": TriccOperator.GET_REPEATED_VALUE,
```

**Normalize argument 0 to a `TriccReference`.** This is the single most important detail. CQL
quoting decides the operand class today:

| Authored | Parsed as | Consequence without normalization |
|----------|-----------|-----------------------------------|
| `GetRepeatedValue('code')` | `TriccStatic` (`visitStringLiteral`) | Never resolved; exported as an ODK **string literal** |
| `GetRepeatedValue("code")` | `TriccReference` (`resolve_scv`) | Correct |
| `GetRepeatedValue(code)` | `TriccReference` (dotted-name guess) | Correct |

Single quotes are the natural way to write a concept code and must work. Introduce a declarative
set of operators whose first argument is a concept reference and coerce it after the operation is
built:

```python
CONCEPT_REF_FIRST_ARG = {TriccOperator.GET_REPEATED_VALUE}
```

Coerce `TriccStatic(str)` → `TriccReference(str)` for those operators; a non-string first argument
is an authoring error. `GET_NUMBER_OF_REPEAT` is a candidate for the same treatment later, but is
out of scope here.

### 10.2 Resolve — `tricc_oo/visitors/tricc.py`

The existing branch breaks on both arities:

```1187:1191:tricc_oo/visitors/tricc.py
        ref_repeat = None  # TODO: manage repeat in scv get_repeat(node)
        if operation.operator == TriccOperator.GET_HISTORY_VALUE:
            ref_repeat = 0
        elif operation.operator == TriccOperator.GET_REPEATED_VALUE:
            ref_repeat = int(operation.reference[1])
```

Two defects to fix:

1. **`IndexError`** with one argument — guard on `len(operation.reference) > 1`.
2. **`TypeError`** with two — `reference[1]` is a `TriccStatic`, so `int()` on the model raises.
   Read `.value`.

Behaviour after the fix: one argument leaves `ref_repeat` at `None` (any slot), two arguments pin
the slot. No other resolver change is needed.

### 10.3 Serialize — `tricc_oo/strategies/output/xls_form.py`

The existing handler delegates every operand to coalesce:

```822:825:tricc_oo/strategies/output/xls_form.py
    def tricc_operation_get_repeated_value(self, ref_expressions, original_references=None):
        # Enum value is "ge_repeated_value". Lookups resolve to this operator
        # (not GET_INHERITED_VALUE) so CHT does not prepend coalesce(., …).
        return self.tricc_operation_coalesce(ref_expressions, original_references)
```

That is correct for the one-argument form but **wrong for the two-argument form**. The repeat slot
is consumed at resolution time as a *filter*; it is not a runtime value. Resolution replaces only
the concept operand and leaves the slot literal in place, and
`get_tricc_operation_expression` serializes **every** entry of `operation.reference`:

```389:406:tricc_oo/strategies/output/xls_form.py
        for r in operation.reference:
            original_references.append(r)
            if isinstance(r, list):
                r_expr = [
                    (
                        self.get_tricc_operation_expression(sr)
                        if isinstance(sr, TriccOperation)
                        else self.get_tricc_operation_operand(sr, coalesce_fallback)
                    )
                    for sr in r
                ]
            elif isinstance(r, TriccOperation):
                r_expr = self.get_tricc_operation_expression(r)
            else:
                r_expr = self.get_tricc_operation_operand(r, coalesce_fallback)
            if isinstance(r_expr, TriccReference):
                r_expr = self.get_tricc_operation_operand(r_expr, coalesce_fallback)
            ref_expressions.append(r_expr)
```

So `GetRepeatedValue('weight', 2)` would emit `coalesce(${weight_r2}, 2)` — the slot number leaking
in as a fallback value, meaning the calculate silently evaluates to `2` whenever slot 2 is empty.

The handler must therefore serialize the **concept operand only** (which already carries the
newest-first coalesce of matching versions) and ignore any trailing slot literal, in addition to
applying the guard from §10.4. CHT strategies inherit the corrected handler unchanged.

### 10.4 Fail loudly instead of emitting `1`

Two existing mechanisms silently turn an unresolved lookup into a constant, and this is the failure
mode the guard exists to prevent.

**An empty calculation becomes `1` everywhere it is referenced.** `tricc_operation_coalesce`
returns `""` for an empty operand list, the row is dropped as an empty calculate, and then every
reference to it — *including note labels* — is rewritten:

```363:364:tricc_oo/strategies/output/xls_form.py
        for index, empty_calc in df_empty_calc.iterrows():
            self.df_survey.replace("${" + empty_calc["name"] + "}", "1", regex=True)
```

So `For this child the weight is ${last_weight_value}` renders as `… is 1`.

**An unresolved reference becomes a bare token.** `TriccReference` subclasses `TriccStatic`, so the
first branch below shadows the second and the `${…}` fallback is unreachable:

```720:724:tricc_oo/strategies/output/xls_form.py
        elif isinstance(r, (TriccStatic, str, int, float)):
            return get_export_name(r)
        elif isinstance(r, TriccReference):
            logger.warning(f"reference `{r.value}` still used in a calculate")
            return f"${{{get_export_name(r.value)}}}"
```

`get_export_name` then emits a quoted ODK string literal for a `TriccStatic`
(`tricc_to_xls_form.py`), so the note would read `… is etat.r.006`.

Required guards:

1. **Serializer guard** — in `tricc_operation_get_repeated_value`, if `ref_expressions` is empty, or
   any entry in `original_references` is still a `TriccReference` / `TriccStatic` rather than a
   resolved node, `logger.critical` naming the calculate node **and** the concept code, then
   `exit(1)`. This makes "concept never collected before this point" a hard authoring error, per
   the agreed decision, and structurally prevents the empty-calculate rewrite.
2. **Operand branch order** — move the `TriccReference` check above the `TriccStatic` check in
   `get_tricc_operation_operand` so leftover references warn instead of degrading quietly. This is
   a pre-existing bug; fixing it is what makes guard 1 observable rather than silent.

### 10.5 Explicitly unchanged

- `GET_HISTORY_VALUE` and the `GetHistoryObservation*` CQL family — different scope (previous
  consultations), untouched.
- `populate` contexts and `populate_helper.py`.
- `GET_INHERITED_VALUE` behaviour for plain concept references.
- `repeat_helper.py` CQL — see §12.
- The `_wt_jun19` and `_wt_pre_goto` worktrees.

## 11. Interaction with concept repeat

The re-ask must not be swallowed by duplicate-capture skip logic. Recommended authoring is
`repeat=2` on the re-ask: a real second slot is asked, and a one-argument `GetRepeatedValue` placed
after it coalesces newest-first to the corrected value.

`repeat=-1` is **not** suitable: the inheritance expansion excludes `-1` deliberately, so a later
`GetRepeatedValue` would never see the correction. Document this in `docs/tricc-elements.md`
alongside the existing repeat notes.

## 12. FHIR / OpenSRP (deferred)

Out of scope for this phase, but the shape is already right. Since the current-encounter dedup work
(`feature/20260812-intervention-order-and-dedup.md`), the `GetObservations` family filters on
`O.encounter.reference`, so `GetRepeatedValue` is already encounter-scoped in generated CQL. A
future phase adds a `repeatIndex is null` → "latest across slots" overload in `repeat_helper.py` and
a `tricc_operation_get_repeated_value` handler on `FHIRStrategy`. Until then, the FHIR strategy
raises `NotImplementedError` for this operator through its existing dispatch, which is the desired
behaviour — no silent wrong output.

## 13. Code checklist

- [x] `FUNCTION_MAP` entry for `GetRepeatedValue` (`converters/cql_to_operation.py`)
- [x] `CONCEPT_REF_FIRST_ARG` + `as_concept_reference()` normalization of argument 0 to `TriccReference`
- [x] `process_operation_reference`: arity guard + `.value` fix (`visitors/tricc.py`)
- [x] Serializer: concept operand only (drop trailing slot literal) + `_assert_repeated_value_resolved` guard (`strategies/output/xls_form.py`)
- [x] `get_tricc_operation_operand`: `TriccReference` branch before `TriccStatic`
- [x] Docs: `docs/tricc-elements.md`, `docs/pipeline.md`, `feature/concept-repeat.md` cross-reference
- [x] Tests per §14 (`tests/test_get_repeated_value.py`, 3 YAML fixtures)

## 14. Tests

YAML fixtures under `tests/data/yaml/` (preferred per `AGENTS.md`), driven like the existing
`concept_repeat_*` and `note_text_injection` cases. Calculates are authored via the `calculate:`
attribute, which routes through `parse_expression` → `transform_cql_to_operation`.

| Fixture / test | Asserts |
|----------------|---------|
| `get_repeated_value_latest.yaml` | One-argument call resolves to the earlier capture; ODK calculation is `${…}` / `coalesce(…)`, never a literal or `1` |
| `get_repeated_value_confirm_overwrite.yaml` | Full weight confirm flow with `repeat=2` re-ask; post-re-ask calculate coalesces newest-first |
| `get_repeated_value_slot.yaml` | Two-argument call still pins the slot (regression for the `.value` fix), and the slot number does **not** leak into the exported expression as a coalesce fallback |
| Unit — parse | Single-, double-, and un-quoted first argument all produce `TriccReference`; arity 1 and 2 both parse |
| Unit — resolve | One argument leaves `ref_repeat=None`; two arguments yield `int(n)`; no `IndexError` / `TypeError` |
| Unit — guard | Unresolvable concept exits with a message naming node and code; no empty calculate row is produced |
| Unit — note | `${last_weight_value}` in a note label survives export as a field reference, not `1` |
| Regression | `python -m pytest tests/` green, in particular `test_concept_repeat.py`, `test_display_reference_inheritance.py`, `test_populate_context.py`, `test_fhir_repeat.py` |

## 15. Acceptance criteria

1. `GetRepeatedValue('etat.r.006')` in a draw.io / YAML calculate exports as an ODK reference to the
   earlier capture of that concept — `${…}` or `coalesce(…)` — and never as `1` or a quoted literal.
2. Single, double, and unquoted concept codes are all accepted.
3. `GetRepeatedValue('etat.r.006', 2)` still resolves to repeat slot 2 only, and the slot number
   does not appear in the exported expression.
4. The confirm-and-overwrite flow works end to end on XLSForm and CHT: note shows the earlier
   value, re-ask appears only when the user answers "no", and a calculate after the re-ask reflects
   the correction.
5. A concept never collected earlier in the flow fails the conversion with a message naming the
   calculate and the concept code.
6. `GET_HISTORY_VALUE`, populate contexts, and existing inheritance behaviour are unchanged; the
   full test suite passes.

## 16. Implementation phases

| Phase | Content |
|-------|---------|
| 1 | Parse: `FUNCTION_MAP` + first-argument normalization, with unit tests |
| 2 | Resolve: arity guard and `.value` fix, with unit tests |
| 3 | Serialize guards: unresolved/empty error and operand branch order |
| 4 | YAML fixtures for the confirm-and-overwrite flow; full regression run |
| 5 | Docs update; set status to `Implemented` |
| 6 | *(separate spec)* FHIR overload and `repeat_helper.py` CQL |
