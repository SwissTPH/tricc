# Concept texts from the frontend: codes-only YAML, questionnaire text, and the message tree

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Related** | `feature/20260909-display-message-ast.md` (Implemented; this adds a JSON input path to the tree), `feature/display-text-injection.md`, `feature/20260907-project-config.md`, commits 9676af2 (YamlStrategy reads node and option texts from the CodeSystem), d76bf11 (hint/help as designations), a3ad036 (translations from designations) |
| **Frontend** | `../tricc_frontend/feature/20261008-data-dictionary-and-concept-texts.md` §2.0, §2.4, §2.5, §2.6, §2.7. The frontend side of every item below is implemented, not committed. |
| **Strategy** | `YamlStrategy` (input). XLSForm/CHT and FHIR translation output (`serializers/xls_form_translations.py`). `converters/datadictionnary.py`. |
| **Approval** | — |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business description

## 1. What changes

The authoring app (`tricc_frontend`) no longer writes texts into activity YAML. A question, a
display node or an answer carries only its **name**, which is the code of a concept in the
project CodeSystem. Its texts live on that concept, in every language: display, hint, help, and a
new **questionnaire text**.

Three things follow for `tricc_oo`.

1. **Codes-only YAML must load.** A node whose label comes only from its concept must get that
   label. `YamlStrategy` mostly does this already (commit 9676af2); the frontend relies on it, so
   it needs fixtures that pin the behaviour.
2. **Questionnaire text** (`q-display`) is a new designation use.
   - A concept's display stays its short dictionary name, used in CQL and lists.
   - The questionnaire text is what the form shows. It falls back to the display.
   - It can be scoped to one intervention, for example a shorter wording in the community
     intervention.
3. **Formatted text arrives as a tree.** The app's text editor writes `tricc_oo`'s own message
   tree (bold, italics, underline, breaks, lists, `${name}`) as JSON in a designation extension.
   `tricc_oo` reads that tree directly instead of re-parsing a string. That was the point of the
   message AST: formatting and injected data come out the same in every export and every
   language.

## 2. Who is affected

- Projects saved by the authoring app: activity YAML with names only, and texts in the CodeSystem.
- Draw.io projects: unchanged. The frontend converts their labels when it opens them; `tricc_oo`
  keeps reading draw.io as today.
- Exports: the form label is now the questionnaire text when one exists. Translated labels gain
  `${}` renaming and formatting that they lack today.

## 3. Example

A CodeSystem concept:

```json
{
  "code": "give_dose",
  "display": "Give dose",
  "designation": [
    {
      "language": "en",
      "use": { "system": "https://tricc.org/CodeSystem/designation-use", "code": "q-display" },
      "value": "**Give ${dose} mg**",
      "extension": [
        { "url": "https://tricc.org/StructureDefinition/designation-message",
          "valueString": "{\"type\":\"message\",\"children\":[{\"type\":\"mark\",\"kind\":\"strong\",\"children\":[{\"type\":\"text\",\"value\":\"Give \"},{\"type\":\"interp\",\"name\":\"dose\"},{\"type\":\"text\",\"value\":\" mg\"}]}]}" }
      ]
    },
    {
      "language": "en",
      "use": { "system": "https://tricc.org/CodeSystem/designation-use", "code": "q-display" },
      "value": "Give the dose",
      "extension": [
        { "url": "https://tricc.org/StructureDefinition/designation-intervention", "valueCode": "community" }
      ]
    }
  ]
}
```

The activity YAML node:

```yaml
- id: n12
  type: note
  name: give_dose
```

- **Intervention `sick-child`:** the XLSForm label is `**Give ${dose_export_name} mg**`.
- **Intervention `community`:** the label is `Give the dose`.
- **Concept used in CQL:** it reads as "Give dose".

## 4. Benefits

- One source for every text. Translations and rewording happen in one place.
- Formatting and `${}` behave the same in every language. Today translated designations are used
  as is, and their `${}` are not renamed (commit a3ad036).
- No HTML or Markdown string is re-parsed on the way in.

## 5. Limitations

- The tree is carried only when the text has structure. A plain text is just `value`, so FHIR
  resources do not grow for nothing.
- `display` stays plain text. It is a dictionary name.
- The JSON form has no paragraphs. The frontend joins blocks with a break, which is the same rule
  the HTML parser applies to `div`/`p` after content.

## 6. Out of scope

- Moving activity and intervention titles out of YAML.
- Planning and care-plan texts.
- A Markdown parser. The value is Markdown for readers only; `tricc_oo` never parses it back,
  because the tree travels beside it.

---

# Part II — Technical specification

## 1. Codes-only YAML (frontend §2.6)

**Rule.** A text-bearing node or option with no `label`/`hint`/`help` takes them from its concept:
the explicit `concept`, else the node `name` in `default_code_system`. The frontend writes
`default_code_system` as the CodeSystem **url** (`https://tricc.org/CodeSystem/<project id>`
for a CodeSystem it created). `find_concept` must accept a url, a name, or an id.

The text-bearing types are the capture types (`select_*`, integer, decimal, quantity, text,
date), plus note, diagnosis, proposed_diagnosis and not_available. calculate and rhombus are not
text-bearing (`NO_CONCEPT_TEXT_TYPES`).

**Fixtures** (`tests/test_yaml_codes_only.py`):

- A decimal with only `name: weight_kg` gets label, hint and help from the concept `weight_kg`.
- A `select_one` with options that have only `name` gets the option labels from the concepts
  `yes` / `no`. One answer concept is shared by several questions.
- The same with `default_code_system` given as url, as name, and as id.
- A node with an explicit `concept: {system, code}` in another CodeSystem.

## 2. Questionnaire text `q-display` (frontend §2.4, §2.5)

**`converters/datadictionnary.py`**

- Add `"q-display": ("https://tricc.org/CodeSystem/designation-use", "q-display")` to
  `DESIGNATION_USES`.
- `concept_text(concept, use, lang, default_lang, intervention=None)`:
  - **`use="q-display"`:** return the q-display designation for that language, else
    `concept_text(..., "display", ...)`.
  - **Intervention scope:** a designation with one or more extensions
    `{"url": "https://tricc.org/StructureDefinition/designation-intervention", "valueCode": <id>}`
    applies only to those intervention ids. When `intervention` is given, a scoped designation
    for it wins over the unscoped one. An unscoped designation is used otherwise. A scoped one is
    **never** used for another intervention, or when `intervention` is `None`.
  - **Uniqueness:** at most one designation per (use, language, scope). The frontend validates
    this (`concept.duplicate-designation`).

**YamlStrategy (`strategies/input/yaml.py`)**

- `TEXT_FIELD_USES`: `label` → `q-display`, with the display fallback above. `hint` → hint and
  `help` → help, unchanged.
- Pass the intervention being built down to `_concept_texts` (around line 666).
  - Each intervention is converted separately, and shared files are read once per intervention
    (`docs/tricc.yaml.template`). So two interventions listing the same activity may get two
    different labels, with no node copy.

**Translations (`serializers/xls_form_translations.py`)**

- `label::<lang>` takes q-display, then display, then the gettext catalogue, then the default
  text.
- Use the same intervention scope.

**Fixtures**

- One activity listed by two interventions. The concept has an unscoped q-display and a
  q-display scoped to one intervention. The two XLSForms carry different labels.
- A concept with only a display: the label is the display, as today.
- `label::fr` comes from a French q-display.

## 3. The message tree in a designation (frontend §2.7)

**Storage**

- `value` is the Markdown rendering of the tree, by this repo's rules: `serialize_injection_for_js_text`
  — `**strong**`, `_em_`, no marker for underline, `\n` for breaks, `- ` / `1. ` for list items,
  and `${name}` unrenamed.
- When the tree has structure, the designation also carries:

  ```json
  { "url": "https://tricc.org/StructureDefinition/designation-message", "valueString": "<compact JSON>" }
  ```

  Structure means a mark, an interpolation, a break, or a list: anything `_simplify_message` would
  not reduce to `str`.

**JSON form.** This is this repo's wrapper tree with a `type` discriminator. It is the dialect
`20260909-display-message-ast.md` §2.9 left open; the frontend fixed it.

| JSON | Python |
|------|--------|
| `{"type":"message","children":[…]}` | `TriccMessage` |
| `{"type":"text","value":…}` | `TriccMessageText` |
| `{"type":"interp","name":…}` | `TriccReference(name)` (unresolved) |
| `{"type":"break"}` | `TriccMessageBreak` |
| `{"type":"mark","kind":"strong"\|"em"\|"u","children":[…]}` | `TriccMessageMark` |
| `{"type":"mark","kind":"color","color":"#d32f2f","children":[…]}` | `TriccMessageMark(kind=COLOR, value="#d32f2f")`, **new**, see §3.1 |
| `{"type":"list","ordered":bool,"items":[{"type":"item","children":[…]}]}` | `TriccMessageList` / `TriccMessageListItem` |

There is no paragraph node.

**Code**

1. In `visitors/text_injection.py`, add `message_from_json(data) -> TriccMessage` and
   `message_to_json(message) -> dict`.
   - The discriminator lives in the codec only. The Pydantic models stay as they are.
   - Unknown `type` is a load error naming the concept code.
2. `concept_text`: when the selected designation has the `designation-message` extension, return
   `message_from_json(json.loads(valueString))`. Pass it through `_simplify_message`. Do not use
   `value`.
   - `load_display_text` already returns message trees untouched (`_is_message_tree`).
     `process_reference` then resolves and renames the interpolations as for any label.
   - Without the extension, behave as today: `value` goes through the HTML/plain path.
3. Translation export renders other-language designations through the same tree, so their `${}`
   are renamed. Today they are copied verbatim.

**Parity fixtures**

- The frontend generated `packages/core/src/text/__fixtures__/messages.json` with **this repo's**
  `load_display_text` and `serialize_injection_for_js_text`: 18 HTML inputs, each with its tree
  in the JSON form above and its Markdown. The frontend parser and Markdown writer match all of
  them.
- Copy that file to `tests/fixtures/messages.json`. Add `tests/test_message_json.py`, which for
  each entry checks:
  - `message_to_json(load_display_text(html))` equals `tree`;
  - `message_from_json(tree)` serializes to `markdown`.
- When the parser changes, regenerate the file here and copy it back to the frontend. The
  frontend test then shows where the two disagree.

**Fixtures** (`tests/test_concept_message_texts.py`)

- A note whose concept q-display carries the extension
  `**Give ${dose} mg**`, with `dose` a decimal in the same activity.
  - XLSForm label: `**Give ${<dose export name>} mg**`.
  - FHIR `item.text` as today for messages.
- The same concept with a French q-display tree: `label::fr` has the renamed interpolation.
- A broken `valueString` falls back to `value` with a warning, not a crash.

## 3.1 Font colour (added 2026-10-09, Patrick)

Authors can colour part of a text, for example a danger sign in red. Colour is a new mark kind.

**Model**

- `TriccMessageMarkKind.COLOR = "color"`.
- `TriccMessageMark` gains `value: Optional[str]`, the CSS colour. Accept `#rgb`, `#rrggbb` or
  `#rrggbbaa`, or a colour name. Anything else is dropped with a warning, never passed through,
  because it ends up in HTML.

**Markdown** (`_markdown_node`)

- `<span style="color:#d32f2f">inner</span>`. ODK Collect and CHT render this inline HTML in
  labels.
- `inner` is the usual Markdown of the children, so `**Give ${dose}**` inside a colour stays
  bold.

**FHIR.** Use the same span in the XHTML rendering of `item.text`, where XHTML is used. In plain
`text`, it is the inner text.

**HTML parse**

- Two tags become a colour mark instead of being unwrapped (they are in `UNWRAP_TAGS` today):
  - `font color="…"`;
  - `span style="…color:…"`.
- Other styles stay ignored.
- This changes the parity fixture `<span style="color:red">Danger</span> <img src="x.png"> sign`.
  Regenerate `tests/fixtures/messages.json` and copy it to the frontend, whose `fromHtml` follows
  in the same change.

**Frontend status.** The tree, the JSON (`kind: "color"` with `color`), the Markdown, and the
editor (preset colours plus a picker) are implemented. The frontend `fromHtml` still unwraps
colour, as `tricc_oo` does today, so parity holds until this section lands.

## 4. Checklist

| # | Item | Where |
|---|------|-------|
| 1 | `find_concept` accepts url / name / id for `default_code_system` | `converters/datadictionnary.py` |
| 2 | Codes-only YAML fixtures | `tests/test_yaml_codes_only.py` |
| 3 | `q-display` use; `concept_text(..., intervention=None)` with scope | `converters/datadictionnary.py` |
| 4 | `TEXT_FIELD_USES` label → q-display; pass the intervention down | `strategies/input/yaml.py` |
| 5 | Translations use q-display and scope | `serializers/xls_form_translations.py` |
| 6 | `message_from_json` / `message_to_json` | `visitors/text_injection.py` |
| 7 | `concept_text` returns the tree from `designation-message` | `converters/datadictionnary.py` |
| 8 | Translated trees rename `${}` | `serializers/xls_form_translations.py` |
| 9 | Parity fixtures and tests | `tests/fixtures/messages.json`, `tests/test_message_json.py` |
| 10 | Docs: designation uses and the two extensions | `docs/cli-and-inputs.md`, `docs/tricc.yaml.template` |
| 11 | Colour mark: model, JSON, Markdown span, HTML parse of `font color` / `span style=color`, regenerated fixtures | `models/message.py`, `visitors/text_injection.py`, `tests/fixtures/messages.json` |

## 5. Acceptance

- Codes-only YAML from the frontend converts with the same labels as the inline-label YAML it
  replaces. The regression suite is unchanged for draw.io and for YAML with inline labels.
- An intervention-scoped q-display changes that intervention's form only.
- A designation tree and the equivalent HTML label produce identical Markdown.
- The parity fixtures pass on both sides.

## 6. Coordination

- The frontend already writes all of this:
  - codes-only YAML, migrating inline labels on open;
  - `q-display`;
  - the intervention-scope extension;
  - the `designation-message` extension.
- Until items 3–7 land, `tricc_oo` reads the frontend's projects with these limits:
  - labels come from `display`; a q-display is ignored;
  - scoped texts are ignored;
  - a formatted text arrives as its Markdown `value` through the HTML/plain path. The `${}` still
    resolve, but `**` stays literal.
