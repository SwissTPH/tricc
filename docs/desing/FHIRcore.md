**Updated & Further Tidied Requirements Specification: OpenSRP/FHIR-Core Export Strategy (v4)**

**Project Context**  
This is the final consolidated specification for adding a new output strategy (`OpenSRPStrategy` / `FHIRCoreStrategy`) to TRICC.  
It strictly follows the “Adding a New Output Strategy” workflow from the TRICC Cline Rules (inherit from `BaseOutputStrategy`, implement `convert()` + `validate()`, register in the strategy factory, add tests + docs).  
The strategy reuses patterns, utilities, and code from `pyfhirsdc` (XLSX→FHIR pipeline) wherever possible, **especially the existing manual openMRS concept_type → FHIR resource mapping**.  
Output: FHIR SDC resources (Questionnaire, PlanDefinition, Library+CQL, StructureMap/FLM, Binary, ValueSets, CodeSystems) + FSH (FHIR Shorthand) files + a top-level `Composition` resource (with Binary manifest) that matches the exact openSRP/fhircore configuration model documented at https://github.com/opensrp/fhircore/tree/main/docs/engineering/app/configuring.

**Important clarifications applied in v4**  
- Reuse **existing openMRS mapping from pyfhirsdc** (manual per-concept mapping).  
- OCL (Open Concept Lab – spin-off of OpenMRS) is the proper long-term standard for terminology/mappings, but we stick to the pyfhirsdc manual approach for now.  
- Use **openSRP profile** for all resources (no generic Tricc profiles or custom profiles at this stage – user will refine later).  
- fhircore configuration relies heavily on a top-level `Composition` + `Binary` resources as the config manifest. Questionnaires must reference `planDefinitions` array and `cqlInputResources` (Libraries).

---

### 1. OpenSRP / fhir-core Target Requirements (Fully Clarified)

- **Questionnaire Launch & Workflow**  
  - Exactly **one FHIR `Questionnaire`** per logical “process”.  
  - `$populate` operation (CQL-based `initialExpression`) for defaults and complex calculations (support to be added to openSRP).  
  - Launched via named triggers / named events (cpg-common-process style).  
  - Questionnaires **must** reference `planDefinitions` array and `cqlInputResources` (Library IDs).

- **Orchestration via PlanDefinition**  
  - `PlanDefinition`(s) use named triggers/events (cpg-common-process).  
  - Eligibility evaluation for patient + context → list of eligible PlanDefinitions.  
  - Post-selection, openSRP loops over named-events and displays next available Questionnaire(s).  
  - Propagate `care-plan-id` between sequential questionnaires / generate CarePlan/Task.

- **Data & Logic Handling**  
  - Relevance → `enableWhenExpression` (FHIRPath).  
  - Option relevance → `answerOptionsToggleExpression` on the parent choice item (FHIRPath; true = option enabled). See `fix/20260813-option-relevance-toggle.md`.
  - Constraints → item-level rules or `questionnaire-constraint` extensions.  
  - Images → FHIR `Binary` resources.  
  - Data extraction → FLM/StructureMap per Questionnaire (driven by concept_type → FHIR resource + data_type conversion).

- **Profiles, Terminology & Extensions**  
  - **Use openSRP profile** for all resources (user will validate/refine later).  
  - Choice lists expressed as ValueSets (TRICC already generates CodeSystems → reuse and create corresponding ValueSets).  
  - Extensions created only when required by openSRP.

- **Packaging (fhircore-specific)**  
  - Top-level `Composition` resource that references **all** generated resources (required manifest).  
  - `Binary` resources for images **and** for the configuration package itself.  
  - FSH files for every resource (ensures compliance with published FHIR IGs).  
  - Folder structure and resource references must match fhircore’s expected layout (questionnaire/, structuremap/, binary/, etc.).

---

### 2. TRICC Implementation Requirements (Fully Clarified)

- **Process Detection**  
  - Reusable `get_process()` helper (graph/visitor layer):  
    - If node is `activityMainStart` → return `node.process`.  
    - If current node belongs to an activity whose root is `activityMainStart` → return root.process.  
    - Otherwise recurse on previous node/activity.  
  - Groups nodes into exactly one `Questionnaire` per process.

- **Node-Type → FHIR Questionnaire.item Mapping**  
  Reuse/extend the `pyfhirsdc/converters/questionnaireItemConverter.py` pattern and create a documented mapping table (to be added to `docs/tricc-elements.md`):

  | TRICC Node Type       | FHIR Item Type                  | Notes / SDC Extensions |
  |-----------------------|---------------------------------|------------------------|
  | primitive (integer, decimal, text, date) | `question` + `answerValueType` | Straight-forward |
  | `select_multiple`     | `choice` (checkbox)             | `answerValueSet` + display_type → SDC extensions |
  | `select_one`          | `choice` (radio)                | `answerValueSet` + display_type → SDC extensions |
  | `select_yesno`        | `boolean`                       | Native boolean (preferred for yes/no questions). No answerOption. OpenSRP visible items also get `questionnaire-choiceOrientation`=`horizontal`.
  | `note` / display      | `display`                       | display_type handling |
  | `calculate`           | `question` + `calculatedExpression` (FHIRPath, live) when refs are in-form, else `initialExpression` (CQL via `$populate`) | — |
  | All others            | Defined in full table           | — |

  - `display_type` on any node → add corresponding SDC extensions exactly as in pyfhirsdc.

- **concept_type → Target FHIR Resource Mapping**  
  - **Reuse the existing openMRS mapping from pyfhirsdc** (manual per-concept mapping).  
  - Explicit rule: `Diagnosis` → `Condition`.  
  - This mapping drives FLM/StructureMap generation, profile selection, and data extraction.  
  - Note: OCL is the future standard; manual pyfhirsdc mapping is used for now.

- **Canonical URL / Naming / ID Conventions**  
  - Base: configurable per project **or** default `https://fhir.tricc.io`.  
  - Questionnaire: `{project_id}-{process}-{resource_type}`  
  - Library / FML: `{project_id}-{resource_type}`  
  - PlanDefinition: `{project_id}-PD`

- **CQL Library Structure**  
  - One **Helper** library providing generic data access functions (e.g. retrieval of Observations/Conditions by concept name/code, age helpers, etc.). Data access happens via FHIR resources, not raw questionnaire paths.
  - **Current-encounter scoping (2026-08-12)**: the Helper library declares a top-level `parameter encounterid String default null`, populated by the client at `$populate` time. `GetObservation(Value)`/`GetRepeated(Value)`/`GetNumberOfRepeat` and the new Condition family (`GetCondition(Value)`) filter by `encounter.reference = 'Encounter/' + encounterid`, returning nothing when absent (e.g. a visit's first process). This backs an auto-attached dedup `initialExpression` on answerable Observation/Condition-typed items with no author-authored expression, so a later process in the same visit doesn't re-ask what an earlier one already captured. `group` and `display` items (notes, activity/start containers) are never given `initial`/`initialExpression` — SDC forbids it and openSRP `$populate` throws `IllegalStateException` if they appear. See `feature/20260812-intervention-order-and-dedup.md`.
  - **Repeat-aware helpers** (when `repeat != 1` on capture nodes): `GetRepeated`, `GetRepeatedValue`, `GetNumberOfRepeat` — in `repeat_helper.py`. Repeat-index metadata is written onto the extracted Observation via a real executable FML rule in the per-process extraction StructureMap.
  - **History helpers** (any-time, *not* encounter-scoped): `GetHistoryObservation`/`GetHistoryObservationValue` (renamed 2026-08-12 from `GetHistory`/`GetHistoryValue` to disambiguate from the Condition family), `GetHistoryCondition`/`GetHistoryConditionValue` — replace legacy `GetLast` / `GetLastValue`.
  - **Populate helpers**: `GetPatientValue`, `GetFacilityValue`, `GetLocationValue`, `GetPractitionerValue`, `GetEncounterValue`, `GetHistoryObservationValue` — in `populate_helper.py`, injected into the Helper template.
  - Thin **per-process/segment** libraries that include the Helper and define named calculations (simple `define "Calc_xxx": ...` expressions, often delegating to the Helper).
  - A Questionnaire typically references only one main library (declared via the `library` element or SDC `cqlInputResources` extension).
  - Expressions in the Questionnaire use **simple define names** (e.g. `"Calc_bmi"`) with `text/cql-identifier` — but only inside `initialExpression`. `calculatedExpression` never carries CQL; it is FHIRPath referencing other Questionnaire items via `%resource.repeat(item).where(linkId=...)` (nested groups). Choice membership tests read `.answer.valueCoding.code`; primitives use `.answer.value`. See `fix/20260813-fhirpath-choice-answers.md`.
  - This design follows patterns from pyfhirsdc and WHO SMART CQL libraries.

- **Advanced TRICC Navigation**  
  - `goto`, `link_in`/`link_out`, `bridge`, multi-instance activities: already managed in the input strategy → no additional handling required.

- **Strategy Pattern Integration**  
  - New class `OpenSRPStrategy` inherits from `BaseOutputStrategy`.  
  - `convert(tricc_graph)` → directory containing JSON resources, FSH files, Composition, and Binary manifest.  
  - `validate()` checks openSRP/fhircore compatibility.  
  - Register in strategy factory; support CLI flag `-O OpenSRPStrategy`.

---

### 3. Remaining / Minor Open Aspects (Now Minimal)

1. Exact folder layout and Binary manifest details inside the Composition (final confirmation against latest fhircore docs – already largely covered).  
2. Full node-type mapping table (one-time creation; will be documented).

---

### Next Steps & Validation Checklist (Implementation-Ready)

- [x] Core FHIRStrategy + OpenSRPStrategy implemented (Questionnaire with FHIRPath/CQL expressions, CQL Library generation, StructureMap stubs, export).
- [x] `select_yesno` nodes now emit native `boolean` items (no answerOption).
- [x] OpenSRP visible boolean / yes-no items emit `questionnaire-choiceOrientation`=`horizontal`
      (`feature/20260819-boolean-choice-orientation.md`).
- [x] CQL architecture: Helper library for FHIR resource access by concept + thin per-segment libraries. Simple define names used in Questionnaire expressions.
- [x] Concept repeat: Questionnaire item extension + Helper repeat functions + FML hints (`repeat_helper.py`).
- [x] `FHIRStrategy` registered via `@register_output_strategy("FHIRStrategy")` and eager import in `strategies/__init__.py`.
- [x] Basic nesting support for groups/activities in Questionnaires.
- [x] Full StructureMap / data extraction driven by concept_type (CodeSystem `conceptType`: Symptom-Finding/Question → Observation; proposed_diagnosis → Condition provisional; AcceptDiag → confirmed/refuted; `repeat != 1` → Observation extension).
- [ ] Complete ValueSet generation.
- [x] Binary (images) generation — question/answer illustration images via `itemMedia`/
      `itemAnswerMedia` extensions (`contentType` + `Binary/<id>` URL) and per-image
      `Binary` resources (`fix/20260814-questionnaire-item-media.md`,
      `fix/20260818-item-media-binary-display.md`).
- [ ] Full $populate-ready wiring (Questionnaire.library declaration + properly qualified cql-identifier expressions).
- [ ] Comprehensive tests + golden CQL output validation.
- [ ] Documentation updates reflecting final CQL patterns (see this spec + user's pyfhirsdc reference implementation).

This specification (v4) is now **complete, precise, and implementation-ready**. All clarifications (including the latest on pyfhirsdc openMRS mapping, OCL note, fhircore Composition/Binary, and openSRP profile) have been ordered, cleaned, and integrated.

**Recommendation**: Create a GitHub issue titled “Add OpenSRPStrategy (FHIR-Core export)” with this spec as the description, then start with the `get_process()` utility + mapping table (these unblock everything else).  

Let me know if we should draft the PR skeleton / detailed implementation plan now or proceed directly to coding the first component!