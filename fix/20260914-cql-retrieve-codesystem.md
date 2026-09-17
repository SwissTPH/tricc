# Helper CQL retrieves filter on a code system that nothing writes

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `feature/project-level-config` |
| **Related** | `feature/20260812-intervention-order-and-dedup.md` (the encounter-scoped helpers this fixes), `fix/20260821-merge-input-into-populate.md` (the populate accessors that route through them), `feature/20260826-concept-persistence-mapping.md` (Draft — the terminology surface that would let the read side filter by system again), `feature/20260813-concepttype-structuremap.md` (the write side), `docs/desing/FHIRcore.md`, `docs/open-srp-export.md` |
| **Origin** | Found 2026-09-14 while asking why a weight captured in the Diabetes questionnaire is not pre-filled in the Hypertension Followup questionnaire. Independently recorded at the bottom of `tests/output/demo_prepopulate/README.md`. |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Issue analysis

### Symptom

Nothing a previous form recorded ever comes back. Every value the exported Questionnaire
expects to arrive from the patient's record — a weight measured earlier in the same visit, a
diagnosis confirmed by an earlier process, any `populate` node — stays empty, and the health
worker is asked the question again.

Concretely, on the two questionnaires that surfaced this: both Diabetes and Hypertension
Followup export the same weight triplet — a visible `weight_c` ("Weight (kg)") carrying a
dedup `initialExpression`, a hidden `load_t_weight` populate inlet, and a hidden `weight`
calculate that reads `iif(weight_c answered, weight_c, load_t_weight)`. The author's intent is
plainly "do not re-ask what we already know". Neither inlet is ever filled.

### Who is affected

Every project exported through `FHIRStrategy` / `OpenSRPStrategy`: the generated **Helper**
library is the single route to recorded data, and all of it is affected — dedup
pre-population, all four `populate` contexts, `GET_REPEATED_VALUE`, history lookback,
Condition existence tests.

### Expected vs actual

| | Expected | Actual |
|---|---|---|
| `Helper.GetObservationValue('weight_c')` | the value of the Observation the extraction StructureMap wrote for concept `weight_c` | empty — the retrieve's terminology filter matches no Observation |
| Helper library translation | translates | `"http://snomed.info/sct"` and `"active"` are quoted CQL **identifiers** that resolve to no declaration in the library, so translation fails outright |

Two distinct defects, both in generated Helper CQL:

1. **Code system mismatch.** The retrieves are hardcoded to
   `[Observation: Code code from "http://snomed.info/sct"]`
   (`tricc_oo/converters/fhir/repeat_helper.py:110,155,182,210` and
   `tricc_oo/strategies/output/fhir_form.py:227`), while extraction stamps the code system that
   owns the concept — `cc('http://example.com/fhir/CodeSystem/tricc', 'weight_c', 'Weight (kg)')`
   in the Diabetes/HTN maps. TRICC concepts are not SNOMED codes; they are project concepts in
   project code systems.
2. **Undeclared identifiers.** CQL's `Code <x> from "<name>"` requires a `codesystem`
   declaration named `"<name>"`, and `~ "active"` requires a `code`/`concept` declaration
   named `"active"`. The generated Helper declares neither, and the Libraries ship as plain
   `text/cql` with no pre-compiled ELM, so this only fails at app/server translation time —
   which is why it reads as "pre-population silently does nothing" in the field.

### Why not just declare the SNOMED code system

Because a single declared system cannot be correct here. The write side resolves the system
**per concept**, from whichever CodeSystem in the project holds it
(`_concept_system_url`, `structuremap.py:241`), falling back to `{base_url}/CodeSystem/tricc`.
A real project therefore spreads codes over several systems at once — `tricc_codesystem.json`,
`sym_codesystem.json` and `calculate_codesystem.json` all exist side by side in
`tests/output/`, and a concept absent from every CodeSystem gets the fallback URL, so two
Observations extracted by the *same form* can carry different systems.

TRICC already treats a concept code as unique project-wide on the read side —
`lookup_codesystems_code` searches every CodeSystem by code alone and returns the first hit.
Matching on the code and ignoring the system makes the read side consistent with that, and is
correct for every one of those layouts.

### Out of scope

- **Making a value cross an encounter.** `GetObservations`/`GetConditions` are deliberately
  scoped to the current encounter (`encounterid`), per
  `feature/20260812-intervention-order-and-dedup.md`. A follow-up visit is a different
  encounter, so reaching a *previous visit's* weight is authoring work — a `populate` node
  with `context=history`, which routes to the unscoped `GetHistory*` family — not a change here.
  This fix is what makes that authoring work actually retrieve anything.
- **Concept alignment.** `load_t_weight`'s concept is `t_weight`, while the measured value is
  stored under `weight_c`; a populate node has to name the concept that records the value.
  That is authoring (and, longer term, `feature/20260826-concept-persistence-mapping.md`).
- **`GetPatientValue` / `GetFacilityValue` / `GetLocationValue` / `GetPractitionerValue`**,
  which return `null` by design today.
- Anything in a child/segment library: those contain only `define`s delegating to `Helper.`
  and carry no terminology references.

---

## Part II — Fix approach

### Root cause

The Helper CQL was written against a SNOMED-coded content IG and never re-based on TRICC's own
project terminology when `conceptType`-driven extraction
(`feature/20260813-concepttype-structuremap.md`) made the write side resolve the system per
concept. Nothing tested the read side against the system the write side emits, and because the
Libraries carry no ELM, no build step ever translated the CQL.

### Emission rules

1. **Retrieves carry no terminology filter.** `[Observation: Code code from "…"]` becomes
   `[Observation]`, matched in the `where` clause by concept code across any system. In
   `context Patient` the unfiltered retrieve is already patient-scoped.
2. **Two code-matching helpers** are emitted in the repeat block and used by every retrieve:

   ```cql
   define function ObservationHasCode(O Observation, conceptCode String):
     exists(O.code.coding C where C.code = conceptCode)

   define function ConditionHasCode(C Condition, conceptCode String):
     exists(C.code.coding CC where CC.code = conceptCode)
   ```

   Resource-typed parameters match the existing style (`ObservationRepeatIndex(O Observation)`);
   `conceptCode` rather than `code` so nothing shadows the `code` element inside the query.
3. **`clinicalStatus` is compared by code, not by a declared concept.**
   `C.clinicalStatus ~ "active"` becomes
   `exists(C.clinicalStatus.coding CS where CS.code = 'active')`.
4. **No `codesystem` declaration is emitted.** With (1)–(3) the Helper library has no quoted
   identifier other than its own name and the `FHIRHelpers` include — i.e. nothing left that
   can fail to resolve.
5. Every other clause is untouched: `encounterid` scoping, the status filter, repeat-index
   matching, `sort by effective desc`, the history family's `skip`/`take`, and every public
   function name and signature. Previously generated child libraries keep working.

### Code checklist

- [x] `tricc_oo/converters/fhir/repeat_helper.py` — `cql_helper_repeat_block`: add
      `ObservationHasCode` / `ConditionHasCode`; drop the terminology filter from
      `GetObservations`, `GetHistoryObservation`, `GetConditions`, `GetHistoryCondition`.
- [x] `tricc_oo/strategies/output/fhir_form.py` — `CQL_HELPER_TEMPLATE`: same for
      `HasCondition`, plus the `clinicalStatus` comparison.
- [x] `tests/test_fhir_repeat.py` — assertions below.
- [x] `docs/open-srp-export.md` — record that concept retrieval matches on code across systems.

### Tests

- `cql_helper_repeat_block()` contains no `snomed.info/sct` and no `Code code from`.
- It defines `ObservationHasCode` / `ConditionHasCode`, and each of the four retrieves is
  guarded by one of them.
- The assembled `CQL_HELPER_TEMPLATE` contains no `from "` retrieve and no `~ "active"`.
- **Round-trip:** for a node whose concept lives in a project CodeSystem, the system in the
  extraction rule (`build_extraction_rule(...).code_system_url`) is no longer required to
  equal anything in the Helper CQL — asserted as "the Helper filters on the bare code, so the
  rule's code appears as the argument" — guarding against a future reintroduction of a
  hardcoded system.
- Existing encounter-scoping / repeat / Condition-family assertions must keep passing
  unchanged.

### Acceptance criteria

1. Generated `*-Helper.cql` has no undeclared quoted identifier; the only `"…"` are the
   library name and the `FHIRHelpers` include.
2. `Helper.GetObservationValue('<code>')` matches an Observation written by this project's own
   extraction StructureMap, whichever project CodeSystem owns `<code>`.
3. No public Helper function is renamed and no signature changes.
4. `python -m pytest tests/` passes.
