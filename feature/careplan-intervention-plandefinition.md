# CarePlan → Intervention PlanDefinition Nesting (scoped implementation)

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `feature/zscore` (current branch) |
| **Related** | `feature/careplan-claude.md` §11 (raises this exact question), `docs/open-srp-export.md`, `feature/opensrp-register.md`, `feature/20260812-intervention-order-and-dedup.md` (supersedes the "trigger on every action" placement below — see its Update note) |
| **Scope** | Deliberately narrower than `feature/careplan-claude.md` — no multi-CarePlan, no scheduling, no applicability/eligibility CQL, no QuestionnaireResponse-status gating. Matches **today's reality**: one project = one Intervention. |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Update 2026-08-12 (later same day) — `available-care` trigger moved to a wrapper action

The section directly below ("CarePlan/`available-care` catalog PlanDefinition removed") put the
`available-care` named-event on **every** per-process action, since only the catalog PD's own
trigger had just been removed. A later pass the same day
(`feature/20260812-intervention-order-and-dedup.md`) went further: `available-care` now appears
**once**, on a single wrapper action nested one level above the per-process actions
(`action[0].action[]`), not repeated on each one — "PD-level" as closely as FHIR's
action-only-trigger schema allows. Each process action keeps its own process-name trigger and
gains `tricc-process`/`tricc-process-order` extensions. Verified this is still same-resource
nesting (not the cross-resource catalog-PD pattern that caused the original bug this section
describes) — see that spec's §1 for the fhircore source-level justification.

## Update 2026-08-12 — CarePlan/`available-care` catalog PlanDefinition removed

The original design (Parts I–II below, kept as historical record) exported **two**
PlanDefinitions: the Intervention PD described below, plus a wrapping
`{form_id}-available-care-catalog` PlanDefinition whose only jobs were (a) carry the
`available-care` named-event trigger and (b) link down to the Intervention PD via a single
child action.

**Why removed:** checked against the actual openSRP FHIR-Core Android source
(`openSRP-fhircore/android`). `NamedEventInterventionService` (`engine/.../task/`) searches all
synced PlanDefinitions for an `action.trigger` matching the configured named-event (default
`available-care`), then per match either evaluates the action directly, or — if the matching
action's own `definitionCanonical` points at **another PlanDefinition** — resolves *every* one
of that nested PlanDefinition's top-level actions **unconditionally**, without ever running
`passesFhirPathConditions` on them. Because only the catalog PD carried the `available-care`
trigger, that's exactly the path taken: the app listed one "Start care" entry per process
action inside the Intervention PD, with no applicability filtering — reported by the user as
"getting 2 lines, one for the available care and one for the first questionnaire" for a
single-process project.

**Fix:** drop the catalog PD entirely. `generate_intervention_plandefinition()` now puts
**two** `named-event` triggers on every action — the process name (unchanged) **and**
`available-care` (moved down from the catalog). `NamedEventInterventionService` then matches
the Intervention PD directly and evaluates each action on the fast, condition-respecting path
— one clean list entry per process, no nested-PlanDefinition indirection.

**What changed:**
- `tricc_oo/strategies/output/opensrp.py`: `generate_available_care_catalog()` deleted;
  `self.available_care_catalog` attribute removed; `generate_intervention_plandefinition()`
  actions now emit two triggers; `validate()`, `generate_composition()`,
  `_write_plan_definitions()`, `_stamp_package_app_id_tags()` no
  longer reference the catalog. The unused TRICC config Binary is no longer emitted.
  `named_events.available_care` lives on the Intervention PD's actions.
- `tests/test_strategies/test_opensrp_strategy.py`: `test_generate_available_care_catalog`
  removed; `test_generate_intervention_plandefinition_structure` now asserts the
  `available-care` trigger **is** present on each action.
- `docs/open-srp-export.md`, `feature/opensrp-register.md`, `feature/opensrp-export-hygiene.md`
  updated to describe the single-PD shape.

Everything below (Parts I & II) describes the two-PD design as it stood before this update;
read "CarePlan PlanDefinition (`available-care`)" as historical, superseded by the section
above.

---

## Part I — Business description

Today, `OpenSRPStrategy` exports one independent **leaf `PlanDefinition`** per process, each
carrying its own `available-care` named-event trigger, plus a separate catalog
`PlanDefinition` (`{form_id}-available-care-catalog`) whose child actions point straight at
each process's Questionnaire. There is no FHIR resource that represents "the Intervention" —
processes look like N unrelated siblings rather than one care pathway.

This change introduces the middle layer explicitly, scoped to what a single-intervention
project needs **today**, with eligibility/scheduling left for later:

- **One Intervention `PlanDefinition`** — one project's entire process chain, expressed as one
  `action` per process (`1 process = 1 action = 1 Questionnaire`, unchanged Questionnaire
  generation).
- **One CarePlan `PlanDefinition`** ("available care") — the entry point openSRP's Start-care
  picker discovers via the `available-care` named-event. Its single action links to the
  Intervention PlanDefinition above (`definitionCanonical` → Intervention PD canonical URL),
  rather than to each Questionnaire directly.

Applicability (who this applies to, whether an action is still due) is **explicitly not**
part of this pass — every action is unconditionally listed, same as today. Sequencing/gating
between processes (§11 of `feature/careplan-claude.md`) is also out of scope here; this pass
only changes **which resource owns which action**, not when actions become available.

## Part II — Technical specification

### Resource shape

```
PlanDefinition (CarePlan, "{form_id}-available-care")
  action[0]:
    trigger: named-event "available-care"
    definitionCanonical: PlanDefinition/{intervention-pd-id}   ← NEW: links down, not to a Questionnaire

PlanDefinition (Intervention, "{form_id}-intervention-PD")
  action[]: one per process, in process_chain order
    trigger: named-event <process name>                        (available-care trigger REMOVED here — lives on the CarePlan PD only)
    definitionCanonical: Questionnaire/{process questionnaire}  (unchanged)
  library: [Library/{process lib} for every process]            (was one per leaf PD; now one PD covers all processes)

Questionnaire (unchanged, one per process)
  extension sdc-questionnaire-planDefinitions → PlanDefinition/{intervention-pd-id}  (was leaf pd id; now shared)
```

### Code changes (`tricc_oo/strategies/output/opensrp.py`)

1. Replace `generate_plandefinition(process, version)` (per-process leaf PD) with
   `generate_intervention_plandefinition(version)` — builds the single PD described above from
   `self.process_chain`.
2. `export()`: build the Intervention PD once, store as the sole entry of
   `self.plan_definitions` (dict keeps existing `{key: pd}` shape for `Composition`/binary-config
   iteration — key becomes `"intervention"`); wire every Questionnaire's `planDefinitions`
   extension to it; keep the per-process loop only for `generate_task_structuremap` (unaffected
   contract, planning-only, still not used for Start care).
3. `generate_available_care_catalog(version)`: single child action, `definitionCanonical` →
   Intervention PD canonical URL (was: one child per process → Questionnaire).
4. `generate_task_structuremap()`: `tricc-task-plandefinition` extension now references the
   shared Intervention PD id (was a leaf pd id keyed on uuid5(process)).
5. `validate()`: per-action Questionnaire-canonical check moves from "one check per leaf PD" to
   "one check per action inside the single Intervention PD"; the `available-care` named-event
   check moves from every leaf PD to the CarePlan PD's own action.
6. No TRICC config Binary: process / PD ids stay on the Intervention PlanDefinition.

### Tests

`tests/test_strategies/test_opensrp_strategy.py` updated to exercise
`generate_intervention_plandefinition` (multi-action PD) and the revised
`generate_available_care_catalog` (single child → PlanDefinition, not Questionnaire).

### Acceptance criteria

- [x] Exactly one Intervention PD is written per export, with one action per non-empty process.
- [x] Exactly one CarePlan PD (`available-care`) is written, its one action pointing at the
      Intervention PD.
- [x] Every process Questionnaire's `planDefinitions` extension points at the Intervention PD.
- [x] `docs/open-srp-export.md`, `feature/opensrp-register.md`, `feature/opensrp-export-hygiene.md`
      updated to match (terminology + contract tables).
- [x] Unit tests pass (133/133); a real `tests/build.py … -O OpenSRPStrategy` run against
      `tests/data/etat.drawio` (2 real processes) produced the expected two-PD shape — verified
      by hand: CarePlan PD's one child → Intervention PD canonical; Intervention PD has one
      action per process, each → its Questionnaire; both process Questionnaires' `planDefinitions`
      extension point at the same Intervention PD id.
