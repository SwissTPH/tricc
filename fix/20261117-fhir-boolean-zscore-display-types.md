# FHIR output: a library that does not compile, a Boolean on a string item, `'Zscore'` as a value

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `develop` |
| **Related** | `fix/20260929-cql-initial-expression-on-device.md` (§6 `_cql_node_reference`, §8 boolean calculates), `fix/20260831-fhir-dynamic-display-text.md` (display text `${REF}` injection) |
| **Origin** | 2026-11-17. The global Almanach child package (`global-almanach`, `L2/child` + `L2/common`, `OpenSRPStrategy`) run against HAPI 8.12 Clinical Reasoning (server-side `$populate`) and rendered with kotlin-fhir-data-capture. Requested in session ("fix it in tricc and regenerate global as PR"). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Issue analysis

### Symptoms

1. Every CQL pre-fill of *Diagnostic Testing* was empty. HAPI's `Library/$evaluate`
   answered `Library imci-icrc-global-child-diagnostic-testing-1.0.0 loaded, but had errors`:
   `Could not resolve call to operator ToBoolean with signature (System.Boolean)` and
   `Could not resolve call to operator Less with signature (System.String, System.Integer)`
   (the `IsTrue` / `And` / `Or` / `Coalesce` errors follow from these two).
2. Once the library compiled, opening *Diagnostic Testing* failed in the renderer:
   `Mismatching question type string and answer type Boolean for CHE_B27_G_DE04`.
3. `WFA` / `WFH` / `WFL` were `string` items whose `calculatedExpression` was the text
   `'Zscore'`.
4. The diazepam display text read the dose as
   `…answer.where($this.exists()).value.where($this.exists()).value` — always empty.
5. `CHE_B23_DE02A_Vv_1` (*History of obstructed or absent breathing*) got no value while any
   hidden calculate it reads (`CHE_B27_G_DE01 … = false`) had none.

### Causes

| # | Where | Cause |
|---|-------|-------|
| 1, 2 | `_expression_returns_boolean` | A calculate is `coalesce(get_inherited_value(<rule>), get_inherited_value(<itself>))`. Only `parenthesis` was looked through, and `coalesce` was never classified, so a Boolean rule kept the default hidden `string` item. |
| 1 | `_cql_boolean_operand` | Decided `ToBoolean(…)` from that item type, also when the operand is the node's own `Calc_` define — a Boolean. CQL has no `ToBoolean(Boolean)`. |
| 1, 3 | `xpath_to_cql` / `cql_to_operation` | `zscore(…)` becomes the CQL call `Zscore(…)`; `FUNCTION_MAP` knows `ZScore`, so it stays a `native` operation. FHIR typing does not see a number (item `string`, CQL `ValueAsString(…) < -3`) and the native passthrough emits the quoted name `'Zscore'`. |
| 4 | `_wrap_operand_if_needed` | A list of references is wrapped one element at a time with `str.replace`; the same reference twice wraps the already wrapped text again. |
| 5 | `tricc_operation_fhirpath_is*` | `X = false` / `X != true` are empty when `X` has no answer, and one empty operand blanks an `and`. CQL's `is false` is false for null; `is not true` is true for null. |

---

## Part II — Fix (`tricc_oo/strategies/output/fhir_form.py`)

* `_unwrap_operation` also looks through a single-operand `get_inherited_value` (it is only
  used for type checks).
* `coalesce` is Boolean when one operand is Boolean and none is known to be another type
  (`_coalesce_returns_boolean`, `_operand_boolean_kind`): the self fallback, a populate or a
  hidden text calculate has no type of its own and does not decide.
* `_cql_boolean_operand` passes a `Calc_` define through when the node computes a Boolean.
* `native` `zscore` / `izscore` count as `decimal` for typing, and the native passthrough
  raises `NotImplementedError` for them like `ZSCORE` does (no `'Zscore'` text; the
  calculate gets no expression until z-scores are implemented in FHIR). The parser is left
  alone: XLSForm CDSS implements `ZSCORE`, and mapping `Zscore` there would change that
  output too.
* `_wrap_operand_if_needed` wraps only occurrences not already followed by
  `.where($this.exists())`.
* FHIRPath `is true` / `is false` / `is not true` / `is not false` are
  `X.where($this = true|false).exists()|empty()`, with `X` parenthesised by `_fhirpath_atom`
  when needed.

### Not changed

* Equality with a Boolean literal (`EQUAL(x, false)`, e.g. the TT vitamin A items) still
  emits `… = false` (27 in the global package, from 118).
* Z-scores are still not computed in FHIR output (`tricc_operation_zscore`).

---

## Part III — Verification

* `tests/test_strategies/test_fhir_cql_types.py` — 11 tests; 8 fail on `develop`.
* Expectations of `tests/test_operation_expression.py` (`istrue`, `isfalse`, `isnottrue`,
  `if_`) and `tests/test_strategies/test_fhir_relevance_fhirpath.py` updated to the null-safe
  form. Full suite: 890 passed, 138 skipped.
* Global child package regenerated: no `ToBoolean(Calc_…)`, no `ValueAsString(W…) <`, no
  double `.value`; `WFA`/`WFH`/`WFL` `decimal`, `CHE_B27_G_DE04` `boolean`. Loaded on HAPI 8.12:
  all 7 libraries translate; *Diagnostic Testing* `$populate` pre-fills (e.g.
  `CHE_B24_G_DE03 = 48` recorded earlier in the encounter) and opens in
  kotlin-fhir-data-capture.
