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
| `PlanDefinition` | One per cpg-common-process; named-event trigger + applicability condition |
| `Composition` | Manifest listing all resources for the form package |
| `Binary` | App config JSON (base64) + image binaries |
| FSH files | FHIR Shorthand for all of the above (SUSHI-ready) |

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
│   └── Questionnaire-<process>.json
├── library/
│   ├── Library-<form_id>-<process>.json
│   └── Library-<form_id>Helper.json
├── structure-map/
│   └── StructureMap-<process>.json
├── ValueSet/
│   └── ValueSet-<node_id>.json
├── plan-definition/
│   └── PlanDefinition-<process>.json
├── binary/
│   ├── Binary-config.json
│   └── Binary-<node_id>.json   # images
├── Composition.json
└── fsh/
    ├── Questionnaire-<process>.fsh
    ├── Library-<form_id>-<process>.fsh
    ├── PlanDefinition-<process>.fsh
    ├── Composition.fsh
    └── ...
```

---

## Architecture

### Class hierarchy

```
BaseOutPutStrategy
└── FHIRStrategy          (standard FHIR SDC — Questionnaire, Library, StructureMap, ValueSet, Binary)
    └── OpenSRPStrategy   (adds PlanDefinition, Composition, Binary config, FSH, openSRP wiring)
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
              ├── generate_plandefinition(process)  → plan-definition/
              ├── _wire_questionnaire_extensions()  → cqlInputResources + planDefinitions on Q
              ├── generate_composition()            → Composition.json
              ├── generate_binary_config()          → binary/Binary-config.json
              └── _write_fsh_files()                → fsh/
```

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
    "expression": "%resource.item.where(linkId='age').answer.value >= 18"
  }
}
```

### Calculations (calculatedExpression / initialExpression)

Calculate nodes (and some relevance logic) are converted to **CQL** using
`convert_expression_to_cql()`. A shared **Helper** library provides data
access via FHIR resources (e.g. `GetObsValue("concept.code")`). Per-process
libraries are thin wrappers that expose named defines.

In the Questionnaire, expressions use **simple define names** (the
Questionnaire declares its library/libraries at the top level):

```json
{
  "url": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-calculatedExpression",
  "valueExpression": {
    "language": "text/cql-identifier",
    "expression": "Calc_bmi"
  }
}
```

Example generated CQL style (segment library):

```cql
include fhir_formHelper version '1.0.0' called Helper

define Calc_bmi: Helper.GetObsValue("weight") / (Helper.GetObsValue("height") * Helper.GetObsValue("height"))
```

---

## PlanDefinition

Each cpg-common-process gets a `PlanDefinition` with:

- **trigger**: `named-event` → `cpg-common-process-<process>`
- **condition**: CQL applicability expression `"Is Applicable"`
- **action**: `definitionCanonical` pointing to the Questionnaire

```json
{
  "resourceType": "PlanDefinition",
  "id": "pd-registration",
  "status": "active",
  "trigger": [{ "type": "named-event", "name": "cpg-common-process-registration" }],
  "action": [{
    "title": "Fill registration form",
    "definitionCanonical": "http://example.org/Questionnaire/registration",
    "condition": [{
      "kind": "applicability",
      "expression": { "language": "text/cql", "expression": "Is Applicable" }
    }]
  }]
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

References the PlanDefinition for this process:

```json
{
  "url": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-planDefinition",
  "valueCanonical": "http://example.org/PlanDefinition/pd-<process>"
}
```

---

## StructureMap (Extraction)

Each node with a `concept` attribute generates a StructureMap rule that
extracts the answer into the appropriate FHIR resource:

| TRICC concept type | FHIR resource | Profile |
|---|---|---|
| `diagnosis` | `Condition` | `http://hl7.org/fhir/StructureDefinition/Condition` |
| `proposed_diagnosis` | `Condition` | `http://hl7.org/fhir/StructureDefinition/Condition` |
| `observation` | `Observation` | `http://hl7.org/fhir/StructureDefinition/Observation` |
| `medication` | `MedicationRequest` | `http://hl7.org/fhir/StructureDefinition/MedicationRequest` |
| `procedure` | `Procedure` | `http://hl7.org/fhir/StructureDefinition/Procedure` |
| `encounter` | `Encounter` | `http://hl7.org/fhir/StructureDefinition/Encounter` |

---

## FSH Output

All resources are also serialized to
[FHIR Shorthand (FSH)](https://build.fhir.org/ig/HL7/fhir-shorthand/)
in the `fsh/` subdirectory, ready for compilation with
[SUSHI](https://fshschool.org/docs/sushi/).

The FSH serializer (`tricc_oo/converters/fhir/fsh_serializer.py`) supports:

- `Questionnaire` → `Instance: … InstanceOf: SDCQuestionnaireExtract`
- `Library` → `Instance: … InstanceOf: Library`
- `StructureMap` → `Instance: … InstanceOf: StructureMap`
- `ValueSet` → `ValueSet: …` with concept includes
- `PlanDefinition` → `Instance: … InstanceOf: PlanDefinition`
- `Composition` → `Instance: … InstanceOf: Composition`
- `Binary` → `Instance: … InstanceOf: Binary`
- Any other resource type → generic `Instance` with JSON comments

---

## Testing

```bash
# Run all strategy tests
python -m pytest tests/test_strategies/ -v

# Run a specific test class
python -m pytest tests/test_strategies/test_opensrp_strategy.py::TestFshSerializer -v

# Full integration test (requires a draw.io file)
python tests/build.py \
  -i tests/data/demo.drawio \
  -o tests/output/opensrp/ \
  -O OpenSRPStrategy \
  -l d
```

---

## Key Files

| File | Purpose |
|---|---|
| `tricc_oo/strategies/output/opensrp.py` | `OpenSRPStrategy` class |
| `tricc_oo/strategies/output/fhir_form.py` | `FHIRStrategy` base class |
| `tricc_oo/converters/fhir/questionnaire_item_mapper.py` | Node type → FHIR item type mapping |
| `tricc_oo/converters/fhir/concept_mapper.py` | Concept type → FHIR resource mapping |
| `tricc_oo/converters/fhir/fsh_serializer.py` | FHIR dict → FSH text serializer |
| `tricc_oo/visitors/tricc.py` | `get_process()` graph walker |
| `tests/test_strategies/test_opensrp_strategy.py` | Unit tests |

---

## References

- [FHIR R4 Specification](https://hl7.org/fhir/R4/)
- [SDC Implementation Guide](https://hl7.org/fhir/uv/sdc/)
- [CPG Implementation Guide](https://build.fhir.org/ig/HL7/cqf-recommendations/)
- [OpenSRP FHIR-Core Documentation](https://docs.opensrp.io/fhir-core/)
- [FHIR Shorthand (FSH)](https://build.fhir.org/ig/HL7/fhir-shorthand/)
- [SUSHI Compiler](https://fshschool.org/docs/sushi/)
