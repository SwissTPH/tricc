# tricc-lang changelog

The version in `VERSION` covers the whole folder; it is bumped on any change to any file in it,
an upstream grammar update included.

## 1.0.0 (2026-11-25)

- CQL: upstream HL7 `cql.g4` / `fhirpath.g4` tag `v5.7.0`, untouched; TRICC profile
  `tricc_cql.g4` (entry `triccExpression`, `not in`, `{{placeholders}}`; no retrieve, query,
  union / intersect / except, indexer, member invocation, unit, plural precision).
- `errors.json`: named messages for the constructs outside the profile.
- `functions.json`: the function catalogue (operators, arguments, `reads`, `foldable`), including
  the decision-table calls `DMN`, `DMNFirst`, `DMNList`.
- `meaning.json`: the meaning rules both sides test (references, texts, expression arguments,
  `'text'` ↔ FEEL `"text"`).
- FEEL: upstream KIE `FEEL_1_1.g4` release `10.2.0`, untouched; `tricc_feel.g4` (lexer, with
  `TriccText`), `TriccFeelParser.g4` (decision-table cells), `cells.json`.
