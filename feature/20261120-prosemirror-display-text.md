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
| mark | `textStyle` | `color` (CSS colour, validated as today) | `span[style]` holding a valid `color` |

Marks sit on leaves, so empty, split or neighbouring bold cannot exist: the editor model is
normalised by construction. That removes `normalize_message` and its helpers. `img` is kept
only for a `Binary/<id>` source (draw.io's embedded pictures are dropped, as today); other
unknown elements (`font`, `a`, `table`, …) give their text, as in the browser editor.

**Library.** `prosemirror` on PyPI (prosemirror-py, port of `prosemirror-model` /
`prosemirror-transform`; deps `lxml`, `cssselect`). It gives `Schema`, `Node.from_json` /
`to_json`, `DOMParser` (HTML import) and `DOMSerializer` (HTML/XHTML export). It needs
Python ≥ 3.10: `requires-python` moves from `>=3.8` to `>=3.10` (CI already tests 3.10–3.12).

**New package `tricc_oo/text/`:**

- `schema.py` — the schema above (`TEXT_SCHEMA`).
- `parse.py` — every reader returns ProseMirror JSON (`dict`) in canonical form (§1.4):
  - `from_html(raw) -> dict`: draw.io label HTML → lxml → whitespace pre-pass (§1.1) →
    `DOMParser.from_schema(TEXT_SCHEMA).parse(...)` → `${name}` split → typed Markdown (§1.2).
    `from_text(raw)` picks `from_html` for a string holding a tag or an entity, else
    `from_markdown`. A paragraph the import leaves without any content is dropped: it is a
    `div` / `p` wrapping only blocks (`<div><ul>…</ul></div>`) or an empty one, and shows no
    line (a blank line, `<div><br></div>`, still holds its `hardBreak` at that point).
  - `from_markdown(text) -> dict`: `markdown-it-py` (preset `zero` + `list`, `emphasis`,
    `newline`, `image`) with an `interp` inline rule for `${name}`; tokens mapped to nodes and
    marks by a table, the way `prosemirror-markdown`'s `MarkdownParser` does it. Used for YAML
    labels and for typed Markdown.
  - `from_json(data) -> dict`: `Node.from_json(TEXT_SCHEMA, data)`; schema errors are rejected,
    not half-read.
  - `from_message_json(data) -> dict`: reads the old `designation-message` tree (read-only
    compatibility, §1.3).
- `render.py` — all walk the document:
  - Blocks are lines (as draw.io writes a label: one `div` per line, `<div><br></div>` for a
    blank line): each paragraph and each list item starts a line, an empty paragraph is a blank
    line, a `hardBreak` is a line break. Lines inside a list item are indented under its
    marker.
  - `to_plain(doc, interp)`: text, `hardBreak` → `\n`, list items → `• ` / `1. `,
    `interp` → `interp(name)`, `image` → its `alt` or nothing.
  - `to_markdown(doc, interp)`: a small serializer modelled on `prosemirror-markdown`'s
    `defaultMarkdownSerializer` (mark open/close around runs, so `**Give ${dose} mg**` stays one
    span; spaces at a run's edge are emitted outside the markers). `**` bold, `_` italic,
    `- ` / `1. ` items, `![alt](Binary/<id>)`; underline and colour have no Markdown and are
    dropped; text is not escaped (as today).
  - `to_xhtml(doc, interp)`: `DOMSerializer` with the schema's `toDOM` for the inline
    content, wrapped in `<div xmlns="http://www.w3.org/1999/xhtml">`. Lines one after the other
    are one `p` with `<br/>` between them, a blank line starts a new `p` (as today); written as
    XML (`<br/>`, text escaped without quotes).
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
`${dose} mlDiazepam`. The JavaScript parser keeps the space. Cause: `DOMParser._wrap_lxml_text`
turns lxml `text` / `tail` into the `lxmltext` pseudo-nodes the parser reads, but only when they
are not blank, so a blank one is never seen. Until it is fixed upstream, the pre-pass wraps
blank `text` / `tail` the same way; the parser's own whitespace rules (those of the JavaScript
parser) then decide what is kept, so both sides read the same document. Moving the space into
the previous element, as first planned, would put it inside the bold and merge
`<b>…ml</b> <b>Diazepam</b>` into one bold run, which the frontend does not do. The pre-pass also
reads `&nbsp;` as a space (as today). `test_upstream_whitespace_bug_still_present` fails once the
bug is fixed upstream, and the pre-pass can go.

#### 1.2 Typed Markdown

After the HTML import, a paragraph (also one in a list item) whose text holds `*` or `_`, or a
line starting with `-`, `+` or `1.` / `1)`, is re-read with `from_markdown`. Its existing marks
are written as Markdown first (bold `**`, italic `*`), so markers spread over several HTML
elements meet. The re-read result is kept when it holds emphasis or a list; in a list item, only
when it is one paragraph. A paragraph holding a `textStyle` colour or `underline` is not re-read
(Markdown has neither); it keeps its literal text and a warning is logged with the node id.
Neighbouring lists left by re-read lines (`<div>* a</div><div>* b</div>`) are one list (§1.4).
In CommonMark, an intraword `*` is emphasis and `_` is not.

#### 1.4 Canonical form

Every reader ends with `normalize(doc)`, and the shared fixtures hold documents in this form:

- `hardBreak` and `image` carry no marks; neighbouring text nodes with the same marks are one;
  marks are in schema order.
- Line breaks are read as a browser shows them: a run of `hardBreak`s opening a paragraph, or
  a run of two or more inside or closing it, is a blank line (it ends the paragraph and leaves
  one empty paragraph); a single `hardBreak` closing a paragraph shows nothing and is dropped.
  So `</ul><br>Then` and `<div><br>- item</div>` keep the blank line the author sees, and
  `<div>For x<br></div><div>Give</div>` has none. Spaces at a paragraph's edges are dropped.
- Consecutive empty paragraphs are one; none opens or closes the document or sits in a list
  item; an empty document is one empty paragraph.
- Neighbouring lists of the same kind are one list (an ordered one only when its `start`
  continues the first).
- `simplify(doc)`: one paragraph of unmarked text is a plain `str` (`""` when empty).

#### 1.3 Storage and compatibility

- A designation carries the document in a new extension
  `https://tricc.org/StructureDefinition/designation-doc`, `valueString` = compact ProseMirror
  JSON. `value` stays the Markdown (`to_markdown`) for any FHIR reader.
- The old `designation-message` extension is still read (`from_message_json`) and never written.
- `YamlStrategy` reads `designation-doc` first, then `designation-message`, then `value`
  (Markdown, read as a label is: `from_text`) — `concept_display_text` /
  `designation_text` in `converters/datadictionnary.py`. An extension that cannot be read is
  logged with the concept code and `value` is used.
- The hint / help designations `tricc_oo` adds from authored nodes (`add_concept_texts`) carry
  `designation-doc` when the text has structure (`designation_doc_extension`).

### 2. Validation and errors

- `from_json` rejects a document that does not fit the schema (logged with the concept code, the
  designation falls back to `value`).
- Unknown marks or nodes in HTML are dropped by the schema's parse rules (as the browser editor
  does); an `interp` whose name resolves to nothing is reported like a missing `${REF}` today.
- `textStyle.color` keeps the colour check from `isColor` in the frontend.

### 3. Tests

- `tests/text/fixtures/*.json`: shared cases, one per file:
  `{"name", "input": {"html"|"markdown"|"json": …}, "doc", "plain", "markdown", "xhtml"}`
  (input → expected ProseMirror JSON in canonical form → expected plain / Markdown / XHTML;
  an `interp` is `…` in plain and XHTML, `${name}` in Markdown). The same files are copied into the frontend and
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
