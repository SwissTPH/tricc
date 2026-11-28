# CQL grammar (TRICC profile)

| File          | Origin                                                                                       |
| ------------- | -------------------------------------------------------------------------------------------- |
| `cql.g4`      | HL7 [cqframework/clinical_quality_language](https://github.com/cqframework/clinical_quality_language) tag `v5.7.0`, `grammar/cql.g4` (CQL 1.5). **Untouched.** |
| `fhirpath.g4` | same tag, `grammar/fhirpath.g4`. **Untouched.** (`cql.g4` imports it.)                       |
| `tricc_cql.g4`| TRICC profile: `grammar tricc_cql; import cql;`, whole rules overridden, upstream labels kept. |

Licence of the upstream files: Apache-2.0 (© HL7 International and the cqframework contributors).

sha256 of the upstream files (checked by `tests/test_lang_package.py`):

- `cql.g4` `517d9fa780de80f49a2a3f234e56e4b6dda5f04cb22fe31c89e7ee31811dbba1`
- `fhirpath.g4` `54324384cb009c51379ab0327dbe6dad67a1ee99a6206c8103f74a8359e90627`

## The profile (`tricc_cql.g4`)

| Rule             | Change from upstream                                                                                         |
| ---------------- | ------------------------------------------------------------------------------------------------------------ |
| `triccExpression`| new entry rule: `expression EOF`                                                                             |
| `expression`     | adds `#negateMembershipExpression` (`x not in y`, not standard CQL); drops `#retrieveExpression`, `#queryExpression`, `#inFixSetExpression`, `#durationBetweenExpression`, `#differenceBetweenExpression` |
| `expressionTerm` | drops `#invocationExpressionTerm` (`x.member`, `x.f()`), `#indexedExpressionTerm` (`x[0]`), `#durationExpressionTerm`, `#differenceExpressionTerm` |
| `term`           | adds `PLACEHOLDER #placeholderTerm`                                                                          |
| `literal`        | drops `#quantityLiteral`, `#ratioLiteral` (units)                                                            |
| lexer            | `PLACEHOLDER`: `{{name}}`, `{{name \| raw}}`. `{{x}}` (a list in a list) now lexes as a placeholder.         |

A construct removed by the profile is reported with the message of `../errors.json`.

## Generated parsers

`scripts/generate-lang-parsers.sh` (ANTLR 4.13.2, Java) writes the Python parsers into
`tricc_oo/converters/cql/`: `tricc_cql*` for expressions, `cql*` (untouched upstream) for
project libraries in standard CQL. They are committed; `--check` fails on drift. The frontend
generates TypeScript from a pinned copy of this folder with the same ANTLR version.

Updating upstream: replace `cql.g4` / `fhirpath.g4` with the new tag's files, update the tag
and sha256 above, bump `../VERSION`, regenerate, run the tests (`meaning.json`, overrides).
