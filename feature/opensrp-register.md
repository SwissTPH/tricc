# OpenSRP Flexible Client Register — TRICC Export Contract

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `develop` |
| **Related** | `docs/open-srp-export.md`, `docs/desing/FHIRcore.md`, openSRP `android/feature/register-tricc.md` |
| **Named event (default)** | `available-care` |
| **Strategy** | `OpenSRPStrategy` |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business description

## 1. Overview

TRICC’s **OpenSRPStrategy** must export FHIR content that openSRP FHIRCore can consume for:

1. A **single All clients** register (Patient-based) — **no** separate household TRICC register.
2. **Client profile** relations via **RelatedPerson** (parents/guardians and children).
3. **Dynamic interventions**: app only hardcodes named-event `available-care`; PlanDefinitions (with applicability) are synced and discovered at runtime.
4. **Add related person** with invariant: **`RelatedPerson.patient` always = the child**.

This document is the **TRICC export contract** (WP5). Runtime UX and Android wiring live in `android/feature/register-tricc.md`.

## 2. What OpenSRPStrategy must emit

| Artifact | Purpose |
|----------|---------|
| Questionnaire + Library + StructureMap per process | Forms and extraction |
| **Intervention PlanDefinition** (one per project, the **only** PlanDefinition exported) | One wrapper action carrying `available-care` once, nested with one child `action` per process; each child's own `trigger` is its process-name named-event, plus `tricc-process`/`tricc-process-order` extensions; **`definitionCanonical` → Questionnaire** (see `feature/careplan-intervention-plandefinition.md` for the nesting, `feature/20260812-intervention-order-and-dedup.md` for the 2026-08-12 wrapper-action + order change; no separate CarePlan/catalog PD) |
| Composition | **Package** manifest (not the OpenSRP app-id shell) |
| RelatedPerson contract (Binary + helpers) | Registration / add-relation extraction rules |
| Task / ActivityDefinition StructureMaps | **Optional export** today; **not** used for Start care launch (see §2.1) |

### 2.1 Questionnaire launch vs Task-wrapped Questionnaire (planning)

| Path | When | PD `action.definitionCanonical` | Runtime |
|------|------|----------------------------------|---------|
| **Start care / due now** | Intervention is applicable **now** | **Questionnaire** absolute URL | openSRP `APPLY_NAMED_EVENT` lists options and **launches the form directly** |
| **Planning / not due now** | Upcoming **planning** feature: schedule work for later | Contained **ActivityDefinition (`kind: Task`)** + transform → Task with `reasonReference` → Questionnaire | Task appears on a **task register** / worklist until due; then open the Questionnaire |

**Contract:** wrapping a Questionnaire in a **Task** is reserved for the **planning** track — when the form is **not due now**. Do **not** use Task/AD as the Start-care launch target.

Task StructureMaps (`generate_task_structuremap`) may still be emitted for multi-process chaining experiments; they are **not** wired as the Intervention PD's `definitionCanonical` for the available-care picker until planning lands.

## 3. App vs content responsibility

| Concern | Owner |
|---------|--------|
| Named-event string `available-care` | App config only |
| Intervention list & eligibility | Synced PlanDefinitions (this export) |
| All clients register UI | App config (thin) |
| RelatedPerson shape | **This contract** + registration StructureMaps |
| App-id Composition (`cdss`) | **Shell only** (Binaries + registration Q/SM) — not rewritten per form |
| Multi-form content delivery | Tag resources with app id + **sync**; package Composition is export/audit, not app bootstrap |

### 3.1 Package Composition must not collide with the shell

OpenSRP loads **one** Composition for the app id (`Composition?identifier={appId}` → first match).

| Rule | Detail |
|------|--------|
| Package `Composition.identifier` | Use `system = https://fhir.tricc.io` (or similar), **never** `value = cdss` / app id |
| Clinical resources | Tag `meta.tag` with `system = https://smartregister.org/app-id`, `code = {appId}` (**OpenSRPStrategy stamps this** via `OPENSRP_APP_ID` / `FHIR_APP_ID`, default `cdss`) |
| StructureMap id | Last segment of Questionnaire `targetStructureMap` canonical (device loads by id) |
| Shell registration Q/SM | Owned by the Android/platform seed, not each TRICC form package |
| Device sync query | `ResourceType?_tag=https://smartregister.org/app-id\|{appId}` (cdss shell `sync_config.json`) |
| PlanDefinition status | **`active`** (not draft) so runtime discovery treats interventions as live |
| Questionnaire `subjectType` | **`["Patient"]`** required — openSRP toast *Missing subject type* without it |
| Questionnaire status | Prefer **`active`** (not draft) for forms launched from Start care |

Preferred multi-package model: **shell Composition + tagged sync** (see openSRP `android/feature/register-tricc.md` Part V-bis). Multi-Composition search-from-shell is a possible future app feature, not current OpenSRP behaviour.

**Gateway:** content GETs by `_tag` must be on the sync-filter **skip list** (`SYNC_FILTER_IGNORE_RESOURCES_FILE`), or the gateway injects org/location `_tag` and ANDs hide app-id-only packages. POC override: openSRP `conf/gateway/hapi_sync_filter_ignored_queries.json`.

---

# Part II — RelatedPerson contract

## 4. Rules

1. Mother, father, guardian are always **`Patient`** clients (never RelatedPerson-only).
2. Child is always a **`Patient`**.
3. **`RelatedPerson.patient` always references the child**.
4. Role uses standard codes: `MTH`, `FTH`, `GUARD` (RoleCode / RoleClass).
5. Parent/guardian client link uses **`RelatedPerson.identifier`** (not a custom extension).

## 5. Identifier (Patient client link)

| Field | Value |
|-------|--------|
| `use` | `secondary` |
| `type` | v2-0203 **`PI`** (Patient internal identifier) |
| `system` | `urn:ietf:rfc:3986` |
| `value` | `Patient/{id}` or absolute Patient URL |

```json
{
  "resourceType": "RelatedPerson",
  "identifier": [{
    "use": "secondary",
    "type": {
      "coding": [{
        "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
        "code": "PI",
        "display": "Patient internal identifier"
      }]
    },
    "system": "urn:ietf:rfc:3986",
    "value": "Patient/marie"
  }],
  "patient": { "reference": "Patient/jean" },
  "relationship": [{
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
      "code": "MTH",
      "display": "mother"
    }]
  }]
}
```

### 5.1 Add related person

| Viewing | Meaning |
|---------|---------|
| Child profile | Link/create parent Patient; `RP.patient` = this child |
| Adult profile | Link/create child Patient; `RP.patient` = **child**; identifier → adult |

Never set `RelatedPerson.patient` to the parent.

## 6. TRICC helpers

Python API (export / StructureMap authoring):

```python
from tricc_oo.converters.fhir.related_person import (
    build_related_person,
    patient_url_identifier,
    relationship_coding,
    RELATED_PERSON_CONTRACT,
)
```

| Function | Role |
|----------|------|
| `patient_url_identifier(patient_ref)` | PI + secondary + URI identifier |
| `relationship_coding(role)` | `MTH` / `FTH` / `GUARD` |
| `build_related_person(...)` | Full RelatedPerson dict |
| `RELATED_PERSON_CONTRACT` | Machine-readable constants written to `contract/related-person-contract.json` |

---

# Part III — PlanDefinition / available-care

## 7. Intervention PlanDefinition (one per project, one action per process, the only PD exported)

**Superseded terminology:** this section originally described one independent "leaf PD" per
process. `feature/careplan-intervention-plandefinition.md` replaced that with a single
**Intervention PlanDefinition** whose `action[]` has one entry per process
(1 process = 1 action = 1 Questionnaire).

**Update 2026-08-12:** a separate `{form_id}-available-care-catalog` CarePlan PlanDefinition
used to wrap this one and carry the `available-care` trigger on its own. It was **removed** —
checked against openSRP FHIR-Core's `NamedEventInterventionService` (`android/engine`), a
PlanDefinition whose action `definitionCanonical` links to *another* PlanDefinition has its
child actions resolved unconditionally (no applicability filtering), so the catalog produced
one extra, unfiltered "Start care" entry per process action instead of a clean list. See
`feature/careplan-intervention-plandefinition.md`'s 2026-08-12 update for the full trail.

**Update 2026-08-12 (later same day):** the two-triggers-per-action shape above was replaced —
`available-care` now lives once, on a wrapper action (`action[0]`) nested one level above the
per-process actions (`action[0].action[]`), instead of repeating on every one. Each nested
per-process action keeps its own process-name named-event trigger (cpg-common-process name when
known, else process id, e.g. `registration`, `clinical-assessment`) and gains two new extensions:
`tricc-process` (the process name) and `tricc-process-order` (a fixed, cross-PD-comparable order —
10, 20, 30… by the canonical cpg-common-process list order). `NamedEventInterventionService` still
discovers this PlanDefinition directly via the wrapper's trigger — see
`feature/20260812-intervention-order-and-dedup.md` for the full rationale and the fhircore
source-level verification that same-resource nested actions still get their own applicability
check (unlike the removed cross-resource catalog PD).

No applicability `condition` is emitted yet (out of scope for this pass — see
`feature/careplan-claude.md` §11 for the open question on gating/sequencing). `definitionCanonical`
→ **Questionnaire** absolute URL directly (Start care / due now); ActivityDefinition (`kind: Task`)
+ `Task.reasonReference` remains the **planning / not-due-now** path only (§4 of
`feature/opensrp-export-hygiene.md`), not used for Start care. Empty questionnaires
(`item: []`) are not exported (no action for that process).

## 8. Package metadata

No TRICC “config Binary” is emitted. The OpenSRP shell already owns `application` /
`sync` / navigation Binaries. Related-person rules live in
`contract/related-person-contract.json`. Named-event and PlanDefinition ids are on
the Intervention PlanDefinition itself.

---

# Part IV — Implementation map

| Component | Path |
|-----------|------|
| OpenSRPStrategy | `tricc_oo/strategies/output/opensrp.py` |
| RelatedPerson helpers | `tricc_oo/converters/fhir/related_person.py` |
| Tests | `tests/test_strategies/test_opensrp_strategy.py` |
| User docs | `docs/open-srp-export.md` |
| Android companion | `android/feature/register-tricc.md` |

## Push to FHIR server

Export packages include `push-to-fhir.sh` and `env.fhir.example` (from
`tricc_oo/strategies/output/templates/opensrp/`). A `.env` file is created from
the example **only if missing** (never overwritten on re-export). Configure
`.env` / `.secrets` with `FHIR_BASE_URL`, `APP_ID` (e.g. `cdss`), and Keycloak
credentials, then:

```bash
cd <export>/<form_id>/
./push-to-fhir.sh
```
## Success criteria

1. Every Intervention PD action carries both its own process trigger **and** the
   `available-care` trigger (see §7). No separate CarePlan/catalog PD is exported.
2. The Intervention PD is the sole PlanDefinition written under `plan-definition/`.
3. Related-person contract is written under `contract/`; Intervention PD carries the named-event and questionnaire ids.
4. Helpers produce RelatedPerson with `patient`=child, PI identifier for parent, standard role codes.
5. Unit tests cover Intervention PD action triggers/structure and RelatedPerson builder.
6. Export directory contains executable `push-to-fhir.sh` + `env.fhir.example`.
