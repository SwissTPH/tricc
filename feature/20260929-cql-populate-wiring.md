# Wiring the CQL populate path: `cqf-library`, `encounterid`, and cross-visit reads

| Field | Value |
|-------|-------|
| **Status** | Approved |
| **Branch target** | `feature/project-level-config` |
| **Related** | `fix/20260929-cql-initial-expression-on-device.md` (Approved — makes the libraries this spec points at compile and return item-typed values), `fix/20260914-cql-retrieve-codesystem.md` (Implemented — made the retrieves match the extracted code; prerequisite for this), `feature/20260812-intervention-order-and-dedup.md` (introduced `encounterid` and the dedup `initialExpression`), `fix/20260821-merge-input-into-populate.md` (the populate accessors), `feature/20260826-concept-persistence-mapping.md` (Draft — concept→resource/element declarations), `docs/desing/FHIRcore.md`, `docs/open-srp-export.md`, `tests/output/demo_prepopulate/README.md` (the config-level alternative, working today) |
| **Origin** | 2026-09-14. A weight captured in the Diabetes questionnaire never appears in the Hypertension Followup questionnaire on a live openSRP install, with the retrieve fix already deployed. Revised 2026-09-29 after the on-device validation below; approved by the user in session the same day. |

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
   on the Helper *and* each segment library. **Resolved 2026-09-29:** fhircore's CQL
   `initialExpression` path passes `encounterid` itself, as the logical id of the Encounter
   in the launch context (`QuestionnaireViewModel.evaluateCqlInitialExpressions`); the
   start-care session supplies that Encounter from the second form of a visit onward. No
   launchContext extension is emitted.
4. **History populate reaches across visits, within its period.** `context=history` emits
   `Helper.GetHistoryObservationValueSince('<code>', Now() - <period>, 1, <repeat>)`, which
   is not encounter-scoped and only considers Observations effective on or after the start
   of the window. `period` is an ISO 8601 duration (`P3M`, `P1Y`, `P2W`, `P10D`, `P1Y6M`),
   defaulting to `P1Y` as before; a period with a time part or an explicit start/end is
   not translated and reads without a window (warning). *Revised 2026-09-29:* the period
   used to be accepted and ignored.
5. **Populate source concept (`source`).** *Added 2026-09-29, approved by the user in
   session.* A populate node reads the concept it names, unless it declares
   `source="<concept>"`, in which case it reads that concept and keeps its own name for
   every in-form reference. This is what lets a flow keep a "previous value" node
   (`t_weight`, read by the `weight` calculate) distinct from the question that records
   the value (`weight_c`): renaming the node to the question's name would make them two
   versions of one concept, which TRICC merges. `source` applies to the FHIR / openSRP
   export; other outputs keep reading by name.
6. **Populate nodes are not extracted.** A populate value was received, not captured: the
   extraction map no longer writes it back, which previously re-recorded a carried-over
   value as a new Observation dated today (and, with `source`, would have created one under
   the node's own name on every save).
7. **Unpersisted populate concept warning.** When a populate node's concept (its `source`,
   else its name) is persisted by **no** extraction rule in the project, log a warning naming
   the node and the concept — the silent case that produced this issue. (Only this
   project's extraction is visible to the exporter; a concept recorded by another project
   still warns, so the message says so.)

### Code checklist

- [x] `tricc_oo/strategies/output/fhir_form.py` — emit `cqf-library` per Questionnaire with
      CQL expressions; emit `Library.parameter` for `encounterid`; add
      `relatedArtifact: depends-on` to segment libraries.
- [x] `tricc_oo/strategies/output/opensrp.py` — reuse `_process_library_url`; keep the
      "no Library → no extension" rule; emit the launch context if §3 resolves that way.
- [x] `source` on populate nodes: `drawio_type_map.py`, `TriccNodePopulate`,
      `populate_helper.resolve_populate_reference` (§5).
- [x] Helper `GetHistoryObservationValueSince` + ISO duration → CQL quantity (§4).
- [x] `structuremap.build_extraction_rule` skips populate nodes (§6).
- [x] `tricc_oo/strategies/output/fhir_form.py` (or the populate pass) — warning for a
      populate concept that no extraction rule persists.
- [x] `docs/open-srp-export.md` — the populate path end to end: who supplies `encounterid`,
      when `cqf-library` appears, encounter vs history scope.
- [x] `docs/tricc-elements.md` — `context=history` as *the* cross-visit mechanism, with the
      concept-naming rule.


_2026-09-29: `cqf-library` is emitted by `OpenSRPStrategy._wire_questionnaire_extensions` (next to
`cqlInputResources`); `Library.parameter` / `depends-on` by `FHIRStrategy._make_library_resource`.
All items done; status stays Approved until the on-device acceptance run._

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

### Validation (done 2026-09-29)

On a tablet running the fhircore 2.2.2 debug build (commit `1a5bb44c3`, CQL
`initialExpression` support), with the Hypertension Followup package patched by hand to the
shape this spec and `fix/20260929-cql-initial-expression-on-device.md` describe, a weight
entered in the Diabetes form (63.4 kg) appeared in the Hypertension Followup weight field.
Findings that shaped the spec:

- `cqf-library` (`valueCanonical`) is the only trigger; `cqlInputResources` is read by
  nothing. `valueReference` is not accepted by fhircore's `cqfLibraryUrls()`.
- The CQL engine resolves the library by the **last segment of its canonical URL**, which
  must therefore be the CQL library name (fix §1).
- Libraries reach the CQL engine only through the app manifest (`Composition?identifier=<app
  id>`); a Library downloaded by data sync alone is not evaluable. This is deployment, not
  export, and is documented in `docs/open-srp-export.md`.
- fhircore does not re-index a changed Library on re-login when the data sync already
  stored it; *Settings → Sync configuration* does. fhircore issue, documented.

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
