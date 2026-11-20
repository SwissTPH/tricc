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
- Translations carry plain text only; there is no translated formatted label.

---

## Part II — Fix

### Rules (`tricc_oo/converters/fhir/text_format.py`)

- `tidy_markdown` repairs the strong emphasis `markdownify` breaks on draw.io labels: empty
  pairs (`**H****erpes**`), spaces inside the marker (`**VITAMIN **A`), a pair closed on the
  next line (`**HIV exposed:\n**`), lines holding only `**`. Runs of blank lines collapse.
- `markdown_to_plain`: emphasis, links, images, headings and escapes dropped, bullets `•`,
  line breaks kept, `${name}` → `…` (`PLACEHOLDER_STAND_IN`).
- `markdown_to_xhtml`: `<div xmlns="http://www.w3.org/1999/xhtml">` with `p`, `ul`/`ol`/`li`,
  `strong`, `em`, `a`, `br`; text escaped; `${name}` → `…`.
- `set_text_rendering(element, field, label, text_format)` puts
  `rendering-markdown` (`valueMarkdown`, tidied, placeholders neutralised) or
  `rendering-xhtml` (`valueString`) first on `element._<field>.extension`, replacing an
  earlier rendering extension and keeping `translation` / `cqf-expression`. Nothing is
  written when the label already equals the plain value.

### Strategy (`tricc_oo/strategies/output/fhir_form.py`)

- `FHIRStrategy(..., text_format="markdown" | "html")`, default `"markdown"`; any other value
  raises `ValueError`. `OpenSRPStrategy` forwards it.
- `_plain_text(node, use, label)`: `concept_text(node_concept, use, lang_code)` when the
  concept has that text, else the label; then `markdown_to_plain`.
- `generate_base`: `item.text` = `_plain_text(node, "display", label)` (hidden items keep
  their sanitised name), `set_text_rendering(item, "text", label)`; the Questionnaire
  `title` is plain.
- `_attach_help_hint_items`: the same for the `help` / `flyover` display children.
- `_answer_option_coding`: `display` plain (concept display, else option label); the
  answerOption coding also gets `set_text_rendering(coding, "display", option label)`. The
  `answerOptionsToggleExpression` codings stay without it.
- `_concept_translations`: translation texts are plain.
- `cqf-expression` on `_text` is attached as before (`set_item_text_expression` keeps the
  other extensions).

### Tests

`tests/test_strategies/test_fhir_text_format.py`: conversion (plain, XHTML, tidy cases from
Global Almanach, snake_case and `3*4` kept), item / help / hint / option text, concept
display wins, no extension for a plain label, `html` format, `cqf-expression` kept next to
the rendering extension, invalid `text_format`, OpenSRP forwarding.
`tests/test_strategies/test_fhir_display_text_expression.py`: the static text of a `${REF}`
label now reads `…` instead of `${name}`.

### Acceptance

Global Almanach child package (`L2/child` + `L2/common`, `OpenSRPStrategy`): no `**`, `${`
or triple newline in any `text`, title or option `display`; every formatted label in a
`rendering-markdown` extension; 77 `cqf-expression`s unchanged.

## Open questions

1. Placeholder in static text: `…` (chosen) vs empty. Recommendation: keep `…`, it shows
   where the value goes until clients evaluate the expression.

## Decisions

- 2026-11-20: `text` = concept display (plain), formatted label in `rendering-markdown` or
  `rendering-xhtml` on `_text`, selected by a strategy parameter, default markdown; applies
  to item text, prefix, help/instructions and answer options; `cqf-expression` kept as is.
  (@delcroip, relayed)
