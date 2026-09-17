# Wiring the CQL populate path: `cqf-library`, `encounterid`, and cross-visit reads

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Branch target** | `feature/project-level-config` |
| **Related** | `fix/20260914-cql-retrieve-codesystem.md` (Implemented — made the retrieves match the extracted code; prerequisite for this), `feature/20260812-intervention-order-and-dedup.md` (introduced `encounterid` and the dedup `initialExpression`), `fix/20260821-merge-input-into-populate.md` (the populate accessors), `feature/20260826-concept-persistence-mapping.md` (Draft — concept→resource/element declarations), `docs/desing/FHIRcore.md`, `docs/open-srp-export.md`, `tests/output/demo_prepopulate/README.md` (the config-level alternative, working today) |
| **Origin** | 2026-09-14. A weight captured in the Diabetes questionnaire never appears in the Hypertension Followup questionnaire on a live openSRP install, with the retrieve fix already deployed. |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

### What authors expect

An author draws a `populate` node for a value the form should *receive* rather than ask —
"the participant's last weight" — and wires the question so it is only asked when nothing
was found. TRICC exports the inlet and the fallback faithfully: both the Diabetes and the
Hypertension Followup questionnaires carry a hidden `load_t_weight` and a calculate that
reads `iif(weight_c answered, weight_c, load_t_weight)`.

What the author does not get is a value. Nothing recorded by an earlier form ever reaches
the inlet, so the health worker measures and types the weight again at every visit, and any
algorithm branch that depends on a previously recorded value behaves as if this were the
patient's first ever contact.

### Why (in plain terms)

The exported package is missing the plumbing that connects three things that each work on
their own:

1. **The form does not say which library its expressions come from.** The questions carry
   CQL expressions by name (`Calc_load_t_weight`), and the library defining those names is
   exported — but the Questionnaire never names the library, so the renderer has nothing to
   resolve the names against and skips them.
2. **Nobody says which visit is "now".** The library asks for the current visit's id as an
   input, with no value supplied anywhere in the package. Every read is written to return
   nothing when that input is absent — deliberately, so a form cannot silently read another
   visit's data — so absent input means every read returns nothing.
3. **"This visit" is the wrong question for a follow-up.** Even supplied, a same-visit read
   cannot see last month's weight. Reaching back across visits is a different, already
   exported accessor, selected by the author writing `context=history` on the populate node
   — and pointing it at the concept that actually records the value (`weight_c`), not at a
   separate `t_weight` concept.

(1) and (2) are export gaps and are fixed here. (3) is authoring, and this spec's job is to
document it and make it work once chosen.

### What changes for an author

Nothing in the drawing, except the two things (3) covers: a populate node intended to reach
a previous visit says `context=history`, and it names the concept whose value it wants. In
return, exported forms stop re-asking what the record already holds.

### Limitations

- A value can only come back if it was **extracted** in the first place: a concept has to be
  persisted as an Observation/Condition for any read to find it.
- Cross-visit reads are only as good as the effective date on the stored resource.
- This does not replace the config-level `PREPOPULATE` route
  (`tests/output/demo_prepopulate/README.md`), which stays the right tool when the value
  comes from outside the record (a register field, a computed age) or when a value must land
  in a *visible* field. Note that pre-filling a visible capture item means submission
  extracts it again, dated today — a carried-over measurement re-recorded as a fresh one.
- Renderer support for CQL `initialExpression` is a property of the deployed app, not of the
  export. Where it is absent, `PREPOPULATE` remains the only route.

---

## Part II — Technical specification

### Current state (verified 2026-09-14, on the pushed Diabetes / HTN packages)

| Fact | Evidence |
|---|---|
| Questionnaire top-level extensions are `cqlInputResources`, `planDefinitions`, `targetStructureMap` — no `cqf-library` | both `Questionnaire-questionnaire-registration.json` |
| `grep -rn "cqf-library" tricc_oo/` → no match | exporter never emitted it |
| `encounterid` appears only as `parameter encounterid String default null` inside Helper CQL; `Library.parameter` is absent; no extension or PlanDefinition supplies a value | `Library-*-Helper.json`, `grep -rn encounterid` |
| Segment Library has no `relatedArtifact` `depends-on` → Helper resolvable only by CQL `include` name | `Library-*-registration.json` |
| `GetObservations` returns `{} as List<Observation>` when `encounterid is null` | `repeat_helper.cql_helper_repeat_block` |
| Extraction *does* set `subject`, `encounter` (when the QR carries one), `status = 'final'`, `effective = QR.authored`, `code = <project system>|<code>` | `extract_weight_c` in both extract maps |
| `Calc_load_t_weight` reads concept `t_weight`; the measurement is stored as `weight_c` | HTN/Diabetes `*-registration.cql` vs extract maps |

### Semantics

1. **Library declaration.** Every Questionnaire carrying at least one
   `text/cql-identifier` expression declares its segment library:

   ```json
   {"url": "http://hl7.org/fhir/StructureDefinition/cqf-library",
    "valueCanonical": "<base_url>/Library/<segment library id>"}
   ```

   Emitted from the same resolved Library the `cqlInputResources` extension already uses
   (`OpenSRPStrategy._process_library_url`) — and, like it, **omitted when the process has
   no generated Library**, so this never introduces a dangling canonical
   (`fix/20260909-opensrp-empty-main-questionnaire-dangling-library.md`).
2. **Dependency declaration.** The segment Library gains
   `relatedArtifact: [{type: "depends-on", resource: "<base_url>/Library/<Helper id>"}]`,
   so an evaluator resolving the CQL `include` has a FHIR-level pointer.
3. **`encounterid` hand-off.** The Helper keeps the parameter and its null-safe behaviour.
   The package additionally declares it so a client knows to supply it:
   `Library.parameter` = `{name: "encounterid", use: "in", min: 0, max: "1", type: "string"}`
   on the Helper *and* each segment library. **Open question (decide before Approved):**
   whether the app is expected to pass it via the SDC launch context
   (`sdc-questionnaire-launchContext` `encounter`, from which a `cqf-library`-aware renderer
   derives the parameter) or via an openSRP config param; the answer determines whether an
   `encounter` launchContext extension is also emitted. This needs one confirmation against
   the deployed fhircore build — see "Validation" below.
4. **History populate reaches across visits, unchanged.** `context=history` already emits
   `GetHistoryObservationValue(code, period, 1, repeat)`, which is not encounter-scoped. No
   code change; the `period` argument stays advisory (it is accepted and ignored by the
   Helper today — **listed as a known gap**, out of scope here).
5. **Populate concept alignment.** A populate node reads the concept it names. Authoring
   fix, with an exporter guard: when a populate node's concept is persisted by **no**
   extraction rule anywhere in the project, log a warning naming the node and the concept —
   the silent case that produced this issue.

### Code checklist

- [ ] `tricc_oo/strategies/output/fhir_form.py` — emit `cqf-library` per Questionnaire with
      CQL expressions; emit `Library.parameter` for `encounterid`; add
      `relatedArtifact: depends-on` to segment libraries.
- [ ] `tricc_oo/strategies/output/opensrp.py` — reuse `_process_library_url`; keep the
      "no Library → no extension" rule; emit the launch context if §3 resolves that way.
- [ ] `tricc_oo/strategies/output/fhir_form.py` (or the populate pass) — warning for a
      populate concept that no extraction rule persists.
- [ ] `docs/open-srp-export.md` — the populate path end to end: who supplies `encounterid`,
      when `cqf-library` appears, encounter vs history scope.
- [ ] `docs/tricc-elements.md` — `context=history` as *the* cross-visit mechanism, with the
      concept-naming rule.

### Tests

- A Questionnaire with a `text/cql-identifier` expression gets exactly one `cqf-library`
  pointing at the same Library id as `cqlInputResources`; one with no CQL expression gets
  neither.
- A process with no generated Library gets neither extension (regression guard for
  `fix/20260909-…`).
- Helper and segment Library both declare the `encounterid` parameter (`use: "in"`,
  `min: 0`).
- Segment Library declares `depends-on` the Helper.
- `context=history` populate on concept `weight_c` emits
  `GetHistoryObservationValue('weight_c', …)` and no `GetEncounter*` accessor.
- A populate node naming a concept that no extraction rule persists logs a warning.

### Validation (must happen before `Implemented`)

The one thing this repo cannot settle on its own: whether the deployed fhircore build
evaluates a CQL `initialExpression` off `cqf-library`, and how it expects `encounterid` to
arrive. Confirm against `android/feature/cql-initial-expression.md` in the fhircore repo and
one on-device run before flipping status. Until then the config-level `PREPOPULATE` route
stays the supported answer for cross-form values.

### Acceptance criteria

1. A weight recorded by the Diabetes questionnaire appears at the Hypertension Followup
   questionnaire's `load_t_weight` inlet on a live install, with no app-config param — for
   a populate node authored `context=history` on concept `weight_c`.
2. Same-visit dedup pre-populates an answerable item captured by an earlier process in the
   same encounter.
3. No package contains a canonical pointing at a Library it does not ship.
4. `python -m pytest tests/` passes.

### Phases

1. `cqf-library` + `depends-on` + `Library.parameter` (export-only, no semantic change).
2. On-device validation of §3's open question; emit launch context if required.
3. The unpersisted-populate-concept warning.
4. Authoring pass on the real projects: `context=history` + concept alignment for the
   vitals that should carry over.
