# OpenSRP questionnaires balloon with unused duplicate empty calculates

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260821-output-pass-calculate-readiness.md`, `fix/20260820-opensrp-inherited-value.md`, `feature/opensrp-export-hygiene.md`, `docs/open-srp-export.md`, `docs/desing/FHIRcore.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |
| **Constraint** | Keep **one Questionnaire per CPG process**. Do not split a process into several forms. |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## 1. Symptom

OpenSRP export of the global IMCI child content produces a **22 MB** registration
Questionnaire (`Questionnaire-questionnaire-registration.json`). Most of it is
hidden calculate items with **no** `calculatedExpression` and **no**
`initialExpression`. The same pattern appears, smaller, on diagnostic-testing
(2.9 MB) and dispense-medications (593 KB).

openSRP FHIR Data Capture has to parse and index every `Questionnaire.item`.
A 22 MB form with 85k items is not usable on device even if the extra items
are hidden.

## 2. What the registration JSON actually contains

Census of
`/mnt/data/Development/tests/output/global_opensrp/imci_icrc_global_child/questionnaire/`
(build of 2026-08-21):

| Questionnaire | Size | Items | Unique `linkId` | Extra copies | Hidden empty (no expr) | `calculatedExpression` | `enableWhenExpression` | `initialExpression` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| registration | 22 MB | 85 165 | 624 | **84 541** | 84 774 | 0 | 0 | 197 |
| diagnostic-testing | 2.9 MB | 11 203 | 83 | **11 120** | 11 159 | 0 | 0 | 33 |
| dispense-medications | 593 KB | 2 010 | 1 030 | 980 | 1 504 | 0 | 0 | 33 |
| determine-diagnosis | 150 KB | 232 | 232 | 0 | 59 | 0 | 0 | 172 |
| others | ≤ 25 KB | small | ≈ items | few | few | 0–2 | 0–2 | few |

Registration `linkId` copies (same `linkId` repeated as sibling items):

| `linkId` | copies |
|---|---:|
| `needs_test` | 39 385 |
| `needs_test_Vv_14` | 20 431 |
| `needs_test_Vv_13` | 9 846 |
| `needs_test_Vv_12` | 4 554 |
| `needs_test_Vv_11` | 2 461 |
| `test_malaria_Vv_10` | 1 478 |
| `needs_test_Vv_10` | 1 092 |
| `che_referral` | 320 |
| remaining dups | … |

Each `needs_test` copy is identical:

```json
{
  "linkId": "needs_test",
  "text": "needs_test",
  "type": "string",
  "extension": [
    { "url": "http://hl7.org/fhir/StructureDefinition/questionnaire-hidden", "valueBoolean": true }
  ]
}
```

Copy counts roughly **double at each version**. That is the shape of a
diamond/fan-in graph being re-emitted on every incoming path, not 39k
distinct authored nodes.

FHIR requires `Questionnaire.item.linkId` to be unique within the resource.
This Questionnaire is therefore invalid SDC as well as huge.

## 3. Are the calculates used?

**No** for the duplicate empty ones, and **no** for most of the unique empty
ones either.

On the registration Questionnaire:

| Check | Result |
|---|---|
| FHIRPath `linkId='…'` references in any SDC expression | **0** |
| `needs_test` / `test_malaria` / `che_referral` mentioned in any expression | **0** |
| Duplicate `linkId`s referenced by anything | **0** |
| `calculatedExpression` on any item | **0** |
| `enableWhenExpression` on any item | **0** |
| `initialExpression` | **197**, all `Dedup_*` (encounter prefills on questions / populate / diagnoses) |
| Registration CQL library | **197** `define`s, all those same `Dedup_*` names — no `Calc_needs_test` |

So the 84 541 extra copies contribute **nothing** to live calculation, skip
logic, `$populate`, or extraction. They are dead weight.

Of the **624 unique** `linkId`s:

- **265** look real (visible questions, groups, displays, populate `load_*`,
  diagnoses that already carry a `Dedup_*` `initialExpression`).
- **359** are unique empty hidden calculates (rhombus/bridge/path/`needs_test*`
  versions, etc.). None of those 359 are referenced by an expression in this
  Questionnaire.

Keeping unique `linkId`s only would shrink registration from ~22 MB to
**~0.16 MB**. Dropping the 359 unused empty uniques as well would land near
**~100 KB**. That is still **one** registration Questionnaire.

## 4. Who is affected

- **Implementers** trying to load the IMCI child package in openSRP FHIR-Core
  (form open / `$populate` / sync).
- **Authors** are not at fault: the guideline does not contain 39k
  `needs_test` nodes. This is exporter behaviour.

## 5. Expected vs actual

| | Expected | Actual |
|---|---|---|
| Items per Questionnaire | One item per exported node of that process; `linkId` unique | Same `linkId` appended tens of thousands of times |
| Hidden calculate | Emitted **once**, with FHIRPath `calculatedExpression` or CQL `initialExpression` when the value is needed | Emitted on every walk visit, **empty** |
| Unused path/bridge/rhombus | Not an item, or dropped if nothing in this form reads it | Serialised as empty hidden strings |
| One Questionnaire per process | Unchanged | Unchanged (the file is one process — it is just stuffed) |

## 6. Out of scope

- Splitting registration (or any process) into several Questionnaires.
- Changing CPG process assignment in the draw.io / who owns which activity.
- ODK / CHT serialisation (`coalesce`, survey-row dedup already exists there).
- Replacing the versioning engine (`set_last_version_false`,
  `GET_INHERITED_VALUE` construction) — only what FHIR **emits**.
- Compact JSON (`indent=2` → minified) as the main fix. Nice extra after
  item count is sane; it does not fix invalid duplicate `linkId`s.

---

# Part II — Fix approach

## 7. Root causes (two bugs, one hygiene pass)

### 7.1 Output walk re-emits the same node

`walktrhough_tricc_node_processed_stached` calls the callback **before**
checking `processed_nodes`, and when a predecessor is processed it re-stashes
every `next_node` that is not currently in the stash — **including nodes
already processed**.

XLSForm survives this because visitor `generate_base` only mutates when
`node not in processed_nodes`.

FHIR `FHIRStrategy.generate_base` **always** `target_list.append(item)` and
returns `True`. Every extra visit of `needs_test` adds another sibling.

### 7.2 Calculate / relevance attach to the wrong Questionnaire

`generate_base` places the item with `_node_segment(node)` → `get_process(node)`
(e.g. `registration`).

`generate_calculate` and `generate_relevance` look the item up with
`getattr(node, "segment", None) or "main"`. `node.segment` is frequently
unset (already noted in `fix/20260820-opensrp-inherited-value.md`), so they
search **main** (13 items) and attach nothing. `_enter_serialisation_context`
already resolves the Questionnaire that **holds** the `linkId`; calculate
and relevance still do not use it for the item lookup.

Consequence: even the first copy of a calculate stays empty, and relevance
never becomes `enableWhenExpression` (0 on registration).

This is the same class of miss as the inherited-value / output-pass fixes;
those stopped the export from crashing or writing `true`, they did not put
the expression on the item that was actually emitted.

### 7.3 No “is this calculate used in this Questionnaire?” filter

XLSForm tracks `used_calculates`. FHIR emits every calculate / rhombus /
bridge / wait the walk reaches in that process, whether or not any remaining
item’s value or skip logic reads it. After 7.1, that is 39k copies of an
unused hub. After 7.1 is fixed, it is still hundreds of unique empty
hidden items that this form never reads.

## 8. Emission rules (keep 1 Questionnaire / process)

**R1 — Emit each `linkId` at most once per Questionnaire.**
If `generate_base` is invoked again for a node whose export name is already
an item of that Questionnaire, do not append. Continue the walk (`return True`).
This is the FHIR analogue of XLSForm’s `if node not in processed_nodes`.

**R2 — Do not append when the node is already in `processed_nodes`.**
Same as XLSForm. Guards object-identity revisits even before the `linkId`
check.

**R3 — Attach calculate and relevance on the Questionnaire that already
contains the item**, via `_segment_for_item` (already used for extraction
and `GET_INHERITED_VALUE`). Never assume `node.segment` / `"main"`.

**R4 — Keep a hidden calculate item only if this Questionnaire needs it.**
Needed means any of:

- a surviving item’s `calculatedExpression` / `enableWhenExpression` /
  option toggle FHIRPath reads its `linkId`, or
- it carries a CQL `initialExpression` that `$populate` must run (populate,
  encounter dedup, out-of-form value), or
- it is extracted (Observation / Condition / etc.).

Path `DisplayBridge` / `Bridge` / rhombus items that nobody in **this**
form reads are omitted. Other processes keep their own copy if they need
it — still one Questionnaire per process.

**R5 — Versions (`name_Vv_n`).**
Do not emit an old version solely because the transformation engine cloned
it. Emit it only under R4 (something in **this** Questionnaire reads that
`linkId`, typically a `GET_INHERITED_VALUE` FHIRPath union). Recency and
cross-process values stay as in `fix/20260820-opensrp-inherited-value.md`
(in-form union of versions that exist here; otherwise concept-keyed CQL
dedup / encounter `initialExpression`).

**R6 — Do not change process boundaries.**
Registration stays one Questionnaire. Diagnostic-testing stays one.
No extra forms, no merging processes.

## 9. Implementation phases

### Phase A — Stop the copies (size: 22 MB → ~0.16 MB)

In `FHIRStrategy.generate_base`:

1. If `node in processed_nodes`: return `True` without appending.
2. After computing `link_id = get_export_name(node)`, if
   `_find_item_by_link_id(q["item"], link_id)` is not `None`: return `True`
   without appending.
3. Then append as today.

Add a unit test that walks a diamond (two paths into one calculate) and
asserts the Questionnaire has **one** item for that `linkId`.

### Phase B — Put expressions on the surviving item

`generate_calculate` / `generate_relevance`: resolve `segment` with
`_segment_for_item` (or `_enter_serialisation_context`’s
`self._current_segment`) before looking up the item. After Phase A there is
only one item per `linkId`, so the first match is the right one.

Tests: a calculate whose `get_process` is `registration` but `node.segment`
is unset still receives `calculatedExpression` or `initialExpression` on
the registration item; a visible item with relevance receives
`enableWhenExpression` on that same Questionnaire.

### Phase C — Drop unused empty hidden calculates (size: ~0.16 MB → ~0.1 MB)

After calculate + relevance (+ option toggles) have been attached, prune
each Questionnaire:

- hidden item
- type is a calculate-like (`boolean`/`string`/`integer`/`decimal`)
- no `calculatedExpression` / `initialExpression`
- `linkId` not referenced by any remaining expression in **that**
  Questionnaire
- not an extraction source

Do this **per Questionnaire**, not globally, so a calculate used only in
diagnostic-testing is kept there and dropped from registration.

Tests: unused `needs_test` not in registration; a calculate that a
registration question’s `enableWhenExpression` reads is kept.

### Phase D — Optional write hygiene (small)

Write Questionnaires with compact JSON (no `indent=2`) or a CLI flag.
Only after A–C; indent is not the 22 MB.

## 10. Code checklist

- [x] `tricc_oo/strategies/output/fhir_form.py` — `generate_base` R1/R2
- [x] `generate_calculate` / `generate_relevance` — R3 segment lookup
- [x] prune unused hidden calculates after those passes (R4/R5), per Questionnaire
- [x] `docs/open-srp-export.md` — unique `linkId`; unused hidden calculates omitted
- [x] tests (`tests/test_strategies/test_fhir_questionnaire_hygiene.py`):
  - diamond / multi-path calculate → one item
  - expression attached despite unset `node.segment`
  - unused hidden calculate omitted; referenced one kept
  - still exactly one Questionnaire per process (registration not split)

## 11. Acceptance criteria

1. Registration Questionnaire `linkId`s are unique.
2. No hidden calculate item without an expression **and** without a reader
   in that Questionnaire.
3. Visible questions that have skip logic still get `enableWhenExpression`
   on the same form.
4. Calculates that live in-form still get FHIRPath `calculatedExpression`
   (or CQL `initialExpression` when the value is outside the form).
5. Export still emits **one** Questionnaire per CPG process; process names
   and PlanDefinition actions unchanged.
6. On the global IMCI child package, registration is on the order of
   **hundreds of KB**, not tens of MB (target: unique surviving items ≈
   authored questions + used calculates + populate/dedup, not 85k).
7. Existing FHIR/OpenSRP tests pass; new tests above pass.

## 12. Suggested order of work

Do **A then B then C**. A alone makes the file small and valid. B makes the
remaining calculates actually compute. C removes the leftover unused uniques
once expressions exist so the prune can see real references. D is optional.
