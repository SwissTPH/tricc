# Output capability statements: check a project against its outputs before export

| Field             | Value |
| ----------------- | ----- |
| **Status**        | Approved (2026-11-25, RFC #102) |
| **Branch target** | `feature/lang-and-capabilities` → `develop` |
| **Scope**         | new `capabilities/` folder (one package per output strategy), `strategies/output` (every strategy: `base_output_strategy`, `xls_form`, `xlsform_cdss`, `xlsform_cht`, `xlsform_cht_hf`, `fhir_form`, `opensrp`, `html_form`, `openmrs_form`, `dhis2_form`, `spice`), `models/project_config` (`capabilities`, `output_strategies`), `runner`, `converters/retrieval`, `converters/decision_table`; frontend: `@tricc/core` (project format, validation), `@tricc/editor` (project capabilities screen) |
| **Related** | #98 (shared expression languages and function catalogue: statements name its operators and functions and declare the `@tricc/lang` version they were written for). #101 (calculate functions: `E_FUNCTION_NOT_EXPORTABLE` moves here). `feature/20261123-decision-tables.md` (`decision_table_calls`, CHT extension library). `feature/20261109-project-retrievals.md` (retrieval contexts per strategy). Frontend mirror (project format, capabilities screen, loading from npm / GitHub Packages / file, editor checks): SwissTPH/tricc-frontend, mirror into `tricc-frontend/feature/` on approval. |
| **RFC**           | SwissTPH/tricc#102 |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

### The problem

A project is built into several outputs: XLSForm, CHT, FHIR, OpenSRP and others. Each output
can write only part of what an author can draw: a function body FHIRPath cannot express, a
retrieval context CHT cannot read, a decision table too large to write inline. Today the author
finds out at the end, when the export of one output fails, often after a long build and with a
message about code rather than about the drawing. The editor cannot warn at all: it does not
know what each output can do.

### What changes for an author

- Each output publishes a **capability statement**: what it can write (operators, functions,
  retrieval and prefill contexts, data types, decision-table calls, function bodies). Each one is
  its own package with its own version, so one output can be updated without touching the
  others. A statement can build on another (CHT on XLSForm).
- The **project lead** manages the statements of a project:
  - a new project opens with the latest published statements, and the lead picks which apply;
  - a statement can be loaded but not active (kept for later, or for comparison);
  - a statement is added or updated from npm, from GitHub Packages, or by uploading a file (an
    output written in-house, or a local change).
  The project keeps a copy of each loaded statement, so builds do not depend on the network.
- The build checks the project against every **active** statement when it loads, before any
  walk, and stops with an error that names the node, the construct and the output ("`IsAdult`
  uses `Power`, which the FHIR output cannot write inline").
- The editor shows the same errors while the author draws.
- A project with no active statement is not checked; export still fails as today.

### Out of scope

- Adding capabilities to an output: this RFC only describes what each output does today.
- Choosing another way to write a construct when an output lacks it (fallback rewrites).
- Publishing to npm or GitHub Packages (release process): this RFC defines the packages; the
  release workflow is a separate task.
- Argument types in statements (operators and contexts only for now).

---

## Part II — Technical specification

### 1. Statements

- **One package per output strategy.** `capabilities/<strategy-id>/` in SwissTPH/tricc, each with
  its own `package.json` (`@tricc/capabilities-<strategy-id>`, e.g. `-xlsform`, `-xlsform-cdss`,
  `-xlsform-cht`, `-xlsform-cht-hf`, `-fhir`, `-opensrp`), `CHANGELOG.md` and `statement.json`.
  Each is versioned on its own (semver) and bumped on any change to its statement.
- **`statement.json`:**
  - `id`, `version`, `strategy` (the output strategy class it describes, e.g. `FHIRStrategy`);
  - `extends`: `{package, version range}` of the parent statement (`-xlsform-cht` extends
    `-xlsform-cdss`, as the classes do); also a `dependencies` entry in `package.json`. A child
    lists only what it adds (`add`) or removes (`remove`);
  - `lang`: the `@tricc/lang` version range (#98) whose operators and functions it names;
  - `operators`: `TriccOperator` names it writes, each with the contexts where it can (e.g. FHIR
    `inline` (FHIRPath) / `library` (CQL));
  - `functions`: catalogue function names (#98) it writes;
  - `retrieval_contexts` / `populate_contexts`: values from `RETRIEVAL_CONTEXTS`;
  - `data_types`, `features` (`decision_table_calls`, `function_bodies`, `repeat`, …), and
    `limits` (e.g. inline decision-table rows).
  A JSON Schema (`capabilities/statement.schema.json`) checks it, on both sides (tricc_oo ships
  a copy in `tricc_oo/data/capabilities/`, kept equal by a test). A root statement also lists its
  `contexts` (`form`; FHIR `inline` / `library`), the values its operators' contexts take.
- **Kept true by tests.** `tests/test_output_capabilities.py` feeds every `TriccOperator` and
  catalogue function to each strategy's expression writer. A construct the writer handles must
  be in the strategy's resolved statement (after `extends`) and one it rejects must not, so the
  packages in the repo cannot drift from the code.

### 2. The project's statements

- **tricc.yaml** gains `capabilities`, one entry per loaded statement:

  ```yaml
  capabilities:
    - package: "@tricc/capabilities-fhir"
      version: 1.4.0
      source: npm            # npm | github | file
      registry: https://registry.npmjs.org   # npm / github sources
      file: capabilities/@tricc/capabilities-fhir@1.4.0.json
      sha256: …
      active: true
  ```

  `file` is the resolved statement copied into the project folder (its `extends` chain is copied
  too, as entries with `active: false` unless the lead activates them). The build reads only
  these files, never the network. `sha256` checks the copy.
- **Sources** (frontend, mirror spec): npm (`registry.npmjs.org`), GitHub Packages (the npm
  registry `npm.pkg.github.com`, which needs a token), or a file upload (a `statement.json`;
  `source: file`, no registry). Loading resolves `extends` from the same source when it can,
  else asks for the parent.
- **New project.** The editor lists the latest version of every published `@tricc/capabilities-*`
  package; the lead picks the active ones. Their copies are written as above.
- **Update.** Choosing a newer version (or a new file) replaces the copy and the entry; the
  editor shows what changed (added / removed operators, functions, contexts).
- **`output_strategies`** stays the list of outputs to build. An output with no active statement
  for its strategy is built unchecked (`W_OUTPUT_NO_STATEMENT`). An active statement whose
  strategy is not in `output_strategies` is still checked (the lead may check against an output
  before building it).
- **Third-party outputs** provide a statement like any other: their own package, or a file.

### 3. Validation

- `runner` reads the active entries of `capabilities`, loads their files (checking `sha256` and
  the schema), resolves `extends`, and, after the project is loaded and before `process_pages`,
  checks every expression, decision-table call, function body (#101), retrieval and prefill
  node against each one.
- Error `E_OUTPUT_UNSUPPORTED` per construct and statement, naming the node (activity, name), the
  construct and the strategy. `W_OUTPUT_LIMIT` when a limit is exceeded but the output has a
  fallback (e.g. a long inline table).
- `E_CAPABILITY_FILE`: a listed file is missing, fails the schema or its `sha256`.
  `E_CAPABILITY_EXTENDS`: the parent is not loaded or its version is out of range.
  `W_CAPABILITY_LANG`: the statement's `lang` range does not include the `@tricc/lang` version in
  use.
- Export keeps its own errors (`E_FUNCTION_NOT_EXPORTABLE`, …) for anything the check misses.
- The frontend mirror runs the same check in `@tricc/core` validation, from the same files.

### 4. Tests

- Each package's statement against its writer (§1).
- `extends` resolution: a child adds and removes constructs; a missing parent fails.
- A fixture project using a FHIRPath-inline-only gap, an unsupported retrieval context and a
  decision table over the inline limit: errors and warning per active statement; nothing for a
  loaded but inactive one; no check when none is active; `W_OUTPUT_NO_STATEMENT`.
- tricc.yaml: `capabilities` read and written back unchanged; a bad `sha256` fails.

### 5. Phases

1. The packages and schema for the XLSForm family, FHIR and OpenSRP, with the writer tests.
2. tricc.yaml `capabilities` and the load-time check in `runner`, errors.
3. Frontend mirror: project format, capabilities screen (list, activate, load from npm / GitHub
   Packages / file, update with a change summary), editor checks.
4. Statements for the remaining strategies.

---

## Open questions

None.

## Decisions

- 2026-11-24: Outputs publish capability statements; a project's active statements turn on the
  check, so errors come before export. (@delcroip)
- 2026-11-25: One package per output strategy, versioned on its own, with `extends` for
  inheritance, so one output can be updated alone. Statements declare the `@tricc/lang` range
  they name. (@delcroip)
- 2026-11-25: Statements list operators and the contexts they work in; argument types later.
  (@delcroip)
- 2026-11-25: Statements are managed per project by the project lead: a new project opens with
  the latest published ones; each can be loaded but inactive; loaded or updated from npm, GitHub
  Packages or a file; the project keeps a copy, so builds are offline. Third-party outputs use the
  same route (no class method). (@delcroip)
- 2026-11-25: Approved for implementation with #98 on one branch, frontend mirror included. (@delcroip)
