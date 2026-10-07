# Large navigation pages trip the loop guard although the drawing has no loop

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `fix/looping-error-crash-calculation-exponential` / `develop` (PR #72) |
| **Related** | `fix/20260902-expression-recursion-hang-guard.md` (the guard this follows up; its §5 lists this memoisation as out of scope), `tricc_oo/visitors/loop_guard.py` |
| **Strategy** | pipeline-wide (expression generation in `tricc_oo/visitors/tricc.py`, used by every input/output strategy) |
| **Approval** | Implemented in PR #72; reviewed 2026-10-07. |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability). Same two-part
shape and status gate; see `AGENTS.md`.

---

# Part I — Issue analysis

*Audience: authors and implementers whose large project stops with a "loop guard tripped" error.*

## 1. What went wrong

Since `fix/20260902-expression-recursion-hang-guard.md`, a conversion that does runaway work stops after
20,000 recursive expression calls with `loop guard tripped`, instead of hanging. That guard was meant to catch
real dependency loops. Large projects with no loop at all hit it too: a long Navigation page that dispatches to
sub-flows is enough. The conversion fails, and the guard's report points at a "loop" the author cannot find in
the drawing, because there is none.

## 2. Who is affected

Anyone converting a project whose entry page chains many decisions, each followed by a `goto` and both
branches meeting again — the "navigation ladder" pattern. Each extra step doubles the work, so the failure
appears suddenly once a page grows past roughly 12–14 steps. Small projects (`demo`, `etat`, `combacal`) are
unaffected.

## 3. Expected vs actual

| | |
|---|---|
| **Expected** | A drawing without loops converts, whatever its size; the guard only trips on a real loop. |
| **Actual** | Past a dozen or so navigation steps, the conversion stops with `loop guard tripped`. |

## 4. Why it happened

To build the expression of a node, the converter builds the expression of each predecessor. In a navigation
ladder every step reaches the previous step along two paths (the "Yes → goto" branch and the "continue"
branch), and the previous step's expression was rebuilt from scratch for each path. The work therefore doubles
per step: 2^n expansions for n steps. Measured on the synthetic ladder used by the test:

| Steps | Guarded calls, before | Guarded calls, after |
|------:|----------------------:|---------------------:|
| 8 | 2,805 | 56 |
| 12 | 45,045 | 84 |
| 16 | 720,885 | 112 |
| 30 | (≈ 2^30, never finishes) | 210 |

The guard budget is 20,000 calls, so the 16-step ladder already fails.

## 5. Scope of this fix

In scope: build each predecessor's expression once per top-level request, so the work grows linearly with the
size of the page, and real loops still trip the guard.

Out of scope: reusing expressions *across* top-level requests (the graph and the processed-node set change
between them), and any change to the guard's budgets or diagnostics.

---

# Part II — Fix approach

## 1. Memoise `get_node_expression` within one top-level call

`get_node_expression` (the guarded entry point) keeps a cache, `_EXPRESSION_CACHE`, that exists only while a
top-level call is running:

- The outermost call creates it (`None` → `{}`) and clears it in a `finally`, so it never survives the call,
  including when the guard raises `TriccLoopError`.
- Key: `(id(in_node), id(processed_nodes), get_overall_exp, is_prev, negate, process[0])` — every argument
  that changes the result.
- A result is cached only **after** it has been built. A node whose expression is still being built is not in
  the cache, so a real dependency loop keeps recursing and still trips the guard.
- The entry stores `(in_node, expression)`: keeping the node alive stops Python from reusing its `id()` for
  another node during the call.
- Hits and fresh results are both returned as a copy (`TriccOperation.copy(keep_node=True)`), so callers
  never share — and mutate — one operation. Non-operation results (`TriccStatic`, `None`) are returned as is.

## 2. Why the cache cannot go stale within a call

Every nested call in one top-level request receives the same `processed_nodes` object. The expression helpers
(`get_prev_node_expression`, `get_calculation_terms`, `get_rhombus_terms`, `get_applicability_expression`, …)
read it but do not add to it or remove from it, and do not change the graph in a way that affects an already
built expression (the rhombus `path` back-fill is idempotent). Callers add nodes to `processed_nodes` only
after the top-level call returns, which is why results are never reused across calls.

## 3. Design note: module-level cache

The cache is module state, like `EXPRESSION_GUARD`. TRICC converts single-threaded, so this is safe today.
If conversions ever run concurrently in one process (threads or async, e.g. behind a web front end), move it
to a `contextvars.ContextVar` or onto `RecursionGuard`, which already resets per top-level entry; the
semantics above stay the same.

## 4. Code checklist

- [x] `tricc_oo/visitors/tricc.py` — `_EXPRESSION_CACHE`, `_expression_cache_key`,
      `_cached_expression_copy`; `get_node_expression` consults and fills the cache around the guarded call.

## 5. Tests — `tests/test_expression_memoisation.py`

- [x] A 30-step ladder (2^30 paths) builds within a budget of 20 calls per step.
- [x] The cache is `None` after the top-level call returns.
- [x] Two requests for the same node return equal but distinct operations, with distinct operand lists.

## 6. Acceptance criteria

- [x] `python -m pytest tests/` passes (588 tests).
- [x] `flake8` reports nothing new in the changed files.
- [x] `demo.drawio` converts to identical XLSForm content and identical FHIR output with and without the fix.
