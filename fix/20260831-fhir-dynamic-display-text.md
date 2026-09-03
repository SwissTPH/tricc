# FHIR display text injection (`${REF}`) renders the expression source — Fix Specification

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `feature/segment` / `develop` |
| **Related** | `feature/display-text-injection.md` (authoring syntax), `fix/20260824-fhirpath-nested-item-path.md`, `docs/open-srp-export.md` |
| **Affected strategies** | `FHIRStrategy`, `OpenSRPStrategy` |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## Symptom

A note (or any display text) authored as

```text
Patient is ${age} years old
```

is exported to the Questionnaire as

```json
{ "linkId": "note_age", "text": "'Patient is ' + age + ' years old'", "type": "display" }
```

and the openSRP / FHIR-Core app shows the raw text **`'Patient is ' + age + ' years old'`** on screen
instead of `Patient is 21 years old`.

Reproduced with:

```bash
python tests/build.py -i tests/data/yaml/note_text_injection.yaml -o out/ -I YamlStrategy -O FHIRStrategy
```

Real exports are affected too — `tests/output/cohort_fup/questionnaire/Questionnaire-questionnaire-registration.json`
currently contains five such items, e.g.
`"text": "'You selected the following relationship status: ' + marstat_l + '. Please verify your selection'"`.

## Who is affected

Every author who uses the documented `${REF}` injection syntax
(`feature/display-text-injection.md`) on a node exported to FHIR: notes, question labels,
hint and help messages. ODK/CHT are **not** affected — they re-serialize the injection to
`${export_name}`, which the ODK engine substitutes at display time.

## Expected vs actual

| | Questionnaire item |
|---|---|
| **Expected** | `text` holds readable fallback copy, and the item carries a **dynamic-text expression** the renderer evaluates against the in-progress QuestionnaireResponse, so the user sees `Patient is 21 years old` |
| **Actual** | `text` holds a CQL expression string; nothing dynamic is emitted; the app prints the expression verbatim |

## Out of scope

- ODK/CHT/DHIS2/OpenMRS text injection (already correct).
- Full expression tokens in text (`${age + 1}`) — the authoring syntax stays "bare field name",
  per `feature/display-text-injection.md`.
- `constraint_message` / `required_message` — these are not rendered from `Questionnaire.item.text`;
  dynamic validation messages are tracked separately.
- Questionnaire `title` injection.

---

# Part II — Fix approach

## Root cause

`tricc_oo/strategies/output/fhir_form.py`:

- `_build_questionnaire_item` (line ~605, carrying a `# FIXME, does not work like this` comment)
  renders a `TriccOperation` label through **`get_tricc_operation_expression`** — the **CQL**
  serializer — and assigns the resulting string straight to `item["text"]`.
  `tricc_operation_concatenate` (line ~2222) joins operands with `" + "`, hence the `+` the user sees.
- `_questionnaire_item_text` (line ~690) does the same for `help` / `hint`, whose text ends up in the
  nested `help` / `flyover` display items built by `build_item_control_display_item`.

Two defects: the wrong expression flavour (CQL, not FHIRPath), and — the real one — **no dynamic-text
extension is ever emitted**, so an expression can only ever be shown as literal text.

## Target emission

openSRP/FHIR-Core renders with the Android FHIR Data Capture library, which supports dynamic item
text through **`cqf-expression` on the `text` element** (`Questionnaire.item._text`):

- `QuestionnaireViewModel` evaluates `questionnaireItem.textElement.cqfExpression` and writes the
  result into `QuestionnaireResponse.item.text`;
- `QuestionnaireViewItem.questionText` prefers that value over the static `item.text`;
- `ExpressionEvaluator.evaluateExpressionValue` **throws unless the language is `text/fhirpath`**,
  takes `singleOrNull()` and calls `.primitiveValue()` — so the expression must yield exactly one
  primitive value;
- the evaluation context is the same one already used for `enableWhenExpression` /
  `calculatedExpression`: `%resource` = the in-progress QuestionnaireResponse.

Emitted shape:

```json
{
  "linkId": "note_age",
  "type": "display",
  "text": "Patient is ${age} years old",
  "_text": {
    "extension": [
      {
        "url": "http://hl7.org/fhir/StructureDefinition/cqf-expression",
        "valueExpression": {
          "language": "text/fhirpath",
          "expression": "'Patient is ' & %resource.item.where(linkId='age').answer.where($this.exists()).value.toString() & ' years old'"
        }
      }
    ]
  }
}
```

## Emission rules

1. **Trigger** — only when a display-text field (`label`, `hint`, `help`) is a `TriccOperation`.
   Plain strings keep today's behaviour, byte for byte.
2. **Expression flavour** — FHIRPath only, via `get_tricc_operation_expression_fhirpath`.
   `tricc_operation_fhirpath_concatenate` already joins with `&` (correct: `&` yields `''` for an
   empty operand, so an unanswered question renders `Patient is  years old`, not an error).
   If a text operation cannot be expressed in FHIRPath (an operator that raises
   `NotImplementedError`), log an error, emit the static fallback only, and continue — never fall
   back to the CQL serializer for text.
3. **String coercion** — `&` operands must be strings. A new `_fhirpath_string_parts()` helper
   (mirroring `_fhirpath_numeric_parts`) appends `.toString()` to every operand that is not already
   a string literal or a `.display` access.
4. **Reference rendering inside text**:
   - non-choice reference → `…answer.where($this.exists()).value.toString()` (existing
     `_wrap_operand_if_needed` / `_answer_value_suffix` machinery);
   - choice reference (`select_one` / `select_yesno`) → `…answer.where($this.exists()).value.display`,
     i.e. the option label, not the code. `_answer_option_coding` always sets `display`, so this
     resolves for both CodeSystem-backed and inline options. `_answer_value_suffix` gains a
     `for_text` mode; its existing `.value.code` behaviour for logic contexts is unchanged.
   - `select_multiple` in text is unsupported (a multi-answer collection breaks `singleOrNull`) —
     log a warning and emit the static fallback only.
5. **Static fallback `text`** — static segments verbatim, each reference rendered as
   `${<export_name>}` (the authoring token, produced by the existing
   `serialize_injection_for_js_text`). Renderers without `cqf-expression` support then show a
   recognisable placeholder rather than code. *(Decided: option A, see below.)*
6. **Hidden items** — hidden / internal calculate items keep `_sanitize_hidden_item_text` and get
   **no** `_text` extension (nothing is rendered, and an extra expression is dead weight for the
   renderer).
7. **help / flyover children** — `build_item_control_display_item` takes an optional
   `text_expression` and emits the same `_text` block, so `${}` works in hint and help too.
8. **One extension per element** — `_text.extension` carries at most one `cqf-expression`, matching
   the singleton rule in `fix/20260821-sdc-singleton-expressions.md`.
9. **Deferred resolution** — text operations are collected during `process_base` and serialized in a
   dedicated `process_display_text()` pass after `process_calculate`. Only then does every
   Questionnaire item exist, so references resolve to nested
   `%resource.item.where(linkId=…).item.where(linkId=…)` paths instead of the `repeat(item)`
   fallback. The pass runs **before** `_prune_unused_hidden_calculates`, and
   `_collect_expression_link_ids` also scans `_text`, so a calculate displayed only inside a note's
   text is not pruned as unused.

## Code checklist

- [x] `tricc_oo/converters/fhir/questionnaire_item_mapper.py`
      — `CQF_EXT_TEXT_EXPRESSION` constant, `build_text_expression_extension(fhirpath)` and
        `set_item_text_expression(item, fhirpath)` (singleton-safe).
- [x] `tricc_oo/strategies/output/fhir_form.py`
      — `_display_text_and_operation()` (static text + dynamic operation) used by
        `_build_questionnaire_item` (replacing the `# FIXME` block) and by
        `_questionnaire_item_text` / `_attach_help_hint_items`;
      — `_pending_text_expressions` + `process_display_text()` pass, wired into `execute()` after
        `process_calculate`;
      — `_display_text_fhirpath()`, `_text_reference_link_ids()`, `_operand_link_id()`;
      — `_fhirpath_string_parts()` / `_fhirpath_as_string()` and the `_in_display_text` flag on
        `_answer_value_suffix` (`.value.display` for choices);
      — `_collect_expression_link_ids` also scans `_text` extensions.
- [x] `tricc_oo/converters/fhir/fsh_serializer.py` — render `_text` extensions under
      `<item>.text`.
- [x] `tricc_oo/visitors/text_injection.py` — reused `serialize_injection_for_js_text` for the
      static fallback (no change to the module, no behaviour change for ODK).
- [x] `docs/open-srp-export.md` — dynamic display text documented alongside
      `enableWhenExpression` / `calculatedExpression`.

## Tests

`tests/test_strategies/test_fhir_display_text_expression.py` (new) with fixture
`tests/data/yaml/display_text_injection.yaml` (new):

1. [x] Note label `Patient is ${age} years old` → `item["text"] == "Patient is ${age} years old"`
   and one `cqf-expression` on `_text` with `language == "text/fhirpath"`, containing `&`, the
   `linkId='age'` path and no `" + "`.
2. [x] An integer reference is cast: the operand ends in `.value).toString()`.
3. [x] A `select_one` reference renders `.value.display`, never `.value.code`.
4. [x] Hint / help injection produces `_text` on the nested `flyover` / `help` display items.
5. [x] Hidden calculate items get no `_text`.
6. [x] A plain (non-injected) label emits `text` only, with no `_text` key.
7. [x] `_collect_expression_link_ids` sees `_text` references, so the pruner keeps them.
8. [x] Full-pipeline YAML walk asserts the same on a processed project.

## Acceptance criteria

1. No exported Questionnaire `text` value contains a serialized expression
   (grep for `'…' + ` over `tests/output/**/Questionnaire-*.json` returns nothing).
2. `Patient is ${age} years old` displays as `Patient is 21 years old` in openSRP once `age` is answered.
3. Unanswered references render as empty, never as an error or as the expression source.
4. `python -m pytest tests/` passes; `flake8 tricc_oo` clean.

## Static fallback decision (settled)

**Option A** — `text` keeps the author's tokens: `Patient is ${age} years old`. Author-recognisable,
and a renderer without `cqf-expression` support shows a clear placeholder rather than a blank gap
(option B) or a second syntax to learn (option C, `{{age}}`).

## Verification

`tests/data/yaml/display_text_injection.yaml` exports:

```json
"text": "Patient is ${age} years old and ${sex}",
"_text": { "extension": [ { "url": "http://hl7.org/fhir/StructureDefinition/cqf-expression",
  "valueExpression": { "language": "text/fhirpath", "expression":
    "'Patient is ' & (%resource.item.where(linkId='start_dti').item.where(linkId='age').answer.where($this.exists()).value).toString() & ' years old and ' & %resource.item.where(linkId='start_dti').item.where(linkId='sex').answer.where($this.exists()).value.display" } } ] }
```

Evaluated with an R4-model FHIRPath engine against a QuestionnaireResponse holding
`age = 21` / `sex = male (Male)`:

- answered → `Patient is 21 years old and Male`
- unanswered → `Patient is  years old and ` (no error, no expression source)
