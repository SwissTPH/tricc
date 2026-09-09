# Display message AST (replace Concatenate for formatted text)

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Related** | `feature/display-text-injection.md` (Implemented — `${REF}` authoring stays; **Concatenate as the in-memory message type is replaced by this spec**), `docs/tricc-elements.md`, `docs/pipeline.md` |
| **Strategy** | All strategies that emit display text: `XLSFormStrategy` (+ CHT variants), `FHIRStrategy` / `OpenSRPStrategy`, `HTMLStrategy`, test-spec. `TriccOperator.CONCATENATE` is unchanged for **calculate** expressions. |
| **Approval** | — |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business description

*Audience: clinical authors, guideline developers, implementers.*

## 1. What this is

Notes, question labels, hints, help, and validation messages can mix **formatting** (bold, italic,
lists — the styling you set in the drawing) with **live values** (`${age}`, `${dose}`).

Today the exporter stores that mix as a string-join (concatenate): “this bit of text” + “that
field” + “more text”. Concatenate is the right tool for *calculating* a string in a formula. It is
the wrong tool for a **message**, because formatting is not a formula. Markdown conversion then
runs on flattened pieces, so bold/italic around a live value often breaks (markers split across the
value, extra blank lines, tags left behind on short labels).

This spec stores each message as a small **tree** (an AST): “this phrase is bold, and inside it
there is the age field, then the unit”. Formatting is converted to Markdown or HTML from that
tree, so markers always wrap a complete phrase. Live-value tokens still work as they do today.

Authors do not change how they write diagrams. `${field}` in a label still means “show this field’s
value here”.

## 2. Who is affected

Anyone who authors **display** text on notes, questions, options, hints, help, or constraint /
required messages — especially when the drawing uses **bold, italic, or lists** together with
`${…}` injection. Clinicians see correctly formatted sentences instead of broken Markdown
(`**Give ` then the dose then ` mg**`) or leftover HTML.

Logic nodes (calculates, rhombus, waits) are unchanged. A calculate that truly concatenates strings
keeps using concatenate.

## 3. Example

Drawn note (bold around the dose):

```text
Give **${dose} mg** of amoxicillin.
```

| | Today (concatenate of fragments) | With a message tree |
|--|--|--|
| Stored as | `"Give **"` + dose + `" mg** of amoxicillin."` | bold phrase = [dose] + `" mg"`, then the rest |
| ODK / CHT label | Markers can sit on either side of `${dose}`, so the app may not bold the number | `Give **${dose} mg** of amoxicillin.` |
| Same idea in HTML from draw.io | HTML is turned into Markdown *before* the tree exists, so tags and `${…}` fight each other | HTML becomes the tree first; Markdown is produced last |

A label with no styling and no `${…}` stays ordinary text.

## 4. Benefits

- Bold, italic, and lists survive export when a live value sits in the middle of the phrase.
- One structure for every language of a multi-language label.
- The exporter can still find which fields a message depends on (so versioned / repeated names
  resolve the same way as today).

## 5. Limitations

- Tokens remain bare field names (`${age}`), not expressions (`${age + 1}`).
- Only the formatting draw.io already keeps after stripping images, tables, and links
  (bold, italic, line breaks, simple lists). No new authoring syntax.
- Calculate / CQL / XLSForm **`concat(...)`** for computed values is a different feature and is
  not replaced.

## 6. Out of scope

- Changing `${REF}` authoring or which node types allow injection (still display models only).
- New rich-text controls in the drawing tool.
- Using concatenate operations as the stored form of a label, hint, help, or message.
- Shipping a JS rich-text editor in this change. The tree must still be **easy to
  interchange** with one (see Part II §2.9).

---

# Part II — Technical specification

*Audience: developers.*

## 1. Problem

After `feature/display-text-injection.md`, a display field is typed as `DisplayText`:

```python
Union[str, Dict[str, Union[str, TriccOperation]], TriccOperation]
```

When the string contains `${REF}`, input load builds `TriccOperation(CONCATENATE, [TriccStatic…, TriccReference…])`.

That is wrong on three axes:

1. **Domain.** `CONCATENATE` is a value operator (`tricc_operation_concatenate` → XLSForm
   `concat()`, CQL `+` / `Concatenate`). Questionnaire / XLSForm *labels* are not calculations.
   FHIR already has a `FIXME` that feeds `get_tricc_operation_expression(label)` into
   `item.text`.
2. **Formatting.** `load_display_text` **must** `remove_html` the *whole* string before split
   (`text_injection.py`: never clean per Concatenate segment — tags would be unbalanced).
   `remove_html` is `markdownify` + BeautifulSoup, and it **no-ops when the string has no space**,
   so `<b>Weight</b>` stays HTML while `<b>Weight kg</b>` becomes Markdown. `markdownify` also
   emits trailing newlines and uses `*` for both strong and em.
3. **Unround-trippable Markdown.** After split, markers straddle interpolations
   (`**Give ` + ref + ` mg**`). You cannot convert, indent, or strip a segment without breaking
   Markdown. Export then serializes those fragments back to one string (ODK) or to a concatenate
   expression (FHIR), so the damage is locked in.

`get_references()` on `TriccOperation` is the only reason Concatenate was convenient: processing
(`process_operation_reference`, stashing, versioned names) already walks it. A message type must
keep that contract and drop the operator.

## 2. Formal model

### 2.1 Naming

The root type is **`TriccMessage`** unless approval picks another name. Child types share the
same prefix (`TriccMessageText`, `TriccMessageMark`, …). The union alias **`DisplayText`** stays
the field type (`str | dict | <root>`). Authors never see this name.

| Name | Why it fits | Why not |
|------|-------------|---------|
| **`TriccMessage`** (default) | Matches `constraint_message`, `required_message`, and node types `help-message` / `hint-message`. Short. Clearly not an operation. | A question `label` is not usually called a “message”. |
| `TriccRichText` | Usual name for formatted text + interpolations; covers `label` as well as help/hint. | Does not match existing `*_message` fields. |
| `TriccFormattedText` | Explicit. | Long; every child type becomes noisier. |

Do **not** reuse `TriccOperation`, `TriccStatic`, or the `DisplayText` alias as the tree root.
If the root name changes at approval, it is a prefix rename only — shape and `get_references`
do not change.

### 2.2 Type

Pydantic tree: leaves and wrappers, not an operator. Working name **`TriccMessage`**.

```text
TriccMessage
  children: TriccMessageNode[]

TriccMessageNode =
    TriccMessageText(value: str)
  | TriccReference            # unresolved ${name}
  | <resolved TriccNodeBaseModel>   # after process_reference
  | TriccMessageBreak
  | TriccMessageMark(kind: strong | em | u, children: TriccMessageNode[])
  | TriccMessageParagraph(children)
  | TriccMessageList(ordered: bool, items: TriccMessageListItem[])
  | TriccMessageListItem(children)
```

**Interpolation leaf.** In the Python graph, an interpolation may be a `TriccReference` or a
resolved node (same as Concatenate operands today). For **JSON / a JS editor**, it is always a
dedicated atom `{ "type": "interp", "name": "dose" }` — never a live `TriccNodeBaseModel`.
Resolution stays a pipeline concern; authoring JSON is unresolved names only.

Resolved interpolations may stay as `TriccReference` whose `.value` was replaced via
`replace_node`, or as the node object itself (`serialize_injection_for_js_text` already accepts
both). Prefer **the same objects Concatenate already stores as operands** so resolution code
stays shared.

`DisplayText` becomes:

```python
Union[str, Dict[str, Union[str, TriccMessage]], TriccMessage]
```

Never `TriccOperation` on `label` / `hint` / `help` / `constraint_message` / `required_message`.

Keep **`str`** when there is no interpolation and no remaining markup (majority of fixtures).
Build a `TriccMessage` when there is at least one `${REF}` **or** at least one kept mark
(bold / italic / break / list).

### 2.3 `get_references` / `replace_node` / `copy`

`TriccMessage` (and every wrapper node) must implement:

| Method | Contract |
|--------|----------|
| `get_references()` | `OrderedSet` of `TriccReference` and/or `TriccNodeBaseModel`, depth-first, same as `TriccOperation.get_references()`. Text / breaks contribute nothing. |
| `replace_node(old, new)` | Replace interpolation targets in place (including inside marks/lists). |
| `copy(**kwargs)` | Deep copy of the tree; interpolations follow the same `TriccReference` vs node-name rules as `TriccOperation.__copy__`. |

Duck-typing: `hasattr(x, "get_references")` used by `iter_node_dependencies` / walk path length
must succeed on `TriccMessage`.

### 2.4 Pipeline

```text
raw display HTML/text
  → parse HTML to TriccMessage (BeautifulSoup; do not markdownify first)
  → split text nodes on ${REF} → TriccReference leaves
  → if tree is a single TriccMessageText with no marks: store str
  → process_reference / process_operation_reference via get_references + replace_node
  → export walk:
        ODK/CHT: message_to_markdown() with ${export_name} for interpolations
        FHIR:    message_to_markdown() or XHTML for item.text;
                 if a calculated label is still required, *emit* concatenate at
                 serialize time from complete literal runs (never store Concatenate)
        logs / get_name: first text leaf (label_text_for_name)
```

**Rule.** HTML → Markdown is a **serializer of the AST**, not a pre-processor of the source
string. `remove_html` / `remove_html_full` stay for non-message strings (edge labels, attributes).
Display fields do not call them on the raw string before parse.

### 2.5 HTML subset (parse)

Match what `remove_html` already keeps / strips:

| Action | Tags |
|--------|------|
| Keep as marks / structure | `b`, `strong` → `strong`; `i`, `em` → `em`; `u`; `br`; `ul` / `ol` / `li`; wrapped text as paragraph or inline sequence |
| Unwrap (keep children) | `span`, `font`, `div`, `a`, `p` (p may become `TriccMessageParagraph`) |
| Drop | `img`, `table` (and their descendants) |

`${name}` is matched only inside text nodes (`INJECTION_TOKEN_RE` unchanged). Adjacent text
nodes may be merged after unwrap.

### 2.6 Markdown serialize (ODK / CHT)

Walk the tree and wrap **the full serialization of a mark’s children** in one pair of markers:

- `strong` → `*`…`*` or `**`…`**` (pick one pair and use it only for strong; em must differ —
  e.g. `**strong**` and `_em_` — so nested marks stay unambiguous). Do **not** reuse
  `markdownify`’s `strong_em_symbol="*"` for both.
- Interpolations inside a mark stay inside the wrapper:
  `Mark(strong, [Text("Give "), Ref(dose), Text(" mg")])` → `**Give ${dose} mg**`.
- Lists: `- ` / `1. ` per item; line breaks as `\n`.
- Do not emit a trailing newline unless the tree contains an explicit break / paragraph split.
- `serialize_injection_for_js_text` becomes a markdown walk (or is replaced by
  `message_to_js_text(message, export_name_cb)`). Non-message `TriccOperation` in a display
  field is a load error.

### 2.7 Processing

`process_reference` today only recurses `TEXT_INJECTION_FIELDS` when the value is
`TriccOperation` (including locale dicts). Change that to `TriccMessage` (and still walk locale
dicts). Name resolution, versioned export names, and `GET_INHERITED_VALUE` / last-version rules
for interpolations stay exactly those of `process_operation_reference` — either:

- generalize that function to “anything with `get_references` + `replace_node`”, or
- call it on a throwaway walk that yields the same reference objects the message holds.

`iter_node_dependencies` must include `TEXT_INJECTION_FIELDS` (and locale values) as
`get_references()` sources so a note whose only deps are `${age}` in the label cannot stall
with “no dependencies”.

`label_text_for_name`: first `TriccMessageText` leaf (skip refs), not “first Concatenate static”.

`make_instance` / `copy` of display nodes must copy `TriccMessage` trees (today label is copied
as a shared object unless it is an operation with `copy()`).

`extract_help_title` (`[title]` prefix on help): operate on `message_to_markdown()` / plain
flatten, not `isinstance(..., str)` only.

### 2.8 What stays Concatenate

`TriccOperator.CONCATENATE` remains for **expressions** (calculates, CQL `Concatenate`, XLSForm
`concat()`, string-join in `string_join`). Tests that build Concatenate for calculations are
unchanged. Display-text tests that assert `result.operator == CONCATENATE` switch to
`isinstance(result, TriccMessage)` and inspect leaves.

### 2.9 JS rich-text authoring (interchange, not this delivery)

Most JS editors already persist an AST (or something 1:1 with one). This tree is a **small
subset** of those models, plus one custom inline atom for `${name}`. It should stay that way so a
later authoring UI is a mapper, not a redesign.

| Library | Native document | Fit |
|---------|-----------------|-----|
| **TipTap / ProseMirror** | JSON tree: `doc` → blocks → `text` with **marks on leaves**; mentions as inline atoms | Best default. Map our wrapper `strong` ↔ `marks: ["bold"]` on each leaf; `${dose}` ↔ mention/atom `attrs.name`. |
| **Lexical, Slate / Plate** | Same idea (nodes + marks / properties on text) | Same mapper as ProseMirror, different JSON keys. |
| **Milkdown / remark (mdast)** | Wrapper marks (`strong` / `emphasis`) + `text` — closest to this spec | Easy if the UI is Markdown. Mentions are a custom mdast node (or leftover `${name}` in text until parsed). |
| **Quill** | Linear **Delta** (`insert` + attributes), not a tree | One extra flatten/group step; mentions module exists. Do not make Delta the Python model. |
| **contenteditable / draw.io HTML** | HTML string | Already the input path (`hast`-like parse in §2.5). |

**Do not** copy a full editor schema into Python (headings, code, links, images, selection,
plugin state). Keep the subset we already parse from draw.io.

**Two document shapes, one mechanical conversion:**

```text
this spec (HTML / mdast style)          ProseMirror / TipTap
─────────────────────────────────       ────────────────────────────────
Mark(strong, [                          paragraph:
  Text("Give "),                          text "Give "   marks: [bold]
  Interp("dose"),                         interp name=dose  (marks: [bold])
  Text(" mg")                             text " mg"     marks: [bold]
])
```

Wrapper → marks-on-leaves: push `kind` onto every leaf. Marks-on-leaves → wrapper: group
consecutive leaves that share the same mark set, then wrap (this is also how
`**Give ${dose} mg**` is emitted as **one** Markdown span). Either can be canonical in Python;
the interchange JSON should look like **ProseMirror** (widest editor support) or **mdast**
(if the UI is Markdown-first). Pick one JSON dialect at implementation; do not invent a third.

**Authoring JSON** is the unresolved tree only (`interp.name`, text, marks/blocks). `get_references`
in Python still walks those atoms. YAML fixtures may keep being HTML/Markdown strings; the
editor is not required to write Pydantic objects.

## 3. Code checklist

- [ ] `TriccMessage` (+ node types) with `get_references`, `replace_node`, `copy`
- [ ] `DisplayText` / `label_text_for_name` / test-spec `label_text`
- [ ] HTML parse + `${REF}` split in `text_injection.py` (replace Concatenate builder)
- [ ] Markdown (and optional XHTML) serializers; ODK path uses markdown + `${export}`
- [ ] `process_reference` + `iter_node_dependencies` accept `TriccMessage`
- [ ] FHIR `item.text`: do not call `get_tricc_operation_expression` on a message
- [ ] `extract_help_title`, instance copy
- [ ] Docs: `display-text-injection.md` (intermediate type), `pipeline.md`, `tricc-elements.md`
- [ ] Tests (below)

## 4. Tests

Unit (tree, no full export):

- [ ] `test_plain_string_unchanged` — no tokens, no tags → `str`
- [ ] `test_ref_only` / `test_text_and_ref` — leaves are `TriccReference` + `TriccMessageText`,
      not `TriccOperation`
- [ ] `test_strong_wraps_ref` — `<b>Give ${dose} mg</b>` → one `strong` whose children are
      text + ref + text; markdown is `**Give ${dose} mg**` (or the chosen strong markers),
      not `**Give ` + ref + ` mg**` as separate concatenands
- [ ] `test_html_not_markdownified_before_split` — `${age}` inside `<b>` is still a reference
      (token not destroyed by markdownify)
- [ ] `test_no_space_short_label` — `<b>Yes</b>` becomes strong text, not leftover HTML
      (`remove_html`’s space guard)
- [ ] `test_get_references_walks_marks` — `message.get_references()` includes nested refs
- [ ] `test_replace_node_updates_interp`
- [ ] `test_locale_dict` — `{en: TriccMessage, fr: TriccMessage}`
- [ ] `test_markdown_no_trailing_newline` unless the tree has a break
- [ ] `test_rhombus_label_not_parsed_as_message_ast` — same scope as today (display models only)

Integration:

- [ ] Existing `note_text_injection.yaml` / `tests/test_text_injection.py` updated; ODK label
      still `Patient is ${<export>} years old`
- [ ] Formatted + injection YAML: bold around `${age}` survives XLSForm TRAD as one markdown
      span
- [ ] Processing still waits on the referenced question (stashed-loop / `iter_node_dependencies`)

## 5. Acceptance criteria

1. After input load, no display field is a `TriccOperation`.
2. `${REF}` still resolves through `get_references()` / `process_operation_reference` (versioned
   and repeated names unchanged).
3. A mark that contains both text and a reference serializes to Markdown with a **single**
   balanced wrapper around the whole phrase, including `${export_name}`.
4. HTML from draw.io is parsed to the tree **before** any Markdown conversion.
5. Calculates that use concatenate still export `concat(...)` / CQL concatenate.
6. Existing injection tests pass with the new type.

## 6. Implementation phases

1. Model + `get_references` / `replace_node` / `copy`; `DisplayText` union.
2. Parse + markdown serialize; switch `load_display_text` / `apply_display_text_injections`.
3. Processing + dependencies + instance copy; ODK serialize path.
4. FHIR / other strategies + help-title + `label_text_for_name`.
5. Tests and docs; mark Concatenate-as-message in `display-text-injection.md` superseded by
   this file (authoring section stays).
