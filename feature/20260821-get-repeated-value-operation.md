# `GetRepeatedValue` as a TRICC Operation (XLSForm support)

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `develop` |
| **Related** | `feature/concept-repeat.md` (repeat slots), `feature/20260825-get-repeated-value-latest.md` (optional slot = latest this consultation), `feature/advanced-merge-calc.md` + `fix/20260820-opensrp-inherited-value.md` (multi-version merge), `feature/populate-context.md` + `fix/20260821-merge-input-into-populate.md` (populate contexts / CHT contact-summary channel — see §3.5) |
| **Authoring surface** | Calculate / relevance expressions in draw.io and YAML fixtures |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business Description

*Audience: clinical authors, guideline developers, implementers evaluating TRICC workflows.*

## 1. Overview

Concept Repeat (see `feature/concept-repeat.md`) lets an author capture the **same concept several
times in one encounter** — temperature at triage and again after treatment — using one concept code
and a `repeat` number per capture slot.

What has been missing is a way for an **expression** to say *which slot it means*. Writing
`temperature` in a calculate means "the temperature concept", and TRICC picks whichever slot is in
scope. There is no author-facing way to write "the temperature from slot 2".

This feature makes **`GetRepeatedValue(<concept>, <slot>)`** a first-class TRICC expression function,
usable in any calculate or relevance expression, and supported by the **XLSForm / ODK** output
(and by CHT, which builds on it).

## 2. The problem today

Authors already write `GetRepeatedValue("weight", 2)` in diagrams — the name exists in the
OpenSRP/FHIR export guide (`docs/open-srp-export.md`) and in the repeat feature spec, so it looks
like a supported function. On the XLSForm path it is **not** recognised. Two things go wrong:

1. **The slot argument is ignored.** The concept reference is resolved as if the author had written
   plain `weight`, so the expression silently merges **every** slot of the concept (slot 1 *and*
   slot 2) instead of reading the requested one.
2. **The function text is copied straight into the form.** The generated ODK calculation literally
   contains `GetRepeatedValue(...)`, which ODK cannot evaluate. The form fails validation with:

   ```text
   XPath evaluation: cannot handle function 'GetRepeatedValue'
   Result: Invalid
   ```

The second failure is loud, so the whole form is rejected. The first is silent and clinically
worse: a "weight after treatment" calculation quietly falls back to the triage weight.

## 3. What changes for authors

### 3.1 The function

```text
GetRepeatedValue("<concept name>", <slot>)
```

| Part | Meaning |
|------|---------|
| `<concept name>` | The concept `name` used on the capture nodes (same name in every slot) |
| `<slot>` | The `repeat` value of the capture you want (`1`, `2`, …) |

Example:

```text
integer  name=weight  repeat=1    "Weight at triage"
integer  name=weight  repeat=2    "Weight after treatment"

calculate  name=weight_delta
  GetRepeatedValue("weight", 2) - GetRepeatedValue("weight", 1)
```

Each term now reads its own slot. In the exported ODK form these become the two distinct fields
(`${weight}` and `${weight_Rr_2}`), and the form validates.

### 3.2 How it behaves — "inherited value, but one slot only"

A plain concept reference in an expression already merges **all versions** of that concept — if the
same question is asked on several branches, the expression uses whichever branch was actually
filled (multi-version merge, exported as `coalesce(...)` in ODK).

`GetRepeatedValue` keeps exactly that behaviour, but **restricted to the requested slot**:

| Author writes | Versions considered |
|---------------|---------------------|
| `weight` | all reachable versions of `weight`, any slot |
| `GetRepeatedValue("weight", 2)` | only reachable versions of `weight` whose `repeat` is `2` |

"Reachable" means the same thing as for a normal reference: captures that come **before** this point
in the flow. Slots captured later, or on unrelated branches, are not used.

So if slot 2 of `weight` is asked on two different branches, `GetRepeatedValue("weight", 2)` still
picks whichever of those two was filled — it just never falls back to slot 1.

### 3.3 What it is not

- **Not a history look-up.** `GetRepeatedValue` addresses slots captured *in this form*. For
  values from previous visits use populate `context=history` (`feature/populate-context.md`); see
  §3.5 for how the history accessors relate to this feature.
- **Not a way to reference a slot that is never captured.** If no capture node for that
  `(concept, slot)` exists earlier in the flow, the reference cannot be resolved — the author gets
  an error, not a silent fallback to another slot.
- **No new capture.** It only reads; it does not create a question or a slot.
- **Slot `-1` (local-only) stays local.** `GetRepeatedValue("x", -1)` addresses that one local node
  and never merges it with the encounter-wide slots — same rule as today.

### 3.4 Scope of this change

| Output | Behaviour after this change |
|--------|-----------------------------|
| **XLSForm / ODK** (`XLSFormStrategy`, `XLSFormCDSSStrategy`) | Supported — emits the slot's field reference (with `coalesce` across versions of that slot) |
| **CHT** (`XLSFormCHTStrategy`, `…CHTHFStrategy`) | Supported (inherits the XLSForm behaviour) |
| **FHIR / OpenSRP** | Recognised, no longer emits junk: rendered like a normal slot-scoped reference (FHIRPath in-form, Helper CQL out-of-form). Richer CQL routing is a follow-up, listed in §14. |
| **OpenMRS / DHIS2 / HTML** | Unchanged (these strategies do not implement the value-merge family today) |

### 3.5 Sibling functions — out of scope here, but *not* FHIR-only

**`GetHistoryValue`** (and its resource-specific forms `GetHistoryObservationValue` /
`GetHistoryConditionValue`) **do** have a CHT interpretation. A populate node with
`context=history` is already served in CHT from the **contact summary**
(`instance('contact-summary')/context/<concept>`), which is CHT's channel for anything derived from
previous reports. So an author writing `GetHistoryValue("weight", "P1Y")` in an expression is
expressible on the CHT path — the function just has to be **desugared into a generated populate
node** and then referenced like any other field (see §8 for the mechanism).

That desugaring is a different mechanism from the one this spec implements, and it needs its own
design (naming and deduplication of generated nodes, where they are injected, what plain
XLSForm — which has no contact summary — does with them). It is therefore **out of scope here** and
proposed as a follow-up in §14.

| Function | Status after this change |
|----------|--------------------------|
| `GetRepeatedValue` | **In scope** — resolves to an in-form slot; no generated populate needed |
| `GetHistoryValue` / `GetHistory<Resource>Value` | Out of scope; CHT-expressible via generated populate (§14) |
| `GetRepeated` (resource, not value) | Out of scope — no scalar value to place in a form field |
| `GetNumberOfRepeat` | Out of scope — needs a counting strategy per output |

The distinction that matters: **`GetRepeatedValue` reads data captured inside this form**, so
resolution finds a real node and no external data channel is involved. The history accessors read
data from **outside** the form, which is exactly what populate nodes exist for.

## 4. Benefits

- **Says what it means.** Slot-specific logic ("did the fever come down?") is expressible directly.
- **No silent wrong value.** The slot argument stops being ignored.
- **Valid forms.** No more `cannot handle function 'GetRepeatedValue'` on ODK validation.
- **Same mental model.** Behaves like a plain concept reference, narrowed to one slot.

## 5. Limitations

| Topic | Decision |
|-------|----------|
| Slot argument must be a literal integer | An expression as the slot (`GetRepeatedValue("weight", n)`) is not supported — slot selection happens while the graph is built, before any answer exists |
| Missing slot | Authoring error: unresolved reference, reported like any other unknown reference |
| Omitted slot argument | Latest capture so far, any slot — see `feature/20260825-get-repeated-value-latest.md` |
| Slots captured outside this form | Not read by this feature. CHT and FHIR both *have* a channel for out-of-form data (contact summary / task inputs, and Helper CQL), but reaching it needs the generated-populate route in §3.5 / §14 — not part of this change |

---

# Part II — Technical Specification

*Audience: TRICC developers and contributors.*

## 6. Root cause of the reported failure

`TriccOperator.GET_REPEATED_VALUE` **already exists** (`tricc_oo/models/base.py`) and
`process_operation_reference` **already** has a branch that scopes reference resolution to
`operation.reference[1]` for it (`tricc_oo/visitors/tricc.py`). Two links are missing:

1. **The parser never produces the operator.** `FUNCTION_MAP` in
   `tricc_oo/converters/cql_to_operation.py` has no `GetRepeatedValue` entry, so the author's text
   falls through to `TriccOperator.NATIVE` with `reference = ["GetRepeatedValue", <ref>, <slot>]`.
   Consequences:
   - the repeat-scoping branch in `process_operation_reference` never runs → `ref_repeat` stays
     `None` → the reference resolves across all slots and (for value fields) is wrapped in
     `GET_INHERITED_VALUE` over **every** slot;
   - `XLSFormStrategy.tricc_operation_native` re-emits the function name verbatim → the ODK error.

   Reproduced on a two-slot fixture, the calculate expression comes out as:

   ```text
   minus(
     native('GetRepeatedValue', get_inherited_value(weight@repeat2, weight@repeat1), static(2)),
     native('GetRepeatedValue', get_inherited_value(weight@repeat2, weight@repeat1), static(1))
   )
   ```

   Both terms are identical — the slot argument is inert.

2. **No output strategy implements the operator.** Dispatch is
   `getattr(self, f"tricc_operation_{operation.operator}")`; there is no
   `tricc_operation_*repeated_value` anywhere, so even with the parser fixed, XLSForm would raise
   `NotImplementedError`.

Additionally two defects in the existing code path must be fixed for the operator to work at all:

- **Enum value typo.** `GET_REPEATED_VALUE = "ge_repeated_value"` — since the dispatch method name
  is derived from the enum *value* (`StrEnum`), the handler would have to be named
  `tricc_operation_ge_repeated_value`. Fix the value to `"get_repeated_value"`.
- **`int(operation.reference[1])` raises.** The slot literal is a `TriccStatic`, and
  `int(TriccStatic(2))` is a `TypeError` (verified). It needs a tolerant extractor.

## 7. Formal semantics

`GET_REPEATED_VALUE` is a **resolution-time slot selector**, not a runtime function.

```text
GET_REPEATED_VALUE( <concept reference>, <slot literal> )
   reference[0] = the value operand      (what gets read)
   reference[1] = the repeat slot        (consumed while resolving reference[0])
```

1. **Resolution (visitor).** While processing the operation's references,
   `ref_repeat = <slot literal>` scopes candidate lookup exactly as it does today for
   `GET_HISTORY_VALUE` (`ref_repeat = 0`): `candidates_in_activity` filters on
   `get_repeat(n) == ref_repeat`, and `get_last_version` / `get_versions` are called with
   `repeat=ref_repeat`.
2. **Merge.** For value fields (`inherit_display_versions=True`) the operand becomes
   `GET_INHERITED_VALUE(v_newest … v_oldest)` over the versions **of that slot only**; with a single
   version it is that node. For non-value fields (relevance et al.) it stays the single last version
   of that slot. This is unchanged machinery — only `repeat` is now pinned.
3. **Rendering (strategy).** Because the slot is already baked into the resolved operand (its export
   name / `linkId` carries `_Rr_<n>` for `n > 1`), every strategy renders the operation as **its
   value operand** — i.e. `GET_REPEATED_VALUE` is transparent at serialisation time.

   Therefore: `render(GET_REPEATED_VALUE(x, n)) == render(x)`.

   The wrapper is kept (rather than collapsed in the visitor) so that strategies with an
   out-of-form data source — FHIR's `Helper.GetRepeatedValue(code, n)` — can still see the requested
   slot. `RETURNS_CONCEPT` / `get_datatype()` already read `reference[0]`, so datatype inference is
   correct with this operand order.

### 7.1 Slot literal rules

| Input | Behaviour |
|-------|-----------|
| `TriccStatic(int)` / `TriccStatic("2")` / `int` / numeric `str` | used as the slot |
| absent (single-argument call) | `None` (any slot / latest) — see `feature/20260825-get-repeated-value-latest.md` |
| non-numeric / an expression | `logger.warning`, slot ignored (`ref_repeat = None`) → behaves like a plain reference; do not crash |

### 7.2 Unresolvable slot

If no node matches `(name, slot)`, `process_operation_reference` returns `False` (deferred) and the
name lands in `still_unresolved` — the existing unresolved-reference path (debug log, and
`logger.critical` when codesystems are supplied). No new error channel; but the deferral message
should name the slot so the author can see *why* it failed.

## 8. In-form resolution vs. the generated-populate channel

This spec deliberately lowers `GET_REPEATED_VALUE` **without** touching any external data channel,
because the slot it names is captured inside the form. It is worth writing down why, since the
sibling history accessors (§3.5) need the opposite treatment — and the boundary is the thing that
keeps this change small.

### 8.1 The two channels that already exist

| Channel | Who provides the value | XLSForm/CHT serialisation |
|---------|------------------------|---------------------------|
| **In-form field** | a capture node earlier in the flow | `${<export name>}` (with `_Rr_<n>` for slot > 1) |
| **Generated / authored populate node** | outside the form | CHT: `../inputs/contact/<field>` for `context=encounter`, or `coalesce(instance('contact-summary')/context/<concept>,'')` for every other context (`populate_uses_inputs_group`, `get_cht_contact_summary_expression`); FHIR: the `Helper.Get*Value` accessor from `resolve_populate_reference` |

`GET_REPEATED_VALUE` targets the **first** channel: reference resolution finds the capture node for
`(name, slot)`, and the operand renders as that node's field. Nothing new is required.

### 8.2 Why the history accessors need the second channel

`GetHistoryValue` has no in-form node to resolve to — the value comes from previous reports. On the
CHT path that is not a dead end: `context=history` populate nodes are already exported as a
calculate reading `instance('contact-summary')/context/<concept>`
(`populate_helper.get_cht_contact_summary_expression`, wired in `XLSFormCHTStrategy.get_input_df`
via `get_populate_calc_line`). The missing piece is purely the **desugaring**: an expression-level
`GetHistoryValue("weight", "P1Y")` would have to materialise a `TriccNodePopulate(name="weight",
context="history", period="P1Y")`, inject it into the graph so `export_inputs` picks it up, and
replace the operation with a reference to it.

That is a real mechanism with real design questions — deduplicating generated nodes across
expressions, naming them so they do not collide with authored populate nodes or with capture nodes
of the same concept, deciding what plain `XLSFormStrategy` (no contact summary) emits — and it is
specified separately (§14). Nothing in this change blocks it; the operand-transparent rendering rule
in §7 (rule 3) applies unchanged whether the operand is a capture node or a generated populate node.

### 8.3 Where this leaves an unresolvable slot

§7.2 makes `GetRepeatedValue("weight", 7)` with no slot-7 capture an authoring error. Once the
generated-populate channel exists, there is a defensible alternative: fall back to a generated
`TriccNodePopulate(name="weight", context="encounter", repeat=7)`, which CHT serves from the
`inputs` group and FHIR from `GetEncounterObservationValue(code, 7, …)` →
`Helper.GetRepeatedValue(code, 7)`. That would also remove the hard-coded slot 1 at
`fhir_form.py:1088`.

**Decision for this spec: keep it an error.** A silent switch from "read the field the author drew"
to "read the encounter record" is not something an author can see in the diagram, and the in-form
case is the one that is broken today. Revisit together with §14.

## 9. Code checklist

| File | Change |
|------|--------|
| `tricc_oo/models/base.py` | Fix `GET_REPEATED_VALUE` value typo `"ge_repeated_value"` → `"get_repeated_value"`. (No other code references the old string — verified by grep.) |
| `tricc_oo/converters/cql_to_operation.py` | `FUNCTION_MAP["GetRepeatedValue"] = TriccOperator.GET_REPEATED_VALUE` |
| `tricc_oo/visitors/tricc.py` | Add `get_repeat_index_arg(operation) -> Optional[int]` implementing §7.1 and use it instead of `int(operation.reference[1])`; add `resolve_slot_scoped_children()` and call it as step 0 of `process_operation_reference` (see §9.1 — required, not optional); hoist the slot to `op_repeat` and name it in the unresolved-reference message. |
| `tricc_oo/strategies/input/yaml.py` | Accept `form_id` on the `start` node (`YamlNode` field + `NODE_TYPE_MAP["start"]["attrs"]`) so a YAML fixture can drive a full `export()` + `validate()`. Needed for the end-to-end acceptance test; listed as a limitation in the original draft. |
| `tricc_oo/strategies/output/xls_form.py` | Add `tricc_operation_get_repeated_value(self, ref_expressions, original_references=None)` returning the value operand (`ref_expressions[0]`, or `""` when empty). Deliberately **not** delegating to `tricc_operation_get_inherited_value`, because `XLSFormCHTStrategy` overrides that to prepend `"."` (current-question value) — which is wrong for a cross-node slot read. CHT inherits this handler unchanged. |
| `tricc_oo/strategies/output/fhir_form.py` | Add `tricc_operation_get_repeated_value` and `tricc_operation_fhirpath_get_repeated_value`, both returning the value operand — prevents a new `NotImplementedError` on the FHIR path (today it silently emits the string `GetRepeatedValue`). |
| `docs/tricc-elements.md` | Document `GetRepeatedValue` in the expression-function reference: syntax, slot semantics, XLSForm/CHT support. State that `GetRepeated` / `GetNumberOfRepeat` / `GetHistoryValue` are **not yet usable in expressions on any output** — and specifically do *not* claim the history accessors are FHIR-only, since CHT can serve them from the contact summary once §14 lands. `docs/tricc-elements.md:129` currently lists them under repeat-aware Helper CQL, which reads as FHIR-only. |
| `feature/concept-repeat.md` | Add a "Related" pointer to this spec from §5.2 (the table that lists the repeat helpers) — it currently implies the helpers are FHIR-only. |

No changes needed in `tricc_to_xls_form.py`: `_concept_export_base_name` already appends `_Rr_<n>`
for `repeat > 1`, which is what makes rendering the operand sufficient.

### 9.1 Found during implementation — nesting made a pre-pass necessary

The draft assumed the existing repeat branch in `process_operation_reference` would start working
once the parser produced the operator. It does not, for a reason the reproduction exposed:
**`operation.get_references()` recurses into sub-operations, but the operator check only looks at the
top-level operator.** For `GetRepeatedValue("weight", 2) - GetRepeatedValue("weight", 1)` the
operation being processed is `MINUS`, so no slot was ever picked up. Worse, the flat resolution loop
replaces a name through `TriccOperation.replace_node`, which **rewrites every occurrence in the whole
tree** — so a single flat pass structurally cannot bind two occurrences of one concept to two
different slots.

Implemented as `resolve_slot_scoped_children()`, a pre-pass running before the flat loop: it walks
the working copy and, for each `GET_REPEATED_VALUE` child still holding an unresolved
`TriccReference`, calls `process_operation_reference` **on that child** — where the child *is* the
top-level operator, so its slot applies. The resolved child is spliced back by index, so no
`replace_node` cross-talk is possible. Anything the pre-pass leaves alone (bare references, other
operators) is handled by the flat loop exactly as before.

Notes:

- Deferral is reported through a `deferred` flag, never the walker's return value. Returning `False`
  for "nothing changed" is indistinguishable from `False` for "defer", which produced an infinite
  stash loop (`Stashed node list was unchanged: loop likely or unresolved dependence`) as soon as the
  tree was already resolved and a later pass found nothing to change.
- `GET_HISTORY_VALUE` has the same nesting flaw but is **not** in the pre-pass: it is unreachable
  from author text (absent from `FUNCTION_MAP`) and its `ref_repeat = 0` behaviour is tied to
  populate nodes. Changing it belongs with §14.1.
- The slot is hoisted out of the per-reference loop (`op_repeat`) so the unresolved-reference
  message can name it.

## 10. Tests

New fixture `tests/data/yaml/repeat_value_reference.yaml`: `start → weight(repeat=1) →
weight(repeat=2) → calculate weight_delta = GetRepeatedValue("weight", 2) - GetRepeatedValue("weight", 1)`.

New file `tests/test_get_repeated_value.py`:

| Test | Asserts |
|------|---------|
| `test_parser_maps_function_to_operator` | `parse_expression` on `GetRepeatedValue("weight", 2)` yields `TriccOperator.GET_REPEATED_VALUE` with `reference = [TriccReference("weight"), TriccStatic(2)]` — not `NATIVE` |
| `test_operand_scoped_to_requested_slot` | On the fixture, the slot-2 term resolves to the `repeat=2` node only; the slot-1 term to the `repeat=1` node only; neither is a `GET_INHERITED_VALUE` mixing both slots |
| `test_xlsform_renders_slot_field` | `XLSFormCDSSStrategy.get_tricc_operation_expression` returns `${weight_Rr_2} - ${weight}` (no literal `GetRepeatedValue`) |
| `test_xlsform_coalesces_versions_within_slot` | Two versions of `weight` at `repeat=2` (two branches) → `coalesce(${weight_Rr_2}, ${weight_Rr_2_Vv_…})`, and slot 1 never appears |
| `test_missing_slot_is_unresolved` | `GetRepeatedValue("weight", 7)` with no slot-7 capture → reference reported unresolved (no literal function text reaches the output) |
| `test_slot_argument_variants` | `_get_repeat_index_arg` handles `TriccStatic(2)`, `2`, `"2"`, missing (→ `1` + warning), non-numeric (→ `None` + warning, no raise) |
| `test_repeat_minus_one_stays_local` | `GetRepeatedValue("weight", -1)` resolves to the `repeat=-1` node and does not merge encounter slots |
| `test_cht_does_not_prepend_dot` | `XLSFormCHTStrategy` renders the slot field, not `coalesce(., …)` |

Regression guard on the reported symptom: assert the string `GetRepeatedValue` appears nowhere in
the generated survey/calculate frames for the fixture.

Existing suites that must stay green: `tests/test_concept_repeat.py`,
`tests/test_display_reference_inheritance.py`, `tests/test_fhir_repeat.py`,
`tests/test_dedup_initial_expression.py`, plus the full `python -m pytest tests/`.

## 11. Acceptance criteria

1. `GetRepeatedValue("<concept>", <n>)` in a draw.io / YAML expression produces
   `TriccOperator.GET_REPEATED_VALUE`.
2. Reference resolution honours `<n>`: only versions with `get_repeat() == n` are candidates.
3. XLSForm export contains no `GetRepeatedValue` text; ODK validation no longer reports
   `cannot handle function 'GetRepeatedValue'`.
4. Multi-version merge still applies **within** the slot (`coalesce`), never across slots.
5. FHIR export no longer emits the bare function name for this operator.
6. `python -m pytest tests/` passes; `flake8 tricc_oo` clean.

## 12. Implementation phases

1. **Operator plumbing** — enum typo fix, `FUNCTION_MAP` entry, `_get_repeat_index_arg`.
2. **XLSForm handler** + fixture + tests 1–5 above.
3. **FHIR crash-guard handlers** + CHT test.
4. **Docs** (`docs/tricc-elements.md`, `feature/concept-repeat.md` cross-link), status → `Implemented`.

## 13. Risks

| Risk | Mitigation |
|------|------------|
| Diagrams that already contain `GetRepeatedValue` and today resolve across all slots will change value | That is the bug being fixed; the old output could not validate in ODK anyway. Called out in the changelog. |
| A diagram whose slot argument does not match any capture now fails to resolve instead of silently using another slot | Intended (§7.2); the deferral message names the slot. |
| Enum value change breaks a persisted/serialised operator string | Grep shows the literal `"ge_repeated_value"` is used nowhere outside the enum definition. |

## 14. Follow-ups (not in this change)

### 14.1 Expression accessors → generated populate nodes *(the big one)*

A new spec should define desugaring **out-of-form accessor functions into generated
`TriccNodePopulate` nodes**, which every strategy already knows how to serve (CHT: `inputs` group or
contact summary; FHIR: `Helper.Get*Value`). Target functions:

| Function | Generated populate |
|----------|--------------------|
| `GetHistoryValue(code, period)` | `context=history`, `period=<period>` → CHT `instance('contact-summary')/context/<code>` |
| `GetHistoryObservationValue` / `GetHistoryConditionValue` | same, with `concept_type` pinned so `populate_fhir_target` picks the right resource |
| `GetRepeatedValue(code, n)` **when no in-form slot exists** | `context=encounter`, `repeat=n` (see §8.3 — deliberately *not* done now) |

Design questions that spec has to answer:

1. **Deduplication** — two expressions asking for the same `(code, context, period, repeat)` must
   share one generated node, not emit two fields.
2. **Naming / collision** — a generated node must not collide with an authored populate node or a
   capture node of the same concept; `get_export_name` already special-cases populate nodes that
   use the `inputs` group (`load.<name>`), which is the precedent to follow.
3. **Injection point** — generated during reference resolution in `process_operation_reference`, but
   it must land in an activity's `nodes` so `XLSFormCDSSStrategy.export_inputs` collects it, and it
   must not break `is_ready_to_process` / skip logic (`populate_participates_in_skip` already
   excludes `context=history`).
4. **Plain XLSForm** — `XLSFormStrategy` has no contact summary. Emit an empty calculate, or refuse?
5. **Period validation** — reuse `normalize_populate_node` / `is_valid_period` rather than parsing
   the literal separately.

### 14.2 Smaller items

- `fhir_form.py:1088` resolves an unresolved `TriccReference` in CQL with a hard-coded
  `get_observation_cql_accessor(r.value, 1)`. A `GET_REPEATED_VALUE` parent should pass its slot
  through, so an out-of-form slot becomes `Helper.GetRepeatedValue(code, n)`. Folded into 14.1's
  encounter-context case, or fixed on its own.
- `GetNumberOfRepeat` as a TRICC operation (needs a per-output counting strategy; no populate route).
- **`get_datatype()` is broken for the whole `RETURNS_CONCEPT` family** (`models/base.py`): it calls
  `self.get_reference_datatype(self.reference[0])`, passing a single node into a function that
  iterates its argument — so a pydantic model gets iterated and the datatype comes back as
  `"<class 'tuple'>"`. Pre-existing (`GET_INHERITED_VALUE` and `GET_HISTORY_VALUE` have it too), so
  it was **not** touched here; the fix looks like `self.reference[:1]` but needs a check of what
  consumes these datatypes. The tests assert operand *order* instead of freezing wrong behaviour.
- `YamlStrategy` `start` node does not accept `form_id`, so full-export tests on YAML fixtures
  cannot run `export()`; tests here work at the strategy-API level instead.
