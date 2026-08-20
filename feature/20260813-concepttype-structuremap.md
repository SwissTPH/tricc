# ConceptType-driven StructureMap extraction (Observation, Condition, AcceptDiag)

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `feature/zscore` (current branch) |
| **Related** | `feature/concept-repeat.md` (repeat-index extension on extracted Observations), `feature/20260812-intervention-order-and-dedup.md` (Condition CQL family / current-encounter helpers), `docs/desing/FHIRcore.md` Phase 3, `docs/open-srp-export.md` |
| **Approval** | Implemented from the 2026-08-13 conversation (user asked for StructureMaps driven by codesystem `conceptType`, Observation repeat extension, proposed diagnosis → Condition, AcceptDiag → confirmed/refuted). Spec written after the code landed — the Draft → Approved gate was skipped. |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business description

*Audience: clinical authors, guideline developers, implementers evaluating TRICC / OpenSRP workflows.*

## 1. Overview

When a clinician finishes a TRICC form in OpenSRP, the answers must become real FHIR
records — measurements as Observations, classifications as Conditions — not a pile of
anonymous questionnaire fields. This feature makes that extraction follow the **concept
class already stored on each concept in the project's CodeSystem** (the same
`conceptType` authors see in the terminology: Symptom-Finding, Question, Diagnosis, …).

It also closes two clinical gaps:

1. **Repeat readings** of the same concept (temperature at triage, then again after
   treatment) are stored as separate Observations, tagged with which repeat slot they
   belong to, so later look-ups can tell them apart.
2. **Proposed diagnoses** become Conditions with a *provisional* status. When the
   clinician Accepts or Rejects that proposal in the confirm-diagnosis step, the matching
   Condition is written as *confirmed* or *refuted*. Intermediate "final.…" flags stay
   inside the form logic; they are not a second clinical record.

## 2. What authors and implementers see

- No new draw.io attributes. Classification uses the CodeSystem `conceptType` already
  written when the diagram is loaded (or the node's `concept_type` if the author set one).
- Questionnaires that capture findings extract to Observations on submit.
- A `proposed_diagnosis` node extracts to a Condition (`verificationStatus = provisional`)
  when the proposal is true.
- The generated Accept/Reject question (`pre_final.{code}`) extracts to a Condition with
  the **same concept code**: Accept → confirmed, Reject → refuted.
- The `final.{code}` calculate that XLSForm uses as "this classification is confirmed"
  is **not** written as a FHIR resource. Later processes ask the Helper
  (`HasConfirmedCondition` / `GetConditionValue`) instead.
- If a capture node has `repeat` other than 1, the Observation carries a repeat-index
  extension so CQL `GetRepeated` / `GetNumberOfRepeat` can find the right slot.

## 3. Benefits

- Extraction matches the terminology model instead of dumping every item into Observation.
- Proposed vs confirmed vs rejected diagnoses are visible on Condition.verificationStatus.
- Repeat slots survive persist/read, which the CQL helpers already assumed.
- OpenSRP loads the map from the Questionnaire's `targetStructureMap` (by StructureMap id).

## 4. Limitations

- MedicationRequest / Procedure / ServiceRequest concept classes are mapped in the
  concept table but **not extracted** in this pass (no dedicated node type yet — see
  `feature/20260812-medication-request-dispense-node.md`).
- Accept/Reject **creates** a new Condition with the updated status (same code, later
  `recordedDate`). It does not PATCH the provisional resource. Readers take the latest
  non-refuted Condition.
- `repeat` on diagnosis / proposed_diagnosis is still out of scope
  (`feature/concept-repeat.md`).
- The demo diagram has no proposed diagnoses, so the demo extract map is Observation-only.

---

# Part II — Technical specification

*Audience: TRICC developers.*

## 5. Classification

Order used by `resolve_concept_type` (`tricc_oo/converters/fhir/concept_mapper.py`):

1. Explicit `node.concept_type`
2. CodeSystem concept property `conceptType` for `node.name`
3. Node-type fallback (same rules as `xml_to_tricc.get_concept_type`)

`classify_extraction` then returns:

| Kind | When | Extracted resource |
|------|------|--------------------|
| `observation` | Symptom-Finding, Question, finding, observation, vital, lab, test, sign, labset | Observation (`status=final`). Hidden boolean / option-selected flags extract only when the answer is true and write `valueBoolean = true`. |
| `proposed_condition` | `TriccNodeProposedDiagnosis` / `proposed_diagnosis` | Condition, `verificationStatus=provisional`, `clinicalStatus=active`, only if answer is true |
| `accept_condition` | `TriccNodeAcceptDiagnostic` (`pre_final.{code}`) | Condition, same bare concept code: true → confirmed/active; false → refuted/inactive |
| *(skip)* | Calculation (`final.{code}`), InteractSet (notes), Value (options), `TriccNodeDiagnosis` anchors (`anchor.{code}`), Misc | Not extracted |

Condition code for AcceptDiag / `final.` / `anchor.` strips that prefix
(`diagnosis_concept_code`).

## 6. StructureMap shape

One extraction StructureMap **per Questionnaire / process**:

- Source: `QuestionnaireResponse`
- Target: transaction `Bundle`
- Groups: `extract` → `extractItems` (walks nested `item.item`) → one group per rule
- Companion `.map` FML is the authored mapping. JSON `group[]` in the export
  shell is **not** executed. `push-to-fhir.sh` compiles the `.map` with HAPI
  `StructureMapUtilities.parse` before PUT (see `fix/20260817-structuremap-fml-compile.md`)
- REST `id` = `fhir_resource_id(form, "StructureMap", process, "extract")`
- Written under `structure-map/` next to the existing planning Task maps
- Questionnaire SDC extension
  `sdc-questionnaire-targetStructureMap` → extract map canonical
- Composition lists extract maps first, then Task maps

Rules are keyed by **which Questionnaire already contains the item's `linkId`**, not by
`get_process(node)`. Group nesting can place items under `main` while the graph process
is `registration`; keying by process caused prune-empty to drop the real map.

## 7. Repeat index

When `repeat != 1` and the kind is `observation`, the Observation group stamps:

```
https://fhir.tricc.io/StructureDefinition/observation-repeat-index
valueInteger = <repeat>
```

CQL `ObservationRepeatIndex` / `GetRepeated*` already read this URL
(`tricc_oo/converters/fhir/repeat_helper.py`). Conditions are not repeated in this pass.

## 8. CQL (confirm path, not a second extract)

`final.{code}` stays an in-form FHIRPath calculate when AcceptDiag lives in the same
Questionnaire. It is **not** extracted.

Helper additions (current-encounter scoped like the rest of the Condition family):

- `ConditionVerificationCode`
- `GetActiveConditions` — excludes `refuted` and `entered-in-error`
- `GetCondition` / `GetConditionValue` — now use the active list
- `HasProvisionalCondition` / `HasConfirmedCondition` / `HasRefutedCondition`

So later processes do not treat a rejected proposal as still present.

## 9. Code checklist

- [x] `concept_mapper.py` — OpenMRS/codesystem class names + `classify_extraction`
- [x] `converters/fhir/structuremap.py` — FML + StructureMap JSON builder
- [x] `FHIRStrategy.generate_export` / `_assemble_extraction_maps` / export writer
- [x] `OpenSRPStrategy` — `targetStructureMap`, Composition, prune, app-id tags
- [x] Repeat FML on Observation target (`fml_repeat_extension_on_target`)
- [x] Helper CQL Condition verification family
- [x] Tests: `tests/test_strategies/test_fhir_structuremap.py` (+ mapper / repeat updates)
- [x] Docs: `docs/desing/FHIRcore.md`, `docs/open-srp-export.md`

## 10. Acceptance criteria

1. Symptom-Finding / Question items emit Observation extract groups with the CodeSystem
   URL and concept code (not the stub `linkId -> Observation.linkId` map).
2. `repeat != 1` writes the observation-repeat-index extension in executable FML.
3. proposed_diagnosis → Condition provisional (answer true only).
4. AcceptDiag → Condition confirmed or refuted on the matching concept code.
5. `final.{code}` / notes / options / diagnosis anchors are not extracted.
6. Questionnaire `targetStructureMap` is the extract map, not the Task planning map.
7. Empty-questionnaire prune does not drop extract rules that live on another process's
   Questionnaire.

## 11. Out of scope

- Extracting MedicationRequest / Procedure / ServiceRequest
- PATCH/upsert of the provisional Condition (POST of a new status resource only)
- Repeat index on Conditions
- Changing the determine-diagnosis authoring graph
