# Page groups in YAML activities

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Related** | `converters/xml_to_tricc.py` `get_groups` / `add_group` (draw.io `container_page`), `models/base.py` `TriccGroup`, `serializers/xls_form.py` `GROUP_TRICC_TYPE`, `strategies/input/yaml.py` |
| **Frontend** | `../tricc_frontend/feature/20261009-canvas-comments-and-groups.md`. The frontend writes this format; that side is implemented, not committed. |
| **Strategy** | `YamlStrategy` (input). The outputs already handle `TriccGroup` from draw.io. |
| **Approval** | — |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business description

In draw.io, an author frames questions with a **`container_page`**. `tricc_oo` reads it as a
`TriccGroup`, and the XLSForm (and DHIS2 and OpenMRS) export turns it into a group: a section or
page of the form.

The authoring app now lets authors group nodes the same way. It writes the groups into the
activity YAML. `YamlStrategy` does not read them yet, so a YAML project loses its form sections.

This spec makes YAML groups behave exactly like draw.io `container_page` groups.

# Part II — Technical specification

## 1. Format (written by the frontend)

```yaml
id: danger-signs
groups:
  - id: g1                      # local id, referenced by nodes and other groups
    name: danger_signs          # concept code; the group label comes from the concept, like a node's
    parent: g0                  # optional: nested group
    ui: { x: 300, y: 100, width: 400, height: 300, color: pink }   # frontend only, ignore
  - id: g0
    name: triage
nodes:
  - id: q1
    type: select_yesno
    name: convulsions
    group: g1                   # membership
    ui: { x: 20, y: 40 }        # relative to the group, frontend only, ignore
```

- Neither `label` nor `relevance` is written by the frontend; texts live in the CodeSystem.
- An older file may still carry an inline `label` on a group. Accept it, as for nodes.
- The order of `groups` is the authoring order. Nodes keep their flow order; a group does not
  reorder anything.

## 2. YamlStrategy

**Models**

- `YamlGroup(YamlModel)`: `id: str`, `name: Optional[str]`, `label: Optional[DisplayTextInput]`,
  `parent: Optional[str]`. `ui` is ignored, as everywhere.
- `YamlActivity.groups: List[YamlGroup] = []`.
- `YamlNode.group: Optional[str]`.

**`_build_activity`, after the nodes are built**

1. Create a `TriccGroup` per YAML group:
   - `id = generate_id(activity.id + group.id)`, deterministic;
   - `name = group.name`; when absent, `TriccGroup` generates one;
   - `label`: the inline label when present, else the concept text of `name`. Use the same
     lookup as node labels (`_concept_texts`: q-display, then display).
   - `activity` is the activity.
2. Link the parents: `group.group = groups[parent]` when `parent` is set, else the activity. That
   is what `add_group` does for nested `container_page`.
3. For each node with `group`, set `node.group = groups[group]`. That overrides the default
   `node.group = activity` (yaml.py ~508).
   - Select options take their select's group, as they already do (yaml.py ~621).
4. An unknown `group` or `parent` id: warn and keep the activity as the group. Never fail the
   load.
5. A `parent` cycle: warn and break it at the first repeated id.

Expose the groups wherever the draw.io path exposes `get_groups(...)`, so the outputs find them
the same way.

## 3. Tests (`tests/test_yaml_page_groups.py`)

- One group of two questions: the XLSForm has a `begin_group` / `end_group` around them, named
  `danger_signs`, labelled from the concept display.
- A nested group: nested begin/end groups.
- A group label in French comes from a French concept designation.
- An unknown `group` id: a warning, and the node stays at the activity level.
- Draw.io parity: the same structure drawn with `container_page` produces the same XLSForm group
  rows.

## 4. Acceptance

- A YAML activity with `groups` exports the same form sections as the equivalent draw.io page
  with `container_page`.
- YAML without `groups` is unchanged; the regression suite passes as is.
