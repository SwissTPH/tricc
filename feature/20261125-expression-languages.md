# Shared TRICC expression languages: CQL and FEEL grammars, function catalogue

| Field             | Value                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Status**        | Approved (2026-11-25, RFC #98) |
| **Branch target** | `feature/lang-and-capabilities` → `develop`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| **Scope**         | new package folder `tricc_oo/lang/`; `parsers` (`tricc_oo/converters/cql/`, `converters/cql_to_operation.py`, `converters/cql_library.py`), `models` (`models/params.py`), `visitors/constant_eval.py`, decision tables (#91); frontend consumer: `@tricc/core`, `@tricc/editor`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| **Related**       | Upstream HL7 grammar: cqframework/clinical_quality_language tag `v5.7.0`, `grammar/cql.g4` + `grammar/fhirpath.g4` (CQL 1.5, Apache-2.0). Upstream FEEL lexer: apache/incubator-kie-drools release `10.2.0`, `kie-dmn/kie-dmn-feel/src/main/antlr4/org/kie/dmn/feel/parser/feel11/FEEL_1_1.g4` (Apache-2.0). SwissTPH/tricc-frontend#52 (block arguments as CQL text; its token-level rule is replaced by this parser). Mirror into `tricc-frontend/feature/` on approval (pinned copy, generated TypeScript parser, validation, `isExpressionArg`, decision-table cells). `feature/20261111-block-params-and-start-node.md` §18.5, §18.8 (stored-data functions, expression arguments). `feature/20261119-python-constant-eval.md` (folding; `foldable` in the catalogue). SwissTPH/tricc#85 / #91 / #96 (decision tables: `DMN`, `DMNFirst`, `DMNList`, the FEEL cell subset). tricc-frontend `feature/20260825-cql-authoring.md` (the editor's CQL profile), `feature/20261120-decision-table-editor.md` (cells, DMN interchange). |
| **RFC**           | SwissTPH/tricc#98 |

---

## Part I — Business description

### The problem

An author writes CQL in the editor and decision-table cells in a small part of FEEL; tricc_oo
builds both into a form. The two sides don't read them the same way:

- tricc_oo parses CQL with a full grammar. The editor only splits it into words and guesses, so
  it accepts text the build rejects and can't tell reliably whether a block argument is
  calculated or a fixed text (tricc-frontend#52).
- The functions an author may call live in two places in tricc_oo (a code table and a JSON list
  of functions that read stored data). The editor has its own idea of them.
- Some constructs the build means to refuse (unions, indexers, some date precisions) are not
  refused at all today: they pass through unchecked.
- Decision-table cells are parsed by hand on each side, kept in step by a test file copied
  between the repos with the note "keep both copies identical".

So a project can look valid in the editor and fail, or silently mean something else, at build.

### What changes for an author

- The editor checks CQL with the same rules as the build: an expression that won't build is
  flagged while it is typed, with a message naming the construct ("a query is not supported in a
  form; read that data with a prefilled value").
- The function list, its arguments and what each one reads (patient, encounter, history) are the
  same in the editor's suggestions, its checks and the build. Decision-table calls are in it.
- Whether a block argument is calculated or fixed is decided by a real parse, the same on both
  sides.
- Decision-table cells are checked by the same FEEL grammar in the editor and in the build.
- A few constructs accepted by mistake today become errors. If an existing project uses them,
  the build warns for one release before refusing them; the editor refuses them in new edits.
- A project CQL library is standard CQL unless it says otherwise: it may declare that it uses
  TRICC's dialect.

### Out of scope

- New CQL or FEEL features or functions. This RFC moves what exists into a shared form.
- FEEL beyond decision-table cells (free FEEL expressions, boxed expressions, importing any DMN file): the grammar is built so it can grow, but only the cell subset is in.
- Live highlighting in the editor: the editor's fast tokenizer stays for that.
- Executing CQL (constant folding stays as in `feature/20261119-python-constant-eval.md`).

---

## Part II — Technical specification

### 1. Design

**1.1 The shared package (home: SwissTPH/tricc).** One folder, `tricc_oo/lang/`, inside the
Python package so the wheel ships it (add `"tricc_oo.lang" = ["**/*"]` to `package-data`):

```
tricc_oo/lang/
  VERSION            one version for the whole folder
  CHANGELOG.md
  cql/               cql.g4, fhirpath.g4 (upstream, untouched), tricc_cql.g4, README (tag, licence)
  feel/              FEEL_1_1.g4 (upstream KIE, untouched), tricc_feel.g4, TriccFeelParser.g4,
                     cells.json, README (tag, licence, the cell subset; §1.5)
  functions.json     the function catalogue (§1.3)
  meaning.json       the meaning rules as a test vector (§1.4)
  errors.json        token → message for constructs outside the profile (§2)
```

`VERSION` is bumped on any change to any file in the folder, an upstream grammar update included
(§1.6). Generated parsers record the version they were built from.

**1.2 CQL grammar.**

- `cql/cql.g4` and `cql/fhirpath.g4` are **untouched copies of upstream v5.7.0**. Today's local
  `tricc_oo/converters/cql/g4/cql.g4` differs from upstream in three ways only: the
  `#negateMembershipExpression` alternative (commit `66dbe78`), the duplicate `externalConstant`
  rule removed (it stays in `fhirpath.g4`, which `cql.g4` imports), and a missing trailing
  newline. `fhirpath.g4` is identical. Checked with ANTLR 4.13.2: `tricc_cql.g4` importing the
  untouched upstream pair (duplicate `externalConstant` included) generates Python that compiles
  and parses `"weight" > 38 and AgeInDays() < 60`; upstream CQL has no embedded actions.
- `cql/tricc_cql.g4`: `grammar tricc_cql; import cql;`. It overrides whole rules, keeping upstream
  `#labels` so the generated visitor methods keep their names:

  | Rule overridden  | Change                                                                                                                                                                                                                                                                                                                    |
  | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
  | `expression`     | adds `expression 'not' ('in' \| 'contains') dateTimePrecisionSpecifier? expression #negateMembershipExpression` (not standard CQL); drops `#retrieveExpression`, `#queryExpression`, `#inFixSetExpression` (union / intersect / except), `#durationBetweenExpression`, `#differenceBetweenExpression` (plural precisions) |
  | `expressionTerm` | drops `#indexedExpressionTerm` (`x[0]`), `#invocationExpressionTerm` (`x.member`, fluent `x.f()`; plain calls stay, via `#functionInvocation`), `#durationExpressionTerm` and `#differenceExpressionTerm` (plural precisions)                                                                                             |
  | `term`           | adds `PLACEHOLDER #placeholderTerm`                                                                                                                                                                                                                                                                                       |
  | `literal`        | drops `#quantityLiteral` and `#ratioLiteral` (units)                                                                                                                                                                                                                                                                      |
  | lexer            | `PLACEHOLDER : '{{' WS* IDENTIFIER WS* ('\|' WS* 'raw' WS*)? '}}' ;` (`{{name}}`, `{{name \| raw}}`). `{{1}}`, a list in a list, now lexes differently; nested lists are outside the profile                                                                                                                              |
  | new entry rule   | `triccExpression : expression EOF ;` (replaces wrapping each expression in `library runner define "calc": …`)                                                                                                                                                                                                             |

  The exact list is checked in phase 1 against what `cqlToXlsFormVisitor` handles. Four of its
  rejections are dead code today: `visitInvocationExpression`, `visitIndexerExpression`,
  `visitUnionExpression` and `visistDateTimePrecision` (typo) match no generated visitor method,
  so those constructs fall through `visitChildren` instead of failing.

- tricc_oo keeps substituting placeholders before folding (`PLACEHOLDER`, `models/params.py`), but
  both sides can now parse unrendered text, with errors at the right column.
- **Generated parsers are committed**: Python (`tricc_cqlLexer.py`, `tricc_cqlParser.py`,
  `tricc_cqlVisitor.py`, under `tricc_oo/converters/cql/`) built with ANTLR 4.13.2
  (`antlr4-tools`, matching `antlr4-python3-runtime==4.13.2` in `pyproject.toml`), and TypeScript
  in the frontend (§1.7). Developers don't need Java. `cqlToXlsFormVisitor` and
  `transform_cql_to_operation` move to the new classes; the `−` → `-` normalisation stays before
  lexing.

**1.3 Function catalogue.** `functions.json` replaces `FUNCTION_MAP` (`cql_to_operation.py`) and
`tricc_oo/converters/cql/stored_data_functions.json` (kept as a generated view, or read through
the catalogue, until callers move). It lists the decision-table functions `DMN`, `DMNFirst`,
`DMNList` too (#91, #96).

```json
{
  "functions": [
    {
      "name": "AgeInDays",
      "params": [],
      "returns": "Integer",
      "operator": "AGE_DAY",
      "reads": "patient",
      "foldable": false
    }
  ]
}
```

`reads` is `none | patient | encounter | history | context` (§18.5); `foldable` tells
`constant_eval` it may run it at build. Functions declared `external` in a project library
(`cql_library.FunctionSignature`, `@retrieve`) are added per project with the same fields.

**1.4 Meaning rules, outside the grammar.** `meaning.json` holds the cases both sides must agree
on: `"x"` is a reference, `'x'` a text, a bare word in an argument a fixed text,
`is_expression_arg` per argument (`AgeInDays()`, `"weight"`, `axillary`, `'axillary'`,
`left arm`, `38`, `true`, `{{x}}`, `"x" > {{t}}`, …), and the decision-table rule that TRICC's
`'text'` is FEEL `"text"` (tricc-frontend `decision-table/interchange.ts`). tricc_oo's tests and
the frontend's both run it.

**1.5 FEEL grammar (decision-table cells).** Upstream is the Apache KIE (Drools) grammar
`FEEL_1_1.g4`, release `10.2.0` (2026-04-28, same file on `main`, last changed 2026-01-19;
FEEL from DMN chapter 10, with DMN 1.6 additions), Apache-2.0. It is kept untouched in `feel/`.

Its **parser rules cannot be imported** into a Python or TypeScript grammar: they carry Java
(`@parser::header` importing `org.kie.dmn.feel.parser.feel11.ParserHelper`, `@parser::members`,
36 `helper.*` actions for scopes and names with spaces, Java predicates such as
`{_input.LT(1).getText().equals("list")}?`, `locals [java.util.List<String> …]`). ANTLR merges
an imported grammar's named actions and copies all its rules, so `grammar tricc_feel; import
FEEL_1_1;` generates a Python parser that does not compile (checked with ANTLR 4.13.2). Its
**lexer is clean** (no actions) and generates and runs.

So the FEEL side uses the upstream lexer and a TRICC parser:

- `feel/tricc_feel.g4`: `grammar tricc_feel; import FEEL_1_1;` plus one lexer rule,
  `TriccText : '\'' ( ~['\\\r\n] | '\\' . | '\'\'' )* '\'' ;` (TRICC's `'text'`). Only its
  generated **lexer** (`tricc_feelLexer`, `tricc_feel.tokens`) is kept; the generation script
  drops the generated parser.
- `feel/TriccFeelParser.g4`, a parser grammar with
  `options { tokenVocab = tricc_feelLexer; }`, written from the DMN simple-unary-tests rules (spec #7–#18), with labels:

  ```antlr
  cellRoot  : cellTests EOF ;
  cellTests : SUB #cellAny | NOT LPAREN NULL RPAREN #cellNotNull | cellTest (COMMA cellTest)* #cellList ;
  cellTest  : op=(LT | GT | LE | GE | EQUAL) cellValue #cellCompare
            | NULL #cellNull
            | low=(LPAREN | LBRACK | RBRACK) cellValue ELIPSIS cellValue up=(RPAREN | RBRACK | LBRACK) #cellRange
            | cellValue #cellEquals ;
  cellValue : SUB? (IntegerLiteral | FloatingPointLiteral) | TriccText | StringLiteral | BooleanLiteral ;
  ```

  Checked with ANTLR 4.13.2 and the Python runtime: `-`, `null`, `not(null)`, `< 5`, `>= -2.5`,
  `[1..5)`, `(0..10]`, `'yes', 'no'`, `'it''s'`, `true`, `5` parse; `foo bar` and `[1..` fail
  with a position. Output cells are literals of the column type (`cellValue`).

- Type checks (a range on a text column, a text in a number column) stay in a visitor, with the
  codes the hand parsers use today (`E_DMN_CELL`, `E_DMN_TYPE`).
- `feel/cells.json` (now at tricc-frontend
  `packages/core/src/decision-table/__vectors__/cells.json`) becomes the grammar's shared test
  vector, with one copy. The hand parsers are replaced: tricc-frontend `decision-table/cell.ts`
  (`parseCell`) and tricc_oo's (#91) visit the generated parser. `'text'` ↔ FEEL `"text"` stays
  in `meaning.json` and drives `interchange.ts`.
- Growing beyond cells (free FEEL) means more TRICC parser rules over the same upstream lexer.

**1.6 Upstream updates.** The CQL and FEEL files are pinned to a tag or release. A new upstream grammar is a change
to `cql/` like any other: a PR that bumps `VERSION`, runs the override tests and `meaning.json`.
Nice to have: a scheduled GitHub Action that checks cqframework/clinical_quality_language tags
and opens that PR when `grammar/*.g4` changes (and the same for the KIE FEEL file).

**1.7 Frontend consumer (mirror spec).** A copy of `tricc_oo/lang/` in
`packages/core/src/lang/`, with `lang.lock.json` recording the package `VERSION`, the tricc commit
and a sha256 of the folder, and a sync script (`scripts/sync-lang.mjs`) that copies a given tricc
commit and rewrites the lock. The TypeScript is generated with the same ANTLR 4.13.2 tool as the
Python (`-Dlanguage=TypeScript`), and imports the official `antlr4` npm runtime, pinned to
`antlr4@4.13.2` in `@tricc/core` (checked: the 4.13.2 output imports from `"antlr4"`). It is
committed. One tool version builds every parser of a package version; `antlr4ng` / `antlr-ng`
are not used. The parser is lazy-loaded;
`presentCql` keeps live highlighting. The parser drives validation and `isExpressionArg`,
replacing tricc-frontend#52's token rule. `decision-table/cell.ts` uses the generated FEEL
parser and its tests read `lang/feel/cells.json`.

**1.8 Project CQL libraries.** A library (`tricc.yaml` `libraries`, `cql_library.py`) may declare
its dialect and version, e.g. `libraries[].dialect: tricc-cql@<VERSION>` in `tricc.yaml` or a
`/* @dialect: tricc-cql@<VERSION> */` tag at the top of the file (phase 4 picks one). A library
that declares nothing is **standard CQL**: parsed with the unmodified upstream `cqlParser.library`
(no `not in`, no placeholders), TRICC's limits checked by a visitor. As today, only `define`s are
used, function bodies are rejected and `external` functions are signatures.

**1.9 CI (nice to have).** A GitHub Action in each repo regenerates the parsers (Python in tricc,
TypeScript in the frontend) and fails on drift; the frontend's also checks `lang.lock.json`
against the folder.

### 2. Validation and errors

- Syntax errors keep `CQLErrorListener`, now on `triccExpression`, with line and column of the
  expression itself (no offset from the wrapper library).
- A construct removed by `tricc_cql.g4` gets a named message instead of ANTLR's "no viable
  alternative": the error listener maps the offending token (`[`, `from`, `where`, `union`,
  `.member`, a unit) to a message from `errors.json`, shared with the frontend.
- An unknown function name: `W_CQL_UNKNOWN_FUNCTION` (passed through as `native` today).
- **Tightening.** Before switching, phase 1 runs the new parser over the fixtures and the known
  projects (e.g. `combacal-plus/visual-authoring/dm_int.tricc`). A construct now outside the
  profile that they use is, in tricc_oo, `W_CQL_PROFILE` (a warning, the old behaviour kept) for
  one release, then an error. The editor rejects it in new edits from the start.
- A library with an unknown `dialect`: `E_CQL_DIALECT`.

### 3. Tests

- `tests/test_cql.py`, `test_cql_bare_identifiers.py`, `test_cql_initial_expression.py` green
  on the new parser.
- One test per override in §1.2: accepted (`not in`, `{{x}}`, `{{x | raw}}`) and rejected with
  its message (query, retrieve, union, indexer, member, unit, plural precision).
- `meaning.json` run by `is_expression_arg` and `literal_value`.
- `feel/cells.json` run by the FEEL grammar on both sides (tricc_oo with #91, tricc-frontend
  `decision-table/decision-table.test.ts`); every case that passes today still passes.
- Catalogue: every `TriccOperator` mapped today is in it; `stored_data_functions()` returns the
  same set as before.
- Package: `cql/cql.g4` / `fhirpath.g4` and `feel/FEEL_1_1.g4` equal the upstream files
  (checksum); the generated parsers carry the current `VERSION` and say "Generated … by ANTLR
  4.13.2".
- Frontend: the committed TypeScript matches a fresh ANTLR 4.13.2 generation, and
  `package.json` pins `antlr4` to `4.13.2`.
- Libraries: one with no dialect rejects `not in`; one declaring `tricc-cql` accepts it.
- The fixtures and `tests/data/projects/*` build unchanged; the tightening scan is reported.

### 4. Phases

1. tricc_oo: `tricc_oo/lang/` with `VERSION`, upstream files, `tricc_cql.g4`, `errors.json`,
   generation, visitor moved, tightening scan, tests.
2. tricc_oo: `functions.json` and `meaning.json`; `FUNCTION_MAP` and `stored_data_functions` read
   them.
3. FEEL: `feel/` with the upstream file, `tricc_feel.g4`, `TriccFeelParser.g4`, generation,
   `cells.json`; tricc_oo's cell parser (#91) built on it.
4. Frontend (mirror spec): copy, lock and sync script, TypeScript generated with ANTLR 4.13.2 on
   the `antlr4@4.13.2` runtime, validation,
   `isExpressionArg`, `cell.ts` on the generated FEEL parser.
5. Project libraries: the dialect declaration and the standard-CQL default.
6. Nice to have: the drift Actions (§1.9) and the upstream-tag Action (§1.6).

---

## Open questions

None.

---

## Decisions

- 2026-11-23: the grammar and the catalogue live in SwissTPH/tricc; the frontend generates
  TypeScript from a pinned copy (Patrick).
- 2026-11-23: base is upstream HL7 v5.7.0 (`main`, CQL 1.5), files kept untouched; TRICC changes
  go in a derived `tricc_cql.g4` overriding whole rules, labels kept (Patrick).
- 2026-11-23: semantics outside the grammar: a JSON function catalogue (`FUNCTION_MAP` +
  `stored_data_functions.json`, plus `DMN`, `DMNFirst`, `DMNList`) and the meaning rules as a
  shared test vector (Patrick).
- 2026-11-23: the frontend keeps `presentCql` for highlighting and lazy-loads the parser for
  validation and `isExpressionArg` (Patrick).
- 2026-11-23: a project library may declare its dialect and version; one that declares nothing is
  standard CQL, parsed with the unmodified upstream grammar, TRICC's limits checked by a visitor
  (Patrick).
- 2026-11-23: `{{name}}` is a `PLACEHOLDER` lexer token with a placeholder term (Patrick).
- 2026-11-23: generated parsers, Python and TypeScript, are committed; nice to have: an Action
  that regenerates and fails on drift (Patrick).
- 2026-11-23: tightening: scan the fixtures and known projects first; a construct in use is a
  warning for one release in tricc_oo; the editor rejects it in new edits (Patrick).
- 2026-11-23: the frontend pins a copy with a lock file (package version, tricc commit, sha256)
  and a sync script. The shared package has its own version, bumped on any change to any of its
  files (Patrick).
- 2026-11-23: an upstream HL7 grammar update is a package change like any other (a version
  bump); nice to have: an Action that watches upstream tags and opens the PR (Patrick).
- 2026-11-23: FEEL grammar in the same package (c): one package, one version, so the expression
  languages are coherent for a given TRICC version (Patrick).
- 2026-11-23: slug `expression-languages` (Patrick).
- 2026-11-23: TypeScript via ANTLR 4.13.2 + `antlr4@4.13.2` npm runtime, not `antlr4ng` (Patrick).
- 2026-11-25: Approved for implementation with #102 on one branch, frontend mirror included. (@delcroip)
