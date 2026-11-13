# CHT export stops with "maximum recursion depth exceeded"

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `fix/cht-export-inputs-recursion` / `develop` |
| **Related** | `feature/20261111-block-params-and-start-node.md` (found while building a frontend-written block project), `fix/20260902-expression-recursion-hang-guard.md` and `fix/20261006-expression-memoisation.md` (other recursion fixes; they do not cover this walk) |
| **Strategy** | `XLSFormCDSSStrategy` and its subclasses (`XLSFormCHTStrategy`, `XLSFormCHTHFStrategy`) |
| **Approval** | Approved by Patrick on 2026-11-13 ("yes" to opening the fix PR). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability). Same two-part
shape and status gate; see `AGENTS.md`.

---

# Part I — Issue analysis

*Audience: authors exporting to CHT, and the frontend, whose default output is `XLSFormCHTStrategy`.*

## 1. What went wrong

Exporting to CHT stopped with `RecursionError: maximum recursion depth exceeded` in `export_inputs`. The XLSForm
export of the same project worked.

## 2. Who is affected

Any CHT (or other CDSS XLSForm) export of a project where a page is reached by `goto` from another page. A project
the frontend writes with a process activity called from the triage page is enough, with or without blocks.

## 3. Expected vs actual

| | |
|---|---|
| **Expected** | The CHT form is written, with the populate inputs of every page in the `inputs` group. |
| **Actual** | The export stops with a `RecursionError`. |

---

# Part II — Fix approach

## 4. Root cause

`export_inputs` collects the populate nodes of the start page and, recursively, of every activity among its nodes.
A page reached by `goto` lists itself among its own nodes, and the walk had no record of the pages already visited,
so it called itself on that page until Python's recursion limit. Two pages containing each other did the same.

The function also had a mutable default (`inputs=[]`), so the list was shared between calls: a second export in the
same process started with the first one's inputs.

## 5. Fix

- Keep a set of the activities already walked (by identity); skip an activity already in it, the page itself
  included.
- Default `inputs` to a new list on each call.
- Add a populate node once, even when its page is reached twice.

## 6. Tests

`tests/test_strategies/test_cht_export_inputs.py`: a page listing itself; two pages containing each other with a
shared page reached twice; two calls in a row. All three fail before the fix.

## 7. Acceptance

The frontend-written project (triage page, `danger_signs` process activity, `measure-temperature` block used twice)
exports to CHT with `temp_axillary`, `fever_axillary`, `temp_rectal` and `fever_rectal`.
