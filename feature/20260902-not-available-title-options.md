# Not-available question title and multiple reasons

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `docs/tricc-elements.md` (`not_available`) |
| **Strategy** | Authoring + ODK/CHT export (`XLSFormStrategy` / `XLSFormCHTStrategy`). Other strategies unchanged. |
| **Approval** | Approved 2026-09-02 |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business description

*Audience: clinical authors, guideline developers, implementers.*

## 1. What this is

A “not available” box is the opt-out next to a measurement (for example weight): the clinician
picks a reason instead of entering a value. Until now the box had no question title on the form
(the placeholder `NO_LABEL`) and only one reason, taken from the shape text.

Authors can now draw it like a single-choice question:

- **Header** — the title shown on the form (for example “Weight estimation”).
- **Rows** — one or more reasons (for example “Not stable enough”, “No scale”).

Only those rows are exported. A box with no `select_option` children has no radio options.

## 2. Who is affected

Authors of ODK/CHT forms that use `not_available`. Clinicians see a real title and can pick
among several reasons. The rule “cannot tick a reason if a value is already entered above”
does not change.

## 3. Benefits

- No `NO_LABEL` heading when the author supplies a title.
- Several clinical reasons in one control, instead of one hard-coded sentence.

## 4. Limitations

- **ODK/CHT presentation.** Other export formats are not the target of this change.
- **No invented option.** Boxes without `select_option` rows export no radios.
- The control remains a single-choice list: one reason at a time.

---

# Part II — Technical specification

*Audience: developers.*

## 1. Authoring

| Drawing | Question `label` | Options |
|---------|------------------|---------|
| `odk_type="not_available"` with no `select_option` children | Shape / header text | None |
| Swimlane (or stacked box) with `select_option` children | Shape / header text | Each child option (`name` as stored) |

Scratchpad stencil: same stacked layout as `select_one`, `odk_type="not_available"`.

## 2. Semantics

- Parent measurement coupling is unchanged (relevance / required / constraint on the question).
- Downstream “not available was chosen” is **any option selected** (`EXISTS`).
- Child `select_option.name` is the stored ODK choice value (same as `select_one`).
  No synthetic option is added. Copies of the same concept share one choice list, so
  use the same option `name`s on every copy.
- Outgoing edges attach to **every** option so any reason continues the path. One-option legacy
  boxes still attach only to that one option.

## 3. Code checklist

- [x] `xml_to_tricc.add_tricc_base_node`: collect child options when present; else legacy path.
- [x] `drawio.linking_nodes`: link all options, not only `options[0]`.
- [x] `get_node_expression` / `get_count_terms_details`: any-selected, not `SELECTED(..., 1)`.
- [x] YAML `not_available` with `has_options` for fixtures.
- [x] Scratchpad stencil + `docs/tricc-elements.md`.

## 4. Tests

- No children → header kept, no invented option.
- Titled: children → authored label + those options (authored `name`).
- YAML fixture loads title and multiple options.

## 5. Acceptance criteria

- A stacked `not_available` exports only the `select_option` rows that were drawn.
- No synthetic choice named `1` is added.
- Choosing either reason counts as “not available” for the following path.
