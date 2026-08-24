# Unused hidden calculates with only CQL `initialExpression` stay on the Questionnaire

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260821-opensrp-questionnaire-duplicate-calculates.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## 1. Symptom

OpenSRP registration still carries hidden calculate items that the form never
reads. Example: `pnZZBCRahaURgJo3I0mLJ_58` — hidden boolean, CQL
`initialExpression` `Calc_pnZZBCRahaURgJo3I0mLJ_58` (`true`), no FHIRPath
reader, not an extraction source.

`fix/20260821-opensrp-questionnaire-duplicate-calculates.md` R4 treated **any**
`initialExpression` as a keep-reason (populate / encounter dedup / out-of-form
CQL). Graph-routing calculates that cannot be expressed as FHIRPath fall back
to CQL `true` and therefore survive the prune.

## 2. Rule of thumb

A **hidden** calculate-like item belongs on the Questionnaire only if **this**
form needs its value:

- another remaining item’s FHIRPath reads its `linkId`, or
- **this** Questionnaire extracts it to a FHIR resource (Observation /
  Condition / …).

Hidden **calculates** and **diagnosis anchors** (`TriccNodeType.diagnosis`)
have no persistable mapping of their own. If nothing in this form reads them,
omit them. Visible questions, groups, and `display` items are never pruned.

Populate / `load_*` items that **this** process extracts stay (they round-trip
an Observation even if no enableWhen reads them). The same `linkId` extracted
only in another process does **not** keep a copy here.

## 3. Out of scope

- Changing which node types `classify_extraction` persists.
- Splitting processes.

---

# Part II — Fix approach

## 4. Emission rules

**R1 — `initialExpression` is not a keep-reason.**
Hidden calculate-like items (`boolean` / `string` / `integer` / `decimal` /
`quantity`) are dropped when this Questionnaire does not read the `linkId` and
this Questionnaire does not extract it.

**R2 — Extraction keep is per Questionnaire.**
`extraction_rules[this process]` only. A Condition extracted on
determine-diagnosis does not retain the registration copy.

**R3 — After prune, drop orphans.**
Remove extraction rules whose `link_id` is gone. Remove CQL `Calc_*` /
`Dedup_*` defines no remaining `initialExpression` names. Assemble StructureMaps
and CQL libraries **after** prune.

## 5. Code checklist

- [x] `_is_unused_hidden_calculate` no longer keeps solely for `initialExpression`
- [x] per-segment `extraction_rules` in `_prune_unused_hidden_calculates`
- [x] collect nested toggle FHIRPath `linkId`s
- [x] prune before `_assemble_extraction_maps` / `_assemble_cql_libraries`
- [x] tests: unused CQL `true` calc dropped; unused `load_*` without extraction
      dropped; extraction source kept; other-process extraction does not keep
- [x] `docs/open-srp-export.md`
