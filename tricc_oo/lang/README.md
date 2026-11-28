# tricc-lang: TRICC's expression languages

One folder, one version (`VERSION`), shared by tricc_oo (Python) and tricc-frontend
(TypeScript, pinned copy with a lock file). Spec: `feature/20261125-expression-languages.md`.

| Path            | What                                                              |
| --------------- | ----------------------------------------------------------------- |
| `cql/`          | upstream CQL / FHIRPath grammars and the TRICC profile            |
| `feel/`         | upstream FEEL lexer, the TRICC cell parser, `cells.json`          |
| `functions.json`| the function catalogue                                            |
| `meaning.json`  | meaning rules (a test vector both sides run)                      |
| `errors.json`   | messages for constructs outside the profile                       |
