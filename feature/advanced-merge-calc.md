# Advanced merge calculation — Feature Specification

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `feature/adv_merge_calc` / `develop` |
| **Related** | `feature/concept-repeat.md`, display multi-version refs |
| **Authoring surface** | Implicit (same `name` across activities); no new draw.io attribute |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business Description

*Audience: clinical authors, guideline developers, implementers evaluating TRICC workflows.*

## 1. Overview

When the **same concept name** appears more than once in a flowchart (different activities or branches), TRICC must decide how later calculations and questions **inherit** earlier values.

**Advanced merge calculation** means: inheritance no longer depends only on the *last* prior version. TRICC merges **all prior versions** of that concept so a value remains available even when intermediate activities were never shown.

Typical clinical need:

```text
Activity A (triage):    weight → 3.2 kg
Activity B (optional):  weight → may be skipped entirely
Activity C (treatment): dose depends on weight
```

If Activity B was never entered, older engines that only linked to “the last weight node” could lose the triage value. Advanced merge keeps **every** prior capture of `weight` in the inheritance set and coalesces them at runtime.

## 2. What authors see

Authors do **not** set a new attribute for this feature. Behaviour is automatic when:

- two or more nodes share the same `name` (and the same concept **repeat** slot — see `feature/concept-repeat.md`);
- later logic references that name, or a second question with the same name would otherwise skip / inherit.

### 2.1 Calculate nodes (same formula vs different formulas)

| Situation | Merge behaviour |
|-----------|-----------------|
| Same concept, **same formula origin** (sibling versions) | Combined with `GET_INHERITED_VALUE` (first non-empty / coalesce semantics) |
| Same concept, **different formulas** | Each formula family is grouped; groups are then merged with datatype-aware rules (boolean OR, numeric coalesce/plus, etc.) |
| Later calculate with no local expression | Can inherit solely from prior versions |

### 2.2 Questions / display fields

When a calculation **reads** a multi-version question (e.g. `weight` asked in two activities), the expression uses **all** non-local versions via `GET_INHERITED_VALUE` so the form engine picks whichever instance was filled (ODK: `coalesce`).

**Relevance** still uses a **single** last-version reference (not multi-version coalesce), so skip/show logic stays stable.

### 2.3 Local-only slots (`repeat=-1`)

Nodes with **`repeat=-1`** are **local-only**:

- They stay **addressable by name** in expressions.
- They **do not inherit** prior values.
- They **do not contribute** their value into other nodes’ inheritance merges.
- They **share the export base name** with default `repeat=1` (no `_Rr_` suffix), so version suffixes (`_Vv_n`) keep ODK field names unique.

Use this for temporary or activity-scoped copies of a concept that must not pollute global inheritance. Full rules: `feature/concept-repeat.md`.

## 3. Benefits

- Safer multi-activity guidelines when optional segments may be skipped.
- Predictable “use any prior weight / age / diagnosis flag” without manual bridge calculates.
- One runtime operator (`GET_INHERITED_VALUE`) mapped cleanly to ODK `coalesce` and similar exports.
- Compatible with concept repeat isolation and local-only `-1` slots.

## 4. Limitations

- Inheritance is still scoped by **`(name, repeat)`** — different repeat slots never merge into each other.
- Authors cannot currently pick a custom merge strategy per node (always datatype-aware defaults).
- Very large numbers of same-name versions produce wider coalesce expressions (acceptable for typical CDSS graphs).

---

# Part II — Technical Specification

*Audience: TRICC developers.*

## 5. Operators and merge rules

| Operator | Role |
|----------|------|
| `TriccOperator.GET_INHERITED_VALUE` | Ordered multi-version value pick (export as coalesce / equivalent) |
| `TriccOperator.COALESCE` | Explicit coalesce (e.g. save calculates, some numeric merges) |
| `merge_expressions(...)` | Datatype-aware combine of an expression with prior version operands |

### 5.1 `merge_expressions` rules

| Datatype / shape | Result |
|------------------|--------|
| `boolean` | OR of current expression with `ISTRUE` of each prior |
| `number`/`integer` **with input refs** | `COALESCE(PLUS(priors + current))` |
| other | `COALESCE(current, …priors)` |

### 5.2 Origin-signature grouping (calculates)

`group_prev_versions_by_origin_signature` peels `COALESCE` / `GET_INHERITED_VALUE` wrappers via `_get_defining_expression_op`, then:

1. Buckets prior versions by defining-expression origin signature.
2. **Sibling** bucket (same signature as current) → one `GET_INHERITED_VALUE([local_expr, *siblings])`.
3. **Other** buckets → each becomes `GET_INHERITED_VALUE(list)`.
4. Non-sibling group values are fed into `merge_expressions` with the main sibling op.

## 6. Pipeline hooks

```text
load_calculate(node):
  set_last_version_false(node)          # export-name peer versioning
  all_prev = get_versions(name, …, get_repeat(node)) excluding self
  get_version_inheritance(node, all_prev, …)
  … relevance / skip / generate_calculates …

process_operation_reference(..., inherit_display_versions=True):
  multi-version DisplayModel refs → GET_INHERITED_VALUE(ordered newer-first)
  (False for relevance / non-value fields)
```

### 6.1 `get_version_inheritance`

| Case | Behaviour |
|------|-----------|
| `TriccNodePopulate` with `context=history` | No value inheritance; `last=True` |
| `get_repeat(node) == -1` | No inheritance (local-only receiver) |
| Prior versions | Drop any with `repeat=-1` via `_filter_inheritable_versions` |
| Non-input calculate / display calculate / end | Origin-grouped merge or `merge_expressions` into `expression` / `expression_reference` / `relevance` |
| `TriccNodeInputModel` | Optional save calculate with `COALESCE`; set `expression` to `GET_INHERITED_VALUE(priors)` |

### 6.2 Export version pool (`set_last_version_false`)

Peers that share an **export base** are renumbered together:

- `repeat > 1` → pool key `(name, repeat)` (export uses `_Rr_n`)
- `repeat <= 1` (including default `1` and `-1`) → pool key `(name, "<=1")` so `_Vv_n` disambiguates without `_Rr_`

Implementation: `export_version_filter`, `get_export_version_peers`, `_export_version_bucket_key`.

### 6.3 Output serialization

- XLSForm / CHT: `tricc_operation_get_inherited_value` → same as `coalesce(...)`.
- FHIR/CQL: inherits through existing operation visitors (coalesce-equivalent).

## 7. Code checklist

- [x] `TriccOperator.GET_INHERITED_VALUE` in `models/base.py`
- [x] `get_version_inheritance` merges **all** prior versions
- [x] Origin-signature grouping for calculate inheritance
- [x] `merge_expressions` datatype rules
- [x] `process_operation_reference` display multi-version coalesce (`inherit_display_versions`)
- [x] `repeat=-1` excluded from inheritance sources/receivers; still referenceable
- [x] Export-name peer versioning for `repeat <= 1`
- [x] XLSForm/CHT serialize `GET_INHERITED_VALUE` as coalesce
- [x] Tests: `tests/test_display_reference_inheritance.py`, inheritance YAML fixtures, `tests/test_concept_repeat.py` (`repeat=-1` cases)

## 8. Acceptance criteria

1. When intermediate same-name activities are skipped, a later calculate still sees earlier values via multi-version inheritance.
2. Boolean same-name calculates merge with OR / `ISTRUE` semantics.
3. Multi-version **display** refs in expressions become `GET_INHERITED_VALUE`; relevance keeps a single last version.
4. `repeat=-1` never appears in another node’s inheritance operand list and does not receive inheritance.
5. Export names for `repeat <= 1` peers remain unique via `_Vv_` renumbering.
6. Existing diagrams without multi-version names behave as before (single version → no extra wrapper needed).

## 9. References

- Visitors: `tricc_oo/visitors/tricc.py` — `get_version_inheritance`, `merge_expressions`, `set_last_version_false`, `process_operation_reference`, `_filter_inheritable_versions`
- Export: `tricc_oo/strategies/output/xls_form.py` — `tricc_operation_get_inherited_value`
- Related features: `feature/concept-repeat.md`, `feature/display-text-injection.md`
- Tests: `tests/test_display_reference_inheritance.py`, `tests/data/yaml/inheritance_*.yaml`, `tests/test_concept_repeat.py`
- Docs: `docs/pipeline.md`, `docs/tricc-elements.md`, `docs/testing/transformation-test-coverage.md`
