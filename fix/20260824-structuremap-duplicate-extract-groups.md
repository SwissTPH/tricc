# StructureMap extract groups collide (`extract_p_age_years`)

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260821-opensrp-questionnaire-duplicate-calculates.md`, `fix/20260820-opensrp-inherited-value.md`, `feature/20260813-concepttype-structuremap.md`, `feature/concept-repeat.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |
| **Approval** | 2026-08-24 conversation (OpenSRP submit failed with HAPI `Multiple possible matches for rule 'extract_p_age_years'`; uniqueness is **concept + repeat**, first non-null answer). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability).

---

# Part I — Issue analysis

## 1. Symptom

Submitting the OpenSRP registration Questionnaire fails extraction:

```
org.hl7.fhir.exceptions.FHIRException: Multiple possible matches for rule 'extract_p_age_years'
    at org.hl7.fhir.r4.utils.StructureMapUtilities.resolveGroupReference
    at … executeDependency / executeRule / executeGroup
    at com.google.android.fhir.datacapture.mapping.ResourceMapper.extractByStructureMap
```

HAPI looks up a StructureMap **group** by name. Two groups named `extract_p_age_years` make that lookup illegal. The first answered registration item that hits a duplicate group name is what surfaces; it is not unique to age.

On the IMCI child registration extract map this is widespread: 46 group names are duplicated (age/sex twice; some findings up to 15 copies). The two `extract_p_age_years` groups are byte-identical.

## 2. Why it happens

Questionnaire items are unique per `linkId`. Extraction appended a rule on every walk visit (diamond re-stash, two registration nodes sharing an export name) and named the group after that `linkId`. HAPI parse accepts duplicate `group extract_…`; Android `resolveGroupReference` does not.

Versioned items (`p_age_years` and `p_age_years_Vv_1`) are the same **concept** in one **repeat slot**. They must not become two Observations. In-form logic already merges them with `GET_INHERITED_VALUE` (newest first, first non-null). Extraction must do the same.

## 3. What authors and implementers should see after the fix

- One extract group per **concept + repeat** (one Observation / Condition).
- Several Questionnaire `linkId`s for that concept (`name`, `name_Vv_1`, …) feed that group. The written value is the **first non-null** answer, newest version first — the same order as `GET_INHERITED_VALUE`.
- Repeat slot 2 (`name_Rr_2`) is a second group and a second Observation.
- Submit of registration extracts age once; no `Multiple possible matches`.

## 4. Out of scope

- Changing how the visitor assigns `_Vv_` / `_Rr_` export names.
- PATCH/upsert of Observations (still POST).
- Task StructureMaps.

---

# Part II — Fix approach

## 5. Formal rules

**R1 — one StructureMap group per concept + repeat per process.** Group name is `extract_<concept>` (plus `_Rr_<n>` when `repeat != 1`). Never a `_Vv_` suffix. `…_confirmed` / `…_refuted` stay unique suffixes on AcceptDiag.

**R2 — first non-null, newest first.** Rank sources by `(path_len, version)` descending (same as `GET_INHERITED_VALUE`). Dispatch the newest `linkId` unconditionally; each older `linkId` runs only when every newer version has `answer.empty()`. HAPI evaluates that `where` with StructureMap variable `src` (the QuestionnaireResponse).

**R3 — `generate_export` collects versions, does not drop them.** Skip only a re-visit of the same node (`processed_nodes`) or the same `linkId` already collected. Merge to one rule per concept/repeat when assembling FML.

**R4 — last-line defence.** `merge_extraction_rules` / `build_extraction_fml` collapse later rules that share concept+repeat and union their `link_ids`.

**R5 — prune.** Keep an extract rule if **any** of its `link_ids` remain on the Questionnaire; drop ids that were pruned.

## 6. Code checklist

- [x] `converters/fhir/structuremap.py` — `merge_extraction_rules`, first-non-null dispatch
- [x] `FHIRStrategy.generate_export` — processed-node + same-`linkId` skip; keep version peers
- [x] `_assemble_extraction_maps` / prune use merged `link_ids`
- [x] Tests: `tests/test_strategies/test_fhir_structuremap.py`
- [x] Docs: this file, `docs/open-srp-export.md`

## 7. Acceptance

1. Two `generate_export` calls for the same `p_age_years` `linkId` yield one group.
2. `p_age_years` + `p_age_years_Vv_1` yield one `group extract_p_age_years`; FML reads newest first and older only if newer `answer.empty()`.
3. `repeat=2` is a separate group (`extract_p_age_years_Rr_2`).
4. HAPI `resolveGroupReference('extract_p_age_years')` has a single match.
5. Registration submit extracts age once from the first non-null version.
