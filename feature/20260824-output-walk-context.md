# Output walk callback contract (process, operators, execute pipeline)

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `feature/repeat-inheritance` |
| **Related** | `fix/20260823-questionnaire-item-order.md`, `fix/20260820-opensrp-inherited-value.md`, `fix/20260821-output-pass-calculate-readiness.md`, `feature/advanced-merge-calc.md`, `docs/pipeline.md`, `docs/open-srp-export.md` |
| **Strategy** | Shared output walk (`BaseOutPutStrategy` + visitor). Motivated by `FHIRStrategy` / `OpenSRPStrategy`; XLSForm, CHT, DHIS2, HTML keep working unchanged. |
| **Authoring surface** | None — exporters only. Authors do not change diagrams. |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business description

*Audience: guideline implementers and engineers evaluating OpenSRP / multi-form exports. Authors of draw.io diagrams are unaffected.*

## 1. Overview

TRICC walks the clinical flowchart once per export pass and asks the chosen output format to emit each node. That walk is shared. What each format *does* with a node is not.

XLSForm (ODK, CHT) produces **one form**. OpenSRP / FHIR produces **one form per clinical process** (registration, triage, assessment, …), nested sections, and two kinds of logic: live in-form expressions, and one-time lookup from the patient record.

Those extra OpenSRP needs have been patched around the shared walk: process name forgotten on some steps, parent section reconstructed from visit order, operator handlers given only the rendered text of an expression instead of the original clinical references. The result has been real export defects — questions in the wrong order, inherited values that cannot tell “answered in this form” from “already on the encounter”, calculates that fire before their inputs exist.

This change makes the shared walk **honest about the context every format already needs**, without turning it into an OpenSRP-specific walker. Packaging unique to OpenSRP (PlanDefinition, Composition, Task maps) stays after the walk.

## 2. What implementers see

No new authoring attributes. No change to how a guideline is drawn.

After this lands, OpenSRP packages should be **less sensitive to walk accidents**:

- A node that belongs to triage stays on the triage Questionnaire even when the walk recurses through a nested activity.
- Multi-version values (`weight` asked in two places) still pick the in-form answer when it exists in *this* form, and fall back to the encounter when it does not.
- Relevance is a first-class export pass for every strategy, not a FHIR-only extra step.

XLSForm / CHT behaviour stays the single-form export it is today.

## 3. Benefits

- OpenSRP item order, grouping, and inherited values stop depending on hidden walk quirks.
- New output strategies get a documented callback contract instead of copying FHIR’s private `execute()` or DHIS2’s positional `processed_nodes`.
- Operator handlers that need the original clinical node (OpenSRP inherited value, repeat slot) no longer break the documented base signature.

## 4. Limitations

- This does **not** add OpenSRP packaging to the walk (PlanDefinition, Composition, binaries). Those remain post-walk.
- This does **not** change how authors write expressions or `repeat` slots.
- Grouping for ODK (`begin_group` / `end_group` around a stash batch) stays an XLSForm concern. The walk will not invent ODK groups.
- `get_process(node)` (walk the graph upward for the cpg-common-process name) remains the source of truth for “which clinical process is this node?”. The walk’s process pointer is a **hint that must stay in sync**, not a second competing rule.

## 5. Out of scope

- Rewriting the walker as a FHIR Questionnaire-tree builder.
- Changing CPG process assignment or splitting/merging Questionnaires.
- Replacing `GET_INHERITED_VALUE` semantics (`fix/20260820-opensrp-inherited-value.md`).
- Changing stash order / first-next-node-first (`fix/20260823-questionnaire-item-order.md`).
- Renaming the typo’d walker (`walktrhough_tricc_node_processed_stached`) — mechanical only if touched; not a goal.

---

# Part II — Technical specification

## 6. Current contract (the problem)

Output strategies share one walker:

```text
BaseOutPutStrategy.process_*  →  stashed_node_func  →  walktrhough_tricc_node_processed_stached
                                                     →  callback = generate_base | generate_relevance
                                                                  | generate_calculate | generate_export
```

The walker already *computes* more than it *guarantees*:

| Fact | How it is passed today | Breakage |
|------|------------------------|----------|
| `processed_nodes` / `stashed_nodes` | Keyword args into `**kwargs` | DHIS2/OpenMRS declare them as real parameters; FHIR/OpenSRP read `kwargs`; signatures disagree with `BaseOutPutStrategy.generate_*(node, **kwargs)` |
| `process` (mutable `[name]`) | Named arg on the walker; popped out of kwargs in `stashed_node_func` | Dropped on recursive calls (activity root, groups, dangling calculates, post-activity `next_nodes`, `walkthrough_tricc_next_nodes`, `walkthrough_tricc_option`). FHIR `generate_calculate` still does `kwargs.get("process")` |
| Parent group | XLSForm: `cur_group` in kwargs + custom `activity_export`. FHIR: `self._group_stack` | Stack leaked across Questionnaires; item order reversed until `fix/20260823-questionnaire-item-order.md` |
| Operator operands | Base ABC: `tricc_operation_*(ref_expressions)` | XLSForm and FHIR already call `(ref_expressions, original_references)`. HTML still calls one argument. `GET_INHERITED_VALUE` on FHIR *requires* the original nodes |
| Relevance pass | `process_relevance` exists on the base class | `BaseOutPutStrategy.execute()` never calls it. FHIR, HTML, DHIS2 each copy `execute()` to insert the pass |

OpenSRP’s extra artifacts (PD, Composition, Task StructureMap) are produced in `OpenSRPStrategy.export()` **after** the walks. They do not belong in the walker.

## 7. Formal rules

### R1 — Callback contract (all four `generate_*`)

Every output callback is invoked as:

```python
callback(
    node,
    processed_nodes=processed_nodes,
    stashed_nodes=stashed_nodes,
    process=process,
    warn=warn,
    node_path=node_path,
    **kwargs,
)
```

`BaseOutPutStrategy.generate_base / generate_relevance / generate_calculate / generate_export` declare those names (plus `**kwargs`). Strategies may still keep extra kwargs (`df_survey`, `cur_group`, `pages`, …). They must not rely on `process` arriving only through `kwargs` after a recursive walk.

Return value is unchanged: `True` = processed (or skipped on purpose); `False` = stash and retry.

### R2 — `process` is forwarded on every recursive walk

`stashed_node_func` continues to own a single mutable `process` list (default `["main"]`).

Every call into `walktrhough_tricc_node_processed_stached` from:

- `stashed_node_func` (initial + stash retry),
- activity-end scheduling of `activity.next_nodes`,
- activity-start groups and dangling calculates,
- `TriccNodeActivity` → `node.root`,
- `walkthrough_tricc_next_nodes`,
- `walkthrough_tricc_option`,

must pass `process=process`.

The existing mutate/restore around the callback stays:

```text
prev = process[0]
if node is an activity whose root has .process:
    process[0] = that name
callback(...)
if callback failed and process[0] changed:
    process[0] = prev
```

`get_process(node)` remains the graph-level source of truth for Questionnaire / CQL segmentation. The walk pointer must not disagree with it after R2; FHIR may keep using `get_process(node)` and stop treating `kwargs["process"]` as optional.

### R3 — Operator handlers accept original references

Base (and therefore every strategy) signature:

```python
def tricc_operation_<op>(self, ref_expressions, original_references=None):
```

`get_tricc_operation_expression` (every strategy that dispatches handlers) calls:

```python
handler(ref_expressions, original_references)
```

Handlers that ignore the second argument keep working. FHIR `GET_INHERITED_VALUE` / `GET_REPEATED_VALUE` keep using it. HTML/DHIS2/OpenMRS are updated at the dispatch site so they do not raise `TypeError` if a future handler requires the second arg — passing it is enough; they need not *use* it.

### R4 — Base `execute()` runs the relevance pass

`BaseOutPutStrategy.execute()` becomes:

```text
process_base
process_relevance    # new in the base pipeline
process_calculate
process_export
export
validate
```

XLSForm’s `generate_relevance` can remain a no-op (relevance is still written during `generate_export` from `node.relevance` computed in `load_calculate`). FHIR, HTML, and DHIS2 drop their private copies of this sequence unless they still need strategy-specific setup (FHIR: reset `_group_stack`, resolve form id, assemble CQL/StructureMaps **after** the four walks).

### R5 — Do not FHIR-shape the walker

The walker does **not** grow:

- Questionnaire / `item[]` trees,
- CQL define maps / StructureMap rules,
- `_current_segment` / `_current_node_link_id` (serialisation context stays on `FHIRStrategy`),
- PlanDefinition / Composition / Binary.

Parent grouping:

- XLSForm keeps `cur_group` + `activity_export` (stash-pop batch = one ODK group). That is format-specific and stays out of the walker.
- FHIR keeps nesting in `generate_base`. After R1–R2 it should key the parent by **(process segment, group node)** rather than a process-blind stack; it may keep `_group_stack` as an implementation detail. No new walker argument is required for groups in this spec.

A `WalkContext` dataclass is **not** part of this change. Documented keyword names (R1) are the contract. A context object can be a later refactor once every callback already accepts the same names.

## 8. Pipeline

```text
load_calculate (unchanged, input-side)
        │
        ▼
BaseOutPutStrategy.execute
        ├── process_base        generate_base         (items / names / groups)
        ├── process_relevance   generate_relevance    (enableWhen / skip / program rules)
        ├── process_calculate   generate_calculate    (expressions / CQL / FHIRPath)
        ├── process_export      generate_export       (rows / StructureMap rules)
        ├── [FHIR] assemble CQL + extraction maps, sanitise, prune
        └── export / validate
                └── [OpenSRP] PD, Task maps, Composition, tags  (unchanged, post-walk)
```

## 9. Code checklist

| File | Change |
|------|--------|
| `tricc_oo/visitors/tricc.py` | [x] R2: pass `process=process` on every recursive `walktrhough_*` / `walkthrough_*` call listed in §7. Keep mutate/restore. Do not rename the walker. |
| `tricc_oo/strategies/output/base_output_strategy.py` | [x] R1: `generate_*` signatures include `processed_nodes=None, stashed_nodes=None, process=None, warn=False, **kwargs`. R3: every `tricc_operation_*` stub takes `original_references=None`. R4: `execute()` calls `process_relevance` between base and calculate. |
| `tricc_oo/strategies/output/fhir_form.py` | [x] Use the declared callback args (not only `kwargs.get`). Keep `get_process(node)` for segmentation. FHIR `execute()` kept (CQL assembly must run before `export()`). Dispatch already passes `original_references`. |
| `tricc_oo/strategies/output/opensrp.py` | [x] No walk changes. `export()` / PD / Composition still run after FHIR’s walks. |
| `tricc_oo/strategies/output/xls_form.py` | [x] `generate_relevance` is a no-op (`True`). Custom `activity_export` still forwards `process`. |
| `tricc_oo/strategies/output/xlsform_cht.py` | [x] `execute()` now calls `process_relevance` (inherited no-op). |
| `tricc_oo/strategies/output/html_form.py` | [x] R3 at dispatch (`handler(ref_expressions, original_references)`). Own `execute()` kept (`validate()` is not implemented). |
| `tricc_oo/strategies/output/dhis2_form.py`, `openmrs_form.py`, `spice.py` | [x] R3 at dispatch / handler signatures. |
| `docs/pipeline.md` | [x] Four output passes, callback contract, `process` forwarded, OpenSRP packaging post-walk. |
| `docs/open-srp-export.md` | [x] OpenSRP extra resources are not produced by the node walk. |
| `tests/test_output_walk_context.py` | [x] Recursive process forward, stash restore, operator dispatch, base `execute()` relevance pass. |

## 10. Tests

Existing OpenSRP / FHIR tests stay green (item order, inherited value, calculate readiness, duplicate calculates). Add focused tests; YAML fixtures preferred.

| Case | Assert |
|------|--------|
| Recursive walk keeps process | A node inside a nested activity whose root `process` is `triage` is still visited with `process[0] == "triage"` after the walker has entered via `main`. Probe via a tiny output-strategy double recording `(node.name, process[0])`, or assert the FHIR Questionnaire segment for that node is `triage`. |
| Process restored on stash | If `generate_*` returns `False` inside a process-switching activity, `process[0]` is restored to the caller’s value before the next stash pop. |
| Operator dispatch | A strategy whose `tricc_operation_and` is `lambda self, refs, original_references=None: ...` is callable from both HTML-style and FHIR-style `get_tricc_operation_expression`. |
| Base execute relevance | A strategy that implements `generate_relevance` as a counter is invoked during `execute()` without overriding `execute()`. XLSForm export of `tests/data/yaml` (or demo) still writes relevance on survey rows. |
| OpenSRP packaging unchanged | `OpenSRPStrategy` still emits Composition + Intervention PlanDefinition after questionnaires exist (`tests/test_strategies/test_opensrp_strategy.py` smoke). |
| Regression | `tests/test_strategies/test_fhir_inherited_value.py`, item-order test from `fix/20260823-questionnaire-item-order.md`, `tests/test_output_pass_readiness.py`. |

## 11. Acceptance criteria

1. Recursive walks never start with `process is None` when `stashed_node_func` was given a process list.
2. `BaseOutPutStrategy.execute()` calls `process_relevance`.
3. `tricc_operation_*` on the base class accept `original_references=None`; XLSForm and FHIR keep passing the original AST.
4. No OpenSRP-only arguments on the walker.
5. XLSForm / CHT tests pass without changing begin/end group behaviour.
6. OpenSRP export still writes PD + Composition after the FHIR walks.
7. Authors see no new draw.io attributes.

## 12. Implementation phases

1. **R2** — forward `process` (visitor only). Smallest, unblocks FHIR `kwargs.get("process")`.
2. **R1 + R3** — signatures on base + dispatch sites.
3. **R4** — base `execute()` + drop redundant copies where safe.
4. Docs + tests from §10.

Implemented 2026-08-24. XLSForm `generate_relevance` is a no-op because relevance is still written during export; calling the missing `generate_xls_form_relevance` would have crashed once the base pipeline started the relevance pass. `tests/test_test_spec_strategy.py` failures (`TriccNodeInput` NameError) are pre-existing on this branch and unrelated.
