# Intervention PD-level trigger, cpg-common-process order, and current-encounter dedup

| Field | Value |
|-------|-------|
| **Status** | Approved |
| **Branch target** | `feature/zscore` (current branch) |
| **Related** | `feature/careplan-intervention-plandefinition.md` (supersedes its "trigger on every action" placement), `feature/opensrp-export-hygiene.md`, `feature/opensrp-register.md`, `feature/careplan.md` §26 (closes the "process extension" gap it assumed already existed), `feature/20260812-medication-request-dispense-node.md` (parked, explicitly out of scope here) |
| **Approval** | Approved via planning conversation on 2026-08-12 (multi-round clarification with the user on repo scope, order-table basis, encounter-scoping feasibility, `GetObservationValue` semantics, and repeat-slot dedup — see plan history) before implementation began. |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

Today's Intervention PlanDefinition (one per project, `feature/careplan-intervention-plandefinition.md`)
repeats the `available-care` named-event on **every** per-process action, even though openSRP's
`$apply`/named-event discovery operates on the whole PlanDefinition, not per action. There is also
no notion of *order* between cpg-common-process segments, and no way for the openSRP app to compare
"which unlocked step is earliest" across several selected Interventions. Finally, a patient's
answers to a Finding/Observation/Condition-typed question in one process (e.g. registration) are
never reused by a later process in the same visit (e.g. clinical assessment) — the same question
gets asked twice.

This change:

1. **Moves the `available-care` trigger to a single wrapping action** inside the Intervention PD,
   instead of repeating it on every process action. Each process keeps its own process-name
   named-event (for possible direct invocation later).
2. **Gives the cpg-common-process list a fixed order** (10, 20, 30… by the existing list order in
   `tricc_oo/visitors/utils.py`), carried on each process action via two new extensions
   (`tricc-process`, `tricc-process-order`) so the openSRP client can compare "which unlocked step
   is earliest" across different selected Interventions/PlanDefinitions.
3. **Auto-fills answers already recorded this encounter** for Finding/Observation/Condition-typed
   questions, so a later process doesn't re-ask what an earlier process in the same visit already
   captured. (MedicationRequest/MedicationDispense are out of scope — see
   `feature/20260812-medication-request-dispense-node.md`.)

## Part II — Technical specification

### 1. Wrapper action (PD-level trigger)

`OpenSRPStrategy.generate_intervention_plandefinition()` (`tricc_oo/strategies/output/opensrp.py`)
now emits:

```
PlanDefinition.action[0]:                      # wrapper — carries available-care once
  id: "available-care"
  trigger: [{type: named-event, name: "available-care"}]
  action[]:                                      # one per process, in process_chain order
    id: <existing per-process action id>
    trigger: [{type: named-event, name: <process name>}]   # own trigger kept
    extension:
      - url: {base_url}/StructureDefinition/tricc-process, valueString: <process name>
      - url: {base_url}/StructureDefinition/tricc-process-order, valueInteger: <order>
    definitionCanonical: Questionnaire/...
```

This is same-resource nesting (`action.action`), **not** a second linked PlanDefinition. Verified
against fhircore's `NamedEventInterventionService.collectFromPlanDefinition`
(`android/engine/.../task/`): when a matched top-level action has children, those children —
not the parent — become the candidates evaluated for applicability
(`actionsWithEvent.flatMap { parent -> parent.action ?: listOf(parent) }`), and each child's own
`passesFhirPathConditions` is still checked individually. This is a different code path from the
cross-resource `definitionCanonical` → PlanDefinition link that caused the old catalog PD's
unconditional-resolution bug (`feature/careplan-intervention-plandefinition.md`, 2026-08-12 update)
— so this reproduces "trigger at the PD level" without reintroducing that bug.

### 2. Canonical process order

`tricc_oo/visitors/utils.py`:

```python
PROCESS_ORDER = {name: (i + 1) * 10 for i, name in enumerate(PROCESSES)}
```

`OpenSRPStrategy._process_order()` looks up this table; process names not in `PROCESSES` get the
next free slot after the highest known order (`max(PROCESS_ORDER.values()) + 10`, `+20`, …),
assigned in `process_chain` discovery order and cached per export so repeated lookups are stable.
The order is a **fixed, canonical** value (not recomputed per export from local discovery order),
so it is comparable across different PlanDefinitions/Interventions on the Android side.

### 3. Current-encounter dedup (Finding/Observation/Condition)

Checked before implementing: `resolve_populate_reference`'s `context="encounter"` branch
(`tricc_oo/converters/fhir/populate_helper.py`) already delegated to `GetObservationValue`/
`GetRepeatedValue` — the intent was already "encounter context = an Observation lookup," it just
never actually filtered by encounter. Fixed at the source instead of adding parallel helpers:

- `repeat_helper.py`: Helper CQL gains `parameter encounterid String default null`.
  `GetObservations(code)` (and everything that delegates through it — `GetObservation`,
  `GetObservationValue`, `GetRepeated`, `GetRepeatedValue`, `GetNumberOfRepeat`) now filters by
  `O.encounter.reference = 'Encounter/' + encounterid`, returning nothing when `encounterid` is
  absent (a visit's first process — nothing recorded yet this encounter, which is expected).
  **The parameter name `encounterid` matches existing dead plumbing** in fhircore's
  `QuestionnaireViewModel.evaluateCqlInitialExpressions` — see the companion Android spec, §3.
- **Renamed** `GetHistory`/`GetHistoryValue` → `GetHistoryObservation`/`GetHistoryObservationValue`
  (behavior unchanged: the deliberate any-time/"outside the encounter" lookback used by the
  `context="history"` populate path).
- **New Condition family** (no repeat index — Condition isn't TRICC-repeated the way vitals are):
  `GetConditions`/`GetCondition`/`GetConditionValue` (current-encounter, presence-style —
  `exists(...)`, since Condition has no scalar `.value`) and `GetHistoryCondition`/
  `GetHistoryConditionValue` (any-time).
- **Compatibility note:** the generic calculate cross-reference path
  (`FHIRStrategy.get_tricc_operation_operand` → `get_observation_cql_accessor*`) also calls
  `GetObservationValue`/`GetRepeatedValue`, so calculate nodes referencing an out-of-form input
  are now encounter-scoped too (previously any-time/unscoped). Authors who need an any-time
  calculate lookback should use a `history`-context populate node instead.
- **Repeat-slot correctness:** `repeat` marks the *same* concept measured more than once within
  one encounter (e.g. a BP retaken after treatment) — deliberately the same code, to avoid
  polluting patient history with near-duplicate concepts. Auto-dedup for Observation-typed items
  goes through the existing `get_observation_cql_accessor_for_node(node)` (not bare
  `GetObservationValue`), so a repeat-slot-2 item dedups against slot 2 specifically, not "any
  past Observation with this code."
- **Write-path fix (prerequisite, found during implementation):** the read side
  (`ObservationRepeatIndex`) already assumed every extracted Observation carries a
  `TRICC_OBSERVATION_REPEAT_EXT` extension marking its repeat slot, but
  `FHIRStrategy.generate_export()`'s `fml_repeat_extension_rule()` only ever emitted an FML
  **comment**, never an executable rule — repeat-index metadata was never actually written to real
  extracted Observations. Fixed: `fml_repeat_extension_rule(link_id, content_type, repeat)` now
  emits `{link_id} -> {content_type}.extension as ext then { ext.url = '...'; ext.value = N; }`.
- **Auto-wiring:** `FHIRStrategy._attach_dedup_initial_expression()` (called from
  `generate_export()`, where `concept_type`→`fhir_resource` is already resolved) attaches a
  `Dedup_{link_id}` CQL define + `initialExpression` extension to any **extracted,
  answerable** item whose `fhir_resource` is `Observation`/`Condition` and which has no
  author-authored `initialExpression`/`calculatedExpression` already (checked via the item's
  existing `extension` list). Notes (`display`), activity/start containers (`group`), and
  other non-extracted node types (Calculation / InteractSet / Misc) are skipped: SDC
  forbids `initial`/`initialExpression` on group and display items
  (http://build.fhir.org/ig/HL7/sdc/expressions.html#initialExpression) and openSRP FHIR
  Data Capture throws `IllegalStateException` at `$populate` if they appear. A last-line
  sanitizer (`strip_illegal_initials`) removes any leftover before write.
  MedicationRequest/MedicationDispense are skipped entirely — no node type produces them yet.

### Code changes

| File | Change |
|------|--------|
| `tricc_oo/strategies/output/opensrp.py` | `generate_intervention_plandefinition()` restructured (wrapper + nested children); `_process_order()` new; `validate()` walks the nested tree |
| `tricc_oo/visitors/utils.py` | `PROCESS_ORDER` table added |
| `tricc_oo/converters/fhir/repeat_helper.py` | `encounterid` parameter, encounter-scoped `GetObservations`, `GetHistory(Observation)(Value)` rename, Condition family, executable `fml_repeat_extension_rule` |
| `tricc_oo/converters/fhir/populate_helper.py` | `HISTORY_CONTEXT` branch call-site rename |
| `tricc_oo/strategies/output/fhir_form.py` | `CQL_HELPER_TEMPLATE` gains the `encounterid` parameter declaration; `generate_export()` calls the new `_attach_dedup_initial_expression()`; `fml_repeat_extension_rule()` call site updated for its new `content_type` argument |

### Tests

`tests/test_strategies/test_opensrp_strategy.py` (wrapper/nested-action shape, extensions, order
including an unrecognized process name), `tests/test_fhir_repeat.py` (encounter scoping, rename,
Condition family, executable FML rule), `tests/test_populate_context.py` (rename),
`tests/test_dedup_initial_expression.py` (new — auto-wired dedup for Observation/Condition,
repeat-slot correctness, author-authored expressions are not overwritten, non-dedup concept types
are untouched). Full suite: `python -m pytest tests/` (166 passed; 5 pre-existing, unrelated
goto/repeat-instance failures untouched by this change).

### Verification performed

Real export (`tests/build.py -i tests/data/etat.drawio -O OpenSRPStrategy`) manually inspected:
wrapper action carries `available-care` once; each child action carries its own process trigger +
both new extensions with correct order values (including a `"main"` process not in the canonical
list correctly landing at `160`, one slot past the table's `150` max); `ETAT-Helper.cql` contains
the `encounterid` parameter and the full renamed/Condition function set; `Dedup_*` CQL defines and
`initialExpression` extensions appear on plain Observation-typed items with no author-authored
expression already present.

### Acceptance criteria

- [x] `available-care` trigger appears exactly once per Intervention PD (on the wrapper action),
      not repeated on every process action.
- [x] Each process action keeps its own process-name trigger and gains `tricc-process` /
      `tricc-process-order` extensions with canonical, cross-PD-comparable order values.
- [x] Observation/Condition-typed items with no author-authored populate/calculate expression get
      an auto-attached, current-encounter-scoped dedup `initialExpression`; repeat-slot items dedup
      against their own slot. Group and display items never receive `initial`/`initialExpression`.
- [x] `GetHistory*` renamed to `GetHistoryObservation*`; behavior (any-time lookback) unchanged.
- [x] Repeat-index metadata is now genuinely written to extracted Observations (write-path fix).
- [x] Unit tests pass; real export manually verified.
- [ ] Android-side consumption of the new extensions/`encounterid` parameter — see the companion
      spec in `openSRP-fhircore/android/feature/`.
