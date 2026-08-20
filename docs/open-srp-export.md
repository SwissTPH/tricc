# OpenSRP / FHIR-Core Export

TRICC can export draw.io clinical decision support diagrams to a full
[FHIR R4](https://hl7.org/fhir/R4/) bundle compatible with
[OpenSRP 2 / FHIR-Core](https://docs.opensrp.io/fhir-core/).

---

## Overview

The `OpenSRPStrategy` extends the base `FHIRStrategy` and produces:

| Resource | Description |
|---|---|
| `Questionnaire` | SDC-profiled questionnaire with `enableWhenExpression` / `calculatedExpression` |
| `Library` | CQL logic library (one per cpg-common-process + shared helper) |
| `StructureMap` | Extraction map (Questionnaire → FHIR resources) |
| `ValueSet` | One per `select_one` / `select_multiple` question |
| `PlanDefinition` (Intervention) | **One per project** (today: one project = one Intervention); one wrapper action carrying `available-care` once, nested with one child `action` per **non-empty** process, **`definitionCanonical` → Questionnaire** (Start care / due now); each child's `trigger` is its own process named-event, plus `tricc-process`/`tricc-process-order` extensions |
| `StructureMap` (Task) | Optional Task maps for **upcoming planning** only (Questionnaire not due now) |
| `Composition` | Package manifest (not the openSRP app-id shell) |
| `Binary` | Image binaries only. Question/answer illustrations reference them from SDC `itemMedia` / `itemAnswerMedia` (`contentType` + `url: Binary/<id>`). Bytes stay on the shared `Binary` so one picture can be reused. The OpenSRP shell app configs (`application`, `sync`, …) are a separate Composition and are not generated here. |

**Artifact mode:** JSON only (no FSH dual-write). Empty questionnaires (`item: []`) are dropped.

**Launch rule:** Start care launches the **Questionnaire** now. Wrapping a Questionnaire in a
**Task** is reserved for the **planning** feature when the form is **not due now** (see
`feature/opensrp-register.md` §2.1 and `feature/opensrp-export-hygiene.md` §4).

---

## Quick Start

```bash
# Convert a draw.io file to OpenSRP FHIR-Core output
python tests/build.py \
  -i tests/data/demo.drawio \
  -o tests/output/opensrp/ \
  -O OpenSRPStrategy \
  -d my_form_id
```

### Output directory layout

```
tests/output/opensrp/
├── questionnaire/
│   └── Questionnaire-questionnaire-main.json   # readable name; id inside is UUID
├── library/
│   ├── Library-demo-tricc-Helper.json
│   └── Library-demo-tricc-main.json
├── plan-definition/
│   └── PlanDefinition-demo-tricc-intervention-PD.json   # 1 project = 1 Intervention; action[] = 1 per process
├── structure-map/
│   ├── StructureMap-demo-tricc-main-extract.json
│   ├── StructureMap-demo-tricc-main-extract.map
│   ├── StructureMap-demo-tricc-main-task.json
│   └── StructureMap-demo-tricc-main-task.map
├── binary/
│   └── Binary-<image-uuid>.json   # question/answer illustrations
├── Composition.json            # id inside is UUID
├── push-to-fhir.sh             # PUT {resourceType}/{json.id} — never the filename
└── env.fhir.example
```

Package **filenames** are human-readable. Server REST paths use the JSON **`id`**
(UUID). `push-to-fhir.sh` always reads `resourceType` + `id` from the file body.

### Push export to a FHIR server

After export, the package root contains `push-to-fhir.sh`, `compile-structuremap.sh`,
`env.fhir.example`, and a **`.env` seeded only if it does not already exist**
(re-export will not overwrite your credentials).

StructureMaps are authored as FML (`.map`). The JSON `group[]` TRicc writes is a
shell only. **`push-to-fhir.sh` compiles each sibling `.map` with HAPI
`StructureMapUtilities.parse` and PUTs that result.** A failed compile refuses
to upload the stub (OpenSRP executes JSON groups, not `text.div`).

```bash
cd tests/output/opensrp/<form_id>/
# edit .env (created once from env.fhir.example); secrets can go in .secrets

./push-to-fhir.sh
# or HAPI direct (no auth):
SKIP_AUTH=1 FHIR_BASE_URL=http://localhost:8082/fhir ./push-to-fhir.sh
```

The compiler needs `java` plus either a JDK (`javac`), Docker (`eclipse-temurin`),
or `FHIR_SM_COMPILER_JAR` / `FHIR_SM_COMPILER_CLASSPATH`. Postman uploads must
use the compiled JSON, not the stub file.

Credentials are read from the environment, then `.env`, then `.secrets` (later wins).
Do **not** commit `.env` / `.secrets`. Template sources:
`tricc_oo/strategies/output/templates/opensrp/`.
---

## Architecture

### Class hierarchy

```
BaseOutPutStrategy
└── FHIRStrategy          (standard FHIR SDC — Questionnaire, Library, StructureMap, ValueSet, Binary)
    └── OpenSRPStrategy   (adds PlanDefinition+Task AD, StructureMap, Composition)
```

### Processing pipeline

```
execute()
  ├── process_base()       → generate_base(node)      builds Questionnaire items
  ├── process_relevance()  → generate_relevance(node)  adds enableWhenExpression (FHIRPath)
  ├── process_calculate()  → generate_calculate(node)  adds CQL defines + calculatedExpression
  ├── process_export()     → generate_export(node)     builds StructureMap rules
  └── export()
        ├── [FHIRStrategy] write questionnaire/, library/, structure-map/, ValueSet/, binary/
        └── [OpenSRPStrategy]
              ├── _prune_empty_questionnaires()     → drop item: []
              ├── generate_intervention_plandefinition() → single PD, 1 action/process
              ├── generate_task_structuremap()      → Task map + next Task on done
              ├── _wire_questionnaire_extensions()  → cqlInputResources + planDefinitions on Q
              ├── generate_composition()            → Composition.json
              └── _write_image_binaries()           → binary/Binary-<uuid>.json
```

---

## Boolean / yes-no questions

Visible `select_yesno` items (and a `select_one` whose two options are a yes/no
pair) export as native FHIR `boolean`. OpenSRP also attaches a rendering hint so
the app lays Yes and No **side by side**:

```json
{
  "url": "http://hl7.org/fhir/StructureDefinition/questionnaire-choiceOrientation",
  "valueCode": "horizontal"
}
```

Hidden booleans (calculates, proposed diagnoses, waits) do not get the
extension. Generic `FHIRStrategy` export is unchanged. See
`feature/20260819-boolean-choice-orientation.md`.

---

## cpg-common-process Mapping

Each draw.io **activity** is mapped to a
[cpg-common-process](https://build.fhir.org/ig/HL7/cqf-recommendations/CodeSystem-cpg-common-process.html)
named event via the `process` attribute on `TriccNodeMainStart`.

The `get_process(node)` function (in `tricc_oo/visitors/tricc.py`) walks the
TRICC graph upward to find the process name for any node:

1. If the node itself is a `TriccNodeMainStart` → return `node.process`
2. If the node's activity root is a `TriccNodeMainStart` → return `root.process`
3. Recurse on the activity
4. Fallback: walk `prev_nodes`

Supported process names (from `tricc_oo/visitors/utils.py`):

```
registration, triage, clinical-assessment, determine-diagnosis,
guideline-based-care, dispense-medications, discharge-referral-of-patient,
record-and-report, monitor-and-follow-up-of-patient,
alert-reminder-education-of-patient, guideline-based-care,
dispense-medications, discharge-referral-of-patient,
record-and-report, monitor-and-follow-up-of-patient
```

---

## Expression System

### Relevance (enableWhen)

Relevance conditions from the TRICC graph are converted to **FHIRPath** using
`convert_expression_to_fhirpath()` and attached as an SDC
`enableWhenExpression` extension:

```json
{
  "url": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-enableWhenExpression",
  "valueExpression": {
    "language": "text/fhirpath",
    "expression": "%resource.repeat(item).where(linkId='age').answer.value >= 18"
  }
}
```

### Option relevance (answerOptionsToggleExpression)

A `relevance` on a **select option** (not the question) is emitted as SDC
`answerOptionsToggleExpression` on the parent choice item. The expression is FHIRPath;
when it is true the listed option is shown, otherwise it is hidden. Options without
relevance stay enabled.

```json
{
  "url": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-answerOptionsToggleExpression",
  "extension": [
    {"url": "option", "valueCoding": {"code": "demo.angry", "display": "Angry"}},
    {
      "url": "expression",
      "valueExpression": {
        "language": "text/fhirpath",
        "expression": "%resource.repeat(item).where(linkId='demo_filter').answer.where($this.exists()).value = true"
      }
    }
  ]
}
```

See `fix/20260813-option-relevance-toggle.md`.

### Calculations (calculatedExpression / initialExpression)

`calculatedExpression` **must be FHIRPath** — openSRP/FHIR-Core only evaluates CQL through
`initialExpression` (at `$populate` time). `generate_calculate()` picks the extension/language
per calculate node based on where its references live:

| At least one reference is an item in *this* Questionnaire | Extension | Language |
|---|---|---|
| Yes — value(s) can be read live via `%resource.repeat(item).where(linkId=...)` | `calculatedExpression` | `text/fhirpath` |
| No — depends only on data outside the form (e.g. observation history via the Helper) | `initialExpression` | `text/cql-identifier` |

In-form calculation (e.g. BMI from weight + height both answered in the same Questionnaire):

```json
{
  "url": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-calculatedExpression",
  "valueExpression": {
    "language": "text/fhirpath",
    "expression": "%resource.repeat(item).where(linkId='weight').answer.value / (%resource.repeat(item).where(linkId='height').answer.value * %resource.repeat(item).where(linkId='height').answer.value)"
  }
}
```

**Updated 2026-08-13** (`fix/20260813-fhirpath-choice-answers.md`):

- Item lookup always uses `%resource.repeat(item).where(linkId=...)` so questions nested
  in page/activity groups are found.
- Choice / open-choice answers are stored as `valueCoding`. Membership
  (`SELECTED` / option `CONTAINS`) emits
  `…answer.where(value.code = '<code>').exists()` (HAPI FHIRPath has no
  `valueCoding` child on `answer`). Do not use `'code' in …answer.valueCoding.code`.
- Page / activity groups take `enableWhenExpression` from `activity.relevance`
  (XLSForm begin-group relevant), not only the start node's own `relevance`.
- Boolean / numeric / string items still use `.answer.value`.
- A calculate whose expression is boolean is emitted as Questionnaire `type: boolean`.
- Casting a boolean (e.g. `COUNT(select) - SELECTED(opt_none)`) uses `iif(expr, 1, 0)`,
  not `.toDecimal()`.

Out-of-form calculation (depends on data not captured in this Questionnaire, e.g. observation
history from a prior process) still routes through CQL, but as a one-time `initialExpression`
rather than a live `calculatedExpression`. A shared **Helper** library provides data access via
FHIR resources (e.g. `GetObservationValue("concept.code")`); per-process libraries are thin
wrappers that expose named defines, referenced by **simple define name** (no library-qualified
paths in the Questionnaire).

**Updated 2026-08-12** (`feature/20260812-intervention-order-and-dedup.md`): `GetObservationValue`
(and the functions that delegate through it — `GetObservation`, `GetRepeated`, `GetRepeatedValue`,
`GetNumberOfRepeat`) are now scoped to the **current encounter** via a library-level
`encounterid` parameter (populated by the client at `$populate` time; returns nothing when absent,
e.g. the visit's first process). The Helper library also auto-attaches a dedup
`initialExpression` to **answerable** Observation/Condition-typed items (never `group` or
`display` — SDC forbids `initial`/`initialExpression` on those types, and openSRP FHIR Data
Capture throws at `$populate` if they appear) with no author-authored
populate/calculate expression, so a later process in the same visit doesn't re-ask a question an
earlier one already captured. For an any-time/cross-encounter lookback, use
`GetHistoryObservationValue`/`GetHistoryConditionValue` instead (see "Concept repeat" below).

```json
{
  "url": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression",
  "valueExpression": {
    "language": "text/cql-identifier",
    "expression": "Calc_bmi"
  }
}
```

Example generated CQL style (segment library):

```cql
include fhir_formHelper version '1.0.0' called Helper

define Calc_bmi: Helper.GetObservationValue("weight") / (Helper.GetObservationValue("height") * Helper.GetObservationValue("height"))
```

### Concept repeat (FHIR / CQL)

When a TRICC node has `repeat != 1`, export adds:

- **Questionnaire item extension** — `https://fhir.tricc.io/StructureDefinition/questionnaire-concept-repeat` (`valueInteger`)
- **Helper CQL functions** — current-encounter-scoped `GetRepeated`, `GetRepeatedValue`,
  `GetNumberOfRepeat`; any-time `GetHistoryObservation`, `GetHistoryObservationValue` (renamed
  from `GetHistory`/`GetHistoryValue` 2026-08-12 to disambiguate from the new Condition family);
  populate accessors `GetPatientValue`, `GetFacilityValue`, `GetLocationValue`,
  `GetPractitionerValue`, `GetEncounterValue` (see `populate_helper.py`); Condition equivalents
  `GetConditionValue`/`GetHistoryConditionValue` (see `repeat_helper.py`)
- **StructureMap extraction rule** — a real executable FML rule (not just a comment, fixed
  2026-08-12) sets the `https://fhir.tricc.io/StructureDefinition/observation-repeat-index`
  extension on the extracted Observation

CQL references to repeated concepts use `Helper.GetRepeatedValue("code", n)` when `n != 1`;
default slot (`repeat=1`) uses `Helper.GetObservationValue("code")`.

Authoring surface: `repeat` on capture nodes or `activity_start` in draw.io / YAML.
See [TRICC Elements — Concept repeat](./tricc-elements.md#concept-repeat).

---

## PlanDefinition

**One** `PlanDefinition` resource is exported per project — see
`feature/careplan-intervention-plandefinition.md` for the full rationale and scope. Today
**one project = one Intervention**; multi-Intervention / multi-CarePlan orchestration and
applicability/eligibility gating are future work (`feature/careplan-claude.md`).

An earlier revision also exported a second, wrapping `{form_id}-available-care-catalog`
PlanDefinition (top action triggered by `available-care`, single child action linking down to
the Intervention PD). **Removed 2026-08-12**: fhircore's `NamedEventInterventionService`
resolves a linked PlanDefinition's child actions unconditionally (no applicability check), so
the catalog produced one extra, unfiltered "Start care" list entry per process action instead
of a single clean one. See §8 "Findings" trail in `feature/careplan-intervention-plandefinition.md`.

### Intervention PlanDefinition

**Updated 2026-08-12** (`feature/20260812-intervention-order-and-dedup.md`): one PlanDefinition
for the whole project, with a single **wrapper action** carrying the `available-care` trigger
once, nested with **one child `action` per non-empty process**
(**1 process = 1 action = 1 Questionnaire**):

- **status**: `active`
- **library**: references to every process's CQL Library
- **action[0]** (wrapper): `trigger` = `[{named-event, "available-care"}]` only — this is what
  `NamedEventInterventionService` discovers, not the per-process children directly. This is
  same-resource nesting (`action.action`), not a second linked PlanDefinition — same-resource
  children still get their own applicability check in fhircore, unlike the removed catalog PD.
- **action[0].action[]** (one per process): `trigger` = the process's own named-event
  (cpg-common-process name when known); **two new extensions**:
  - `tricc-process` (`valueString`, the process name)
  - `tricc-process-order` (`valueInteger`, a fixed order — 10, 20, 30… by the canonical
    cpg-common-process list order in `tricc_oo/visitors/utils.py: PROCESS_ORDER`; unrecognized
    process names get the next free slot past the table's max). Comparable across different
    PlanDefinitions, so a client juggling several selected Interventions can pick "whichever
    unlocked action has the lowest order."
  - **definitionCanonical**: **Questionnaire** absolute URL (launch form **now**)
- **No** contained Task ActivityDefinition / **no** `transform`, and no applicability
  `condition` yet (every action is unconditionally listed)

Empty questionnaires (`"item": []`) are **removed** from the package (no action, no library
entry for that process).

### Task-wrapped Questionnaire (planning — not due now)

**Upcoming planning feature only.** When a form is scheduled but **not due now**, export may
use ActivityDefinition (`kind: Task`) + StructureMap so the client holds a Task
(`reasonReference` → Questionnaire) until due. That path is **not** used for Start care.

Optional Task StructureMaps may still be written under `structure-map/` for multi-process
experiments; they are **not** wired as the Intervention PD's `definitionCanonical` for
available-care.

See **`feature/opensrp-register.md`** §2.1 and **`feature/opensrp-export-hygiene.md`** §4.

```json
{
  "resourceType": "PlanDefinition",
  "id": "…-uuid… (Intervention PD)",
  "status": "active",
  "library": ["https://fhir.tricc.io/Library/…"],
  "action": [
    {
      "id": "available-care",
      "title": "… – Available care",
      "trigger": [{ "type": "named-event", "name": "available-care" }],
      "action": [
        {
          "title": "Registration",
          "trigger": [{ "type": "named-event", "name": "registration" }],
          "extension": [
            { "url": "https://fhir.tricc.io/StructureDefinition/tricc-process", "valueString": "registration" },
            { "url": "https://fhir.tricc.io/StructureDefinition/tricc-process-order", "valueInteger": 30 }
          ],
          "definitionCanonical": "https://fhir.tricc.io/Questionnaire/…"
        },
        {
          "title": "Triage",
          "trigger": [{ "type": "named-event", "name": "triage" }],
          "extension": [
            { "url": "https://fhir.tricc.io/StructureDefinition/tricc-process", "valueString": "triage" },
            { "url": "https://fhir.tricc.io/StructureDefinition/tricc-process-order", "valueInteger": 10 }
          ],
          "definitionCanonical": "https://fhir.tricc.io/Questionnaire/…"
        }
      ]
    }
  ]
}
```

---

## Questionnaire Extensions (openSRP wiring)

The `_wire_questionnaire_extensions()` method adds two openSRP-specific
extensions to each Questionnaire:

### `cqlInputResources`

Points to the CQL Library for this process:

```json
{
  "url": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-launchContext",
  "extension": [
    { "url": "name", "valueId": "<form_id>-<process>" },
    { "url": "type", "valueCode": "Library" }
  ]
}
```

### `planDefinitions`

References the shared **Intervention** PlanDefinition (every process's Questionnaire points
at the same one — see "PlanDefinition" above):

```json
{
  "url": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-planDefinitions",
  "valueReference": { "reference": "https://fhir.tricc.io/PlanDefinition/<intervention-pd-id>" }
}
```

---

## StructureMap (Extraction)

Each process gets a QuestionnaireResponse → transaction `Bundle` StructureMap
(under `structure-map/`, referenced from the Questionnaire via SDC
`targetStructureMap`). HAPI / OpenSRP run the compiled JSON `group[]`, not the
narrative in `text.div`. The export `.map` is compiled at push time. Classification uses the CodeSystem `conceptType` property
(the same class `xml_to_tricc.get_concept_type` writes), then the node's
`concept_type`, then a node-type fallback.

| Codesystem `conceptType` / node | Extracted resource | Notes |
|---|---|---|
| `Symptom-Finding`, `Question`, `finding`, `observation`, `vital`, `lab`, `test` | `Observation` (`status=final`) | Answer copied to `value[x]` |
| `proposed_diagnosis` / `Diagnosis` (proposed node) | `Condition` | `clinicalStatus=active`, `verificationStatus=provisional` (only when the hidden boolean is true) |
| AcceptDiag (`pre_final.{code}`) | `Condition` | Accept → `verificationStatus=confirmed`; Reject → `refuted` + `clinicalStatus=inactive`. Same concept code as the proposed diagnosis. |
| Node with `repeat != 1` | Observation extension | `https://fhir.tricc.io/StructureDefinition/observation-repeat-index` (`valueInteger`) |
| `Calculation` (`final.{code}`), `InteractSet` (notes), `Value` (options), diagnosis anchors | *(not extracted)* | Confirmed status is the AcceptDiag extract (and CQL `HasConfirmedCondition`) |

`final.{code}` stays an in-form calculate (FHIRPath from Accept/manual) for the
determine-diagnosis Questionnaire. Later processes read confirmation through
Helper CQL (`HasConfirmedCondition` / `GetConditionValue`, which ignore
`refuted`). Optional Task StructureMaps (`*-task`) remain planning-only and are
**not** the Questionnaire `targetStructureMap`.

---

## Artifact mode (JSON only)

OpenSRPStrategy writes **FHIR JSON only**. Dual-writing hand-built JSON plus FSH was
dropped because SUSHI-generated resources were incomplete relative to the Python export.
The FSH serializer remains available for other tooling; OpenSRP packages do not emit `fsh/`.

## FHIR resource ids

HAPI / openSRP require legal FHIR R4 ids: **`[A-Za-z0-9.-]{1,64}`** (no underscores).

Server-facing resource **`id`** values are **UUIDs** (openSRP-style REST addressing),
generated deterministically with UUID5 from form id + resource type + process/role so
re-exports stay stable for PUT upserts. Human-readable tokens stay in **`name`** /
**`title`**, CQL library names, and **on-disk filenames**.

| Concern | Source |
|---------|--------|
| REST URL | `PUT {base}/{resourceType}/{json.id}` (UUID) |
| Package file | `PlanDefinition-demo-tricc-main-PD.json` (from `name`) |

`push-to-fhir.sh` skips `contract/`, ignores filename stems for URLs, and fails early
if any resource `id` is invalid. Re-export cleans stale UUID-named files from older builds.

---

## Testing

```bash
# Run all tests (project venv recommended)
.venv/bin/python -m unittest discover -s tests -p "test_*.py" -v

# FHIR / OpenSRP focused tests
.venv/bin/python -m unittest tests.test_strategies.test_opensrp_strategy tests.test_fhir_repeat -v

# Full integration test (requires a draw.io file)
.venv/bin/python tests/build.py \
  -i tests/data/demo.drawio \
  -o tests/output/opensrp/ \
  -O FHIRStrategy \
  -l i

.venv/bin/python tests/build.py \
  -i tests/data/demo.drawio \
  -o tests/output/opensrp/ \
  -O OpenSRPStrategy \
  -l i
```

---

## Key Files

| File | Purpose |
|---|---|
| `tricc_oo/strategies/output/opensrp.py` | `OpenSRPStrategy` class |
| `tricc_oo/strategies/output/templates/opensrp/` | `push-to-fhir.sh` + `env.fhir.example` (copied into export) |
| `tricc_oo/converters/fhir/related_person.py` | RelatedPerson contract helpers (PI identifier, roles) |
| `feature/opensrp-register.md` | Flexible client register + available-care export contract |
| `tricc_oo/strategies/output/fhir_form.py` | `FHIRStrategy` base class |
| `tricc_oo/converters/fhir/questionnaire_item_mapper.py` | Node type → FHIR item type mapping |
| `tricc_oo/converters/fhir/concept_mapper.py` | Concept type → FHIR resource mapping |
| `tricc_oo/converters/fhir/structuremap.py` | QuestionnaireResponse extraction StructureMap / FML |
| `tricc_oo/converters/fhir/fsh_serializer.py` | FHIR dict → FSH text serializer |
| `tricc_oo/converters/fhir/repeat_helper.py` | Concept repeat extensions + Helper CQL block |
| `tricc_oo/visitors/tricc.py` | `get_process()` graph walker |
| `tricc_oo/strategies/__init__.py` | Eager strategy registration imports |
| `tests/test_strategies/test_opensrp_strategy.py` | OpenSRP / FHIR unit + smoke tests |
| `tests/test_fhir_repeat.py` | Repeat-aware FHIR/CQL export tests |

---

## References

- [FHIR R4 Specification](https://hl7.org/fhir/R4/)
- [SDC Implementation Guide](https://hl7.org/fhir/uv/sdc/)
- [CPG Implementation Guide](https://build.fhir.org/ig/HL7/cqf-recommendations/)
- [OpenSRP FHIR-Core Documentation](https://docs.opensrp.io/fhir-core/)
- [FHIR Shorthand (FSH)](https://build.fhir.org/ig/HL7/fhir-shorthand/)
- [SUSHI Compiler](https://fshschool.org/docs/sushi/)
