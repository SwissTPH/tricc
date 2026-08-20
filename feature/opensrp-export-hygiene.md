# OpenSRP Export Hygiene — Empty Forms, JSON-only, Task Chaining

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `feature/zscore` / `develop` |
| **Related** | `feature/opensrp-register.md`, `docs/open-srp-export.md`, `docs/desing/FHIRcore.md`, `feature/20260812-intervention-order-and-dedup.md` (2026-08-12: `available-care` moved off every action onto a single wrapper action — see that spec) |
| **Strategy** | `OpenSRPStrategy` (extends `FHIRStrategy`) |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business description

## 1. Overview

OpenSRP / FHIR-Core packages produced by TRICC should be **deployable without manual cleanup**:

1. **No empty questionnaires** — processes with `"item": []` are dropped (no form, no leaf PD).
2. **JSON only** — hand-built FHIR JSON is the single artifact mode (no FSH dual-write; SUSHI output lacked elements).
3. **Start care (due now)** — leaf / catalog PD actions target **Questionnaire** via `definitionCanonical` so openSRP launches the form immediately.
4. **Task-wrapped Questionnaire** — **only for the upcoming planning feature**, when the questionnaire is **not due now** (schedule a Task; open the form later from the worklist). Not used for the available-care picker today.

CarePlan / planning **init** PlanDefinitions and Task-based scheduling are **deferred** until TRICC supports planning authoring.

> **Superseded terminology note:** "leaf PD" below originally meant one independent
> PlanDefinition per process. `feature/careplan-intervention-plandefinition.md` replaced that
> with a single **Intervention PlanDefinition** (one nested `action` per process). A wrapping
> **CarePlan PlanDefinition** (`available-care`) was added, then **removed again on
> 2026-08-12** — it made fhircore's `NamedEventInterventionService` resolve the Intervention
> PD's actions unconditionally (no applicability check), producing a duplicate/leaked
> "Start care" entry per process. The `available-care` named-event now lives directly on every
> Intervention PD action, alongside its process-name trigger. See §4.1 for the corrected
> contract and `feature/careplan-intervention-plandefinition.md`'s 2026-08-12 update for the trail.

## 2. Empty questionnaires

| Rule | Behaviour |
|------|-----------|
| Empty | `"item": []` or missing `item` |
| Drop | Questionnaire, its Intervention PD action, orphan process CQL/libraries |
| Keep | Any questionnaire with at least one top-level item |
| Log | Warning listing dropped process names |

## 3. Artifact mode: JSON only

| Mode | Status |
|------|--------|
| JSON only | **Default / only** for OpenSRPStrategy |
| FSH dual-write | Removed (incomplete vs Python JSON) |
| SUSHI pipeline | Deferred; not required for OpenSRP packages |

Deploy helpers remain: `push-to-fhir.sh`, `env.fhir.example`.

## 4. Start care vs Task (planning / not due now)

### 4.1 Start care — due now (current)

| Concern | Contract |
|---------|----------|
| Intervention PD action `definitionCanonical` | **Questionnaire** absolute URL (one action per process) |
| Intervention PD `transform` | **Not** set for Start care |
| Named-event | **(Updated 2026-08-12)** `available-care` lives once on a wrapper action (`action[0]`); each nested per-process action carries its own process-name trigger — see `feature/20260812-intervention-order-and-dedup.md` |
| openSRP runtime | `NamedEventInterventionService` discovers the Intervention PD directly by `available-care` → launches the matching action's Questionnaire |

### 4.2 Task-wrapped Questionnaire — not due now (upcoming planning)

Use **only** when planning schedules a form for later (not applicable in the Start care picker):

| Concern | Contract (future) |
|---------|-------------------|
| PD / CarePlan action | Contained `#…-task-activity` (`ActivityDefinition`, `kind: Task`) |
| `transform` | StructureMap `{form_id}-{process}-task` |
| Task | `reasonReference` → Questionnaire; status/timing = not due now |
| When due | Client opens Task → launches Questionnaire |
| Multi-process chain | Optional: on Q done, `extractNextTaskOnDone` → next Task (graph order) |

```text
[Planning: form not due now]
        │
        ▼
   Task (reasonReference → Questionnaire, scheduled)
        │ when due
        ▼
   Launch Questionnaire

[Start care: due now]  ──►  definitionCanonical → Questionnaire  ──►  launch now
```

## 5. Success criteria

1. Empty questionnaires are not written; no Intervention PD action for them.
2. No `fsh/` dual-write from OpenSRPStrategy.
3. Intervention PD action `definitionCanonical` targets **Questionnaire** directly for Start
   care; no separate CarePlan/catalog PlanDefinition is exported.
4. Task/AD is **not** the Start-care launch path; reserved for **planning when not due now**.
5. Unit tests cover prune and the Intervention PD shape (including the dual named-event trigger).

---

# Part II — Technical notes

## Implementation map

| Component | Path |
|-----------|------|
| Prune + PD + Task SM | `tricc_oo/strategies/output/opensrp.py` |
| Tests | `tests/test_strategies/test_opensrp_strategy.py` |
| User docs | `docs/open-srp-export.md` |

## Decisions locked (approval)

- Artifact mode: **JSON only**
- Empty rule: **`item: []`**
- Process order: **graph discovery**
- v1: **Task ActivityDefinition only** (no CarePlan init PD)
