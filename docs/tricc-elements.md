# TRICC Elements

This page documents TRICC modeling elements and their meaning based on:

- `tricc_oo/converters/drawio_type_map.py`
- `tricc_oo/tools/TRICCS-Scratchpad.xml`

## Core flow anchors

- `start`: main process entry node.
- `activity_start`: page/activity entry node.
- `activity_end`: closes an activity.
- `end`: closes a process path.

## Question/input elements

- `note`: informational text shown to users.
- `select_one`: single-choice question.
- `select_multiple`: multiple-choice question.
- `select_yesno`: yes/no convenience selection. In FHIR output this typically becomes a native `boolean` item type (preferred over `choice` for simple yes/no questions).
- `integer`, `decimal`, `text`, `date`: typed user inputs.
- `input`: generic input node used in conversion workflows.

## Option and list elements

- `select_option`: answer option under select questions.
- `not_available`: explicit "not available" option pattern.

## Logic and computation elements

- `calculate`: computed value.
- `add`: arithmetic compute helper.
- `count`: option/count compute helper.
- `rhombus`: decision/condition gate using `reference` and labeled out-edges.
- `factor`: sequence scoring node (non-display calculate). Created from numeric edge
  labels; stores the factor in `reference`, uses `path` for the branch condition.
  Expression semantics: **if path then factor else 0** (feeds `count` / `add` nodes).
- `wait`: synchronization gate based on references.
- `exclusive`: exclusivity helper.

## Navigation/linking elements

- `goto`: jump to another page/activity.
- `link_in`, `link_out`: explicit cross-flow links.
- `bridge`: bridge/helper connector.

## Diagnosis/classification elements

- `diagnosis`: diagnosis output node.
- `proposed_diagnosis`: proposed diagnosis output node.

## Enrichment elements (scratchpad patterns)

Scratchpad includes reusable patterns for:

- `container_hint_media` container blocks.
- `hint-message` and `help-message`.
- image-linked enrichment blocks.

These are attached through edges and enrich target question nodes during conversion.

## Common attributes

Examples used across element families:

- `name`, `label`, `list_name`
- `required`, `constraint`, `constraint_message`
- `relevance`, `priority`
- `save`, `expression`, `trigger`
- `reference`, `instance`, `process`, `form_id`
- `repeat` — concept capture slot (see [Concept repeat](#concept-repeat) below)

## Concept repeat

Authors can collect the **same concept more than once** in one encounter by setting an
integer `repeat` on a capture node or on `activity_start`.

| Scope | Attribute | Effect |
|-------|-----------|--------|
| Capture node | `repeat=<n>` | Versioning and skip logic use `(name, repeat)` instead of `name` alone |
| Activity start | `repeat=<n>` | Propagated to in-scope descendants (overrides node-level `repeat`; excludes `input` nodes) |

**Defaults and rules:**

- Omitted `repeat` behaves as **`repeat=1`** (backward compatible with existing diagrams).
- Same `name` + same `repeat` in a later activity is skipped if already captured (encounter-wide).
- **No cross-repeat inheritance** — a value at `repeat=1` is not merged into logic at `repeat=2`.
- Export suffix when `repeat != 1`: `_Rr_<n>` (alongside existing `_Vv_<n>` version and `_Ii_<n>` instance suffixes).
- `repeat=0` on `input` / pre-filled nodes forces in-form collection even when pre-encounter data exists.

**FHIR / OpenSRP:** non-default repeat slots emit Questionnaire item extensions and
repeat-aware Helper CQL (`GetRepeatedValue`, `GetNumberOfRepeat`, `GetLastValue`). See
[OpenSRP / FHIR-Core Export](./open-srp-export.md#concept-repeat-fhir--cql).

Full specification: `feature/concept-repeat.md` (status: Implemented).

## Edge labels (conditional flow)

During draw.io conversion (`process_edges` in `xml_to_tricc.py`), arrow labels are
interpreted as branch semantics. Labels are case-insensitive unless noted.

| Label pattern | Meaning | Typical source node |
|---------------|---------|---------------------|
| `yes`, `oui` | Affirmative branch | `select_yesno`, `rhombus` |
| `no`, `non` | Negative / exclusive branch | `select_yesno`, `rhombus`, calculates |
| `follow`, `suivre`, `continue` | Continue without branching | `select_yesno`, `rhombus` |
| *(empty)* | Treated as **yes** on `rhombus` out-edges | `rhombus` |
| Integer factor (`-1`, `+2`, `3`, …) | **Yes** branch with optional score factor | `rhombus`, selects, calculates |
| Reserved expression tokens | Condition edge → may insert a nested `rhombus` | Any calculate-capable node |

**Integer factors on rhombus:** a numeric out-edge label (for example `-1` on a
condition gate feeding a `count` node) is treated as an affirmative (**yes**) path.
When the factor is not `1`, TRICC inserts a **`factor`** node (`TriccNodeFactor`) with
`path` set to the source and `reference` set to the numeric value. This is a
non-display sequence calculate (like `rhombus` / `wait`), not a regular `calculate`
with both `reference` and `prev_nodes`. Expression: **if path then factor else 0**.
This supports clinical scoring patterns (e.g. subtract points when a risk factor is present).

## Sequence-node semantics (from visual authoring guidance)

- **Rhombus**: conditional split using `reference` (condition) and labeled out-edges.
  Use `Yes` / `No` / `Continue` / `Follow`, or integer factors as above.
- **GoTo**: placeholder link to another activity/tab, replaced during graph construction.
- **Start nodes**: `start` begins process; `activity_start` begins activity.
  `activity_start` may also carry `process` (cpg-common-process name for FHIR export)
  and `repeat` (activity-wide concept capture slot).
- **Wait**: ensures downstream progression only after referenced nodes are reached.
- **Bridge**: merge helper for readability when many paths converge.
- **Ends**:
  - `activity_end`: marks activity completion.
  - `end`: terminates encounter/process path.

## Experimental page behavior

If the activity root has `status="experimental"`, TRICC limits page processing intentionally.
This behavior is implemented in `create_activity` inside `tricc_oo/converters/xml_to_tricc.py`.

Use this to keep draft content present in source diagrams without full production processing.
