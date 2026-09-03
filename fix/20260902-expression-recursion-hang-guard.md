# Conversion hangs forever instead of reporting a runaway expression recursion

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `fix/select-operand-coded-equality` / `develop` |
| **Related** | `AGENTS.md` (Debugging Tips), `docs/troubleshooting.md`, `tricc_oo/visitors/loop_guard.py` |
| **Strategy** | pipeline-wide (`DrawioStrategy` input stage; hit while exporting with `OpenSRPStrategy`) |
| **Approval** | Requested in the 2026-09-02 conversation (user reported `bp_int` never completing and asked for a breakpoint that aborts with a stack trace after a number of loops). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability). Same two-part
shape and status gate; see `AGENTS.md`.

---

# Part I — Issue analysis

*Audience: authors and implementers whose project "never finishes converting".*

## 1. What went wrong

Converting the `bp_int` project (9 draw.io files, ~1.6 MB, entry page **Navigation**) never finished. The run
printed its usual activity/code-system messages, reached

```
# Create the graph from the start node
```

and then produced no further output at all — no error, no progress, no exit. Left alone it stayed there
indefinitely; the only way out was to kill the process.

Nothing in the logs pointed at a page, an activity or a node, so an author had no way to tell whether the
project was too big, whether one particular flowchart was at fault, or whether the tool had crashed silently.

## 2. Who is affected

Anyone converting a large project whose entry page chains many `goto` steps guarded by rhombus conditions —
i.e. exactly the "navigation page that dispatches to sub-flows" pattern. Small projects are unaffected: the
reference projects (`demo`, `etat`, `combacal`) finish in seconds.

## 3. Expected vs actual

| | |
|---|---|
| **Expected** | The conversion either completes, or fails with a message naming the nodes it got stuck on. |
| **Actual** | The process ran forever with no output after `# Create the graph from the start node`. |

## 4. What the hang actually was

Not an infinite `while` loop, and not infinite recursion (Python's recursion limit was never reached). A
stack dump taken while the process was stuck (`faulthandler.dump_traceback_later`) showed the pipeline
cycling through expression generation:

```
get_node_expression -> get_prev_node_expression -> get_calculation_terms -> get_node_expression -> ...
```

with `TriccOperation.__str__` / `__eq__` (via `and_join` -> `clean_and_list`) at the bottom of the stack.

The Navigation page holds a chain of ~16 `goto` steps, each wrapped by a rhombus and its `pnav_rel_*` display
bridge. Expression generation expands each predecessor's expression from scratch, and every navigation step
expands its display bridge **twice** (once as the rhombus path, once as its own relevance). That doubles the
work per step, so the chain costs on the order of 2^16 expansions, each one building and string-comparing an
ever bigger expression tree. The work is finite in theory and unbounded in practice.

## 5. Scope of this fix

In scope: making that class of runaway work **fail fast and loudly**, with the node path and a stack trace,
so the offending part of the drawing is identifiable.

Out of scope (follow-up, needs its own `fix/` spec): removing the exponential re-expansion itself — i.e.
memoising per-node expressions during a walkthrough so a shared predecessor is expanded once. Until that
lands, `bp_int` still does not convert; it now stops in ~5 seconds and says where.

---

# Part II — Fix approach

## 1. New module: `tricc_oo/visitors/loop_guard.py`

Two guards plus a shared trip routine:

* `LoopGuard(name, max_iterations=None)` — iteration budget for a `while` loop. `tick()` once per iteration.
* `RecursionGuard(name, max_calls=None, max_depth=None, describe=describe_node)` — budget for a recursive
  function, used as a context manager (`with GUARD(node): ...`). It tracks nesting depth, the number of
  guarded calls made since the **outermost** call started (so the budget is per top-level entry, and resets
  when that call returns), and the chain of nodes currently being expanded.
* `trip(reason, context)` — logs the reason at `critical`, then the diagnostic lines, then
  `traceback.format_stack()`, and raises `TriccLoopError`. With `TRICC_LOOP_GUARD_PDB=1` it drops into `pdb`
  first, so the stuck state can be inspected live.

Guard targets are stored as-is and only turned into labels (`describe_node`: `Class::activity:instance|name`)
when a guard trips, so guarding a hot call costs one append and two integer comparisons.

## 1b. What a `RecursionGuard` trip reports

The point of the report is to name a spot in the drawing, so it is ordered narrowest-first:

1. **The node the recursion looped on**, with the depths it was seen at and the *repeating segment* between
   those two occurrences. `_find_loop` prefers a repetition that spans other nodes (`A -> B -> A`, a genuine
   graph loop) over an immediate repeat (`A -> A`); an immediate repeat is reported as a *re-entry*, worded to
   say that the level doubles the work, because that is what it means. When no node repeats at all, the report
   says the recursion fans out instead of looping and points at the deepest node.
2. **The path from the nearest branching node down to that loop.** Branching means the graph forks at the
   node: more than one predecessor (the direction expression expansion walks) or more than one next node —
   a rhombus, a merge, a select. The search starts strictly *above* the loop node, so the segment always has
   somewhere to start from; when the loop node branches too, that is called out separately, and when nothing
   above it branches the report says it hangs off the top-level entry. This is the stretch of flowchart to
   open in draw.io.
3. **Every node revisited on the path**, most revisited first.
4. **The full expansion path** (60 levels each side, middle elided) and the Python stack.

On `bp_int` step 1 and 2 read:

```
re-entry on node TriccNodeDisplayBridge::…|pnav_rel_12|…|path: Rhombus|n1462ed8a865ffea5|…: expanded again
  immediately, so every level of the chain doubles the work
  revisited at depth 20 and depth 21 of 37
the loop itself is on a branching node (2 prev, 1 next)
nearest branching above the loop: [19] TriccNodeRhombus::…|n1462ed8a865ffea5|0|1|BP status is active (1 prev, 2 next)
  path from there to the loop:
    [19] TriccNodeRhombus::…|BP status is active
    [20] TriccNodeDisplayBridge::…|pnav_rel_12|…
```

i.e. the rhombus *BP status is active* on the Navigation page and its path bridge — which is precisely the
doubling described in Part I §4.

## 2. Budgets

| Env var | Default | Healthy peak measured on `demo` / `etat` / `combacal` |
|---|---|---|
| `TRICC_MAX_LOOP_ITERATIONS` | 50 000 | 126 iterations |
| `TRICC_MAX_EXPRESSION_CALLS` | 20 000 | 18 calls per top-level entry |
| `TRICC_MAX_EXPRESSION_DEPTH` | 100 | depth 11 |
| `TRICC_LOOP_GUARD_PDB` | unset | — |

Three orders of magnitude of headroom over healthy runs, so a legitimately huge project is not blocked; if
one ever is, the failure message names the variable to raise.

## 3. Code checklist

- [x] `tricc_oo/visitors/loop_guard.py` — `TriccLoopError`, `trip`, `LoopGuard`, `RecursionGuard`,
      `describe_node`.
- [x] `tricc_oo/visitors/tricc.py` — module-level `EXPRESSION_GUARD = RecursionGuard("get_node_expression")`;
      `get_node_expression` is now a documented wrapper that enters the guard and delegates to the unchanged
      body, renamed `_get_node_expression`. All recursive call sites already go through the public name, so
      every level is counted.
- [x] `tricc_oo/visitors/tricc.py` — `stashed_node_func`'s `while len(stashed_nodes) > 0` loop ticks a
      `LoopGuard`. `check_stashed_loop` only detects a *frozen* stash list (it resets its counter whenever the
      set changes), so an oscillating stash could still spin forever; the iteration cap closes that.

No behaviour change on the happy path: the guards only observe.

## 4. Tests — `tests/test_loop_guard.py`

* `LoopGuard`: quiet within budget; trips past it with the env var named in the message; the diagnostic
  context callable is only evaluated when it trips; budgets read from the environment; a non-numeric env
  value falls back to the default.
* `RecursionGuard`: trips on depth; trips on call count even when depth stays low (the exponential case);
  the call budget resets after the top-level call returns; the path unwinds when an unrelated exception
  passes through; state is reset after a trip; diagnostics report revisited nodes and include a stack trace.
* Trip report: names the loop node, its depths and the repeating segment; reports the path from the nearest
  branching node (found via next nodes *or* predecessors) and excludes what sits above it; flags a loop node
  that branches itself; says "top-level entry" when nothing above branches; prefers a spanning loop over an
  immediate re-entry and words an immediate re-entry as a doubling; reports a fan-out when no node repeats;
  elides the middle of a very long path.
* Wiring: two mutually dependent calculates make `get_node_expression` trip (and leave the guard clean
  afterwards); a callback that never reports a node ready makes `stashed_node_func` trip with the callback
  name in the message.

## 5. Acceptance criteria

- [x] `python -m pytest tests/` passes (444 tests).
- [x] `flake8 tricc_oo` reports nothing new.
- [x] `demo`, `etat`, `combacal` convert unchanged.
- [x] `python tests/build_fhir.py -i "<bp_int folder>" -o out/` now exits non-zero after ~5 s with
      `loop guard tripped: get_node_expression made 20001 recursive calls ...`, the looping node
      (`pnav_rel_12`), the path from the rhombus *BP status is active* down to it, the revisited `pnav_rel_*`
      bridges, the full expansion path and a Python stack trace.
