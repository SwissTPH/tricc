# Empty `group` items are exported into the Questionnaire

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260828-answer-reference-on-non-answerable-node.md`, `fix/20260824-prune-unused-initial-calculates.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |
| **Approval** | Approved — 2026-08-28 conversation (user: "a group should not be empty (no items); if empty --> should not be on the questionnaire"). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability).

---

# Part I — Issue analysis

## 1. Symptom

Exported Questionnaires contain `group` items with no children:

```json
{ "linkId": "nc07d18be042f3041", "text": "Demo Tricc", "type": "group", "item": [] }
```

A FHIR SDC `group` is a container: it has no `answer` and nothing to render on its own.
An empty one is a dangling section header — the renderer paints a title (or a blank
page in a paged layout) for a section with nothing in it.

`tests/data/demo.drawio` reproduces it: one empty group in the `main` Questionnaire.

## 2. Who is affected

Every export. Empty groups arise from two directions:

- **Authored** — an activity or page whose nodes all land in a different process /
  Questionnaire, or a routing-only activity whose members are all node types that map
  to no item (`end`, `goto`, `link_in`/`link_out`, `exclusive`).
- **Emitted then emptied** — `_prune_unused_hidden_calculates` removes the last hidden
  calculate inside a group, leaving the container behind. That pass already
  `pop("item")`s an emptied child list but never reconsiders the parent.

## 3. Expected vs actual

**Expected.** A `group` earns its place in the Questionnaire by containing something.
With no items it should not be exported.

**Actual.** It is exported, and openSRP renders it as an empty section.

An empty group is also a standing trap for readers of an export: it is exactly the
shape that made the "Signs" activity in
`fix/20260828-answer-reference-on-non-answerable-node.md` look like a question that
had simply never been answered, rather than a container that can never carry an answer.

## 4. Out of scope

- Whole empty **Questionnaires** — already handled by
  `OpenSRPStrategy._prune_empty_questionnaires`. This fix feeds it: a Questionnaire
  whose only content was empty groups becomes `item: []` and is then dropped by the
  existing pass.
- Deciding *why* an activity ended up with no items. Pruning the empty container is
  correct regardless of the cause; a container that should have had children is an
  authoring or graph-linking issue and shows up as a missing section either way.

---

# Part II — Fix approach

## 5. Root cause

No pass reconsiders a container after its children are resolved.
`_filter_unused_hidden_calculates` (`tricc_oo/strategies/output/fhir_form.py`) removes
the emptied `item` key from a parent:

```python
if new_children:
    item["item"] = new_children
else:
    item.pop("item", None)
```

but the parent itself is then appended to `kept` unconditionally — the only drop test
is `_is_unused_hidden_calculate`, which requires the item's type to be in
`_PRUNE_CALC_ITEM_TYPES` (`group` is not).

## 6. Emission rule

> **R1.** A `group` item with no child `item` is not exported.
>
> **R2.** The test is applied **depth-first**: a group emptied by its own children being
> dropped is itself dropped, transitively, up to the Questionnaire root.
>
> **R3.** Pruning runs **after** `_prune_unused_hidden_calculates` (which is what empties
> groups) and **before** `_assemble_extraction_maps` / `_assemble_cql_libraries`, so
> StructureMaps and CQL libraries see the final tree — the same ordering constraint
> `fix/20260824-prune-unused-initial-calculates.md` established.
>
> **R4.** Per-segment assets are resynced against the surviving `linkId`s exactly as the
> calculate prune does (extraction rules trimmed / dropped, orphan CQL defines removed).
> Groups are not normally extracted, but the two passes must not diverge.
>
> **R5.** A group is judged on child items only. `text`, `enableWhenExpression` and media
> extensions do not save it: there is nothing for a gate to reveal and no author-facing
> content that a childless container can render.

## 7. Code checklist

- [x] `tricc_oo/strategies/output/fhir_form.py`
  - [x] extract the extraction-rule / CQL-define resync tail of
        `_prune_unused_hidden_calculates` into `_resync_segment_assets(segment, q)` and
        call it from there (no behaviour change), so the new pass reuses it (R4).
  - [x] add `_filter_empty_groups(items) -> (kept, removed)`: depth-first, drops
        `type == "group"` items with no `item` (R1, R2).
  - [x] add `_prune_empty_groups()`: per Questionnaire, filter + resync + log.
  - [x] call it from `execute()` between `_prune_unused_hidden_calculates()` and
        `_assemble_extraction_maps()` (R3).
- [x] `docs/open-srp-export.md` — note the pass next to the existing prune documentation.

## 8. Tests

- [x] Empty group at root is dropped; a group with one child is kept.
- [x] Nested: a group whose only child is an empty group is dropped transitively (R2).
- [x] A group is dropped even when it carries `text` and an `enableWhenExpression` (R5).
- [x] Extraction rules naming only dropped `linkId`s are removed; rules naming a
      survivor keep it (R4).
- [x] Pipeline order: after a hidden calculate is pruned as unused, the group that held
      it is gone too (R3) — the "emitted then emptied" path from §2.
- [x] `demo.drawio` openSRP export contains zero empty groups, and no other item is lost.

## 9. Acceptance criteria

1. [x] No exported Questionnaire contains a `group` item without children. Verified on
   the `demo.drawio` openSRP export (was 1, now 0).
2. [x] A Questionnaire left with `item: []` is still dropped by the existing
   `_prune_empty_questionnaires` pass (openSRP). Observed on `demo.drawio`: `main`
   contained *only* the empty group, so it is now dropped along with its extract / task
   StructureMaps. All demo content lives in `registration`; the package goes from 2
   Questionnaires to 1.
3. [x] No non-group item, extraction rule naming a surviving item, or CQL define
   reachable from a surviving item is lost. Package-wide reference sweep after the
   change: 8 resources, 9 references, 0 dangling.

## 10. Note for the reader

Criterion 2's cascade is the visible consequence of this fix, not a side effect to be
undone: a process whose Questionnaire consists solely of empty containers has no content
to capture, and the openSRP package is better without the dangling PlanDefinition action
and Task StructureMap that pointed at it. If a process you expect to have questions
disappears after this change, the bug is upstream — its nodes are landing in another
Questionnaire, or its members all map to no item at all.
