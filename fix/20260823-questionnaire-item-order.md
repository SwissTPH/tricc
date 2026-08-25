# Questionnaire items appear in reverse / late-first order

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260821-opensrp-questionnaire-duplicate-calculates.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` (walk stash order also used by other strategies) |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## 1. Symptom

On the global IMCI child OpenSRP registration Questionnaire, the **first**
authored questions (Registration group, clinician script, age, sex, disclaimer)
are the **last** items. Clinical pages (breastfeeding, vaccination, HIV, …)
appear first — as if each newly visited group was inserted at the beginning
of the form.

openSRP renders items in Questionnaire order, so the clinician script is
the last screen instead of the first.

## 2. Cause

The output walk is a stack: `OrderedSet.insert_at_top` + `pop()` from the
front. Successors were pushed in **authored** `next_nodes` order, which
reverses them (last edge processed first). FHIR `generate_base` also
**always succeeds** (no `is_ready_to_process`), so it emits in that reverse
DFS order instead of waiting for previous nodes.

A linear chain is fine; a start/page with several outgoing activities
(Registration, then assessment pages) emits the last sibling first.

The group stack is global across processes, so a group opened in one
Questionnaire can steal children of another.

## 3. Out of scope

- Changing CPG process assignment (what lives on the registration form).
- Reordering option lists / answerOptions.

---

# Part II — Fix approach

## 4. Emission rules

**R1 — First next-node is processed first.**
When pushing `next_nodes` onto the stash, insert them in reverse so the
stack pops the first edge first.

**R2 — FHIR emits a node only when its prevs are processed**
(`is_ready_to_process`, same as XLSForm `generate_base`). Unready nodes
go to the bottom of the stash.

**R3 — Nest only inside a group of the same Questionnaire.**
`_group_stack` parent is used only when `parent_segment == node segment`.

**R4 — After the base walk, sort each Questionnaire's items (and nested
groups) by `path_len`, then emit sequence.** Earlier flowchart nodes first.

## 5. Code checklist

- [x] `stash_next_nodes` in `visitors/tricc.py`
- [x] FHIR `generate_base` readiness + same-segment group stack
- [x] `_sort_questionnaire_items` after `process_base`
- [x] test: two siblings from start emit in edge order
- [x] `docs/open-srp-export.md`
