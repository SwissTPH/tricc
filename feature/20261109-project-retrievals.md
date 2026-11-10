# Project retrieval dictionary: export of `"#name"` retrievals, and the populate `source`

| Field             | Value |
|-------------------|-------|
| **Status**        | Approved (2026-11-09, in conversation) |
| **Branch target** | `feature/project-retrievals` → `develop` |
| **Scope**         | `YamlStrategy`, `DrawioStrategy` (via `BaseInputStrategy`), `models`, `FHIRStrategy` → `OpenSRPStrategy`, `XLSFormStrategy` → `XLSFormCDSSStrategy` → `XLSFormCHTStrategy` → `XLSFormCHTHFStrategy` |
| **RFC**           | SwissTPH/tricc-frontend#31 (phase 4); SwissTPH/tricc-frontend#34 (populate `source`) |
| **Related**       | Mirror of `../tricc-frontend/feature/20261109-project-retrievals.md` (the format, authoritative) and `../tricc-frontend/fix/20261109-populate-source-period.md`. Builds on `feature/populate-context.md` and `feature/20260929-cql-populate-wiring.md` (the populate accessors it reuses), `feature/20261102-block-params-and-start-node.md` (`calculate_code_system`, same lookup). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

### The problem

Data that exists before the consultation (age, sex, last week's weight) is drawn today as a
"Prefilled value" node in each activity, and the export guesses what it reads from the node
name. The frontend now keeps these definitions once per project, in a **retrieval
dictionary**, and logic refers to them as `"#age_months"`. tricc_oo has to read that
dictionary and turn each retrieval into something every export can run.

### What changes for an author

- An expression can use `"#name"` like any concept: `"#age_months" < 2`. Nothing is drawn.
- Each form loads only the retrievals it uses. A `"#name"` that is not in the dictionary stops
  the build with a message naming it.
- FHIR / OpenSRP: each retrieval is one named expression in the shared Helper library.
- CHT: each retrieval is a hidden field `r_<name>` read from the contact summary (the
  deployment's contact-summary script provides `<name>`).
- Plain XLSForm / CDSS have nowhere to read patient data from: only **custom** retrievals (with
  an XLSForm expression) export there. Anything else stops the build, naming the retrieval and
  the export.
- A custom retrieval with no expression for an export's language stops that export with a
  clear message instead of guessing.
- A "Prefilled value" node can say which concept it reads (`source`), so `t_weight` can read
  `weight` and keep its own name.

### Out of scope

- Migration of populate nodes into the dictionary (frontend phase 3).
- A CHT mapping that computes patient functions from contact fields (they read the contact
  summary like populate nodes do).
- Validation rules of the frontend spec §7 beyond the errors listed below.

---

## Part II — Technical specification

### 1. Reading

- `TriccProjectConfig.retrieve_code_system` / `TriccIntervention.retrieve_code_system`, copied
  in `BaseInputStrategy.new_project`.
- `param_build.role_code_system_key(codesystems, role, configured)`: tagged
  `codesystem-role|<role>` → configured (url, id or name) → key/id/name `<role>` or ending
  in `-<role>`. `calculate_code_system_key` now calls it with `calculate`.
- `tricc_oo/converters/retrieval.py`: `Retrieval` (pydantic), `read_retrieval(concept)` reads
  `context`, `function`, `reads` (valueCoding), `period`, and the `retrieve-expression`
  extensions (`valueExpression.language` → `expression`). The catalogue
  `RETRIEVAL_FUNCTIONS` mirrors `@tricc/core` `terminology/retrieval.ts` (contexts, needs
  `reads`, value type). The concept read gives `reads_data_type` (`dataType`) and
  `reads_concept_type` (`conceptType`, which picks Observation / Condition).
- Errors (`TriccRetrievalError`): code not `#name`, unknown context or function, function not
  allowed in the context, `reads` missing when the function needs it. A period on a context
  without one is a warning and dropped.

### 2. Usage and graph

`BaseInputStrategy.attach_library_calculates` (called by every input after the pages are
loaded) calls `build_used_retrievals(project)`: it walks the `TriccReference`s of every loaded
page's applicability and every node's `relevance`, `expression`, `expression_reference`,
`reference`, `trigger`, `applicability`, `constraint`, `default`, plus the library calculates.
Blocks are built only where used, so this covers activities and the blocks they reach. Each
used retrieval becomes a `TriccNodeRetrieval` (subclass of `TriccNodePopulate`, field
`retrieval`) named by its code, `export_name` `r_<name>`, hung on the main page like a library
calculate, so `"#name"` resolves to it and every populate behaviour (hidden item, never
extracted, no skip) applies. `project.retrievals` / `project.retrieval_nodes` hold them.

### 3. Strategies

`BaseOutPutStrategy.retrieval_expression(retrieval)` raises by default;
`check_retrievals()` runs it for every used retrieval and is called by the runner before
`execute()`.

- `FHIRStrategy` (and `OpenSRPStrategy`): `populate_helper.retrieval_cql_expression` (the
  catalogue); `retrieval_cql_defines` appends `define "#name": …` to the Helper library.
  `resolve_populate_reference` returns `Helper."#name"` for a retrieval node, and
  `populate_value_type` its CQL type. Observation `Latest` is wrapped in `ValueAs<type>` from
  the concept's `dataType`. History periods become `Now() - <quantity>` windows (no period: no
  window).
- `XLSFormStrategy`: `get_retrieval_lines()` builds one `calculate` row `r_<name>` per
  retrieval (`get_input_calc_line` with the calculation swapped), put at the top of the survey;
  only `custom` maps. `XLSFormCHTStrategy` maps every function to
  `coalesce(instance('contact-summary')/context/<name>,'')` and places the rows after the
  populate rows of the inputs section. `XLSFormCDSSStrategy.export_inputs` skips retrieval
  nodes.
- Custom placeholders (`custom_expression`): CQL `{{code}}` → `"<code>"`, `{{period}}` → a CQL
  quantity (`P30D` → `30 days`, single unit only); XLSForm `{{code}}` → the cleaned field name,
  `{{period}}` → days (W = 7, M = 30, Y = 365, hours as fractions).

### 4. Populate `source` (#34)

`YamlNode.source` (code or `{system, code}`; the model keeps the code) is copied to
`TriccNodePopulate.source`; draw.io already read the attribute. `populate_source_concept` uses
it before the node name.

### 5. Tests

`tests/test_project_retrievals.py` with the project `tests/data/projects/retrievals/`
(a retrieve CodeSystem with `AgeInMonths`, a history `Latest` with `reads` and `P30D`, a
`custom` with both languages, an unused entry, and a populate node with `source`): reading,
catalogue, placeholders, CHT and FHIR output, the plain XLSForm error, unknown codes, and the
populate source.

### 6. Phases

1. Reading, usage, FHIR and XLSForm family export, populate `source` (this branch).

---

## Open questions

None.

## Decisions

- 2026-11-09: Approved in conversation as phase 4 of RFC #31, with #34. (@delcroip)
- 2026-11-09: Retrieval defines live in the Helper library, so every segment reaches them as
  `Helper."#name"` and custom CQL can call Helper functions unqualified.
- 2026-11-09: CHT reads every catalogue function from the contact summary (key `<name>`), as
  populate nodes do; plain XLSForm and CDSS support `custom` only.
- 2026-11-09: A history retrieval without period reads without a window (populate nodes keep
  their `P1Y` default).
