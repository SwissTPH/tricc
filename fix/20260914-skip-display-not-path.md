# Skip-if-already-asked must hide the later widget, not the rest of the flow

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `docs/tricc-elements.md` (concept repeat), `docs/pipeline.md`, `docs/troubleshooting.md`, `feature/concept-repeat.md`, group skip at XLSForm export (`get_prev_instance_skip_expression`) |
| **Strategy** | Graph + XLSForm / FHIR display serialisation |
| **Approval** | 2026-09-14 conversation (user: hide the later IV/IO widget if coma already answered; do not hide glucose / successors; path/bridge is arrival **or** already captured) |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability).

---

# Part I — Issue analysis

## 1. Symptom

The same capture (`etat.cv.tt.o2.001`, “Do you have an IV or IO access already?”) appears on coma and again on convulsion. After the coma question is answered:

- The convulsion copy must **not** be asked again (intended).
- **Check blood glucose** (`etat_c_005_r`, 2.5 mmol/l, non-SAM) and the rest of the convulsion flow **must still show** and follow the coma Yes/No.
- Instead the SAM path calculate (`pFPb67OBHywn1cBIkwTEi_0`) inlined `not(coma IV/IO filled and coma activity entered)`, so glucose and everything after the second widget stayed hidden.

Coma “The child is convulsing now” (`etat.coma.001.5`) must still leave coma (coma glucose must not stay open just because registration already has weight/age).

## 2. Who is affected

Clinicians running ETAT (and any guideline that re-asks the same named capture in a later activity). Authors do not need to rename the concept or set `repeat=-1`.

## 3. Expected vs actual

| | Expected | Actual (before fix) |
|---|---|---|
| Later widget | Hidden if an earlier same-name capture has a value | Hidden (via `node.relevance`) |
| Successors | Follow inherited Yes/No (`coalesce` of versions) | Path false because skip was copied into graph relevance |
| Same-page `repeat=1` vs `repeat=2` | Re-ask | — |
| `repeat=-1` | Never skip-suppressed, never a skip source | Already opted out of the fold |

## 4. Out of scope

- Author content / drawing changes.
- Renaming the concept or using `repeat=-1` as a workaround.
- Putting skip on calculate/bridge **survey rows**.
- OR-ing “already captured” into **question** graph relevance (that reopens coma glucose).

---

# Part II — Fix approach

## 1. Root cause

`load_calculate` NANDed “already captured” onto `node.relevance`. `get_node_expression(..., is_prev=True)` **inlines** that relevance for successors (and path/bridge calculates). Skip became both “don’t draw this widget” and “we never passed this node”.

ODK also blanks a hidden field, so successors that read only the later version see empty. Values must use `GET_INHERITED_VALUE` / `coalesce` (already true for several notes); path must not wait on the hidden field alone.

## 2. Three layers

| Layer | Who | Rule |
|---|---|---|
| Graph `node.relevance` | questions, notes, calculates | Arrival / flowchart only. Never NAND “already captured”. |
| Printed survey `relevant` / FHIR `enableWhen` | display widgets only (not calculate rows) | Arrival AND NOT already captured. Same pattern as group skip. |
| Path/bridge calculates (`TriccNodeDisplayBridge` / `TriccNodeBridge`) | only these | Arrival OR already captured. |

## 3. Already captured

- **Other activity:** earlier same-name node has data **and** that activity was entered (`ISTRUE(activity.root)` / `gcalc_…`). Uninstanced pages: identity is `activity.base_instance or activity` (`None != None` is a trap).
- **Same slot only** (`repeat_authored`, else 1), whether same page or later activity. `repeat=2` is an independent capture (ETAT: re-enter age after “estimated weight does not make sense”).
- Do **not** skip across slots. That hid convulsion IV/IO `_Rr_2` after coma, but also hid the age/weight amend questions after confirmation **No**.
- Key skip on `repeat_authored`, not effective `get_repeat` (activity-level override still hides a same-slot copy whose export name is `_Rr_2`).
- **`repeat=-1`:** never skip-suppressed, never a skip source.

## 4. Code checklist

- Remove the skip fold from `load_calculate`.
- Helpers next to group skip in `visitors/tricc.py`: predicate, NAND for print, OR for path/bridges only.
- `pass_skipped` on `get_node_expression` (no module-global flag). Set when the **current** node is a display/fake bridge.
- Keep `repeat_authored` so same-page recapture stays slot-scoped (`propagate_activity_repeat` must snapshot before overwrite).
- XLSForm: `serialize_display_relevance` on question/note `relevant` (and more-info that copies it). If arrival simplifies to true, still print skip.
- FHIR: same helper on display `enableWhen`.
- Do not mutate `node.relevance` with skip. Do not OR skip into question relevance. Do not put skip on calculate/bridge **rows**.

## 5. Tests

- Graph relevance of the second question has no skip.
- Printed second question does hide if the first was answered (**same** author slot, including another activity).
- Later `repeat=2` of the same name does **not** hide (age/weight amend).
- Note/question after the second does not copy NAND skip.
- Path/bridge through the second is true if the first has data even when second arrival is false.
- Same-page `repeat=1` vs `repeat=2` does not skip.
- `repeat=-1` does not skip.

ETAT after export (`tricc -i ./etat -o ./output_drive -T TestSpecStrategy`):

- After the drawing dropped `repeat=2` on convulsion IV/IO, both copies are **slot 1**. `etat_cv_tt_o2_001` on convulsion (no `_Rr_2` unless activity override) `relevant` contains `not(… etat_cv_tt_o2_001 … and gcalc_etat_coma)`.
- Age amend after `etat_c_042` = No (`etat_r_003_Rr_2` / months / years) is **not** `not(registration age and gcalc_etat_registration)`.
- `pFPb67OBHywn1cBIkwTEi_0` ORs “already captured” only for **same-slot** sources (not `not(…)`).
- `etat_coma_005` relevant does not open just because registration/circulation already has weight/age.

## 6. Acceptance

The later same-slot IV/IO widget is hidden after coma answered it; convulsion glucose (non-SAM) and Yes/No treatments still follow the inherited answer; saying **No** to estimated weight still shows the `repeat=2` age amend; coma still hands off to convulsion when “convulsing now” is selected.

## 7. Why (short)

Skip used to live on `node.relevance`, so “don’t draw this box” also meant “we never passed this box.” Print-time NAND on the widget + OR on path/bridges splits those. Skip is **same author slot** so `repeat=2` can recapture (age/weight amend) while omitted `repeat` still hides a later copy of the same question (`instance` is not a new slot).
