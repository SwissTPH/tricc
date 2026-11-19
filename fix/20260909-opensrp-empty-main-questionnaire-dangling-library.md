# Empty `main` Questionnaire survives pruning and carries a dangling CQL Library reference

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `feature/opensrp-export-hygiene.md`, `feature/careplan-intervention-plandefinition.md`, `docs/open-srp-export.md`, `docs/desing/FHIRcore.md` |
| **Strategy** | `OpenSRPStrategy` |
| **Approval** | 2026-09-09 conversation (user: "can you check the fhir questionnaires and see if there is an error … preventing it from rendering in opensrp" → "can you implement the fix"). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability).

---

# Part I — Issue analysis

## 1. Symptom

An exported openSRP package does not render its questionnaires on device. Reproduced on
the `Diabetes` package (`tests/output/Diabetes/`), and present identically in every other
openSRP package in the tree (`demo_tricc`, `ceca_vacc`, `cohort_fup`).

Every one of those packages ships a `Questionnaire-questionnaire-main.json` that:

* has exactly one item — a `group` with **no children** — so there is nothing to draw, and
* declares `sdc-questionnaire-cqlInputResources` → a `Library` that **does not exist** in
  the package.

For `Diabetes`:

```json
"item": [ { "linkId": "nc07d18be042f3041", "text": "Main Start", "type": "group" } ]
...
{ "url": ".../sdc-questionnaire-cqlInputResources",
  "valueReference": { "reference": "https://fhir.tricc.io/Library/4b7f0b39-6972-58e5-8c71-a298a677ca49" } }
```

`Library/4b7f0b39-…` is `fhir_resource_id("Diabetes", "Library", "main")` — the CQL library
for the `main` process. It was never generated (the `main` process has no calculates), so
there is no `library/Library-Diabetes-main.json`, it is absent from `Composition.json`'s
Libraries section, and `push-to-fhir.sh` (which uploads by directory scan) never pushes it.

The same dangling URL is also `PlanDefinition.library[0]`, so it is not contained to the
`main` form: a consumer that resolves `PlanDefinition.library` before evaluating the
Intervention PD's actions fails for **all** processes, including the otherwise-valid
`registration` questionnaire.

## 2. Expected vs actual

| | Expected | Actual |
|---|---|---|
| Questionnaire with no answerable item | pruned before PD / Composition generation | kept, emitted, wired |
| `cqlInputResources` on a Questionnaire | present only when that process has a generated Library | always present, computed from the process name |
| `PlanDefinition.library` | only Libraries that exist in the package | includes never-generated per-process ids |
| FHIR invariant `que-1` | satisfied | violated (`group` with no nested item) |

## 3. Who is affected

Every `OpenSRPStrategy` export whose graph yields a process that produces a start node but
no answerable question — in practice the `main` process of every package built to date.

## 4. Out of scope

* Author content. The empty `main` page is legitimate authoring; the exporter must not ship
  it as a Questionnaire.
* The registration questionnaire itself, which validates clean (no duplicate `linkId`s, all
  389 `text/fhirpath` expressions parse under HAPI `FHIRPathEngine`, all 180
  `text/cql-identifier` refs resolve, no `que-1`/`que-8` violations).
* Separately-tracked emission nits observed in the same audit and **not** addressed here:
  four hidden `string` items whose `calculatedExpression` returns a boolean; redundant
  (HAPI-idempotent) `.value` stacking; `answerOption.valueCoding` without a `system`.

---

# Part II — Fix approach

## 5. Root cause

Two independent gaps, both in `tricc_oo/strategies/output/opensrp.py`.

**(a) Emptiness is tested only at the top level.** `is_questionnaire_empty()` returns
`not q.get("item")`. A questionnaire whose single item is a childless `group` is therefore
"non-empty", so `_prune_empty_questionnaires()` keeps it. The build log confirms no
`dropping empty Questionnaire` warning was emitted for `main`.

**(b) The Library reference is computed, not looked up.** Both
`generate_intervention_plandefinition()` and `_wire_questionnaire_extensions()` derive
`lib_id = self._process_resource_ids(process)["lib_id"]` and use it whenever
`self.libraries` has no entry for the process — i.e. the *absence* of a Library is exactly
the case that produces a reference to it.

## 6. Emission rules

**R1 — Emptiness is recursive.** A Questionnaire is empty when it contains no item of a
type that can hold an answer, at any depth. `group` and `display` items are structural: a
tree of only groups and displays is empty. This matches `que-1` in spirit — a group whose
subtree has no question has nothing to render.

**R2 — Never reference a Library that was not generated.** `cqlInputResources` is emitted
only when `self.libraries` resolves an entry for that process; `PlanDefinition.library`
lists only resolved Library urls. No uuid5 fallback in either place.

**R3 — Pruning stays silent-safe.** Dropping a process must also drop its per-process CQL,
Library, extraction map and StructureMap entries (existing behaviour, retained), and log
at `warning` with the reason.

## 7. Code checklist

- [x] `is_questionnaire_empty()` — walk the item tree; empty iff no non-`group`/`display`
      item exists at any depth. Keep `None` / missing / `item: []` → `True`.
- [x] `_prune_empty_questionnaires()` — reword the log message (no longer only `item: []`).
- [x] `generate_intervention_plandefinition()` — drop the `lib_id` fallback; append to
      `lib_urls` only for processes with a resolved Library.
- [x] `_wire_questionnaire_extensions()` — emit `cqlInputResources` only for a resolved
      Library; always emit `planDefinitions` and `targetStructureMap` as before.
- [x] Tests.
- [x] `docs/open-srp-export.md` — document R1/R2.

## 8. Tests

`tests/test_strategies/test_opensrp_strategy.py`

* `test_is_questionnaire_empty` — extend: childless `group` → `True`; nested
  group/display-only tree → `True`; question nested under groups → `False`.
* `test_prune_empty_questionnaires` — a process whose only item is an empty group is
  dropped along with its `cql_defines`.
* `test_wire_questionnaire_extensions_skips_missing_library` — no `cqlInputResources` when
  `self.libraries` has no entry; present when it does.
* `test_plandefinition_library_only_existing` — `PlanDefinition.library` omits processes
  with no generated Library.

## 9. Acceptance criteria

1. Re-exporting any package emits no `Questionnaire-questionnaire-main.json` when the
   `main` process has no answerable item.
2. No `cqlInputResources` / `PlanDefinition.library` entry resolves to a Library absent
   from the package. A reference audit over the output package reports zero dangling
   references.
3. `python -m pytest tests/` passes.
