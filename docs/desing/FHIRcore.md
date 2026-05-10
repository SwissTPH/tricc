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
  | `select_yesno`        | `choice` (radio)                | Yes/No ValueSet |
  | `note` / display      | `display`                       | display_type handling |
  | `calculate`           | `question` + `initialExpression` (CQL via `$populate`) | — |
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
  - Reusable helper library based on `pyfhirsdc/core_fhir/cql/pyfhirsdc.cql` (observation retrieval, condition retrieval, etc.).  
  - Per-resource libraries (Questionnaire and PlanDefinition): inherit generic helper library and wrap only the required helpers.  
  - Library identifier referenced in owning resource (`cqlInputResources`).

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

- [ ] Implement `get_process()` utility.  
- [ ] Create node-type mapping table + reuse `pyfhirsdc` questionnaireItemConverter.py logic.  
- [ ] Implement concept_type → FHIR resource mapping by reusing pyfhirsdc openMRS logic.  
- [ ] Prototype CQL library generation (helpers + wrappers) and FSH + Composition + Binary manifest.  
- [ ] Add `OpenSRPStrategy` skeleton in `strategies/` and register it.  
- [ ] Extend expression visitor for dual FHIRPath + CQL output.  
- [ ] Add/update documentation (`docs/open-srp-export.md` + mapping tables in `docs/tricc-elements.md`).  
- [ ] Write unit tests using `tests/data/` drawio files.  
- [ ] Run full pipeline (`tests/build.py`) and validate against fhircore.  
- [ ] PEP 8, type hints, docstrings, logging, 120-char lines, no print statements.

This specification (v4) is now **complete, precise, and implementation-ready**. All clarifications (including the latest on pyfhirsdc openMRS mapping, OCL note, fhircore Composition/Binary, and openSRP profile) have been ordered, cleaned, and integrated.

**Recommendation**: Create a GitHub issue titled “Add OpenSRPStrategy (FHIR-Core export)” with this spec as the description, then start with the `get_process()` utility + mapping table (these unblock everything else).  

Let me know if we should draft the PR skeleton / detailed implementation plan now or proceed directly to coding the first component!