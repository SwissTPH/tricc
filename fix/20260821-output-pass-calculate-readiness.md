# Output-pass calculates silently degrade to constant `true`

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260820-opensrp-inherited-value.md`, `fix/20260821-merge-input-into-populate.md`, `docs/pipeline.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` (root cause in `visitors/tricc.py`; `XLSFormStrategy` affected by the fix) |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## 1. Symptom

Every OpenSRP export of real content logs a run of

```
WARNING - Calculate DisplayBridge|…|path: Rhombus|…|Age  < 7 returning no calculations (tricc.py:218)
WARNING - Calculate ProposedDiagnosis|CHE.B23.DE79|1|1|Deworming prevention needed returning no calculations
WARNING - Calculate Calculate|che.referral|1|2|che.referral returning no calculations
```

127 of them on the global almanach, 2 on `tests/data/etat.drawio`. The value is not left out —
it is replaced by the constant `true`, so `ETAT-main.cql` ships

```cql
define Calc_pTMVJByVCYcH1vvGJz3Hm_33: true
```

with an `initialExpression` pointing at it: a path condition that always fires. 45 of the 71
defines in that library are `: true`.

## 2. The expressions are not empty

`FHIRStrategy.generate_calculate` derives a value for nodes that carry no
`expression_reference` / `reference` (synthetic `Bridge` / `DisplayBridge` path nodes, and
calculates whose expression was never set) by calling
`get_node_expressions(node, kwargs["processed_nodes"], …)`. That function computes nothing at
all unless `is_ready_to_process(node, processed_nodes)` holds (`visitors/tricc.py:208`), and
`processed_nodes` here is the **output** walkthrough's own `OrderedSet`: empty at the start of
the calculate pass, filled as it walks. A node reached before its own prev nodes have been
visited *in that pass* fails the gate, `get_node_expression` is never called, `None` comes
back, and `visitors/tricc.py:212-219` turns the `None` into `TriccStatic(True)`.

Probe of the global build (operator left untouched, one record per fallback call):

| | count |
|---|---|
| fallback calls in the calculate pass | 529 |
| `is_ready_to_process` true | 402 |
| `is_ready_to_process` **false** | **127** — exactly the number of warnings |
| of those 127, a direct `get_node_expression` call at that same moment returned a real `TriccOperation` | 123 (`TriccStatic` for the other 4) |

Not-ready nodes by class: `DisplayBridge` 63, `Calculate` 44 (`che.referral`, `test_malaria`,
`needs_test`, `has_severe_disease`, `co_amox_7_1_hd_prescribed`, `CHE.B24.G.DE14`,
`CHE.B27.G.DE01`), `Bridge` 18, `ProposedDiagnosis` 2 (`CHE.B23.DE78`, `DE79`). Each one's
unvisited prevs are visible in the probe — `CHE.B23.DE79` waiting on a `SelectOption`,
`che.referral` on a `ProposedDiagnosis` plus sibling `Calculate`s, `test_malaria` on `Rhombus`
nodes, `has_severe_disease` on an `ActivityStart`.

`load_calculate` never hits this: unready nodes are stashed and retried. In the output pass
`generate_calculate` returns `True` unconditionally, so the node is asked exactly once, at the
wrong moment, and never revisited for that purpose.

Caveat on the probe: for `DisplayBridge` nodes it forced `get_overall_exp=True` where
production computes `False`, so the exact expression for those 63 would differ. The gate
returning `None` is read from the code path, not inferred.

## 3. Second defect in the same code path: duplicate CQL defines

`ETAT-main.cql` holds 71 `define`s but only **13 distinct names** —
`Calc_pTMVJByVCYcH1vvGJz3Hm_33` appears 38 times, `Calc_p4fjCBxxlf2C2cA8FoHnW_59` 16 times.
The walkthrough revisits nodes; once the first visit has stored `node.expression`, later visits
take the normal path and append *another* `define` with the same name to
`self.cql_defines[segment]`. Duplicate definitions make the library invalid CQL, and are a
plausible source of the `CQL Grammar Error` the build reports.

## 4. Not caused by the inherited-value fix

Identical on `HEAD` without `fix/20260820-opensrp-inherited-value.md`: same 2 etat warnings,
same 71 / 13 / 45 define counts.

## 5. Out of scope

- The readiness algorithm itself (`is_ready_to_process`) — unchanged.
- Why `Bridge` / `DisplayBridge` nodes carry no authored expression — that is by design
  (`inject_bridge_path`).
- The bare-`.` and bare-version-identifier CQL operands (separate defect, still open).

---

# Part II — Fix approach

## 6. Root cause

A readiness gate designed for a **retrying** pass (`load_calculate`, which stashes) is reused in
a **non-retrying** pass (`process_calculate` → `generate_calculate`, which always reports
success), and the failure mode is a silent value substitution rather than an error.

## 7. Fix rules

**R1 — retry instead of degrading.** When `generate_calculate` needs the fallback and
`is_ready_to_process(node, processed_nodes)` is false, return `False` so
`walktrhough_tricc_node_processed_stached` stashes the node and `stashed_node_func` re-walks it
once its prevs are processed. `stashed_node_func` already carries loop protection
(`check_stashed_loop`), so a node that can never become ready degrades exactly once, at the end,
instead of on first sight.

**R2 — never substitute a constant for a missing expression.** `get_node_expressions`
(`visitors/tricc.py:212-219`) must stop rewriting `None` to `TriccStatic(True)`. It keeps the
warning (raised to a single summary line per run where possible) and returns `None`, so a
calculate with no derivable expression is *visibly absent* rather than silently always-true.

**R3 — XLSForm keeps a valid `calculation` column.** ODK cannot have an empty `calculation` on a
`calculate` row, so the XLSForm serializer supplies the default that the visitor no longer
injects: when a calculate node's expression is `None`, write `1`. `xls_form.py:319-323` already
drops NaN/empty calculation rows from `df_calculate`, which would silently delete a field other
expressions reference by `${name}` — writing `1` is preferred over dropping. CHT/CDSS inherit
from `XLSFormStrategy` and are covered by the same change; DHIS2 / OpenMRS / HTML need the same
audit before merge.

**R4 — CQL defines are keyed, not appended.** `self.cql_defines[segment]` becomes a mapping
`define name → expression` (rendered to a list at assembly time in insertion order), so a
revisit overwrites its own define instead of appending a duplicate. Assembly
(`_assemble_cql_libraries`) must warn if two different expressions claim the same define name —
that would be a real name collision, not a revisit.

## 8. Code checklist

- `tricc_oo/visitors/tricc.py`
  - [ ] `get_node_expressions`: drop the `TriccStatic(True)` substitution (R2); keep/lower the log.
- `tricc_oo/strategies/output/fhir_form.py`
  - [ ] `generate_calculate`: return `False` when the fallback is needed and the node is not
        ready (R1); leave every other path returning `True`.
  - [ ] `cql_defines` → per-segment dict keyed by define name (R4); update
        `_assemble_cql_libraries`, `_attach_dedup_initial_expression`, and the `TriccNodePopulate`
        branch to write through it.
  - [ ] Skip attaching `initialExpression` / `calculatedExpression` when no expression could be
        derived (R2 consequence).
- `tricc_oo/serializers/xls_form.py` (and `strategies/output/xls_form.py`)
  - [ ] Default a `calculate` row's `calculation` to `1` when the node has no expression (R3).
  - [ ] Re-check the empty/NaN drop at `xls_form.py:319-323` — after R3 it should be unreachable.
- Docs
  - [ ] `docs/pipeline.md` — the output pass stashes like the input pass.
  - [ ] `docs/open-srp-export.md` — a calculate with no derivable expression exports no
        expression (was: constant `true`).

## 9. Tests

- [ ] YAML fixture where a calculate is reached before its prev in the output pass: the emitted
      expression is the real condition, not `true` (regression for the 127).
- [ ] A node that can never become ready: export completes, emits no expression, warns once.
- [ ] Revisited calculate: exactly one `define` per name in the assembled library.
- [ ] Two different expressions on one define name: assembly warns.
- [ ] XLSForm: calculate with no expression serialises `calculation = 1` and the row survives
      (not dropped), so `${name}` references stay valid.
- [ ] `python -m pytest tests/` green; `tests/build.py` on demo/etat/combacal for XLSForm,
      XLSFormCHT, FHIR, OpenSRP still produce loadable output.

## 10. Acceptance criteria — verified 2026-08-21

`tests/data/etat.drawio` → `OpenSRPStrategy`, `ETAT-main.cql`:

| | before | after |
|---|---|---|
| "returning no calculations" warnings | 2 | **0** |
| `define` statements | 71 | **11** |
| distinct define names | 13 | **11** |
| `define …: true` | 45 | **1** — that node's expression really is `TriccStatic(True)` (a bridge straight after MainStart, ready on first visit), not a degradation |

XLSForm side, `demo` / `etat` / `combacal` × `XLSFormStrategy`, `XLSFormCHTStrategy`: all exit 0,
**no empty `calculation` cell anywhere**, and the `1` default appears exactly once (etat). The
etat XLSForm calculate rows are **byte-identical to before this change** (11 rows, no differing
cell) — the visitor's old `TriccStatic(True)` also serialised as `1`, so ODK output is unchanged
while the FHIR export stops inventing `true`.

Global almanach (`L2/child` + `L2/common`), CQL libraries across all segments:

| | before | after |
|---|---|---|
| `define` statements | 96 012 | **1 384** |
| distinct define names | 1 368 | 1 384 |
| duplicates | 94 644 | **0** (defines == unique) |
| `define …: true` | 94 166 | **36** |
| "returning no calculations" warnings | 127 | **0** |

`imci-icrc-global-child-main.cql` alone: 95 564 defines / 920 unique / 94 166 `true` →
928 defines / 928 unique / 36 `true`. Those 36 survive because they are genuinely
`TriccStatic(True)`: with R2 in place an underivable expression returns `None` and
`generate_calculate` emits no define at all, so a `: true` can only come from a real constant.

`initialExpression` on Questionnaire items is unchanged at 457, i.e. the 94 644 duplicate defines
were pure library bloat — every item was already pointing at one name.

Global CHT-HF export: 1 637 rows, 730 `calculate` rows, **0 empty `calculation`**, `1` default on
10 rows, and the 8 pre-loaded values bound through `../inputs/contact/…`.

`pytest`: 251 passed, including `tests/test_output_pass_readiness.py` (9 new).

Not re-stated as criteria but worth recording: `stashed_node_func` calls `exit(1)` when the stash
stops shrinking, so R1 defers only while `warn` is false — the last attempt before that give-up
point derives whatever is available, exactly as before this change.
