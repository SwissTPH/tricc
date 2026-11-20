# FHIR output: plain `text`, the formatted label in a rendering extension

| Field | Value |
|-------|-------|
| **Status** | Approved (2026-11-20, in conversation; decisions relayed from the fhir-workplace session) |
| **Branch target** | `develop` |
| **Scope** | `FHIRStrategy` → `OpenSRPStrategy` (Questionnaire text) |
| **Related** | `fix/20260831-fhir-dynamic-display-text.md` (`cqf-expression` on `_text`), #85 (diazepam dose dropped) |
| **Issue** | SwissTPH/tricc#89 |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Issue analysis

### Symptoms

Labels are authored as formatted text and arrive in the FHIR export as Markdown. The export
copied that Markdown into the question text, which FHIR defines as plain text. A form client
that shows plain text (the kotlin-fhir-data-capture web client) printed the `**` and `*`
marks, runs of empty lines and `${diazepam_dose}`-style placeholders. Example: the
convulsion treatment note of the Global Almanach registration form.

### Who is affected

Everyone using a FHIR / openSRP package in a client that does not guess Markdown.

### Expected vs actual

| | Before | After |
|---|---|---|
| Question, note, help and hint text | the label's Markdown, placeholders included | plain text: the data dictionary wording when there is one, else the label, without formatting; a placeholder shows as `…` |
| Formatted label | nowhere else | next to the plain text, as Markdown (default) or XHTML |
| Answer option text | the label's Markdown | plain text, formatted label next to it |
| Dynamic text (`${…}`) | live expression, as before | unchanged (still not evaluated by the clients we know) |

### Out of scope

- The live expression of dynamic text still yields the label's Markdown; making it yield
  plain text, or a formatted live text, is tracked separately.
- `prefix`: the export writes none today. The helper applies to it when it does.
- Translations carry the data dictionary text as it is; there is no translated formatted label.
- Markdown typed by the author into a label (`**bold**`, `* item`) is text, not formatting:
  it is kept as typed in every output (see Open questions 2).

---

## Part II — Fix

### Display-text tree (`tricc_oo/visitors/text_injection.py`)

Labels are parsed from the source HTML into a `TriccMessage` tree at load
(`parse_html_to_message`, `feature/20260909-display-message-ast.md`). The broken bold of
the issue came from wrapping marks as they were authored: `<b>VITAMIN </b>A`,
`<b>HIV exposed:<br></b>`, `<b>H</b><b>erpes</b>`.

- `normalize_message`, run once in `parse_html_to_message` before `_simplify_message`:
  empty marks dropped; neighbouring marks of the same kind merged; spaces and
  `TriccMessageBreak` at a mark's edges moved outside it; runs of line breaks capped at
  `MAX_CONSECUTIVE_BREAKS` (2); line breaks opening or closing the message or a list item
  dropped (`<li>…<br><br></li>`). This changes the Markdown of every output (CHT / XLSForm
  too).
- `_parse_html_node` keeps a whitespace-only string between two inline elements as one
  space (`<b>a</b> <b>b</b>`); before, it was dropped and the words were glued.
- `_parse_html_children` looks for `${name}` again once neighbouring text is merged: a token
  split over inline elements (`<span>${</span><span>ors_planb_drops}</span>`) was text, so it
  had no live expression and showed as typed in every output.
- Three renderers walk the same tree:
  - `serialize_injection_markdown(value, reference_text)`: `_markdown_node`, the existing
    Markdown renderer (`serialize_injection_for_js_text` uses it with `${name}` tokens);
  - `serialize_injection_plain(value, reference_text)`: text only, line breaks kept, list
    items `• ` / `1. `;
  - `serialize_injection_xhtml(value, reference_text)`: `<div xmlns="http://www.w3.org/1999/xhtml">`;
    two or more line breaks separate `p` blocks, one is `br`; lists `ul` / `ol` / `li`;
    marks `strong` / `em` / `u`; text escaped by construction.
- A label without formatting stays a plain string: plain = Markdown = the string.

### FHIR text (`tricc_oo/converters/fhir/text_format.py`)

Extension constants, `REFERENCE_STAND_IN` (`…`), `plain_text(value)` and
`set_text_rendering(element, field, value, text_format)`: puts `rendering-markdown`
(`valueMarkdown`) or `rendering-xhtml` (`valueString`) first on
`element._<field>.extension`, replacing an earlier rendering extension and keeping
`translation` / `cqf-expression`. Nothing is written when the Markdown rendering equals the
plain value already in `element[field]`. No Markdown parsing.

### Strategy (`tricc_oo/strategies/output/fhir_form.py`)

- `FHIRStrategy(..., text_format="markdown" | "html")`, default `"markdown"`; any other value
  raises `ValueError`. `OpenSRPStrategy` forwards it.
- `_display_value(value)`: the tree or string to render (a node's label, the first
  non-empty locale; a non-`${REF}` operation gives its static text).
- `_plain_text(node, use, value)`: the concept's `use` text in the default language when it
  is the data dictionary's own wording, else `plain_text` of the tree. At load the concept
  display is filled with the label's Markdown (`check_and_add_concept`), so a concept text
  equal to `serialize_injection_for_js_text(label)` is not used
  (`_data_dictionary_text`).
- `generate_base`: `item.text` = `_plain_text(node, "display", label)` (hidden items keep
  their sanitised name), `set_text_rendering(item, "text", label)`; the Questionnaire
  `title` is plain.
- `_attach_help_hint_items`: the same for the `help` / `flyover` display children.
- `_answer_option_coding`: `display` plain (curated concept display, else the option
  label); the answerOption coding also gets `set_text_rendering(coding, "display", label)`.
  The `answerOptionsToggleExpression` codings stay without it.
- `cqf-expression` on `_text` is attached as before.

### Tests

- `tests/test_strategies/test_fhir_text_format.py`: normalisation of the Global Almanach
  HTML cases; plain and XHTML renderers; item / help / hint / option text from HTML-built
  labels; curated concept display wins, a concept display filled from the label does not;
  no extension for a plain label; `html` format; `cqf-expression` next to the rendering
  extension; invalid `text_format`; OpenSRP forwarding.
- `tests/test_strategies/test_fhir_display_text_expression.py`: the static text of a
  `${REF}` label reads `…` instead of `${name}`.

### Acceptance

Global Almanach child package (`L2/child` + `L2/common`, `OpenSRPStrategy`): no `${`
placeholder in any `text`, title or option `display`; formatting authored with the editor
(bold, italic, lists, line breaks) is gone from `text` and is in a `rendering-markdown`
extension; no run of more than one blank line; the 77 `cqf-expression`s are kept and 7
more come from tokens split over inline elements (84).

Not met while Open question 2 is open: 137 texts of that package keep `**` (and `* `
bullets) that the authors typed as Markdown into the labels, e.g. the convulsion note
(`<div>**IF THE CHILD IS CONVULSING NOW - TREAT IMMEDIATELY**</div><div>* Turn …</div>`).

## Open questions

1. Placeholder in static text: `…` (chosen) vs empty. Recommendation: keep `…`, it shows
   where the value goes until clients evaluate the expression.
2. Markdown typed into labels. The Global Almanach draw.io files hold it in most formatted
   labels, also split across HTML elements (`**<span>${</span><span>ors_planb_drops} ml
   </span>ORS**`). Without a parser it stays text. Recommendation: parse it at load with
   `markdown-it-py` (new dependency): render the tree's text to Markdown with references as
   placeholders, parse, and rebuild marks and lists in the tree, so every output gets it.
   Needs @delcroip's OK for the dependency.

## Decisions

- 2026-11-20: `text` = concept display (plain), formatted label in `rendering-markdown` or
  `rendering-xhtml` on `_text`, selected by a strategy parameter, default markdown; applies
  to item text, prefix, help/instructions and answer options; `cqf-expression` kept as is.
  (@delcroip, relayed)
- 2026-11-20: render the display-text tree (plain, Markdown, XHTML), normalised once at
  load; no Markdown regexes. A Markdown parser only with an OK for the dependency.
  (@delcroip, relayed)
