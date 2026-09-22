# Option relevance drops the choice from the XLSForm choices sheet

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260813-option-relevance-toggle.md` (FHIR toggle; XLSForm choice filter already existed), `docs/pipeline.md` (output walk), `docs/tricc-elements.md` |
| **Strategy** | Graph walker + XLSForm / CDSS / CHT export (`generate_xls_form_export`) |
| **Approval** | 2026-09-21 conversation (user: option missing entirely from choices; implement on `fix/option-relevance-dropped-choice`) |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability).

---

# Part I — Issue analysis

*Audience: clinical authors, guideline developers, implementers.*

## 1. What went wrong

On a `select_one`, an author can put a **relevance** condition on a single answer option (for example: show this drip-rate choice only when `"etat.drops.rounded_fl" <= 180`). That is supported: the option should still be listed, and the form should hide it until the condition is true.

After adding that relevance in ETAT, the option **disappeared from the choices list entirely**. Other options on the same question were unchanged. The row is not in the XLSForm `choices` sheet, so CHT/ODK can never show it, even when the drop rate is 180 or less.

The quoted name `"etat.drops.rounded_fl"` is the correct TRICC spelling for a dotted calculate. This is not an authoring mistake.

## 2. Who is affected

Anyone exporting **XLSForm / CDSS / CHT** when an option’s relevance refers to a calculate or question that the exporter has not walked yet (typically a later node on the same page, a parallel branch, or another page). ETAT fluids (drop-rate options) is the reported case.

FHIR / OpenSRP list options from the parent question, not from a separate choices sheet, so they do not lose the row this way. Option hide/show there is `answerOptionsToggleExpression` (`fix/20260813-option-relevance-toggle.md`).

## 3. Expected vs actual

| | Expected | Actual |
|---|---|---|
| Choices sheet | Every authored option is a row. The filtered one has a `choice_filter` hash. | The option with relevance is missing. |
| Question | `choice_filter` shows that row only when the condition is true | Filter may still mention the hash, but there is no matching choice |
| Other options | Always listed | Listed (unchanged) |
| Form at runtime | Option appears when e.g. drop rate ≤ 180 | Option never appears |

## 4. Out of scope

- Changing how authors write option relevance (quotes, CQL).
- FHIR `answerOptionsToggleExpression` emission (already implemented).
- The known ODK limitation of `choice_filter` combined with option images (existing TODO in `generate_choice_filter`).
- Hiding the option in the running form when the condition is false (that is intended).

---

# Part II — Fix approach

## 1. Root cause

Option relevance is a `TriccOperation` on the option. Export and `load_calculate` both call `process_reference` **before** doing any work. That function returns `False` (defer) until every name in the expression is already in **this walk’s** `processed_nodes`.

`"etat.drops.rounded_fl"` is usually processed **after** the `select_one`. First visit of the option therefore fails the gate, and `generate_xls_form_export` never writes the choices row.

Other nodes that fail the gate are **stashed and retried**. Select options are not. After the callback, the walker always marks the option processed:

```text
callback(option, ...)
if option not in processed_nodes:
    processed_nodes.add(option)
```

It does not look at the callback’s return value. The option is never retried, so the row is never written.

The same gate also skips `load_calculate`’s `replace_reference=True` pass, so the authored relevance may stay as unresolved name references. That is a follow-on quality issue for the `choice_filter` XPath (dotted names). The missing row is the export + walker behaviour above.

## 2. Semantics (unchanged)

- Option `relevance` filters **which answers are shown**, not whether the option exists in the list.
- Empty / `true` relevance → always shown (`choice_filter` empty).
- Non-trivial relevance → choice row with a hash; question `choice_filter` is  
  `string-length(choice_filter)=0 OR (choice_filter = <hash> AND <condition>)`.
- Writing the choice row must not wait on the referenced calculate having been exported already. Resolving names for a good XPath can wait and retry; listing the option cannot be skipped forever.

## 3. Code checklist

- In `walktrhough_tricc_node_processed_stached`, treat a failed option callback like any other node: **do not** add to `processed_nodes`; **stash** the option so `stashed_node_func` retries after the referenced calculate is processed.
- Keep scheduling `option.next_nodes` (existing `walkthrough_tricc_option`) so the rest of the flow is not blocked on the filter.
- `generate_xls_form_export`: still write the choice when `process_reference` succeeds on retry. Optionally, write the choice even on a failed gate (parent select already printed) so a stuck stash cannot drop the row — hashes must stay consistent with the question’s `choice_filter` (same `option.relevance` tree).
- `load_calculate`: with stash/retry, the second `process_reference(..., replace_reference=True)` can run once the calculate is processed, so the filter XPath uses `${etat_drops_rounded_fl}` not an unresolved dotted name.
- Do **not** NAND option relevance into the parent question’s graph relevance.

## 4. Tests

YAML fixture (select_one **before** a calculate on the same page):

- `select_one` with two options; one has `relevance: '"later_calc" <= 180'`
- later `calculate` `later_calc`
- Full `XLSFormStrategy.execute()`

Assert:

- Both option values are on the `choices` sheet for that `list_name`
- The filtered option has a non-empty `choice_filter` hash
- The sibling option’s `choice_filter` is empty
- The question’s `choice_filter` mentions that hash and `${later_calc}` (export name)
- Control: the same select with no option relevance still lists both rows

## 5. Acceptance criteria

- ETAT option with `"etat.drops.rounded_fl" <= 180` is present on the choices sheet.
- In the form, that option appears only when the calculate is ≤ 180; other options always appear.
- Options without relevance are unchanged.
- Existing XLSForm / skip / not_available tests still pass.

## 7. Follow-on — shared choice list across versions

The same `select_one` name is one choice list, written once. The choice-row tag used to be a hash of `str(relevance)`, which includes the node id and `_Vv_` version. Copy 1 stored its tag; maintenance fluids (`_Vv_10`) looked for a different tag, so the option stayed hidden even when `<= 180` was true.

The tag is now the concept name (`etat.drops.rounded_fl_ped`), stable across versions. Each question's `choice_filter` still ANDs that shared tag with its own version (`${etat_drops_rounded_fl_ped_Vv_10}<=180`).

## 6. Docs (after Implemented)

- `docs/tricc-elements.md` — option `relevance` is a choice filter; the option always remains in the list definition.
- `docs/troubleshooting.md` — “option with relevance missing from choices” → this fix, not a drawing error.
