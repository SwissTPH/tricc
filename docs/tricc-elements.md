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

## Sequence-node semantics (from visual authoring guidance)

- **Rhombus**: conditional split; out-edges usually use `Yes` / `No` / `Continue` or `Follow`.
- **GoTo**: placeholder link to another activity/tab, replaced during graph construction.
- **Start nodes**: `start` begins process; `activity_start` begins activity.
- **Wait**: ensures downstream progression only after referenced nodes are reached.
- **Bridge**: merge helper for readability when many paths converge.
- **Ends**:
  - `activity_end`: marks activity completion.
  - `end`: terminates encounter/process path.

## Experimental page behavior

If the activity root has `status="experimental"`, TRICC limits page processing intentionally.
This behavior is implemented in `create_activity` inside `tricc_oo/converters/xml_to_tricc.py`.

Use this to keep draft content present in source diagrams without full production processing.
