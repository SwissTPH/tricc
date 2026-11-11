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
  `Patient is ${age} years`). Parsed at input load into a message tree (`TriccMessage`)
  that keeps bold/italic/lists around live values, resolved during processing,
  re-exported as Markdown with `${export_name}` for ODK/CHT and as static Markdown plus
  a serialize-time concatenate FHIRPath for FHIR. Not applied to calculates or rhombus.
  See `feature/display-text-injection.md` and `feature/20260909-display-message-ast.md`.
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
  - **Carrying a value across forms / visits** (FHIR / openSRP): use `context=history`. It
    reads the most recent stored value within `period` (e.g. `P3M` = last 3 months), from
    any earlier form or visit; `encounter` only sees the current visit.
  - optional `source`: the concept to read, when it differs from the node's `name` — e.g. a
    "previous weight" node `t_weight` with `source="weight_c"` reads what the Weight question
    `weight_c` recorded, while flows keep referring to `t_weight`. Do not rename the node to
    the question's name instead: two nodes with one name are merged as versions of one
    concept. (FHIR / openSRP export only.)
  - to carry a **computed status** (`X` calculated from today's answers and `t_X`), mark the
    calculate `X` with `concept_type="observation"` so it is saved, and give `t_X`
    `context=history source="X"`.
  - `context=patient` reads the Patient record (FHIR / openSRP): `sex` / `gender` →
    `Patient.gender` as the FHIR code (`female`, `male`, `other`, `unknown` — compare with these,
    not `'1'`), `age` → whole years from `Patient.birthDate`, `birthdate` / `dob` → the birth
    date. Other names stay empty (warning at export).
  - a `context=history` node whose `source` is a **select_multiple** gets every option code of
    the latest answer, space-separated (`metformin glibenclamide`); individual options can
    also be carried on their own (`t_heart_failure` with `source="heart_failure"`).
  - populate values are never written back on submit; the export warns when a populate node
    reads a concept no form of the project records.
  See `feature/20260929-cql-populate-wiring.md`.

## Option and list elements

- `select_option`: answer option under select questions.
- `not_available`: opt-out next to a measurement (for example weight). Draw it like
  `select_one`: header text is the question title, stacked `select_option` rows are
  the reasons (`name` on each row is the stored code). No extra option is invented.
  ODK/CHT only; parent-empty coupling is unchanged.
  See `feature/20260902-not-available-title-options.md`.

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
    activity / wait). See `feature/goto-snippet-injection.md`. A [block](#blocks-and-parameters)
    is the declared form of this reuse.
  - When two different `goto`s target the **same** `instance` number of the same activity
    (e.g. two callers both call `link: shared_module, instance: 1`), they resolve to the
    **identical shared `TriccNodeActivity` object** — see `TriccNodeActivity.make_instance`'s
    `self.instances` cache. Any node the caller places right after that `goto` must keep its
    relevance tied to *that specific caller*, not to "the shared activity was entered by
    anyone" — see the `wait` entry below.
- `link_in`, `link_out`: explicit cross-flow links.
- `bridge`: bridge/helper connector.
- `block`: use a [block](#blocks-and-parameters), with `link` and `args`.
- `goto` may also carry `args` for a parameterized activity (see below).

## Blocks and parameters

A **block** is a reusable piece of flow, written once and used in many places with
different settings. Spec: `feature/20261111-block-params-and-start-node.md`.

- A block file (`blocks/<id>.block.yaml`, listed in tricc.yaml `blocks: [{id, path}]`)
  has the shape of an activity. Its root is **`block_start`** and it ends at an
  `activity_end`. A block is a template: never a start page, never exported on its own.
- A **`block`** node uses it: `link` is the block's `block_start` name or its id, and
  `args` gives the parameter values. Each use inlines one copy of the block.
- `snippet_start` / `snippet` (the first names) are still read as `block_start` / `block`.

### Parameters

Any block, activity or process can have parameters, in a page-level `params` list:

```yaml
params:
  - {name: site, type: choice, options: [axillary, rectal], required: true}
  - {name: threshold, type: number, default: 37.5}
```

| `type` | Value | Becomes a dictionary concept |
|--------|-------|:---:|
| `boolean` | `true` / `false` | yes |
| `number` | a number | yes |
| `string` | text | yes |
| `choice` | one of `options` | yes |
| `name` | a name fragment (`[a-z0-9_]+`) | no |
| `concept` | `{system, code}` or a code | no |
| `expression` | a CQL expression | no |

Values work like **function arguments**. For each parameter of a called page, the value is
the first of: the call's `args` entry, the **caller's value of the same name** (inherited),
the parameter's `default`. `args: {setting: "{{care_setting}}"}` passes a caller parameter
under another name. At the top, the intervention's `args` (tricc.yaml) give the values.
A parameter that a page's calls leave unbound is a parameter of that page too (computed),
so it can come from further up. Errors stop the build and name the call chain: a required
value missing, an argument the callee does not have, a value of the wrong type, the same name
with two different types along a chain.

Each primitive parameter is a concept `param_<owner>_<name>` of the calculate dictionary
(`<owner>`: the declaring page's name, else its id). The project dictionary wins: tricc_oo
only adds the concepts it lacks (kind `parameter`, `dataType`, `option`, `default`).
The calculate dictionary is the CodeSystem tagged `meta.tag`
`http://tricc.org/fhir/CodeSystem/codesystem-role|calculate`; else tricc.yaml
`calculate_code_system`; else one named `calculate` or `<default>-calculate`.

**draw.io.** A page declares its parameters on one `parameters` shape, one attribute
`param.<name>` per parameter: JSON (`{"type": "string", "label": {"en": "Note"}}`) or the
shorthand `type[(a|b)][!][=default]`, `!` meaning required (`choice(axillary|rectal)!`,
`number=37.5`, `boolean=false`). A `block` (or `goto`) shape gives its values as
`param.<name>` attributes too (`param.site = axillary`, `param.setting = {{care_setting}}`).
(Not `param:<name>`: in XML a `:` starts a namespace prefix.)

### Placeholders

`{{name}}` puts a value in a node field. In expression fields (`relevance`, `calculate`,
`expression`, `reference`, `constraint`, `min`, `max`, edge values) it becomes a literal:
`'axillary'`, `37.5`, `true`, `"concept_code"`, `(expression)`. In text fields (`name`,
`label`, `hint`, `help`, `save`, `constraint_message`) it is the plain text.
`{{name|raw}}` puts plain text in an expression, for example to build a name:
`"temp_{{site|raw}}" > {{threshold}}`. Placeholders are not allowed in `id`, `type`,
`process`, `instance` or `link`.

### A block used several times

Each use inlines a new copy of the block, so its nodes exist once per use. Their **names**
say whether the uses are the same concept or not ([Instance vs repeat](#instance-vs-repeat)):

1. **Different things** (two measurements that must both be kept): the names must differ,
   so put a parameter in them. One that already tells the uses apart can do it
   (`temp_{{site}}` gives `temp_axillary` and `temp_rectal`). When none does, add one only
   for the name, of type `name`:

   ```yaml
   params:
     - {name: prefix, type: name, required: true}
   nodes:
     - {id: t, type: decimal, name: "{{prefix}}_temp"}
   ```

   used with `args: {prefix: admission}` and `args: {prefix: discharge}`.
2. **The same concept, collected once** (the block is reached from several places, the value
   is the same): keep the same names. This is an instance: same name, same `repeat`. At node
   level, TRICC keeps each copy as a version of the one concept (`_Vv_<n>`); a later copy is
   not asked again once the concept is captured, and readers see the merged value. (A `goto`
   to an activity handles the same case by reuse instead: one activity instance, wrapped
   between a bridge and a wait for each call site.)
3. **The same concept, collected again** (the same measurement repeated later in the visit):
   keep the same names and give each use its own `repeat` slot on the `block` node
   (`repeat: 1`, `repeat: 2`). The fields become `temp_axillary` and `temp_axillary_Rr_2`,
   following [Concept repeat](#concept-repeat). Its skip rule currently keys on the slot
   drawn on the node, not on a `repeat` set on the call, so today the second slot is only
   asked when the first is empty.

Names without a placeholder keep the earlier behaviour (each copy gets its own
instance-band suffix).

### Values calculated at the call

An argument can be an expression, evaluated where the block is used, with the names
available there:

```yaml
args:
  site: axillary                                  # a fixed value
  age: {expression: AgeInDays(), intent: {en: Age of the child in days}}
```

draw.io: `param.age = {"expression":"AgeInDays()"}`. The calling page gets a hidden calculate
(`arg_age_<digest>`, labelled by the `intent`) evaluated once at the use. Inside the block,
`{{age}}` reads it: a reference in an expression, `${…}` in a text. Passed on to an inner block
as `{{age}}`, the same calculate is used. It is never inherited by name.

Only a fixed value fits a parameter that shapes the drawing: one used in a node or option
`name`, a `save`, a `{{p|raw}}`, a static decision, a literal argument of an inner call, or of
type `name` or `concept`, here or in a block below. An expression there is
`E_ARG_DYNAMIC_STATIC`. An intervention's `args` are always fixed values.

A block reads no stored data: an expression calling a function of
`tricc_oo/converters/cql/stored_data_functions.json` (`AgeInDays()`, the encounter, history
and practitioner / location / facility readers), or a `populate` node, inside a block is
`E_BLOCK_SCOPE`. Pass the value in as an expression argument. `Today()` and `Now()` are allowed.

### Outputs

Every input and calculate of a block is an output: visible after the use, by its rendered
name. A block can narrow that with `outputs` (template names) beside `params`:

```yaml
outputs: ["fever_{{site}}"]     # only these; outputs: [] for none
```

draw.io: an `outputs` attribute on the `block_start` (`fever_{{site}},temp_{{site}}`, or a JSON
list, `[]` for none). A field not listed is **private**: each use gets its own copy, named with
a per-use suffix (`temp_axillary_3fa2c1`), without a dictionary concept. A reference to it from
outside the block is `E_BLOCK_PRIVATE`. A listed name the block does not have is
`E_OUTPUT_UNKNOWN`.

### Abstract concepts

A node named with a placeholder (`temp_{{site}}`) can have an **abstract concept**: code the
template name verbatim, properties `kind = template`, `notSelectable = true` and `owner` = the
block. Its texts may use placeholders too (`Temperature ({{site}})`). Each use gets a concrete
concept (`temp_axillary`) in the same CodeSystem, with the texts rendered for that use: a
`choice` value shows its option concept's label in each language, else the code. A concrete
concept already in the project dictionary wins. Abstract concepts are never written to the
terminology outputs (CodeSystem JSON, OCL), and selecting one outside its block is
`E_ABSTRACT_SELECTED`.

## Diagnosis/classification elements

- `diagnosis`: diagnosis output node.
- `proposed_diagnosis`: proposed diagnosis output node.

## Enrichment elements (scratchpad patterns)

Scratchpad includes reusable patterns for:

- `container_hint_media` container blocks.
- `hint-message` and `help-message`.
- image-linked enrichment blocks.

A picture attached to a question or option is stored under `media-tmp/images/`.
Project-level `parameters.image_max_width` / `image_max_height` in `tricc.yaml`
shrink oversized bitmaps (aspect ratio kept, never upscaled). On the image shape
itself, `max_width` / `max_height` override that cap for one side (`0` = no cap).
See `feature/20260907-project-config.md`.

These are attached through edges and enrich target question nodes during conversion.

**FHIR / OpenSRP:** `help-message` becomes a nested `display` item with
`questionnaire-itemControl` = `help`; `hint-message` becomes a nested `display`
item with `flyover`. Hidden items emit neither. See
[OpenSRP / FHIR-Core Export](./open-srp-export.md#help-and-hint-messages).

## Common attributes

Examples used across element families:

- `name`, `label`, `list_name`
- `required` — boolean (`1` / `yes` / `true`, or `0` / `no` / `false`) or a boolean expression
- `constraint`, `constraint_message`
- `relevance`, `priority`
- `save`, `expression`, `trigger`
- `reference`, `instance`, `process`
- `form_id` — deprecated: names the form only for a project without `tricc.yaml`
  `interventions` (otherwise ignored with a warning; use `interventions[].name`)
- `repeat` — concept capture slot (see [Concept repeat](#concept-repeat) below)

## Instance vs repeat

`instance` and `repeat` answer two different questions and are **not exclusive** — a
node can carry both.

| | `instance` | `repeat` |
|---|---|---|
| Question | *where* does this collection happen? | *how many times* is it collected? |
| Intent | the **same** collection, which may land at different points of an intervention but must not happen twice | a deliberate **re-ask**, so the answer may differ |
| Value inheritance | **yes** — once collected, later instances reuse the value | **no** — each repeat collects afresh |
| Typical use | "get the fever measurement; depending on the complaint or sign it may happen sooner or later in the intervention" | "check whether the fever status is still the same as at the previous repeat" |

A repeat deliberately does **not** test whether the previous repeat was actually
shown, because there are paths where it does not apply.

`repeat=-1` says only *"do not inherit the previous value"* — the slot number itself
carries no meaning and is never referenced. `tricc_oo` keeps such captures independent
through `_Vv_n` peer renumbering; `tricc_og` instead allocates repeat numbers from
**100** upward, purely so an auto-allocated slot cannot collide with a hand-authored
`repeat=1..n`.

## Concept repeat

Authors can collect the **same concept more than once** in one encounter by setting an
integer `repeat` on a capture node or on `activity_start`.

| Scope | Attribute | Effect |
|-------|-----------|--------|
| Capture node | `repeat=<n>` | Versioning and skip logic use `(name, repeat)` instead of `name` alone |
| Activity start | `repeat=<n>` | Propagated to in-scope descendants (overrides node-level `repeat`; excludes `populate` nodes, including the `input` alias, **and any descendant carrying an `instance`**) |

**Defaults and rules:**

- Omitted `repeat` behaves as **`repeat=1`** (backward compatible with existing diagrams).
- Same `name` + same `repeat` in a later activity is **not re-asked** if already captured
  (encounter-wide). Different `repeat` values (e.g. `1` then `2`) **are** re-asked — that is
  how ETAT re-enters age after “estimated weight does not make sense?” = No.
- That hide applies when the **widget is printed** (`relevant` / FHIR `enableWhen`), not on
  graph `node.relevance`. Path/bridge calculates (`pFPb…`) stay true if you arrived **or** the
  earlier slot already has a value, so glucose and treatments still follow the inherited Yes/No.
  Issue write-up: `fix/20260914-skip-display-not-path.md`.
- Skip keys on the **author slot** (`repeat_authored`): omitted/`1` vs `2` on the node, not on
  `instance` (second page instance) and not only on the export `_Rr_` suffix. An activity-level
  `repeat` still overrides effective `repeat` for export names; skip keeps the drawing’s slot.
- `repeat=-1` is never skip-suppressed and is never a skip source.
- **No cross-repeat inheritance** — a value at `repeat=1` is not merged into logic at `repeat=2`.
- Export suffix **`_Rr_<n>` only when `repeat > 1`** (alongside `_Vv_<n>` version and `_Ii_<n>` instance suffixes). Values `0` and `-1` do not get `_Rr_`.
- `repeat=0` on `populate` / pre-filled nodes forces in-form collection even when pre-encounter data exists.
- **A descendant carrying an `instance` is not repeated.** An instance is by definition a
  collect-once value that later occurrences inherit (see [Instance vs repeat](#instance-vs-repeat)),
  so a repeating activity must not re-ask it — the same reason `populate` nodes are exempt.
- **`repeat=-1` (local-only):** node stays referenceable by name, but does **not** inherit prior values, does **not** feed other nodes’ multi-version coalesce, and is **not** skip-suppressed against other `repeat=-1` occurrences of the same concept (each capture is fully independent — e.g. two different callers each injecting the same snippet activity both get their own, unsuppressed capture). Shares the export base with default `repeat=1`; uniqueness uses `_Vv_n` peer renumbering.

**Same-name value merge:** when several versions of a concept exist in one slot, calculates and expression refs may merge **all** prior versions (`GET_INHERITED_VALUE` → ODK `coalesce`). See `feature/advanced-merge-calc.md`.

**Reading a captured value — `GetRepeatedValue`:** in any calculate or relevance expression:

```text
GetRepeatedValue("<concept name>"[, <slot>])
```

| Authored | Meaning |
|----------|---------|
| `GetRepeatedValue("weight", 2)` | Capture at `repeat=2` only (never falls back to another slot) |
| `GetRepeatedValue("weight")` | Latest capture so far this consultation, any slot |

With an explicit slot it behaves like a plain concept reference — including merging several
versions of that concept via `coalesce` — but **restricted to the requested slot**:

```text
integer  name=weight  repeat=1     "Weight at triage"
integer  name=weight  repeat=2     "Weight after treatment"

calculate  name=weight_delta
  GetRepeatedValue("weight", 2) - GetRepeatedValue("weight", 1)
```

exports to ODK as `coalesce(${weight_Rr_2},'') - coalesce(${weight},'')`.

Omit the slot for confirm-and-overwrite: show the value already collected, re-ask into a new
slot if it is wrong, then read `GetRepeatedValue("weight")` again so downstream logic picks up
the correction.

- An explicit slot must be a **literal integer** — it is resolved while the graph is built,
  before any answer exists.
- The matching capture must sit **earlier in the flow**. If none is processed yet, the
  reference is unresolved — there is no silent fallback to an empty calculate / `1`.
- `GetRepeatedValue("x", -1)` addresses a local-only node and never merges encounter slots.
- Supported on XLSForm/ODK and CHT. FHIR/OpenSRP supports the explicit-slot form; omit-slot
  (latest across slots) is XLSForm/CHT first.

Full specification: `feature/20260821-get-repeated-value-operation.md` (explicit slot) and
`feature/20260825-get-repeated-value-latest.md` (optional slot).

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

Arrow labels (draw.io) and edge `value`s (YAML) are interpreted as branch semantics by
the same routine (`process_edge_label` in `xml_to_tricc.py`). Labels are case-insensitive
unless noted.

| Label pattern | Meaning | Typical source node |
|---------------|---------|---------------------|
| `yes`, `oui` | Affirmative branch | `select_yesno`, `rhombus` |
| `no`, `non` | Negative / exclusive branch | `select_yesno`, `rhombus`, calculates |
| `follow`, `suivre`, `continue` | Continue without branching | `select_yesno`, `rhombus` |
| *(empty)* | Treated as **yes** on `rhombus` out-edges | `rhombus` |
| Integer factor (`-1`, `+2`, `3`, …) | **Yes** branch with optional score factor | `rhombus`, selects, calculates |
| Reserved expression tokens | Condition edge → may insert a nested `rhombus` | Any calculate-capable node |
| `Answer("<code>")` | Condition on the answer, as CQL; `<code>` is the answer concept (option concept code or name): `"<option name>" in $this` (select_one / select_multiple), `$this is true` / `$this is false` for `Answer("yes")` / `Answer("no")` (select_yesno); inserts a rhombus like any condition edge. `Answer('<code>')` is still read | `select_one`, `select_multiple`, `select_yesno` |

In a CQL condition, the answer side of `in` / `contains` is a code: `"rash" in $this` and
`'rash' in $this` both mean `selected(${q}, 'rash')`. The identifier is never read as a node.

Every out-edge of a `select_yesno` needs `yes`, `no` or `follow`: an unlabelled one stops
the conversion. In YAML, a `select_yesno` without `options` gets the built-in yes / no
options (list `yes_no`), as in draw.io.

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
