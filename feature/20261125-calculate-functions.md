# Calculate functions with parameter fallbacks (supersedes #54)

| Field             | Value |
| ----------------- | ----- |
| **Status**        | Implemented (2026-11-25, phases 1–2; phase 3 is the frontend mirror) |
| **Branch target** | `feature/calculate-functions` → `develop` |
| **Scope**         | `converters/cql_library`, `converters/decision_table`, `converters/retrieval`, `visitors/tricc` (`load_calculate`, `is_ready_to_process`, `process_reference`, `process_operation_reference`, `get_version_inheritance`), `strategies/input/base_input_strategy`, `YamlStrategy`, `DrawioStrategy`, `FHIRStrategy` → `OpenSRPStrategy`, `XLSFormStrategy` → `XLSFormCDSSStrategy` → `XLSFormCHTStrategy` → `XLSFormCHTHFStrategy` |
| **Related** | Supersedes #54 (Calculate Registry). `feature/20261123-decision-tables.md` and `feature/20261123-dmn-named-overrides.md` (same call binding; DMN inputs gain the same fallbacks; `E_DMN_ARG_*` / `E_DMN_ARITY` renamed). `feature/20261109-project-retrievals.md` (retrievals as a fallback). #104 (requires and implied retrievals: a required concept becomes an ordinary version, so step 1 of §2.3 finds it). #102 (output capability statements: `E_FUNCTION_NOT_EXPORTABLE` moves there). #103 (`system."code"` references, for `fallback`). #98 (function catalogue). Frontend mirror (parameter fallbacks in the dictionary editor, call chip, data needs view, renamed `E_CALL_*` codes in `validate/tables.ts`): SwissTPH/tricc-frontend, to open. |
| **RFC**           | SwissTPH/tricc#101 |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

### The problem

Protocols often compute the same value in several places as the visit goes on. `is_adult` is
first worked out from the age in triage, then from a "declared adult" answer in registration.
Today each drawing of the calculate becomes a version that depends on the previous one. When
several versions wait for each other, the build can loop and stop. Authors also cannot see
what a calculate depends on, or which values will be read from records instead of asked.

Decision tables (DMN) already solve part of this: a table is called with its inputs, and an
input that is not passed is taken from its concept. Calculates need the same thing for a
formula.

### What changes for an author

- A calculation can be written once as a **function**, with named parameters:
  `IsAdult(age, declared)`. Every place that needs it calls it: `is_adult = IsAdult(age_estimated)`
  in triage, `is_adult = IsAdult(Tuple{ declared: declared })` in registration.
- A function is described in the calculate dictionary (its parameters and where their values
  come from) and its formula may be written there or in a CQL library. The two are linked: the
  dictionary entry and the library function are the same function.
- A call can pass a value, pass `null`, or leave a parameter out:
  - a value is used, and the form waits until that value is available;
  - `null` means "no value": nothing is looked up for it;
  - a parameter left out takes, in order: the latest value of its **fallback concept**; else
    what an **earlier call** of the same function passed for it; else a **retrieval** listed on
    the parameter; else no value.
- The value of a left-out parameter is chosen where the calculate is used. A calculate drawn on
  its own (no arrow into it) is worked out at the first place that reads it; if nothing reads it,
  at the end, and only when its value is saved to the record. To get a new value later with other
  inputs, draw the calculate again (a new version), as today.
- In the second call above, `age` is left out. If the form has no `age`, it comes from the first
  call (`age_estimated`). The two versions of `is_adult` no longer wait for each other.
- Each parameter (of a function or of a decision table input) can list its fallback concept
  and the retrievals allowed for it. There is no default retrieval.
- In expression fields, a function or table call shows as a chip, like a concept. Opening it
  shows the parameters and where each value comes from.
- A data needs view lists, per intervention, every call and where each argument came from.
- A function may share its name with a calculate; the build warns.

### Out of scope

- Prerequisites from earlier in the encounter (`requires`) and implied retrievals: #104.
- A default retrieval per concept (dropped: it could not be blocked cleanly).
- Migrating existing drawn calculates into functions.
- Functions that call other functions recursively.
- Checking before export that an output can write a function body (#102).

---

## Part II — Technical specification

### 1. Functions

- **Dictionary.** A function is a calculate-dictionary concept (`calculate_code_system`) with
  parameters as an extension list (`name`, `type`, `fallback` Coding, `retrievals` `#code` list)
  and, optionally, a body as a FHIR `Expression` extension (`text/cql`). URLs:
  `http://tricc.org/fhir/StructureDefinition/function-parameter` (one per parameter, sub-extensions
  `name`, `type`, `fallback` (valueCoding), `retrieval` (valueCode, repeated)) and
  `.../function-body` (valueExpression); the concept's `dataType` is the return type. A decision
  table input lists its retrievals as `retrievals: ["#code", …]` next to `concept`.
- **Library.** tricc.yaml `libraries` may define it (`define function F(p Type, …) returns T:
  <body>`); `cql_library._function_signature` stops rejecting a body. Parameter tags, one per
  parameter, the name after a dot: `@param.age: fallback=age_years retrievals=#age_years`
  (`_TAG` already accepts the dot; `_parse_tags` lowercases tag names, so the parameter name
  matches case-insensitively).
- **Link.** A library function and a dictionary concept with the same code are **one** function:
  `FunctionSignature` is merged (parameters and their fallbacks from either, the body from the
  one that has it). Both with a body: `E_FUNCTION_TWICE`. Parameter lists that differ (names,
  order or types): `E_FUNCTION_SIGNATURE_MISMATCH`. Parameter metadata given on both sides
  must agree, else the same error. The data needs report and the frontend show the link.
- **Model.** `FunctionSignature` gains `body: TriccOperation | None`, `params:
  List[FunctionParam]` (`name`, `type`, `fallback`, `retrievals`) and `sources` (dictionary
  and/or library). Functions go to `project.function_signatures`.
- **Names.** A function and a calculate or define with the same name: `W_FUNCTION_NAME_SHARED`;
  a call is always `F(…)`, so they never clash.

### 2. Binding a call (functions and DMN)

**2.1 Arguments.** Positional arguments, then a trailing `Tuple{…}` by name. `_split_named` /
`_bind` move from `converters/decision_table.py` to a shared `converters/call_binding.py`. The
binding errors are renamed for both: `E_CALL_ARG_UNKNOWN`, `E_CALL_ARG_TWICE`, `E_CALL_ARITY`
(were `E_DMN_ARG_UNKNOWN`, `E_DMN_ARG_TWICE`, `E_DMN_ARITY`; `E_DMN_TABLE_*` keep their names).

**2.2 Two stages, as for references.** A calculate's references are checked for presence first
(`load_calculate` → `process_reference(replace_reference=False)`), then replaced by node
instances (`replace_reference=True`). Calls follow the same stages:

- **Load (checks only).** `expand_project_tables` and the `expand_node_tables` call in
  `load_calculate` stop expanding: they check the call (known table or function, static table
  argument, arity, names) and leave it a call operation.
- **Presence (walk).** A call's `get_references()` returns its **passed** arguments only; they
  alone block the walk. A left-out or `null` parameter creates no reference.
- **Instantiation.** When the holding node's references are replaced, each left-out parameter is
  bound (2.3), the call is expanded or kept per strategy (§3), and references are replaced.

**2.3 A left-out parameter** takes the first of these that gives a value, at instantiation:

1. **Fallback concept** (`fallback`; DMN: the column `concept`):
   `get_last_version(concept, processed_nodes)`;
2. **Earlier call**: the argument of the same parameter in the latest earlier call of the
   **same function** (DMN: same table and output). The **original expression** is carried over,
   as written (references by name, not the instances it was bound to), and instantiated again
   here: a bare concept, an expression or a constant all carry over, and a concept collected
   again between the two calls gives its newer version;
3. **Retrieval**: the first `#code` in the parameter's `retrievals`. Its `TriccNodeRetrieval` is
   built on demand (`build_used_retrievals` gains `add(code)`, extending `project.retrievals` /
   `project.retrieval_nodes` and hanging the node on the start page). A retrieval reads a static
   record, so it needs no place in the walk; the exports run after the walks and see it;
4. **No value**: `_NULL`, `W_PARAM_NO_VALUE`.

An explicit `null` is no value (`_NULL`, RFC #96); no step is tried.

**2.4 Calculated arguments are sub-calculates.** A passed argument that is an operation
(`IsAdult(age_months / 12)`), or a carried-over one, becomes a **sub-calculate** owned by the
call: it is not stashed or walked on its own. `is_ready_to_process` and `process_reference` of
the holding node run it with the call: its references block as passed arguments, and it is
instantiated when the call is. Each output decides how to write it (§3): its own row (XLSForm
calculate, FHIR item or variable) or injected into the call. Injection repeats the expression
wherever the call is expanded, so a sub-calculate used more than once gets its own row.

**2.5 Free-standing calculates.** A calculate with no `prev_nodes` (drawn without an arrow, or a
library calculate) whose expression holds a call is checked for presence as today but not
instantiated at the end of `load_calculate`. The first node whose instantiation resolves a
reference to it instantiates it, against that node's `processed_nodes`, once. If nothing reads
it: at the end of the walk of its start page, only when it is saved to the record (a persisted
concept); otherwise it is dropped with a debug log.

**2.6 Carry-over state.** `CallArguments`: `{function: {param: original expression}}`, created
once per project in `BaseInputStrategy.link_project` and passed to every `process_pages` through
`stashed_node_func`, like `decision_tables`. Start pages are walked in order; a call in an
earlier walk counts as an earlier call. Updated after each instantiation for parameters bound
by passing or by carry-over; `null`, the fallback concept, a retrieval and no value leave it.

**Change for DMN:** a left-out input no longer becomes `TriccReference(column.concept)` and no
longer blocks; it is bound by 2.3 and can be `null`. Authors who want to wait pass the concept.

### 3. Export

| Strategy | A function call | A sub-calculate |
| -------- | --------------- | --------------- |
| FHIR / OpenSRP | As for a calculate (and DMN): any bound argument an item of the current Questionnaire → `calculatedExpression` (FHIRPath), body expanded inline; else `initialExpression` (CQL) calling a `define function` written once in the Helper library | injected; own item when used more than once |
| XLSForm / CDSS | Body expanded inline with the arguments substituted, like `_expansion` for DMN | injected; own `calculate` row when used more than once |
| CHT | Inline; with `decision_table_calls` on, a function in the `dmn-<project>.js` extension library | as XLSForm |

A body an output cannot write fails at export with `E_FUNCTION_NOT_EXPORTABLE` (function,
strategy, operator); #102 moves the check before the build. A pure function (`@retrieve: false`)
called with constants folds to a constant (`feature/20261119-python-constant-eval.md`).

**Version inheritance.** `get_version_inheritance` leaves out of `all_prev_versions` a previous
version whose expression calls the **same function** (DMN: same table and output) as the current
one: the later call carries the arguments over, so no `GET_INHERITED_VALUE` is built between
them. Every other previous version is merged as today.

### 4. Data needs report

Each build that binds at least one call writes `<form>.data-needs.json` next to the output: per call, the function or table
(and whether it comes from the dictionary, a library or both), the calculate it belongs to, the
node where it was instantiated, and per parameter the step that bound it (`passed`, `null`,
`form`, `earlier_call`, `retrieval`, `none`) with the concept or `#code`. The frontend data needs
view and call chip read it (mirror spec).

### 5. Validation and errors

- `E_FUNCTION_TWICE`, `E_FUNCTION_SIGNATURE_MISMATCH`, `E_FUNCTION_UNKNOWN`,
  `E_CALL_ARG_UNKNOWN`, `E_CALL_ARG_TWICE`, `E_CALL_ARITY` (functions and DMN).
- `E_PARAM_FALLBACK_UNKNOWN`, `E_PARAM_RETRIEVAL_UNKNOWN`, `E_PARAM_TAG_UNKNOWN`.
- `E_FUNCTION_NOT_EXPORTABLE` (§3).
- `W_FUNCTION_NAME_SHARED`; `W_PARAM_NO_VALUE` when step 4 of 2.3 binds a parameter.

Tests, `docs/tricc-elements.md` and the two DMN specs move to the `E_CALL_*` codes.

### 6. Tests

YAML fixtures in `tests/data/yaml/` (activities) with the tables, libraries and dictionaries of
`tests/data/projects/calculate_functions/`, and `tests/test_calculate_functions.py`:

- binding: passed; `null` with an earlier call; left out with the fallback collected, from an
  earlier call, from a listed retrieval, nothing; the fallback wins over an earlier call;
- carry-over: a bare concept re-resolves to its newer version; an expression and a constant
  carry over; across two start pages in walk order;
- only passed arguments block; a call before its fallback is collected gets `null`;
- sub-calculates: blocked and instantiated with the call; injected once; own row when used twice;
- free-standing: bound at the first reader; unread and saved → bound at the end; unread and not
  saved → dropped;
- a retrieval listed only on a parameter is built and exported;
- link: dictionary parameters + library body merge; two bodies fail; mismatched parameters fail;
  `@param.age` parsed, unknown parameter fails;
- inheritance: no `GET_INHERITED_VALUE` between two versions calling the same function; other
  versions still inherit;
- the `is_adult` two-activity case builds without `check_stashed_loop` (the #54 regression);
- DMN: a left-out input no longer blocks; the decision-table vectors pass with `E_CALL_*`;
- export per strategy (FHIR / OpenSRP inline and Helper, XLSForm, CHT,
  `E_FUNCTION_NOT_EXPORTABLE`); the data needs report.

### 7. Phases

1. Shared binding (`call_binding.py`, `E_CALL_*`), the two stages for DMN, fallback steps,
   free-standing calculates, data needs report.
2. Function definitions and link, sub-calculates, version inheritance, export per strategy.
3. Frontend mirror.

---

## Open questions

None.

## Decisions

- 2026-11-24: Supersedes #54: functions with bound arguments replace the cumulative merge,
  detangle and materialization of the Calculate Registry. (@delcroip)
- 2026-11-24: A function sharing a name with a calculate or define is a warning; a call is
  always written with `()`. (@delcroip)
- 2026-11-24: No default retrieval; only the retrievals listed on a parameter are used.
  (@delcroip)
- 2026-11-24: An explicit `null` is no value, with no fallback. A left-out parameter falls back:
  fallback concept, earlier call's argument (same function), listed retrieval. (@delcroip)
- 2026-11-24: Parameter fallbacks and retrievals apply to functions and DMN inputs alike.
  (@delcroip)
- 2026-11-24: FHIR / OpenSRP follow the current calculate rule: FHIRPath (inline body) when any
  argument is in the current Questionnaire, CQL (Helper function) otherwise. (@delcroip)
- 2026-11-24: Calls follow the reference stages: presence checked in the walk (passed arguments
  only), fallbacks bound at instantiation. DMN calls are no longer expanded before the walk.
  (@delcroip)
- 2026-11-24: Calculated arguments are sub-calculates run with the call; the output decides
  between its own row and injection. (@delcroip)
- 2026-11-24: A free-standing calculate is instantiated at its first point of use; if unread, at
  the end of the walk only when saved to the record. (@delcroip)
- 2026-11-24: Carry-over copies the original expression, not its instances; shared across start
  pages in walk order. (@delcroip)
- 2026-11-24: `GET_INHERITED_VALUE` is dropped only between two versions calling the same
  function. (@delcroip)
- 2026-11-24: Functions live in the dictionary and in libraries, linked as one function.
  Parameter tags are `@param.<name>:`. (@delcroip)
- 2026-11-24: A listed retrieval is built when a call binds it. (@delcroip)
- 2026-11-24: Prerequisites (`requires`) move to #104. (@delcroip)
- 2026-11-25: Approved for implementation (phases 1–2; phase 3 is the frontend mirror). (@delcroip)
- 2026-11-25: Phases 1–2 implemented on `feature/calculate-functions`; phase 3 (frontend mirror)
  remains in SwissTPH/tricc-frontend.
