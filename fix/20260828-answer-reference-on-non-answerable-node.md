# `.answer` references emitted against nodes that are not answerable items

| Field | Value |
|-------|-------|
| **Status** | Implemented (`tricc_oo` only — see §8) |
| **Related** | `fix/20260824-fhirpath-nested-item-path.md`, `fix/20260813-fhirpath-choice-answers.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` (tricc_oo) and `FhirFormStrategy` (tricc_og) |
| **Approval** | Approved — 2026-08-28 conversation. User: opt 1 / inline; "it should either copy the enableWhenExpression with a AND logic if the item/group have its own relevance". |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability).

---

# Part I — Issue analysis

## 1. Symptom

In the generated `imci_icrc_global_child` registration Questionnaire, whole branches of
the form never appear, no matter what the clinician answers. Concretely, the group
**"Additional Clinical Questions"** (`id_4f3982a991615e09b00c04ad988db3e68e9f`) — parent
of Diarrhoea, Fever, Ear, Mouth, **Skin**, **Eye**, Anaemia and Oral Fluid test — carries:

```
%resource.item.where(linkId='f06f5a6d5f79fd1470f41dcfe3c2046df65e')
  .answer.where($this.exists()).value = true
```

`f06f5a6d5f79fd1470f41dcfe3c2046df65e` is the **"Signs" activity**, exported as a FHIR
`group` — and, as it happens, an *empty* one (`"item": []`). Groups have no `answer`
element. The path yields an empty collection, `{} = true` yields `{}`, and
`convertToBoolean({})` is `false`. The group is therefore disabled for the entire
lifetime of the form, and by SDC's cascade rule so is every descendant.

This is what makes the Skin/Eye groups look like *their own* `enableWhenExpression` is
broken. It is not — theirs is correct and identical in shape to Ear's and Mouth's:

```
%resource.item.where(linkId='id_8d32…9f4b').repeat(item)
  .where(linkId='CHE_B10S1_DE05').answer.where($this.value.code = 'CHE.B14S1.DE02').exists()
```

The same code shape evaluated *inside* the Symptoms group (which has a valid relevance)
works fine, which is why swapping the coding for `CHE.B12S1.DE02` and testing it from a
hidden calculate in Symptoms appeared to "fix" it. The variable was the location, not the
code.

## 2. Who is affected

Every export where an authored node branches on a **container / routing** node rather than
on a question. Four occurrences in the current child form:

| Item carrying the expression | reads `.answer` of | node kind |
|---|---|---|
| `id_4f3982a99…` Additional Clinical Questions | `f06f5a6d…` "Signs" | activity |
| `…/id_431292c98…` Anaemia | `f06f5a6d…` "Signs" | activity |
| `id_26fe71bdd…` Temperature Measurement | `c965dacbe…` "Weight Measurement" | activity |
| `id_616d8c36a…` Respiratory Rate | `id_670c4821…` "Cough / difficulty breathing" | activity |

Temperature being permanently disabled additionally kills Height/Length Measurement,
whose own relevance reads `pL_qcudoAtlwiP3todriI_49` *inside* Temperature — a second-order
cascade.

## 3. Expected vs actual

**Expected.** Branching on a container node means "this container is relevant". The
exported FHIRPath must reproduce the container's relevance condition.

**Actual.** The exporter emits the *answer-value* idiom — the template used for a boolean
question — against a node that never becomes an answerable Questionnaire item. The
expression is syntactically valid FHIRPath, so nothing fails loudly: it silently and
permanently evaluates false.

Note the failure is asymmetric and therefore easy to misread in the field:
- written as `… = true` → always **false** → subtree never shows;
- written as `… = false` → also always **false** (`{} = false` is `{}`), *not* "true by
  default" as an author would expect.

## 4. Out of scope

- The Skin option's `answerOptionsToggleExpression` gate on `CHE_B27_G_DE01`, which is
  written `… .value = false` and so disallows the "Skin problem" option whenever that
  hidden calculate is merely unanswered. Author-content issue with the same
  empty-collection root cause; track separately.
- The android `AnswerOptionsToggleRebinder` workaround in `openSRP-fhircore` — it fixes
  *painting* of toggled options, unrelated to relevance.

---

# Part II — Fix approach

## 5. Root cause

`get_tricc_operation_operand_fhirpath` (`tricc_oo/strategies/output/fhir_form.py:1662`)
resolves an operand by falling through a type ladder whose last two rungs are identical:

```python
elif issubclass(r.__class__, TriccNodeInputModel):
    return self._fhirpath_answer(get_export_name(r))
elif issubclass(r.__class__, TriccNodeBaseModel):      # ← catch-all
    return self._fhirpath_answer(get_export_name(r))
```

`TriccNodeActivity` derives from `TriccNodeBaseModel` and from neither
`TriccNodeInputModel` nor `TriccNodeCalculateBase`, so it lands on the catch-all. So do
`TriccGroup` and the whole `TriccNodeFakeCalculateBase` family (`TriccNodeBridge`,
`TriccNodeActivityStart`, `TriccNodeActivityEnd`, `TriccNodeExclusive`, `TriccNodeWait`,
`TriccNodePopulate`, `TriccNodeFactor`), none of which are emitted as answerable items.

`tricc_og` has the same latent defect in `get_tricc_operation_operand`
(`tricc/tricc_og/strategies/export/fhir_form.py:295`), with no type discrimination at
all — the final two returns emit `.answer.value` for any `TriccReference` or any node.

## 6. Emission rule

> **R1.** `…answer…` may only be emitted for a node that is exported as an answerable
> Questionnaire item. The authority is `NODE_TYPE_TO_FHIR` / `SKIP_NODE_TYPES` in
> `questionnaire_item_mapper` — the same table `generate_base` emits from — **not** the
> class hierarchy. A node is answerable when its `tricc_type` is outside `SKIP_NODE_TYPES`
> and its mapped FHIR item type is neither `None` nor `group` / `display`. Note this makes
> several `TriccNodeFakeCalculateBase` kinds answerable (`bridge`, `wait`, `factor`,
> `populate` → hidden `boolean` / `decimal` / `string` items), while
> `activity` / `segment` / `page` / `activity_start` / `start` (`group`), `note` / `help` /
> `hint` (`display`) and `activity_end` / `end` / `goto` / `link_in` / `link_out` /
> `exclusive` (no item) are not. An unmapped `tricc_type` stays answerable — the historical
> idiom — rather than being guessed at.
>
> **R2.** For any other node — activity, `TriccGroup`, or a non-materialised routing node —
> the operand must be replaced by that node's own **relevance expression, inlined** and
> parenthesised. Because the operand sits inside the referencing item's own relevance
> operation, an item that also has conditions of its own naturally ends up with
> `own and (container relevance)`; an item whose only condition *is* the container gets a
> verbatim copy of the container's `enableWhenExpression`.
>
> **R3.** Inlining is recursive and must be cycle-guarded. On re-entry for a node already
> being inlined, fail open (`true`) and log a warning rather than recursing.
>
> **R4.** A non-answerable node with no effective relevance inlines to `true`
> (unconditionally relevant), never to an empty `.answer` path.

R2 is deliberately *inlining* (option 1) rather than materialising a hidden carrier
boolean (option 2): materialisation is already TRICC's job via `TriccNodeBridge` /
`TriccNodeDisplayBridge`, and adding a second mechanism in the exporter would produce two
competing sources of truth for the same container's relevance.

## 7. Code checklist — `tricc_oo`

- [x] `tricc_oo/strategies/output/fhir_form.py`
  - [x] import `NODE_TYPE_TO_FHIR`, `FHIR_TYPE_GROUP`, `FHIR_TYPE_DISPLAY` from
        `questionnaire_item_mapper`, and `TriccGroup` from `tricc_oo.models.base`
        (`TriccGroup` is not a `TriccNodeBaseModel`, so it previously fell through to the
        `NotImplementedError` rung).
  - [x] add `_is_answerable_item(node) -> bool` implementing R1 off the mapping table.
  - [x] add `_fhirpath_inlined_relevance(node) -> str`: reuse the existing
        `self._effective_relevance(node)` + `self.convert_expression_to_fhirpath(...)`
        pair (same primitives `generate_relevance` uses, so inlined text is identical to
        what the container's own `enableWhenExpression` would have been), wrap in
        parentheses, return `'true'` when there is no effective relevance (R4).
  - [x] cycle guard: `self._inlining_relevance: set[int]` of `id(node)`, entered/left
        around the recursive call (R3). `NotImplementedError` from the inner conversion
        also fails open to `'true'`, matching `generate_relevance`.
  - [x] split the catch-all in `get_tricc_operation_operand_fhirpath`: answerable →
        `_fhirpath_answer`; otherwise → `_fhirpath_inlined_relevance`.
  - [x] `TriccReference` branch: resolve the name to a node through a lazily-built
        export-name index (`_resolve_reference_node`) and apply the same rule; keep
        current behaviour when unresolvable.
  - [x] **`_should_wrap_first` must return `False` for a non-answerable operand.** Not in
        the original analysis but required: `_wrap_operand_if_needed` re-derives the
        operand text and string-replaces it with
        `<operand>.where($this.exists()).value`, which would corrupt an inlined boolean
        expression into `(<relevance>).where($this.exists()).value`.
- [x] Verify the CQL sibling path (`get_tricc_operation_operand`) does not carry the same
      catch-all — it does not: references resolve to `get_observation_cql_accessor(...)` /
      a bare `define` name, never to a `.answer` path. No change needed.

## 8. Code checklist — `tricc_og`

**Not implemented.** `tricc_og` lives in a separate repository
(`/mnt/data/Development/tricc`), outside this branch; the defect there was confirmed
still present (`get_tricc_operation_operand`'s trailing two returns emit
`%resource.repeat(item).where(linkId=…).answer.value` for any `TriccReference` and any
node). Carry the work over in that repo.

- [ ] `tricc/tricc_og/strategies/export/fhir_form.py`
  - [ ] add `_is_answerable_item(node)`: `self._type_code(node)` must be outside
        `SKIP_CODES` **and** present in `DISPLAY_TO_FHIR` (or the `TriccTask` fallback) —
        i.e. exactly the condition under which `_item_for_node` returns a dict. Deriving
        the predicate from the same tables keeps the two in lockstep.
  - [ ] non-answerable → inline via `get_relevance(...)` / `node.applicability`,
        parenthesised, `'true'` when absent (R4), cycle-guarded (R3).
  - [ ] apply to both the `TriccReference` branch and the trailing catch-all
        (lines 317-323).

## 9. Tests

All in `tests/test_strategies/test_fhir_relevance_fhirpath.py`
(`TestNonAnswerableOperandInlinesRelevance`, `TestGenerateRelevanceOnContainerOperand`).

- [x] Branching on a `TriccNodeActivity` emits the activity's relevance inline, and the
      output contains no `.answer` segment for the activity's `linkId`.
- [x] Same for a `TriccGroup` and a `TriccNodeActivityStart`. **Not** for
      `TriccNodeBridge`: per the corrected R1 a bridge *is* an answerable hidden
      `boolean` item, so it keeps `.answer` — asserted as such instead.
- [x] Answerability table covered directly: activity / `activity_start` / `activity_end` /
      `exclusive` / `note` non-answerable; `select_one` / `calculate` / `bridge`
      answerable.
- [x] Regression: branching on a `TriccNodeCalculate` still emits the exact previous
      string; `SELECTED` on a `TriccNodeSelectOne` still emits `.answer` membership; an
      unresolvable `TriccReference` keeps the answer idiom.
- [x] Cycle: two activities whose relevance references each other terminates and emits
      `true` for the re-entered node.
- [x] No-relevance container inlines to `true`, not to an empty answer path.
- [x] Integration mirror of the symptom: `generate_relevance` on a group whose relevance
      reads a sibling activity attaches one `enableWhenExpression` carrying the
      activity's condition and no `linkId='signs'` `.answer` path.
- [x] `AND` shape: an item with its own condition plus a container reference emits
      `own and (container relevance)`.
- [x] Standing export validation, in code rather than as a fixture assertion:
      `FHIRStrategy._validate_answer_references()` (called from `validate()`) logs an
      error for any exported expression that reads `.answer` of a `group` / `display`
      item, for every form, and is itself unit-tested (positive, negative, and the
      "linkId lives in another Questionnaire" exemption).
- [ ] `tricc_og`: mirror of the activity and calculate cases against `SKIP_CODES` — not
      done, see §8.
- [ ] `imci_icrc_global_child` regeneration — **not verified**: that input is not in this
      repo. `tests/data/demo.drawio` does not branch on a container, so it neither
      reproduced the bug before the fix nor changes after it (verified byte-identical
      export apart from a pre-existing run-to-run ordering flake on `demo_next_time`'s
      placement, present identically before and after). Re-export the real child form to
      close acceptance criterion 2; `validate()` will now log an error per offender.

## 10. Acceptance criteria

1. [x] No exported expression reads `.answer` of a `linkId` that is not an answerable
   item — enforced at emission and re-checked at `validate()`.
2. [ ] "Additional Clinical Questions", Anaemia, Temperature Measurement and Respiratory
   Rate enable from their real underlying conditions; Skin and Eye then respond to their
   `CHE_B10S1_DE05` selections. **Needs a re-export of the real child form to confirm in
   the field** (that input is not in this repo).
3. [x] Existing Calculate / InputNode references are byte-identical to before the change
   (unit-asserted, and the full `demo.drawio` openSRP export is unchanged).
4. [ ] Both repos implement R1–R4 from their own answerability source of truth —
   `tricc_oo` done, off `NODE_TYPE_TO_FHIR` / `SKIP_NODE_TYPES` (not the class hierarchy,
   see R1); `tricc_og` outstanding (§8).
