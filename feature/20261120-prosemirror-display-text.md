# Display text as ProseMirror documents

| Field             | Value |
| ----------------- | ----- |
| **Status**        | Approved (2026-11-20, in conversation) |
| **Branch target** | `feature/prosemirror-display-text` → `develop` (stacked on `fix/89-fhir-text-format`, PR #94) |
| **Scope**         | `models`, `converters/xml_to_tricc`, `DrawioStrategy`, `YamlStrategy`, `XLSFormStrategy` → `XLSFormCHTStrategy`, `FHIRStrategy` → `OpenSRPStrategy` |
| **Related**       | `feature/20260909-display-message-ast.md` (the tree this replaces; §2.9 already named ProseMirror as the interchange to pick). `feature/20261008-concept-texts-q-display-and-message-tree.md` (the `designation-message` extension, superseded here). `fix/20261120-fhir-text-format.md` (#89 / PR #94: the renderers move onto this model). Frontend mirror: `tricc-frontend/feature/20261120-prosemirror-display-text.md`. |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

### The problem

Formatted texts (bold, italic, lists, colours, pictures, live values such as `${dose}`) are kept
in a tree format of our own. Both the app and the converter have their own copy of that format,
and the same reading, cleaning and writing rules are written twice by hand. Each copy carries
repair rules for awkward formatting, such as a bold word split in two or a space inside the bold.
Each new formatting problem means fixing both copies, and they have drifted before.

### What changes for an author

- Nothing in how texts are written, in draw.io or in the app. Bold, italic, underline, colour,
  lists, pictures and `${name}` keep working.
- Markdown typed into a draw.io label (`**bold**`, `* item`) keeps being read as formatting.
- Forms, CHT apps and FHIR questionnaires show the same text as today. Small differences in
  spacing may appear where the old rules were wrong.
- Projects saved by an older app version still open; they are converted when read.

### Out of scope

- New formatting (headings, links, tables).
- The live text expression (`cqf-expression`) still carries Markdown (separate ticket, see #94).
- Changing how `${name}` is written by authors.

---

## Part II — Technical specification

### 1. Design

**One document model: ProseMirror JSON, TipTap names.** The app's editor (TipTap) already
holds this; it is stored as is. Schema (shared with the frontend, same names and attributes):

| Kind | Name | Content / attributes | HTML (`toDOM` / `parseDOM`) |
| ---- | ---- | -------------------- | --------------------------- |
| node | `doc` | `block+` | — |
| node | `paragraph` | `inline*` | `p` (parse also `div`) |
| node | `bulletList` / `orderedList` | `listItem+`; ordered: `start` | `ul` / `ol` |
| node | `listItem` | `paragraph block*` | `li` |
| node | `text` | inline | — |
| node | `hardBreak` | inline leaf | `br` |
| node | `image` | inline leaf; `src` (`Binary/<id>`), `alt` | `img` |
| node | `interp` | inline atom; `name` | `span[data-interp]` |
| mark | `bold` / `italic` / `underline` | — | `strong`,`b` / `em`,`i` / `u` |
| mark | `textStyle` | `color` (CSS colour, validated as today) | `span[style*=color]` |

Marks sit on leaves, so empty, split or neighbouring bold cannot exist: the editor model is
normalised by construction. That removes `normalize_message` and its helpers.

**Library.** `prosemirror` on PyPI (prosemirror-py, port of `prosemirror-model` /
`prosemirror-transform`; deps `lxml`, `cssselect`). It gives `Schema`, `Node.from_json` /
`to_json`, `DOMParser` (HTML import) and `DOMSerializer` (HTML/XHTML export). It needs
Python ≥ 3.10: `requires-python` moves from `>=3.8` to `>=3.10` (CI already tests 3.10–3.12).

**New package `tricc_oo/text/`:**

- `schema.py` — the schema above (`TEXT_SCHEMA`).
- `parse.py`
  - `from_html(raw) -> Node`: draw.io label HTML → lxml → whitespace pre-pass (§1.1) →
    `DOMParser.from_schema(TEXT_SCHEMA).parse(...)` → `${name}` split → typed Markdown (§1.2).
  - `from_markdown(text) -> Node`: `markdown-it-py` (preset `zero` + `list`, `emphasis`,
    `newline`, `image`) with an `interp` inline rule for `${name}`; tokens mapped to nodes and
    marks by a table, the way `prosemirror-markdown`'s `MarkdownParser` does it. Used for YAML
    labels and for typed Markdown.
  - `from_json(data) -> Node`: `Node.from_json(TEXT_SCHEMA, data)`; schema errors are rejected,
    not half-read.
  - `from_message_json(data) -> Node`: reads the old `designation-message` tree (read-only
    compatibility, §1.3).
- `render.py` — all walk the document:
  - `to_plain(doc, reference_text)`: text, `hardBreak` → `\n`, paragraphs → blank line,
    list items → `• ` / `1. `, `interp` → `reference_text`, `image` → its `alt` or nothing.
  - `to_markdown(doc, interp)`: a small serializer modelled on `prosemirror-markdown`'s
    `defaultMarkdownSerializer` (mark open/close around runs, so `**Give ${dose} mg**` stays one
    span; spaces at a run's edge are emitted outside the markers).
  - `to_xhtml(doc, interp)`: `DOMSerializer` with the schema's `toDOM`, wrapped in
    `<div xmlns="http://www.w3.org/1999/xhtml">`.
  - `references(doc) -> list[str]` and `to_concatenate(doc, resolve) -> TriccOperation`
    (dynamic text for CQL / XLSForm, same output as today's `message_to_concatenate_operation`).
- `model.py` — `TriccText` (Pydantic) replaces the `TriccMessage*` classes:
  `doc: dict` (ProseMirror JSON) plus `refs: dict[str, Any]` (name → `TriccReference` or the
  resolved node). `get_references`, `replace_node` and `copy` work on `refs`, so the pipeline
  (`visitors/tricc.py`, `models/base.py`) keeps its contract. A text without structure stays a
  plain `str`, as `_simplify_message` does today.

**Call sites.** `visitors/text_injection.py` keeps its public names
(`load_display_text`, `serialize_injection_for_js_text`, `serialize_injection_plain`,
`serialize_injection_markdown`, `serialize_injection_xhtml`, `message_to_concatenate_operation`)
as thin wrappers over `tricc_oo/text/`, so `xml_to_tricc.py`, `serializers/xls_form.py`,
`strategies/output/fhir_form.py` and `strategies/test/test_spec.py` change only their imports.
`models/message.py` is deleted at the end (phase 4).

#### 1.1 Whitespace pre-pass (prosemirror-py)

Spike (2026-11-20, prosemirror 0.6.1): the Python `DOMParser` drops whitespace-only text between
two inline elements, even with `preserve_whitespace`: `<b>${dose} ml</b> <b>Diazepam</b>` reads
`${dose} mlDiazepam`. The JavaScript parser keeps the space. Until it is fixed upstream, the
pre-pass moves a whitespace-only `tail` between two inline elements to the end of the previous
element's text (collapsed to one space). File the bug upstream with the reproduction; keep a
fixture test so the pre-pass can be removed when it is fixed.

#### 1.2 Typed Markdown

After the HTML import, a paragraph whose text contains Markdown markers is re-read with
`from_markdown`. Its existing marks are written as Markdown first (`to_markdown`), so markers
spread over several HTML elements meet. A paragraph holding a `textStyle` colour is not re-read
(Markdown has no colour); it keeps its literal text and a warning is logged with the node id.
In CommonMark, an intraword `*` is emphasis and `_` is not.

#### 1.3 Storage and compatibility

- A designation carries the document in a new extension
  `https://tricc.org/StructureDefinition/designation-doc`, `valueString` = compact ProseMirror
  JSON. `value` stays the Markdown (`to_markdown`) for any FHIR reader.
- The old `designation-message` extension is still read (`from_message_json`) and never written.
- `YamlStrategy` reads `designation-doc` first, then `designation-message`, then `value`
  (Markdown, via `from_markdown`).

### 2. Validation and errors

- `from_json` rejects a document that does not fit the schema (logged with the concept code, the
  designation falls back to `value`).
- Unknown marks or nodes in HTML are dropped by the schema's parse rules (as the browser editor
  does); an `interp` whose name resolves to nothing is reported like a missing `${REF}` today.
- `textStyle.color` keeps the colour check from `isColor` in the frontend.

### 3. Tests

- `tests/text/fixtures/*.json`: shared cases (input HTML or Markdown → expected ProseMirror
  JSON → expected plain / Markdown / XHTML). The same files are copied into the frontend and
  run there (`packages/core/src/text/fixtures/`); a script `scripts/sync-text-fixtures.sh` copies them.
- Cases: the #94 set (`<b>VITAMIN </b>A`, `<b>HIV exposed:<br></b>`, `<b>H</b><b>erpes</b>`,
  `<b>a</b> <b>b</b>`, `${` split over spans, typed `**…**` and `* item`, markers in separate
  `<b>`s, the convulsion note), lists, colour, images, `${name}` inside bold.
- `designation-doc` round trip; `designation-message` read compatibility; `value` fallback.
- The existing display-text, XLSForm, CHT and FHIR tests stay green with unchanged expectations,
  except the documented spacing fixes.
- Global child export check from #94: 0 `**`, `* ` bullets, `${`, triple newlines.

### 4. Phases

1. `tricc_oo/text/` (schema, parse, render, `TriccText`), the shared fixtures, the whitespace
   pre-pass; `requires-python >=3.10`, dependency `prosemirror`.
2. Switch `text_injection.py` wrappers and the call sites; draw.io and YAML labels load as
   `TriccText`; all outputs render from it.
3. `YamlStrategy` reads `designation-doc` / `designation-message` / `value`.
4. Delete `models/message.py` and the old helpers; docs (`docs/pipeline.md`, `docs/open-srp-export.md`).

---

## Open questions

None open; see Decisions.

## Decisions

- 2026-11-20: ProseMirror JSON with TipTap names is the shared format; the old tree is read only for compatibility. (Patrick, in conversation)
- 2026-11-20: Python uses prosemirror-py; HTML import goes through its `DOMParser`, typed Markdown and YAML through `markdown-it-py`. (Patrick, in conversation)
- 2026-11-20: Python floor raised to 3.10 (prosemirror-py requires it; CI already starts at 3.10).
- 2026-11-20: new extension URL `designation-doc`; `designation-message` read, never written.
