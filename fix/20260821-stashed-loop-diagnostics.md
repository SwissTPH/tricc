# Stashed-loop diagnostics hide the field that blocks a node

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Related** | `docs/troubleshooting.md`, `docs/pipeline.md`, `tests/test_stashed_loop_mermaid.py` |
| **Strategy** | Strategy-independent — `visitors/tricc.py` (`load_calculate` / `stashed_node_func` diagnostics); reproduced on `OpenSRPStrategy` |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## 1. Symptom

A conversion of the global almanach (`OpenSRPStrategy`, `L2/child` + `L2/common`) died with

```
CRITICAL - Stashed node list was unchanged: loop likely or unresolved dependence (tricc.py:2253)
```

followed by ~110 lines of `looped nodes` / `waited nodes` pairs and a 90-node Mermaid diagram.
The single author mistake behind it was **never named anywhere in that output**.

The actual cause was one constraint in `common/measurements.drawio`, page *Height and Length
Measurement*: `select_length_height` carried

```
$this != 'no_height_no_weight' or "CHE.B6.DE20" != '1'
```

`CHE.B6.DE20` sits five steps **downstream** of `select_length_height`
(`select_length_height` → options → `CHE.B6.DE13`/`DE10` → `r_` → `CHE.B6.DE19` → `CHE.B6.DE20`),
and `CHE.B6.DE20` carries the mirror-image constraint pointing back at `select_length_height`. A
node can never be processed before something that comes after it, so `select_length_height` was
re-stashed forever and everything behind it collapsed: the two measurement questions, `WFL`,
`WFH`, `CHE.B27.G.DE03`, `test_appetite`, `tests_display`, and finally the four inter-process
`Wait` barriers, which never saw their activity complete.

Removing that one constraint made the same run finish cleanly (8 questionnaires, 7 CQL
libraries, 8 FML mappings). The author content has since been corrected; **this spec is only
about the diagnostics**, which sent the reader to the wrong place.

## 2. Why the diagnostic pointed the wrong way

In the dump, `select_length_height` appeared in the stashed list with **no dependency at all** —
no `looped` line, no `waited` line, and in the Mermaid diagram a single incoming `prev` edge from
an already-processed `ActivityStart`. Read literally, the output said the node was ready to go.

Meanwhile `WFL`/`WFH` *were* listed as waiting on `CHE.B6.DE13`/`DE10`, so those looked like the
problem — they were three levels of collateral damage away from it.

The reason is a mismatch between two lists of fields:

| | fields |
|---|---|
| `process_reference` **blocks** on | `remote_reference`, `expression_reference`, `reference`, `relevance`, `trigger`, **`constraint`**, **`default`**, **`expression`**, `applicability`, and (display models) `TEXT_INJECTION_FIELDS` = `label`, `hint`, `help`, `constraint_message`, `required_message` |
| `iter_node_dependencies` **reports** (`visitors/tricc.py:2008`) | `expression_reference`, `reference`, `relevance`, `trigger`, `applicability` |

`constraint`, `default`, `expression` and the five text-injection fields can therefore stall a
node with no trace. `iter_node_dependencies` feeds both `get_all_dependant` (the `looped` /
`waited` logs) and `generate_stashed_loop_mermaid`, so the omission blanks the node out of every
diagnostic channel at once. A probe confirmed the deadlock returned from
`process_reference`'s `constraint` branch (`visitors/tricc.py:1049`).

## 3. Second gap: nothing distinguishes the three failure modes

Even for the fields that *are* reported, every unresolved reference is logged as the same
`[X] depends on [Y]` line. Three very different situations are flattened together:

- **Forward reference** — `Y` exists and is reachable downstream from `X`. Never satisfiable;
  the author must move or drop the reference. *(This was the bug.)*
- **Blocked** — `Y` exists but is stalled by something else. Collateral; ignore and fix the real
  one. *(`WFL` → `CHE.B6.DE13`.)*
- **Missing** — no node named `Y` anywhere. Typo or a node that was never drawn.

Only the third is currently recognisable, and only indirectly, by a `TriccReference` surviving in
the `waited` list.

## 4. Who is affected

Anyone authoring TRICC content who introduces a forward or circular reference in a
`constraint` / `default` / `expression` / label-injection field. The run aborts with `exit(1)`
after ~110 log lines that point at unrelated nodes. On the global almanach it took a
source-level bisect to find a single attribute.

## 5. Out of scope

- The circular constraint in `measurements.drawio` — author content, already fixed by hand.
- Making forward references *work*. They are genuinely unsatisfiable in a single-pass
  topological walk; this spec only makes them legible.
- Restructuring `process_reference` or the stash loop. No processing behaviour changes.
- Detecting the problem earlier (at link time, before ~111 futile loop iterations) — worth
  doing, but a separate change with its own risk profile.

---

# Part II — Fix approach

## 1. Root cause

`iter_node_dependencies` (`visitors/tricc.py:1968`) hardcodes a field tuple at line 2008 that
drifted out of sync with the fields `process_reference` (`visitors/tricc.py:888`) actually gates
on. Diagnostics can only show dependencies they enumerate, so a node blocked on `constraint`,
`default`, `expression`, or a text-injection field is reported as having no dependencies.

Separately, `get_all_dependant` classifies an unresolved reference only by
*processed / stashed / neither* and never checks graph reachability, so it cannot tell an
unsatisfiable forward reference from ordinary collateral blocking.

## 2. Rules

**R1 — one source of truth for gating fields.** The field list lives in a single module-level
constant, consumed by both `process_reference` and `iter_node_dependencies`:

```python
REFERENCE_GATING_FIELDS = (
    "expression_reference", "reference", "relevance", "trigger",
    "constraint", "default", "expression", "applicability",
)
```

`TEXT_INJECTION_FIELDS` is appended for `TriccNodeDisplayModel` instances only, matching
`process_reference`'s own guard. `remote_reference` is excluded: it resolves by HTTP fetch, not
by another node.

**R2 — locale dicts are traversed.** Text-injection fields may hold `{locale: TriccOperation}`.
`iter_node_dependencies` must descend into dict values, as `process_reference` does.

**R3 — etype stays `prev` / `ref`.** The Mermaid edge label and the two existing consumers keep
their current contract; the newly-covered fields simply produce `ref` edges that were previously
absent. Field names surface through R4, not through the edge label.

**R4 — a blocking-reference report, keyed by field and classified.** A new
`report_unresolved_references(stashed_nodes, processed_nodes)` runs **first** in
`check_stashed_loop`, before the existing `looped` / `waited` dumps and the Mermaid diagram, so
the actionable lines are at the top of the log rather than after 110 lines of context. For every
unresolved `TriccReference` on a stashed node it emits one line naming the **node, the field, and
the target**, classified as:

| class | condition | level | message shape |
|---|---|---|---|
| `forward` | target found in the graph and reachable from the stashed node by following `next_nodes` (through select options and activity exits) | `CRITICAL` | `unsatisfiable forward reference: [X] field 'constraint' -> [Y], which is downstream of [X] (N step(s)). Move the check onto [Y] or drop it.` |
| `missing` | no node of that name in the project | `CRITICAL` | `unknown reference: [X] field 'constraint' -> 'Y' is not defined in any page` |
| `blocked` | target exists, not processed, not downstream | `INFO` | `[X] field 'constraint' -> [Y] (not processed yet)` |

`forward` and `missing` are author errors requiring action; `blocked` is collateral and stays at
`INFO` so it does not compete for attention.

**R5 — bounded reachability.** Downstream search is a BFS over `next_nodes`, descending into
`TriccNodeSelect.options` and `TriccNodeActivity` entry/exit nodes, with a visited set and a
`MAX_DOWNSTREAM_WALK = 500` node cap. On hitting the cap it degrades to `blocked` rather than
guessing — a diagnostic must not become the slow or wrong part of a failing run.

**R6 — diagnostics never raise.** The report is wrapped like the existing Mermaid call
(`visitors/tricc.py:2303-2307`): any exception is logged at `WARNING` and the original
`CRITICAL` + `exit(1)` path is preserved unchanged.

## 3. Code checklist

- [ ] `tricc_oo/visitors/tricc.py` — add `REFERENCE_GATING_FIELDS` module constant near
      `MIN_LOOP_COUNT` (line 1965).
- [ ] `tricc_oo/visitors/tricc.py:888` `process_reference` — no behaviour change; add a comment
      cross-referencing the constant so the next field added updates both sides.
- [ ] `tricc_oo/visitors/tricc.py:2008` `iter_node_dependencies` — consume
      `REFERENCE_GATING_FIELDS` (+ `TEXT_INJECTION_FIELDS` for display models), and traverse
      locale dicts per R2.
- [ ] `tricc_oo/visitors/tricc.py` — new `iter_reference_fields(node)` yielding
      `(field_name, TriccReference)`, so the report can name the field.
- [ ] `tricc_oo/visitors/tricc.py` — new `_find_node_by_name`, `_is_downstream`, and
      `report_unresolved_references` per R4/R5.
- [ ] `tricc_oo/visitors/tricc.py:2244` `check_stashed_loop` — call the report first, guarded
      per R6.
- [ ] `docs/troubleshooting.md` — new section: reading the three classes, and that a forward
      reference in a `constraint` is an authoring error, with the `select_length_height` /
      `CHE.B6.DE20` case as the worked example.

## 4. Tests

Extend `tests/test_stashed_loop_mermaid.py` (unit-level, no draw.io input needed):

- [ ] `test_constraint_reference_is_reported` — node with only a `constraint` referencing a
      missing name appears in `iter_node_dependencies` and as a red `ref` edge in the diagram.
      This is the regression test for the reported bug.
- [ ] `test_default_and_expression_references_are_reported` — same for `default` and
      `expression`.
- [ ] `test_text_injection_locale_dict_reference_is_reported` — display node whose
      `label` is `{"en": TriccOperation(CONCATENATE, [TriccReference("x")])}` yields `x`.
- [ ] `test_non_display_node_skips_text_injection_fields` — mirrors `process_reference`'s guard.
- [ ] `test_gating_fields_match_process_reference` — asserts every field `process_reference`
      returns `False` on is covered, so the two lists cannot drift again.
- [ ] `test_forward_reference_classified_forward` — `A -> B` via `next_nodes`, `A.constraint`
      references `B`: report yields class `forward` naming field `constraint`.
- [ ] `test_blocked_reference_classified_blocked` — target exists, not downstream → `blocked`.
- [ ] `test_missing_reference_classified_missing` — no such node → `missing`.
- [ ] `test_cycle_in_next_nodes_terminates` — `A -> B -> A` does not hang the BFS (R5).
- [ ] `test_report_survives_malformed_node` — node raising from a reference field is logged, not
      propagated (R6).
- [ ] Existing assertions in `tests/test_stashed_loop_mermaid.py` (`-->|ref|` labels) must keep
      passing unchanged — that is what R3 protects.

## 5. Acceptance criteria

1. A node stalled on a `constraint` / `default` / `expression` / text-injection reference appears
   with that dependency in the `waited` / `looped` logs and as an edge in the Mermaid diagram.
2. Re-introducing the `select_length_height` constraint into `measurements.drawio` produces, in
   the **first** lines of the loop report, a `CRITICAL` naming `select_length_height`, the field
   `constraint`, and `CHE.B6.DE20` as downstream.
3. `WFL` → `CHE.B6.DE13` and the other collateral entries are classified `blocked` at `INFO`,
   not mixed in with the actionable lines.
4. A misspelled reference is classified `missing`, distinctly from `forward`.
5. `python -m pytest tests/` passes; `flake8 tricc_oo` clean.
6. No change to which nodes get processed: `tests/output/` for
   `python tests/build.py -i tests/data/demo.drawio -o tests/output/` is byte-identical before
   and after.

## 6. Phases

1. **R1–R3** — field-list unification and dict traversal, plus their tests. Fixes the invisible
   dependency on its own; low risk, no new logic.
2. **R4–R6** — classification report and `check_stashed_loop` wiring, plus tests.
3. **Docs** — `docs/troubleshooting.md`.
