# The start node is the activity; activity starts need no name

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Related** | `../tricc_frontend/feature/20261008-drawio-import-and-sequence-nodes.md` §2.1, §2.2 (source of this spec), `feature/20261008-intervention-name-replaces-form-id.md` (activity / intervention `name`) |
| **Strategy** | `DrawioStrategy`, `YamlStrategy` (all outputs through activity / root labels) |
| **Source** | Patrick, 2026-10-08: "The root node of a page is the activity" (both `start` and `activity_start`); start, activity start and activity end are sequence nodes with no business name. |
| **Approval** | — |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

**An activity start needs no name.** Start, activity start and activity end only mark where a
flow begins and ends. TRICC gives them an internal id, so authors should not have to invent a
name. Today a draw.io activity start without a `name` stops the conversion.

**The start node is the activity.** The shape that starts a page *is* that activity: its label
is the activity's title, and in YAML the title, name, process and applicability are written
once, on the activity, not repeated on the start node.

- In draw.io, an activity is titled by its start shape's label. The page tab name is only used
  when the shape has no label. Today the page tab name always wins.
- In YAML, the start node can be just `{id, type}`. It takes its label from the activity
  `title` and, for a process start, its process from the activity `process`. Older files that
  still put `label`, `process` or `relevance` on the start node keep working.

**Effect on forms.** Drawings whose page tab name differs from the start shape label get the
shape label as the activity (group) title. Nothing else changes.

---

## Part II — Technical specification

### 2.1 Activity start without a name

- `converters/drawio_type_map.py`: `activity_start` `mandatory_attributes` `["label", "name"]` →
  `["label"]`.
- Names stay deterministic without a `name`:
  - activity name: `_get_name("act_", shape id, page id)` = `act_<page id><shape id>`
    (`create_root_node`);
  - node name: `TriccNodeBaseModel.__init__` → `get_rand_name(id)`, a blake2b hash of the id.
- YAML: `TriccNodeActivityStart` without `name` already gets `get_rand_name(id)`.
- `TriccNodeActivityEnd.set_name` is not touched.

### 2.2 Root label and attributes

**Draw.io** (`create_root_node`, `create_activity`):

- Root label = the root shape's `label`, else the page name, for both `start` and
  `activity_start` (`start` already reads the shape label; `activity_start` read the page name).
  The label keeps its HTML like every other node label; exports strip it as today.
- `activity.label` = the same value (was the page name).
- The activity id stays derived from the page id (ids are `goto` targets).

**YAML** (`_build_activity`), activity level is the single copy; the root node values are a
legacy fallback:

| Attribute | Root node gets | Activity gets |
|-----------|----------------|---------------|
| label / title | its own `label`, else the activity `title` | `title`, else the root `label`, else the id |
| process (main `start` only) | its own `process`, else the activity `process` | unchanged |
| relevance / applicability | unchanged | `applicability`, else the root `relevance` (as draw.io) |

- "Activity title set" means `title` was written in the file (`model_fields_set`), since
  `title` defaults to the id.
- When both are set and differ, the root value is kept on the root (outputs of older files do
  not change) and the activity value on the activity; no message (the frontend emits
  `activity.root-attribute-dropped` on its side).

### 2.3 Tests

- Draw.io: an `activity_start` with a label and no `name` loads; activity name
  `act_<page id><shape id>`, stable across two loads; root and activity label = shape label.
- Draw.io: empty shape label → page name.
- YAML: `activity_start` with no `name` / `label` loads; root label = title.
- YAML: `start` with no `process` takes the activity `process`; a legacy root `label` /
  `process` still wins on the root.
- Unit + regression suites; regression baseline changes are listed with the reason.

### 2.4 Open questions

| # | Question | Recommendation |
|---|----------|----------------|
| 1 | Activity label from the shape: keep the HTML or strip it? | Keep it, like every node label; exports already strip or convert it. |
| 2 | YAML conflict (root `label` ≠ activity `title`): which wins on the root? | The root's own value, so older fixtures' outputs stay byte-identical. |
