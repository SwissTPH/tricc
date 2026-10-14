# YAML activities lose their branching: edge labels are not interpreted

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `converters/xml_to_tricc.py` `process_edges`, `process_yesno_edge`, `process_exclusive_edge`, `process_factor_edge`, `process_condition_edge`, `get_nodes` (rhombus path); `strategies/input/yaml.py` `_build_activity`, `_create_node`; `visitors/tricc.py` `get_select_yes_no_options`; `feature/20261008-start-node-is-the-activity.md` (nameless start / end) |
| **Frontend** | Reported by the `tricc_frontend` session, 2026-10-12. The frontend writer emits `value: "yes"` / `"no"` on rhombus and select_yesno out-edges, `value: "Answer('<option name>')"` on select_one / select_multiple out-edges, and no `options:` for select_yesno. |
| **Strategy** | `YamlStrategy` (input). All outputs are affected through relevance. The XLSForm/CHT select_yesno row is also affected. |
| **Approval** | Approved 2026-10-12 (Patrick: "go"; also re-baseline the other YAML cases — before the frontend, YAML was only used for tests) |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability).

---

# Part I — Issue analysis

## 1. Symptom

An activity drawn in draw.io and the same activity written as YAML (by the authoring app or by
hand) should give the same form. They do not: in YAML, nearly every branch is lost.

Example (triage): *Fever?* (yes/no) → yes: *Temperature*, no: *Age* → *Cough?* (yes/no list) →
only when cough = **no**: *Weight* → decision *weight > 10* → yes: *Height*, no: *MUAC*.

| Question | Expected display condition | Actual (YAML) |
|---|---|---|
| Fever | shown | **missing from the form** (warning "unsupported type select_one yesno") |
| Temperature | fever = yes | always shown |
| Age | fever = no | always shown |
| Cough | shown | shown |
| Weight | cough = no | always shown |
| Height | weight > 10 | weight > 10 |
| MUAC | **not** (weight > 10) | weight > 10 (same as the yes branch) |

## 2. Who is affected

Every project built from YAML: everything the authoring app (`tricc_frontend`) writes, and the YAML
test fixtures. Draw.io projects are not affected.

## 3. Why

When it reads a drawing, TRICC reads the label on each arrow: "yes" / "no" after a decision or a
yes/no question, a number (a factor), a condition, "follow". It turns each label into the
matching logic. The YAML reader copies the arrows but **never reads their labels**. This step
was never written for YAML.

Two smaller problems add to this:

- A yes/no question in YAML gets an internal type that the XLSForm/CHT export does not recognise,
  so the question is dropped. When the YAML lists no options, the yes/no answers are also not
  created.
- An arrow leaving one answer of a list question is written by the authoring app as
  `Answer('no')` on the arrow from the question. Draw.io instead draws the arrow from the answer
  shape. TRICC does not read the YAML form.

## 4. Expected behaviour after the fix

A YAML activity branches exactly as the same drawing does:

- **Decision (rhombus):** "yes" or no label = condition true; "no" = condition false; a number = a
  factor; "follow" = continue regardless of the decision.
- **Yes/no question:** "yes" / "no" arrows leave the matching answer. The yes/no answers are
  created when the YAML lists none. The question appears in the form.
- **List question:** an arrow labelled `Answer('<option name>')` leaves that option.
- **Other labels** on a question's arrow ("no" after a calculate, a factor, a condition with an
  operator) mean the same as in draw.io.

## 5. Out of scope

- XLSForm/CHT needing a process named `main` (the frontend only offers CPG process names).
- A `diagnosis` node directly in a main process looping on `final.<name>`.
- New label syntax. YAML gets the draw.io labels plus `Answer('…')`, nothing more.

## 6. Side effect on existing results

Some YAML test fixtures already have "no" edges after a rhombus (`minimal_decision`,
`inheritance_relevance_merge`, `goto_instance_multi_caller`, and others). Their recorded outputs
encode the bug (both branches the same) and will change. Draw.io results must not change.

---

# Part II — Fix approach

## 1. Root cause

`xml_to_tricc.process_edges` mixes two jobs:

1. draw.io-only work: enriching nodes from edges whose source is not a node (hint, help, media
   via `enrich_node`), and detecting the end (`end_found`, fake `activity_end`);
2. label semantics, which apply to any input: retargeting edges into a rhombus to its `path`,
   `process_yesno_edge`, and per-label handling (follow / no → `process_exclusive_edge` / yes /
   factor → `process_factor_edge` / operator → `process_condition_edge`), with the injected
   calculate inserted between source and target.

Before that, `get_nodes` gives every rhombus a `path` (`inject_bridge_path`, else the root).

`YamlStrategy._build_activity` (step 3) builds `TriccEdge(source, target, value)` and wires
prev/next straight away. It never gives a rhombus a path and never interprets a label. The
rhombus path is filled in later (`visitors/tricc.py`, `node.path = prev_nodes[0]`), so "yes"
works by accident. "no" gets no `TriccNodeExclusive` and therefore the same relevance as "yes".

For select_yesno, the YAML `NODE_TYPE_MAP` sets `tricc_type: TriccNodeType.select_yesno`
(`"select_one yesno"`), which is not in `ODK_TRICC_TYPE_MAP`. The draw.io node keeps the model
default `select_one`, with `list_name = "yes_no"` and options from `get_select_yes_no_options`.
YAML options also never go into the activity's `nodes` dict, so no edge can come from one.

## 2. Fix

### 2.1 One shared label step (`xml_to_tricc.py`)

Extract the label part of `process_edges` into a public function used by both inputs:

```python
def process_edge_labels(activity, nodes, where: str) -> None:
    """Interpret edge labels in place (rhombus path retarget, yes/no, no→exclusive,
    factor, condition, follow, Answer('…')). Injected calculates go into ``nodes``."""
```

- Body: the loop of `process_edges` from the rhombus retarget to the end of the label handling,
  unchanged in behaviour. `where` replaces the `diagram.attrib.get('name', …)` text in the logs.
  The `exit(1)` on an unknown rhombus label stays (same rule for both inputs).
- `process_edges` keeps enrichment and end detection, and calls `process_edge_labels` per edge
  (or once after its own loop, if the order allows; the implementation checks that the draw.io
  regression baselines stay byte-identical).
- Extract the rhombus path step of `get_nodes` as `assign_rhombus_paths(activity, nodes)` and
  call it from both inputs.

### 2.2 `Answer('<name>')` source routing (shared)

In `process_edge_labels`, before the label dispatch: when the source is a `TriccNodeSelect`
(not yes/no) and the value matches `^\s*Answer\(\s*'((?:[^']|'')*)'\s*\)\s*$`, unescape `''` → `'`,
find the option whose `name` equals it, and set `edge.source = option.id`
(`source_external_id = None`). The edge is then a plain option edge, exactly as draw.io makes it.
If no option matches: `logger.warning` and leave the edge (unconditional, as today). Draw.io
drawings never contain this label, so they are not affected.

### 2.3 select_yesno matching by name

`process_yesno_edge` picks the yes option by `option.label.lower() == "yes"`. Concept texts make
the label translatable ("Oui"), so match on `name` first (`TRICC_TRUE_VALUE` / "yes" → yes,
`TRICC_FALSE_VALUE` / "no" → no), falling back to the label. When the yes or no option is still
missing, log a warning and leave the edge (no `AttributeError` on `None.id`).

### 2.4 YamlStrategy (`strategies/input/yaml.py`)

- `NODE_TYPE_MAP["select_yesno"]`: drop the explicit `tricc_type` so the model default
  (`select_one`) applies, as in draw.io (`not_available` already does this).
- `_create_node` for select_yesno: `list_name = "yes_no"`. If the YAML lists no options, use
  `get_select_yes_no_options(node, group)`. If it lists options, keep them (existing fixtures).
- `_build_activity`: register every option in `nodes` (`nodes[opt.id] = opt`) so option edges
  resolve. Then, after creating the edges and before `_wire_prev_next`, call
  `assign_rhombus_paths(activity, nodes)` and `process_edge_labels(activity, nodes, yaml_act.id)`.
  Then `activity.nodes = nodes` (it now includes the injected exclusives / factors / rhombuses).
  `_wire_prev_next` then wires the rewritten edges, including option → target.
- Check that options in `activity.nodes` do not lead `_collect_dangling_calculates` or the
  later visitors into double processing. draw.io already has them in `nodes`, so that is the
  shape the visitors expect.

### 2.5 Nameless `end` (optional, cosmetic)

A YAML `end` without `name` exports as `tricc_end_` (two become `tricc_end_`, `tricc_end__Vv_1`).
Give it `_get_name("end_", id, activity.id)`, the same rule as the activity start
(`feature/20261008-start-node-is-the-activity.md`).

## 3. Tests

- New fixture `tests/data/yaml/edge_labels.yaml`: the triage flow from Part I §1 (inline labels,
  no terminology, select_yesno without options, `Answer('no')`, rhombus yes/no). It becomes 4
  regression cases automatically (`tests/regression/cases.py`).
- New `tests/test_yaml_edge_labels.py` (XLSFormStrategy and XLSFormCHTStrategy) asserting
  survey relevance: `fever` row present with type `select_one yes_no`; `temperature` relevance
  tests `${fever}` = yes, `age` = no; `weight` tests `cough` = `no`; `height` contains `>10`;
  `muac` contains the negation (`not(` … `>10`). Also an `Answer('it''s')` quoting case and an
  unknown option name (warning, no crash).
- Unit tests of `process_yesno_edge` name matching (label "Oui", name "yes").
- The frontend's projects (`names/{edges,two,proj,named}`) can run as regression cases through
  `TRICC_REGRESSION_DIRS`; they are not committed (scratch data of another session).
- Regression: re-baseline the YAML cases whose output changes, and check each diff is a branch
  becoming correct. All `drawio__*` baselines must stay unchanged.

## 4. Acceptance criteria

1. The Part I §1 example gives the expected column for every row, in XLSForm and CHT.
2. No "unsupported type select_one yesno" warning for YAML select_yesno.
3. A YAML rhombus "no" branch gets the negated condition.
4. `drawio__*` regression baselines unchanged. Full `python -m pytest tests/` green.
5. One label routine (`process_edge_labels`) used by both inputs, not a copy.

## 5. Implementation notes (2026-10-12)

- `process_edge_label`, `route_answer_edge`, `assign_rhombus_path`, `get_yes_no_options` in
  `converters/xml_to_tricc.py`; draw.io `process_edges` / `get_nodes` call them, and the
  `drawio__*` baselines are byte-identical.
- The rule that every `select_yesno` out-edge needs a label now applies to YAML. Ten
  unlabelled yes/no edges in six test fixtures (used only as "continue", the gating being in
  `relevance`) were labelled `follow`.
- A nameless `end` is named `end_<activity id><id>` (`_get_name`), which renames the
  `tricc_end_` row in most YAML baselines.
- `TestSpecStrategy.edges` walks through nodes the form model does not hold (the injected
  path bridge), so every edge ends on a known node.
- YAML baselines re-recorded. The non-rename changes are all corrections: yes/no questions
  now present in XLSForm (and given the radio-button item control in FHIR, as from draw.io),
  "no" branches negated. The 14 YAML cases that already failed to build still fail the same
  way (`cur_path` UnboundLocalError, CHT recursion, fever_encounter_populate loop); not in
  scope here.

## 6. Revision 2026-10-13 — `Answer('<code>')` is a condition, not an option edge

Patrick, 2026-10-13: an `Answer('<code>')` edge is no longer re-attached to the option.
`answer_edge_condition` (replacing `route_answer_edge`) rewrites it into a CQL condition, which
the condition-edge path turns into a rhombus between the select and the target:

| Source | `Answer(…)` | Condition |
|---|---|---|
| select_one, select_multiple | `Answer('<code>')` | `'<code>' in $this` → `selected(${q}, '<code>')` |
| select_yesno | `Answer('yes')` (or the yes option's name) | `$this is true` |
| select_yesno | `Answer('no')` (or the no option's name) | `$this is false` |

An unknown code warns but keeps the condition. A code containing a quote warns and the edge
stays unconditional. Plain `yes` / `no` labels on a select_yesno still leave the option (draw.io).
The fixture now uses `Answer('yes')` / `Answer('no')` on its yes/no question and adds a
select_multiple `Answer('rash')` branch.

Known effect, not fixed here: when two condition edges leave the same question, the output walk
emits the second branch first (`reorder_node_list` gives every rhombus `RHOMBUS_PRIORITY_TO_UP`,
so the second rhombus overtakes the first branch's question). draw.io condition edges go through
the same walk. Seen in the fixture: `age` (fever = no) comes before `temperature` (fever = yes).

### 6.1 Revision 2026-10-14: `Answer("<code>")`, the answer concept

Patrick, 2026-10-14: options are concepts, so the answer is written as a CQL identifier,
`Answer("<code>")`, not a string. A string would have to be looked up in the data dictionary
to tell it from a real string value. `<code>` is matched against the option's concept code,
then its name; the condition uses the option name (`'<option name>' in $this`). The string form
`Answer('<code>')` is still read for files written before. The fixture uses the identifier form.

Kept from the first reading of this request (quotes inside codes): CQL string literals are now
unescaped by the parser (`\'`, `\\`, `\uXXXX`); XLSForm prints a string holding `'` with
double quotes (or `concat(...)`); FHIRPath escapes `'` and `\`. Also fixed: the per-option
calculate of a select_multiple was `contains(${q}, code)` with the code unquoted (always true in
XPath); it is now `selected(${q}, 'code')`. This changed the XLSForm/CHT baselines of combacal,
demo, etat and the three populate fixtures.

### 6.2 Revision 2026-10-14: the answer side of `in` / `contains` is a code

`Answer("<code>")` now writes `"<option name>" in $this` (identifier form). On its own this
broke select_multiple: the flat reference pass resolved `"rash"` to the option's per-option
calculate (also named `rash`), giving `selected(${signs}, ${rash})` and, in FHIR, a
`linkId='rash'` answer. The CQL parser (`cql_to_operation._get_membership_expression`) now
turns an identifier on the answer side of `in` (left) and `contains` (right) into a literal
code (`as_code_literal`), so every output prints `'rash'`. No fixture or drawing used an
identifier there; all baselines unchanged.
