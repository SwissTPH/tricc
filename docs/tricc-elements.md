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

- `note`: informational text shown to users. Display fields (`label`, `hint`,
  `help`, `constraint_message`, `required_message`) on **display models only**
  may embed ODK/JS-style value injection with `${field_name}` (e.g.
  `Patient is ${age} years`). Parsed at input load into concatenate operations,
  resolved during processing, re-exported as `${export_name}` for ODK/CHT and as
  concatenate expressions for FHIR. Not applied to calculates or rhombus.
  See `feature/display-text-injection.md`.
- `select_one`: single-choice question.
- `select_multiple`: multiple-choice question.
- `select_yesno`: yes/no convenience selection. In FHIR output this typically becomes a native `boolean` item type (preferred over `choice` for simple yes/no questions). OpenSRP export also attaches `questionnaire-choiceOrientation` = `horizontal` on visible boolean/yes-no items so Yes/No render side by side; hidden booleans (calculates, diagnoses, waits) do not.
- `integer`, `decimal`, `text`, `date`: typed user inputs.
- `input`: **legacy alias of `populate`** (kept so existing diagrams keep parsing). It builds the
  same node, with `context` defaulting to `encounter` — the data it always fetched. Not a
  question: always hidden, only ever fetches context or historical data. See
  `fix/20260821-merge-input-into-populate.md`.
- `populate`: pre-loaded data node (non-display calculate). Attributes: `context`
  (`patient`, `facility`, `practitioner`, `location`, `encounter`, `history`),
  optional `period` (ISO Duration/Period; default `P1Y` for `history` only),
  optional `repeat` (read slot). Excluded from activity `repeat` propagation.
  See `feature/populate-context.md`.

## Option and list elements

- `select_option`: answer option under select questions.
- `not_available`: explicit "not available" option pattern.

## Logic and computation elements

- `calculate`: computed value.
- `add`: arithmetic compute helper.
- `count`: option/count compute helper.
- Anthropometric operators (CDSS / XLSForm): `Zscore(table, sex, x, y)` and
  `Izscore(table, sex, x, z)` resolve LMS params from choice secondary instances
  filtered by `sex` + `y_min`/`y_max`. Phase 1 table: `wfa` (weight-for-age).
  Only tables referenced by the form are injected into the choices sheet.
  See `feature/cdss-zscore.md`.
- `rhombus`: decision/condition gate using `reference` and labeled out-edges.
- `factor`: sequence scoring node (non-display calculate). Created from numeric edge
  labels; stores the factor in `reference`, uses `path` for the branch condition.
  Expression semantics: **if path then factor else 0** (feeds `count` / `add` nodes).
- `wait`: synchronization gate based on references. Injected automatically before/after a
  `goto` that has outgoing edges (`inject_bridge_path` / `get_activity_wait` in
  `xml_to_tricc.py::get_nodes`) so the node placed after the call derives its relevance from
  the caller's own entry bridge (`Wait.path`), never from the called activity's own
  completion. This is what keeps two different callers of the same (or same-instance) nested
  activity from leaking relevance into each other's continuation — see the `goto` `instance`
  note above and [Troubleshooting — Node after a repeated activity call](./troubleshooting.md#node-after-a-repeated-activity-call-never-appears).
- `exclusive`: exclusivity helper.

## Navigation/linking elements

- `goto`: jump to another page/activity.
  - `instance` (default `1`): nested activity instance number; `0` auto-unique nested instance;
    **`-1` injects the target activity as a snippet** into the caller (inline nodes; no nested
    activity / wait). See `feature/goto-snippet-injection.md`.
  - When two different `goto`s target the **same** `instance` number of the same activity
    (e.g. two callers both call `link: shared_module, instance: 1`), they resolve to the
    **identical shared `TriccNodeActivity` object** — see `TriccNodeActivity.make_instance`'s
    `self.instances` cache. Any node the caller places right after that `goto` must keep its
    relevance tied to *that specific caller*, not to "the shared activity was entered by
    anyone" — see the `wait` entry below.
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

**FHIR / OpenSRP:** `help-message` becomes a nested `display` item with
`questionnaire-itemControl` = `help`; `hint-message` becomes an `entryFormat`
extension on the question (`http://hl7.org/fhir/StructureDefinition/entryFormat`).
Hidden items emit neither. See
[OpenSRP / FHIR-Core Export](./open-srp-export.md#help-and-hint-messages).

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
| Activity start | `repeat=<n>` | Propagated to in-scope descendants (overrides node-level `repeat`; excludes `populate` nodes, including the `input` alias) |

**Defaults and rules:**

- Omitted `repeat` behaves as **`repeat=1`** (backward compatible with existing diagrams).
- Same `name` + same `repeat` in a later activity is skipped if already captured (encounter-wide).
- **No cross-repeat inheritance** — a value at `repeat=1` is not merged into logic at `repeat=2`.
- Export suffix **`_Rr_<n>` only when `repeat > 1`** (alongside `_Vv_<n>` version and `_Ii_<n>` instance suffixes). Values `0` and `-1` do not get `_Rr_`.
- `repeat=0` on `populate` / pre-filled nodes forces in-form collection even when pre-encounter data exists.
- **`repeat=-1` (local-only):** node stays referenceable by name, but does **not** inherit prior values, does **not** feed other nodes’ multi-version coalesce, and is **not** skip-suppressed against other `repeat=-1` occurrences of the same concept (each capture is fully independent — e.g. two different callers each injecting the same snippet activity both get their own, unsuppressed capture). Shares the export base with default `repeat=1`; uniqueness uses `_Vv_n` peer renumbering.

**Same-name value merge:** when several versions of a concept exist in one slot, calculates and expression refs may merge **all** prior versions (`GET_INHERITED_VALUE` → ODK `coalesce`). See `feature/advanced-merge-calc.md`.

**Reading a specific slot — `GetRepeatedValue`:** in any calculate or relevance expression,

```text
GetRepeatedValue("<concept name>", <slot>)
```

reads the capture of `<concept name>` made at `repeat=<slot>`. It behaves exactly like a plain
concept reference — including merging several versions of that concept via `coalesce` — but
**restricted to the requested slot**, so it never falls back to another slot:

```text
integer  name=weight  repeat=1     "Weight at triage"
integer  name=weight  repeat=2     "Weight after treatment"

calculate  name=weight_delta
  GetRepeatedValue("weight", 2) - GetRepeatedValue("weight", 1)
```

exports to ODK as `coalesce(${weight_Rr_2},'') - coalesce(${weight},'')`.

- The slot must be a **literal integer** — it is resolved while the graph is built, before any
  answer exists. Omitting it means slot `1` (with a warning).
- The slot must be **captured earlier in the flow**. If no capture matches
  `(name, slot)`, the reference is reported unresolved — there is no silent fallback.
- `GetRepeatedValue("x", -1)` addresses a local-only node and never merges encounter slots.
- Supported on XLSForm/ODK, CHT, and FHIR/OpenSRP.

Full specification: `feature/20260821-get-repeated-value-operation.md`.

**Not yet usable in expressions:** `GetRepeated` (returns a resource, not a value),
`GetNumberOfRepeat`, and the history accessors `GetHistoryValue` /
`GetHistoryObservationValue` / `GetHistoryConditionValue`. These exist as **generated Helper CQL**
only — reach the same data from an expression by declaring a `populate` node (`context=history`)
and referencing it by name. The history accessors are *not* inherently FHIR-only: CHT already
serves `context=history` populate nodes from the contact summary
(`instance('contact-summary')/context/<concept>`), so making them callable from expressions is a
matter of desugaring them into generated populate nodes — see
`feature/20260821-get-repeated-value-operation.md` §14.1.

**FHIR / OpenSRP:** non-default repeat slots emit Questionnaire item extensions and
repeat-aware Helper CQL (`GetRepeatedValue`, `GetNumberOfRepeat`, `GetHistoryValue`). See
[OpenSRP / FHIR-Core Export](./open-srp-export.md#concept-repeat-fhir--cql).

Full concept-repeat specification: `feature/concept-repeat.md` (status: Implemented).

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
