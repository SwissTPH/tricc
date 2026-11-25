# Expression languages and output capabilities

## The shared expression languages (`tricc_oo/lang/`)

TRICC reads CQL (calculations, conditions, block arguments) and FEEL (decision-table cells) with
grammars shared with the editor (tricc-frontend), in one versioned folder, `tricc_oo/lang/`
(`VERSION`, `CHANGELOG.md`):

- `cql/`: the HL7 CQL grammar (tag `v5.7.0`, untouched) and TRICC's profile `tricc_cql.g4`.
  The profile adds `x not in y` and `{{placeholders}}`, and leaves out what a form cannot run:
  queries, retrieves (`[Observation]`), `union` / `intersect` / `except`, indexers (`x[0]`),
  member access (`x.member`, `x.f()`), units (`5 'mg'`, `3 days`) and plural precisions
  (`years between`). Each is refused with a named message (`errors.json`, `E_CQL_PROFILE`).
- `feel/`: the Apache KIE FEEL lexer (release `10.2.0`, untouched) and TRICC's cell parser
  (`TriccFeelParser.g4`); `cells.json` is the shared test vector.
- `functions.json`: the function catalogue (arguments, result, what each reads: `patient`,
  `encounter`, `history`, `context`, and whether the build may fold it). A call to a function
  outside it, the project libraries and the decision-table aliases is `W_CQL_UNKNOWN_FUNCTION`.
- `meaning.json`: the meaning rules both sides test (`"x"` is a reference, `'x'` and a bare word
  are text, which block arguments are calculated).

The Python parsers are generated (`scripts/generate-lang-parsers.sh`, ANTLR 4.13.2, needs Java)
and committed into `tricc_oo/converters/cql/` and `tricc_oo/converters/feel/`;
`--check` fails on drift.

Project CQL libraries are standard CQL unless their opening comment says
`/* @dialect: tricc-cql@1.0.0 */` (see [CLI and inputs](cli-and-inputs.md)).

## Output capability statements

Each output publishes a capability statement, an npm package
`@tricc/capabilities-<strategy>` (folder `capabilities/` of the repository): the operators it
writes and where (`form`; FHIR: `inline` = FHIRPath, `library` = CQL), the catalogue functions,
the retrieval and prefill contexts, data types, features (`decision_table_calls`) and limits.
A statement may extend another (CHT extends CDSS, which extends XLSForm; OpenSRP extends FHIR).

A project lists the statements it loaded in `tricc.yaml`:

```yaml
capabilities:
  - package: "@tricc/capabilities-fhir"
    version: 1.0.0
    source: npm            # npm | github | file
    registry: https://registry.npmjs.org
    file: capabilities/@tricc/capabilities-fhir@1.0.0.json
    sha256: …
    active: true
```

The build reads only the copies in the project folder (`file`, checked by `sha256` and the
schema), never the network. After the project is loaded, before the walk, every expression,
decision-table call, retrieval and prefill node is checked against each **active** statement:

| Code                    | Meaning                                                                    |
| ----------------------- | -------------------------------------------------------------------------- |
| `E_OUTPUT_UNSUPPORTED`  | a node uses a construct the output cannot write; the build stops          |
| `W_OUTPUT_LIMIT`        | over a limit the output has a fallback for (a long table written inline)  |
| `W_OUTPUT_NO_STATEMENT` | an output to build has no active statement: it is built unchecked         |
| `E_CAPABILITY_FILE`     | a listed file is missing, fails the schema or its `sha256`                |
| `E_CAPABILITY_EXTENDS`  | the parent statement is not loaded or its version is out of range         |
| `W_CAPABILITY_LANG`     | the statement names a `@tricc/lang` range that excludes this TRICC        |

A loaded but inactive statement is not checked; with no active statement nothing is checked.
Export keeps its own errors for anything the check misses.
