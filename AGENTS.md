# TRICC Project - Cline Rules

This file (`AGENTS.md`) is the source of truth for coding standards, domain reference, and workflow
in this repository — including for Claude Code (`CLAUDE.md` just points here).

## Project Overview

TRICC (Transformable Rule-based Interactive Clinical Calculator) converts clinical decision-support
flowcharts (authored visually in draw.io) into runnable digital forms: XLSForm/ODK, CHT, OpenMRS,
DHIS2, FHIR SDC (Questionnaire + CQL), and OpenSRP/FHIR-Core bundles. It processes visual flowcharts
created in draw.io and converts them into various output formats. Core library under `tricc_oo/`,
installed as the `tricc` console script (`tricc_oo/cli.py`, entry point in `pyproject.toml`).

## Key Technologies

- **Language**: Python 3.8+
- **Core Dependencies**: lxml, pydantic, pandas, xlsxwriter, antlr4
- **Code Style**: PEP 8, max line length 120 (see .flake8)
- **Architecture**: Strategy pattern for input/output processing
- **Models**: Pydantic-based data models with custom types

## Project Structure

```
tricc_oo/
├── converters/      # Format conversion logic (drawio→tricc, tricc→outputs)
├── models/          # Pydantic data models (nodes, edges, operations)
├── parsers/         # XML parsing for draw.io files
├── serializers/     # Output format serialization
├── strategies/      # Input/output strategy implementations
├── tools/           # Draw.io templates and utilities
└── visitors/        # Graph traversal and processing
feature/             # Feature specs (new capabilities); Draft → Approved gate
fix/                 # Issue analysis + fix approach (bugs / export correctness); same gate
tests/               # Test suite and build scripts
docs/                # MkDocs documentation
```

## Commands

```bash
# activate the project venv first (dependencies + registered strategies must match this env)
source .venv/bin/activate

# run the full test suite (pytest, ~138 tests)
python -m pytest tests/

# run a single test file / test / method
python -m pytest tests/test_cdss_zscore.py
python -m pytest tests/test_strategies/test_opensrp_strategy.py -v
python -m pytest tests/test_strategies/test_opensrp_strategy.py::TestFhirIds::test_underscore_replaced -v

# lint (max line length 120, see .flake8)
flake8 tricc_oo

# run a conversion directly (the dev entry point; more actively used than the `tricc` script)
python tests/build.py -i tests/data/demo.drawio -o tests/output/
python tests/build.py -i tests/data/demo.drawio -o tests/output/ -O XLSFormCHTStrategy
python tests/build.py -i tests/data/demo.drawio -o tests/output/ -O FHIRStrategy -l d   # -l d = debug logging

# YAML fixtures are the preferred input for exercising transformation logic in tests
# (git-friendly, no draw.io XML needed) — see tricc_oo/strategies/input/yaml.py
python tests/build.py -i tests/data/yaml/my_test_case.yaml -o out/ -I YamlStrategy
```

`tests/build.py` supports Google Drive URLs as input (`-i https://drive.google.com/...`), downloading
to a temp dir first; restricted files need service-account credentials at `auth/google.json`. See
`.vscode/launch.json` for the full matrix of real-world example inputs/strategies used during
debugging, and `docs/cli-and-inputs.md` for all flags.

## Architecture

The pipeline runs in distinct stages — understanding *which stage* a bug lives in is usually the
fastest way to navigate this codebase (full detail in `docs/pipeline.md`):

1. **Input collection** — `tests/build.py` resolves CLI args/URLs into raw file content strings.
2. **XML parsing** — `tricc_oo/parsers/xml.py` (`read_drawio`) parses draw.io's `mxfile` XML via `lxml`.
   (`YamlStrategy` bypasses this for test fixtures.)
3. **Page/activity creation** — `tricc_oo/converters/xml_to_tricc.py` (`create_activity`) builds
   activity objects from nodes/edges, interprets edge labels (yes/no, factors, conditions), and
   enriches nodes with hints/help/media.
4. **Graph linking** — `DrawioStrategy.linking_nodes` wires next/prev pointers, resolves `goto`
   traversal (including repeated-activity instances), and connects `link_out`→`link_in`.
5. **Calculate load, versioning, inheritance** — the core transformation engine, in
   `tricc_oo/visitors/tricc.py`, orchestrated by `load_calculate` (~4200 lines; this is the file
   you'll spend the most time in for logic bugs). Handles export-name versioning
   (`set_last_version_false`), multi-version inheritance merging (`get_version_inheritance`,
   `GET_INHERITED_VALUE`), and relevance/skip propagation. See
   `docs/testing/transformation-test-coverage.md` for a method-by-method map to test cases.
6. **Output strategy execution** — the selected strategy (`-O`) serializes the processed graph.

### Strategy pattern + registry

Input and output formats are pluggable strategies registered declaratively:

```python
from tricc_oo.strategies.registry import register_input_strategy, register_output_strategy, get_output_strategy

@register_output_strategy("MyStrategy")
class MyStrategy(BaseOutputStrategy):
    ...

get_output_strategy("MyStrategy")   # by name
get_output_strategy(MyStrategy)     # or pass the class directly (handy in tests)
```

Built-in strategies are eagerly imported in `tricc_oo/strategies/__init__.py` so their decorators
run at import time — a strategy name reported as "unknown" at runtime usually means its module isn't
imported there. Output strategies form an inheritance chain worth knowing:
`XLSFormStrategy` → `XLSFormCDSSStrategy` → `XLSFormCHTStrategy` → `XLSFormCHTHFStrategy`, and
separately `FHIRStrategy` → `OpenSRPStrategy`. `tricc_oo/strategies/output/base_output_strategy.py`
and `input/base_input_strategy.py` define the contracts new strategies must implement.

### Data model

- `tricc_oo/models/base.py` — `TriccNodeBaseModel` and the `TriccNodeType` enum (all node kinds:
  flow anchors, questions, inputs, calculate/logic, navigation, diagnosis).
- `tricc_oo/models/calculate.py` / `models/tricc.py` — `TriccOperation` + `TriccOperator` (the
  expression system) and `TriccProject`/activity/page containers.
- Pydantic models throughout; graph nodes are connected via edges with optional labels, processed in
  topological order where possible.

### FHIR / CQL specifics

When touching `FHIRStrategy` or `OpenSRPStrategy` (`tricc_oo/converters/fhir/`,
`tricc_oo/strategies/output/fhir_form.py`, `opensrp.py`): route resource access through a single
Helper CQL library keyed by concept, keep per-segment libraries thin, and use unqualified `define`
names in Questionnaire expressions — never raw QuestionnaireResponse item paths in CQL.
In-form FHIRPath uses `%resource.repeat(item).where(linkId=...)` and, for choice answers,
`.answer.valueCoding.code`. Full architecture in `docs/desing/FHIRcore.md`; user-facing
export guide in `docs/open-srp-export.md`. See the "FHIR CQL / Library Generation" section
below for the detailed rules.

## Coding Standards

### General Guidelines
- Follow PEP 8 style guide
- Maximum line length: 120 characters
- Use type hints with Pydantic models
- Write docstrings for public functions and classes
- Prefer composition over inheritance where appropriate
- Use logging instead of print statements

### Python Conventions
- Use `snake_case` for variables and functions
- Use `PascalCase` for class names
- Use `UPPER_CASE` for constants
- Private methods/attributes prefixed with underscore
- Module-level docstrings for packages

### Error Handling
- Use specific exception types
- Log errors with appropriate levels (debug, info, warning, error, critical)
- Fail early with clear error messages
- Validate inputs at boundaries

### Testing
- Write unit tests for new functionality
- Use existing test patterns in `tests/` directory
- Test both happy paths and edge cases
- Maintain test coverage for critical paths

## Domain-Specific Patterns

### Node Types
The system uses various node types defined in `TriccNodeType` enum:
- **Flow anchors**: `start`, `activity_start`, `activity_end`, `end`
- **Questions**: `select_one`, `select_multiple`, `select_yesno`, `note`
- **Inputs**: `integer`, `decimal`, `text`, `date`
- **Logic**: `calculate`, `rhombus`, `wait`, `add`, `count`
- **Navigation**: `goto`, `link_in`, `link_out`, `bridge`
- **Diagnosis**: `diagnosis`, `proposed_diagnosis`

### Expression System
- Expressions are built using `TriccOperation` with `TriccOperator` enum
- Operators include boolean logic, arithmetic, comparisons, and domain-specific functions
- Use `TriccReference` for variable references
- Expressions are evaluated lazily during graph processing

### Strategy Pattern
- Input strategies: `DrawioStrategy` (default)
- Output strategies: `XLSFormStrategy`, `XLSFormCHTStrategy`, `XLSFormCHTHFStrategy`, etc.
- Each strategy handles specific conversion requirements

### Graph Processing
- Nodes are connected via edges with optional labels
- Processing follows topological order when possible
- Support for multiple activity instances and cross-page linking
- Experimental pages have limited processing

## Feature Development Workflow

New capabilities follow a **two-step gate** before code changes land:

### Step 1 — Feature specification (`feature/`)

1. Create `feature/<YYYYMMDD>-<feature-name>.md` (or update an existing spec) — see
   "Feature file naming" below for why the date is required.
2. Structure the document in **two parts**:
   - **Part I — Business description** — for clinical authors, guideline developers, and implementers evaluating workflows. Plain language, examples, benefits, limitations. No file paths or function names unless unavoidable.
   - **Part II — Technical specification** — for developers: formal semantics, pipeline, code checklist, tests, acceptance criteria, implementation phases.
3. Set the status table at the top to **`Draft`**.
4. Do **not** implement until the spec is approved.

### Step 2 — User approval

1. The user reviews Part I (and Part II if needed).
2. When the user approves, update the spec status to **`Approved`** in the same `feature/<feature-name>.md` file.
3. Only then begin implementation, following Part II.
4. After implementation and tests pass, update status to **`Implemented`**.

**Status values:** `Draft` → `Approved` → `Implemented` → `Superseded`

Example specs live under `feature/` (e.g. `feature/concept-repeat.md`).

### Feature file naming (dating for chronological order)

Feature filenames **should embed a `YYYYMMDD` date**: `feature/YYYYMMDD-<feature-name>.md`
(e.g. `feature/20260811-careplan-orchestration.md`). Specs are often drafted or revised in
parallel across branches before merge, and git commit timestamps alone don't reliably show
"which spec supersedes which" when just browsing the `feature/` directory or comparing
branches — a filename date makes relative recency visible at a glance, without git archaeology.

- Use the date of the **most recent substantive edit**, not the original creation date.
- **Rename the file** (`git mv`) each time the spec is substantively revised, bumping the date
  prefix to the revision date. Do this on every substantive update **until the spec reaches
  `Implemented` or `Superseded`** — at that point the content (and filename) is frozen; stop
  renaming.
- When renaming, update any cross-references to the old filename in other `feature/*.md`
  files' "Related" rows.
- A different mechanism than a filename date is acceptable, provided it still (a) makes
  relative recency visible without comparing branches or digging through git log, and (b)
  doesn't rely on a shared/centralized index or counter file that every branch would need to
  edit — that generates merge conflicts and defeats the purpose.

## Fix / issue analysis workflow (`fix/`)

Use `fix/` when the work is **correcting existing behaviour** (wrong FHIRPath, broken
export, regression), not adding a capability. The gate and file shape match `feature/`:

1. Create `fix/<YYYYMMDD>-<issue-name>.md` (same dating / rename rules as feature files).
2. Structure the document in **two parts**:
   - **Part I — Issue analysis** — symptoms, who is affected, expected vs actual, what is
     out of scope (author content vs exporter bugs). Plain language first.
   - **Part II — Fix approach** — root cause, formal emission/semantics rules, code
     checklist, tests, acceptance criteria.
3. Set the status table to **`Draft`**. Do not implement until the spec is approved.
4. After approval → **`Approved`**, implement, then **`Implemented`**.

**Status values:** `Draft` → `Approved` → `Implemented` → `Superseded`

Do **not** put new-capability specs in `fix/`, and do **not** use `feature/` for
issue-analysis write-ups. Cross-link the other folder only from the Related row.

Example: `fix/20260813-fhirpath-choice-answers.md`.

## Documentation Requirements

### When Adding Features
1. Complete Step 1 and Step 2 above (feature MD + user approval) before coding
2. Update relevant documentation in `docs/` directory
3. Add inline code comments for complex logic
4. Update README if user-facing changes
5. Add type hints to all function signatures
6. Include docstrings with Args, Returns, Raises sections

### Documentation Structure
- `docs/getting-started.md` - Installation and basic usage
- `docs/cli-and-inputs.md` - Command-line interface documentation
- `docs/tricc-elements.md` - Element reference and semantics
- `docs/pipeline.md` - Processing pipeline explanation
- `docs/visual-authoring-concepts.md` - Visual design patterns
- `docs/troubleshooting.md` - Common issues and solutions
- `docs/desing/FHIRcore.md` - Detailed spec for the FHIR / OpenSRP output strategy (including CQL architecture)
- `docs/open-srp-export.md` - User-facing guide for OpenSRP/FHIR-Core export
- `docs/planning/` - Implementation plans (e.g. FHIR remediation plan)

## Common Workflows

### Adding a New Output Strategy
1. Create class inheriting from `BaseOutputStrategy`
2. Implement required methods: `convert()`, `validate()`
3. Register strategy using `@register_input_strategy("Name")` or `@register_output_strategy("Name")` (see `tricc_oo/strategies/registry.py`)
4. Add tests for conversion logic
5. Document strategy capabilities and limitations

**FHIR-specific notes** (when working on `FHIRStrategy` / `OpenSRPStrategy`):
- Follow the refined CQL architecture: one Helper library + thin per-segment libraries.
- Use simple names in Questionnaire expressions.
- Prefer concept-driven data access in the Helper library over raw paths.
- Update the FHIR remediation plan and main docs when making architectural changes.

### Adding a New Node Type
1. Add to `TriccNodeType` enum in `models/base.py`
2. Define Pydantic model inheriting from `TriccNodeBaseModel`
3. Update `drawio_type_map.py` for XML mapping
4. Implement conversion logic in appropriate converter
5. Add to documentation in `docs/tricc-elements.md`

### Modifying Expression Logic
1. Update `TriccOperator` enum if new operators needed
2. Modify expression building in `converters/` directory
3. Update operator mappings and evaluation logic
4. Add comprehensive tests for expression evaluation
5. Document operator behavior and return types

### FHIR CQL / Library Generation (FHIRStrategy)
- `calculatedExpression` is **FHIRPath-only** (openSRP/FHIR-Core does not evaluate CQL through it) — never emit a CQL identifier there. `initialExpression` is the **only** extension allowed to carry CQL (`text/cql-identifier` / `text/cql`), evaluated once at `$populate`.
- `generate_calculate()` routes each calculate node by whether at least one of its references is itself an item in the *same* Questionnaire (reachable via `%resource.repeat(item).where(linkId=...)`): if so, emit a live `calculatedExpression` in FHIRPath; otherwise the value depends on data outside the form (e.g. observation history) and must be computed once via CQL `initialExpression` instead.
- In-form FHIRPath **must** walk nested groups with `%resource.repeat(item).where(linkId=...)` — never a top-level-only `%resource.item.where(...)`.
- Select-option `relevance` is emitted as SDC `answerOptionsToggleExpression` on the parent choice item (`fix/20260813-option-relevance-toggle.md`), not as a hidden Questionnaire item.
- Choice / open-choice answers are `valueCoding`. Membership tests (`SELECTED` / `CONTAINS`) emit `…answer.where(value.code = '<code>').exists()`. Scalar comparisons on primitives keep `.answer.value`. See `fix/20260817-choice-membership-and-group-relevance.md`.
- Use a **Helper** library for all FHIR resource access (Observations, Conditions, etc.) keyed by concept name/code — only reachable from the CQL/`initialExpression` path, never from FHIRPath.
- Keep per-process/segment libraries **thin** — they should mostly contain named `define` statements that delegate to the Helper.
- In `initialExpression`, use **simple define names only** (e.g. `"Calc_bmi"`). Do not qualify with library name.
- Pre-loaded values are one node type (`TriccNodePopulate`; the drawio `input` keyword is a legacy alias defaulting to `context=encounter`). Their accessor is **resource-specific**: `GetEncounterObservationValue` / `GetEncounterConditionValue` (and the `GetHistory*` pair), both scoped to the current encounter through the `encounterid`-filtered `GetObservations`/`GetConditions`. `GetEncounterValue` remains only as a deprecated alias. See `fix/20260821-merge-input-into-populate.md`.
- A calculate whose expression cannot be derived emits **no** expression — never a constant `true`. The output pass stashes a node whose prevs it has not visited yet, and XLSForm supplies ODK's required `1` at serialization time. See `fix/20260821-output-pass-calculate-readiness.md`.
- Each Questionnaire emits a `linkId` **once**. `generate_base` skips a node already in `processed_nodes` and skips an export name that is already an item of that Questionnaire (the output walk re-stashes fan-in hubs). After calculate / relevance / extraction, unused hidden calculates are dropped from **this** Questionnaire when nothing here reads their `linkId`, they have no `initialExpression`, and they are not an extraction source. Still one Questionnaire per process. See `fix/20260821-opensrp-questionnaire-duplicate-calculates.md`.
- Each item has **at most one** `calculatedExpression` / `initialExpression` / `enableWhenExpression`. Re-visits replace the existing extension; a second copy crashes openSRP FHIR Data Capture at render. See `fix/20260821-sdc-singleton-expressions.md`.
- Numeric calculates are Questionnaire `integer` / `decimal` (not `string`). Relational FHIRPath casts operands with `.toDecimal()` — HAPI cannot compare string to integer (`age_in_months >= 2`). See `fix/20260821-fhirpath-numeric-compare.md`.
- Questionnaire items follow authored edge order (first next-node first). The output walk is a stack: pushing `next_nodes` in list order used to reverse siblings so the registration / clinician-script page appeared last. See `fix/20260823-questionnaire-item-order.md`.
- Multi-version values (`GET_INHERITED_VALUE`, emitted when the same question/calculate is reachable on several paths) are **not** plain `coalesce` here: FHIRPath unions only the versions captured in the *current* Questionnaire, newest first, and reads the winning answer (`(v2.answer | v1.answer).where($this.exists()).first().value[.code]`); with no version in this process the value comes from the encounter dedup `initialExpression`, and CQL deduplicates the concept-keyed Helper accessors instead of emitting `Coalesce(x, x)`. See `fix/20260820-opensrp-inherited-value.md`.
- The Questionnaire declares its library/libraries at the top level (via `library` element or SDC `cqlInputResources` extension).
- Avoid embedding raw questionnaire answer paths (`%resource.repeat(item).where(...)`) in CQL. Route data access through the Helper using concept identifiers. (FHIRPath expressions, by contrast, use `%resource.repeat(item).where(...)` directly — that's the whole point of using FHIRPath for in-form calculations.)
- Follow patterns from pyfhirsdc and WHO SMART CQL examples (thin form libs + rich base/helper libs).
- When adding new CQL helpers or changing the template, update `docs/desing/FHIRcore.md` and `docs/open-srp-export.md`.

## Validation Checklist

Before committing code changes:

- [ ] Code follows PEP 8 and project style (120 char lines)
- [ ] All public functions have type hints
- [ ] Docstrings added for public APIs
- [ ] No print statements (use logging)
- [ ] Error handling is appropriate
- [ ] Tests pass (`python -m pytest tests/`)
- [ ] Documentation updated if needed
- [ ] No breaking changes to existing APIs
- [ ] Import statements are clean and organized
- [ ] No hardcoded values (use constants/config)
- [ ] Security considerations addressed (file paths, injections)

## Testing Guidelines

### Running Tests
```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python tests/test_cql.py

# Build and test conversion
python tests/build.py -i tests/data/demo.drawio -o tests/output/
```

### Test Data
- Use files in `tests/data/` directory
- Draw.io files: `demo.drawio`, `combacal.drawio`, `etat.drawio`
- YAML fixtures (preferred for transformation testing): `tests/data/yaml/`
- JSON files for specific formats: `medlacreator.json`

See `docs/testing/transformation-test-coverage.md` for a detailed mapping of core transformation methods (`load_calculate`, inheritance/versioning, expression generation, etc.) to recommended test cases.

### Expected Outputs
- Check `tests/output/` directory for generated files
- Compare against expected outputs
- Validate XLSForm, CHT, or other format-specific outputs

## Debugging Tips

### Common Issues
1. **XML Parse Errors**: Check draw.io file format (must be valid XML)
2. **Expression Errors**: Verify operator syntax and reference validity
3. **Graph Errors**: Check for cycles or disconnected nodes
4. **Strategy Errors**: Ensure correct strategy for output format

### Logging
- Use `logger.debug()` for detailed processing info
- Use `logger.warning()` for recoverable issues
- Use `logger.error()` for failures
- Check `log.txt` for execution logs

### Validation
- Use `tricc_type` to identify node types
- Check `instance` numbers for multi-instance activities
- Verify edge connections and labels
- Validate expression references exist in graph

## Performance Considerations

- Process large diagrams incrementally when possible
- Cache computed expressions to avoid recalculation
- Use efficient data structures (OrderedSet for ordered collections)
- Profile before optimizing critical paths
- Consider memory usage for large graphs

## Security Notes

- Validate file paths to prevent directory traversal
- Sanitize user inputs in expressions
- Be cautious with XML parsing (XXE prevention)
- Validate external URLs before downloading
- Use appropriate file permissions for outputs

## Resources

- **Main Repository**: https://github.com/SwissTPH/tricc
- **Documentation**: https://swisstph.github.io/tricc/
- **Issue Tracker**: https://github.com/SwissTPH/tricc/issues
- **PyPI Package**: tricc-oo

## Quick Reference

### Important Files
- `tricc_oo/models/base.py` - Core data models
- `tricc_oo/converters/xml_to_tricc.py` - Draw.io to TRICC conversion
- `tricc_oo/strategies/` - Input/output strategy implementations
- `tests/build.py` - Main entry point for conversions
- `pyproject.toml` - Project configuration and dependencies

### Key Commands
```bash
# Convert a drawio file
tricc -i input.drawio -o output/

# Specify output strategy
tricc -i input.drawio -o output/ -O XLSFormCHTStrategy

# Set form ID
tricc -i input.drawio -o output/ -d my_form_id

# Set log level
tricc -i input.drawio -o output/ -l d  # debug
```

### Common Patterns
- Use `generate_id()` for creating unique identifiers
- Use `get_rand_name()` for human-readable names
- Use `OrderedSet` for maintaining order without duplicates
- Use Pydantic validation for data integrity
- Follow strategy pattern for extensibility

## file changes request format

SEARCH AND REPLACE ARE MANDATORY
``` 
------- SEARCH
            var ftpClient = GetOrCreateFtpClient(machineName);
=======
            var ftpClient = GetOrCreateFtpClient(machineName);
            X
+++++++ REPLACE
```