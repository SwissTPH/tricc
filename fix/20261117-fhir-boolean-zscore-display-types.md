# FHIR output: a library that does not compile, a Boolean on a string item, `'Zscore'` as a value

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `develop` |
| **Scope** | `tricc_oo` FHIR output, project CQL libraries |
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
* `_cql_boolean_operand` decides from the operand node (`original_references`), not from
  the CQL text: a node with its own define in the current library (`_calc_define_name`) is
  read through that define by `_cql_node_reference`, so it passes through when the node
  computes a Boolean.
* A `native` call is typed from the project. A tricc.yaml `libraries` file declares
  functions in CQL, with CQL documentation tags in the `/* */` comment just before them:

  ```cql
  /*
  @description: Weight-for-age z-score from the WHO tables
  @retrieve: false
  */
  define function Zscore(chart String, sex String, value Decimal) returns FHIR.decimal: external
  ```

  `cql_library.parse_cql_library_functions` reads each into a `FunctionSignature`
  (`return_type` as a FHIR data type, from a FHIR type or its CQL System name; `arguments`
  as `(name, type as written)`; `tags` as written; `external`) in
  `TriccIntervention.function_signatures`. `external` (CQL: implemented elsewhere) is a
  declaration only and is never written into a generated library; a function with a body
  (real CQL to copy into the generated library) is rejected for now. `@retrieve: true`
  (`FunctionSignature.retrieve`) marks a value read from recorded data, never a constant;
  the default `false` means it depends only on its arguments (for the constant evaluator,
  #86). `native_function_type` looks a name up there (case-insensitive), then in
  `BUILTIN_FUNCTION_TYPES` (`zscore` / `izscore`: `decimal`, since `xpath_to_cql` writes
  them). The native passthrough raises `NotImplementedError` for `zscore` /
  `izscore` like `ZSCORE` does (no `'Zscore'` text; the calculate gets no expression until
  z-scores are implemented in FHIR). The operator is left `native`: XLSForm CDSS implements
  `ZSCORE`, and mapping `Zscore` there would change that output too.
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

* `tests/test_strategies/test_fhir_cql_types.py` — 16 tests; 8 fail on `develop`. Also
  covered: a node with no define in the library still gets `ToBoolean`; an undeclared
  native is untyped; a project declaration types it (and overrides the built-in).
* `tests/test_project_terminology_libraries.py` — function signatures: FHIR types,
  arguments, tags (`@retrieve`, multi-line values), not calculates; errors (no `returns`,
  unsupported type, a body, declared twice, `@retrieve` not true/false).
* Expectations of `tests/test_operation_expression.py` (`istrue`, `isfalse`, `isnottrue`,
  `if_`) and `tests/test_strategies/test_fhir_relevance_fhirpath.py` updated to the null-safe
  form. Full suite: 915 passed, 138 skipped.
* Global child package regenerated: no `ToBoolean(Calc_…)`, no `ValueAsString(W…) <`, no
  double `.value`; `WFA`/`WFH`/`WFL` `decimal`, `CHE_B27_G_DE04` `boolean`. Loaded on HAPI 8.12:
  all 7 libraries translate; *Diagnostic Testing* `$populate` pre-fills (e.g.
  `CHE_B24_G_DE03 = 48` recorded earlier in the encounter) and opens in
  kotlin-fhir-data-capture.

---

## Decisions

- 2026-11-19: whether an operand is read through its node's define is decided from the node
  (`original_references`), never from the CQL text (PR #84 review, @delcroip).
- 2026-11-19: native function types are declared once per project, not per call, as CQL
  functions in a tricc.yaml library, typed with FHIR data types (PR #84 review, @delcroip).
- 2026-11-19: extra data about a function goes in CQL documentation tags (`@retrieve: true`
  for a value read from recorded data); `external` marks a declaration that is not CQL to
  write out, a body marks real CQL (supported later). Shared with #86 (@delcroip).
