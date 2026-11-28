# Decision tables: `DMN(table, …)` lookups, with `DrugDosage` as an alias

| Field             | Value |
| ----------------- | ----- |
| **Status**        | Implemented (2026-11-23; approved 2026-11-23, in conversation) |
| **Branch target** | `feature/decision-tables` → `develop` |
| **Scope**         | `models` (`project_config`), `converters/cql_to_operation`, `visitors/tricc` (`load_calculate`), all output strategies through `IFS` (`XLSFormStrategy` → `XLSFormCHTStrategy`, `FHIRStrategy` → `OpenSRPStrategy`, `OpenMRSStrategy`, `DHIS2Strategy`) |
| **RFC**           | #85 (implementation #91) |
| **Related** | `tricc-frontend/feature/20261120-decision-table-editor.md` (mirror: the table editor, SwissTPH/tricc-frontend#51), `feature/20261123-dmn-named-overrides.md` (RFC #96: named overrides, `null` inputs), `feature/20261123-dmn-instance-lookup.md` (large tables as ODK instances, zscore on tables), `fix/20261118-fhir-end-node-process-skip.md` (origin: the empty diazepam dose in FHIR), `feature/20261111-block-params-and-start-node.md` (not needed: a function, not a block) |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

### The problem

Dosing tables and similar lookups ("from 6 kg, give 0.75 ml") live outside TRICC today. In
CHT they are JavaScript (`drugs.js`, called through `DrugDosage(...)`), which only CHT can run:
the FHIR / OpenSRP export has no dose at all (the convulsion treatment text in the Global
Almanach shows an empty diazepam dose), ODK has none either, and the tables cannot be reviewed
or changed by a clinical author.

A dose usually depends on what was just entered (the weight measured in this visit), so it
must be computed in the form, offline, on Android and on the web.

### What changes for an author

- A lookup is a **decision table**: one YAML file per table in the project, with input
  columns (each a concept: weight, age, …), output columns (dose, text, …) and rows read top
  to bottom. The table's **hit policy** says how matching rows give the result: **first**
  (the first matching row, order matters; the default), **unique** (at most one row can
  match, checked at load) or **rule order** (the list of every matching row's output, in row
  order). Counts, "does any row match" and scores are built on that list (`Count`, `exists`,
  `Sum`).
- An expression calls it like a function: `DMN('diazepam', "CHE.B6.DE07", "age_in_months")`,
  arguments in the order of the input columns. It can be used anywhere an expression is.
  `DMN` uses the table's hit policy; `DMNFirst(…)` and `DMNList(…)` override it for one call.
- `DrugDosage('diazepam', age, weight)` keeps working as an alias: existing drawings (31
  drugs in the Global Almanach) need no change.
- Every export computes it from the same table: in the form when the inputs are in the form
  (FHIRPath in FHIR, XPath in ODK, a library generated from the tables in CHT), from the
  record otherwise (CQL), like any other calculation. `drugs.js` is no longer needed.

Example (`tables/diazepam.yaml`):

```yaml
id: diazepam
title: Diazepam, rectal (ml)
hit_policy: first
inputs:
  - name: weight
    concept: CHE.B6.DE07      # kg
    type: decimal
  - name: age
    concept: age_in_months
    type: integer             # rounded down before the tests
outputs:
  - name: dose
    type: string
rules:                        # one cell per input, then the outputs
  - [">= 20",    "-",        "2.5"]
  - ["[15..20)", "-",        "1.7"]
  - ["[10..15)", "-",        "1.2"]
  - ["[6..10)",  "-",        "0.75"]
  - ["[3..6)",   "-",        "0.4"]
  - ["-",        ">= 36",    "1.7"]   # no usable weight: by age
  - ["-",        "[12..36)", "1.2"]
  - ["-",        "[5..12)",  "0.75"]
  - ["-",        "[2..5)",   "0.4"]
```

The age rows also catch a weight below the first threshold, as `drugs.js` does; a cell `null`
("empty") instead restricts them to "no weight entered".

### Out of scope

- zscore: the WHO LMS tables (≈1,800 rows each) stay a built-in operator with their data files.
- Full DMN / FEEL: no expressions in cells, no other hit policies than `first`, `unique` and
  `rule_order` (no `last`, DMN `any`, `priority`, `output order` or `collect` aggregations:
  those are built from the list), no decision requirement graphs. DMN XML is an import / export format only.
- Tables whose rows depend on runtime data other than their inputs.

---

## Part II — Technical specification

### 1. Design

**Files.** `tricc.yaml` gains:

```yaml
decision_tables:
  - tables/*.yaml            # globs, relative to the project
aliases:
  DrugDosage: {function: DMN, args: [table, age, weight]}   # call args → table inputs by name
```

`ProjectConfig` (`tricc_oo/models/project_config.py`) loads them into
`project.decision_tables: Dict[str, DecisionTable]` (new model in `tricc_oo/models/decision_table.py`:
`id`, `title`, `hit_policy: first | unique | rule_order` (default `first`; DMN XML `FIRST`,
`UNIQUE`, `RULE ORDER`), `inputs: [Column]`, `outputs: [Column]`, `rules: [[str]]`).

**Cells** (a FEEL unary-test subset, parsed once at load into `TriccOperation`s on a
placeholder operand):

| Cell | Test |
|---|---|
| `-` | any value (no test) |
| `null` / `not(null)` | empty / not empty |
| `< v`, `<= v`, `> v`, `>= v`, `= v`, `v` | comparison / equality (`v` number, `'text'`, `true`/`false`) |
| `[a..b)`, `(a..b]`, `[a..b]`, `(a..b)` | range, bracket = inclusive |
| `a, b, c` | any of |

Output cells are literals of the column type.

**Call.** `cql_to_operation.FUNCTION_MAP` gets `DMN` → `TriccOperator.DMN` (`table`, `*args`);
the first argument must be a string literal (`E_DMN_TABLE_NOT_STATIC`). `DMNFirst` and
`DMNList` map to the same operator with the policy forced to `first` / `rule_order`; `DMN`
takes the table's. The policy sets the result type: one value for `first` / `unique`, a list
for `rule_order`. `DMN('t', …)` returns
the first output; `DMN('t.output', …)` a named one. An alias is rewritten to `DMN` by the
parser, mapping its arguments to inputs by name; `DrugDosage` stays a built-in alias when the
project declares no other, replacing `TriccOperator.DRUG_DOSAGE`.

**Expansion.** In `load_calculate` (before references are resolved), each `DMN` operation is
expanded according to its policy, with one `(and of the row's cell tests on the bound
arguments, output literal)` pair per row, in row order:

| Policy | Operation | FHIRPath | XPath (CHT, ODK) | CQL |
|---|---|---|---|---|
| `first`, `unique` | `IFS`, no default (empty) | nested `iif` | nested `if` | `case` |
| `rule_order` | new `TriccOperator.LIST_IF` (pairs → outputs whose test holds) | `iif(c1, v1, {}).combine(iif(c2, v2, {}))…` (`combine`, not `\|`, keeps duplicates) | `normalize-space(concat(if(c1, 'v1', ''), ' ', if(c2, 'v2', '')…))`, a space-separated list that `selected()` and `count-selected()` read | `flatten { if c1 then {v1} else {}, … }` |

`LIST_IF` is added to every strategy; OpenMRS and DHIS2 follow their `IFS` serialisation and
are checked in phase 2. In XPath a list value cannot contain a space (`E_DMN_LIST_VALUE`).

An `integer` input is wrapped
in a floor. `unique` checks at load that no two rows can both match on the cell intervals
(`E_DMN_OVERLAP`) and is otherwise exported like `first`. A column with a `concept` and no
argument at the call reads that concept.

Every strategy already serializes `IFS` (FHIRPath nested `iif`, XPath nested `if`, CQL `case`,
OpenMRS, DHIS2), and the calculate follows the usual rule: `calculatedExpression` (FHIRPath)
when its inputs are in the Questionnaire, `initialExpression` (CQL) otherwise. No strategy
change is needed beyond removing the `DRUG_DOSAGE` handlers (`fhir_form.py` raises today,
`xlsform_cht.py` calls `drugs.js`).

**Migration.** `tricc_oo/tools/drugs_js_to_tables.py` reads a `drugs.js` (its two tables) and
writes one YAML table per drug: weight rows, then age rows with weight `-`; non-numeric doses
(`"-"`, `"--"`, `""`) kept as text.

### 2. Validation and errors

`E_DMN_TABLE_UNKNOWN`, `E_DMN_TABLE_NOT_STATIC`, `E_CALL_ARITY` (argument count ≠ inputs; was
`E_DMN_ARITY` before RFC #101),
`E_DMN_CELL` (cell syntax, with table / row / column), `E_DMN_TYPE` (cell value vs column
type, or a list result used as one value), `E_DMN_OVERLAP` (`unique`), `E_DMN_LIST_VALUE` (a list output value with a space, XPath),
`E_ALIAS_UNKNOWN_INPUT`. A table no call uses is a warning.

### 3. Tests

- Cell parser: every form of §1, errors.
- Expansion: the diazepam table to `IFS` and, with `DMNList`, to `LIST_IF`; FHIRPath /
  XPath / CQL output strings (25 kg and 40 months: `first` → 2.5, list → 2.5 and 1.7).
- Global parity: for each of the 31 generated tables, the expansion and `drugs.js` (run with
  node) give the same dose on a grid of weights and ages, including empty weight and weight
  below the first threshold.
- End to end: `tests/data/yaml/decision_table.yaml` built with `OpenSRPStrategy` and
  `XLSFormCHTStrategy`; a UAT scenario on Global (weight 11.5 kg → diazepam 1.2 in the
  convulsion text).

### 4. Phases

1. Model, `tricc.yaml` keys, cell parser, validation.
2. `DMN`, `DMNFirst`, `DMNList`, expansion to `IFS` and `LIST_IF`, aliases (`DrugDosage`), removal of `DRUG_DOSAGE`.
3. `drugs_js_to_tables.py` and the Global tables (in the Global repo), parity test.
4. Docs: `docs/tricc-elements.md` (expressions), `docs/nodes/` page for decision tables.

---

## Open questions

None. The three questions of the RFC were settled with their recommendations (see Decisions).

## Implementation notes

Where the code differs from, or adds to, Part II:

- **Where the expansion runs.** `tricc_oo/converters/decision_table.py`
  `expand_project_tables` runs at the start of `DrawioStrategy.process_pages` (shared by
  `YamlStrategy`), before linking: activity instances then copy the expanded expressions, and
  `node.reference` is rebuilt from them, so the walk waits for the inputs a call reads.
  `load_calculate` repeats the per-node expansion as a safety net (`decision_tables` /
  `aliases` kwargs).
- **Representation.** `DMN`, `DMNFirst`, `DMNList` and `DrugDosage` parse to
  `TriccOperator.DMN` with the call name as first operand (`TriccStatic`); an alias declared
  in `tricc.yaml` parses as `NATIVE` and is recognised by name at expansion.
- **Literals are folded.** A literal or `null` argument is tested at expansion: rows it fails
  are dropped, tests it passes are removed (`DMN('diazepam', 11.5, 24)` is `'1.2'`). A call
  where no row can match gives an empty value, with a warning.
- **Floor.** New `TriccOperator.FLOOR`: XPath `int()` (JavaRosa has no `floor()`; the same for
  the non-negative values a table rounds down), FHIRPath `.floor()`, CQL `Floor()`.
- **IFS.** The CQL `tricc_operation_ifs` now reads `[cond, value]` pairs like the XLSForm and
  FHIRPath ones; OpenMRS and DHIS2 got pair-aware `IFS`, `LIST_IF` and `FLOOR`. Neither
  strategy runs on `develop` (`OpenMRSStrategy` is abstract, `DHIS2Strategy` is not
  registered), so their serialisers are unit-tested only.
- **FHIR list item.** A calculate whose expression is a `LIST_IF` gets `repeats: true` (several
  answers). As for any repeating item, display text that references it keeps its static text;
  read it through `Count(…)` (`.answer.count()`) or `selected`.
- **Global tables.** The vendored `drugs.js` (`tests/data/decision_tables/drugs.cjs`, the
  frontend fixture) has 33 drugs, not 31. The tool and the parity test are here; writing the
  tables into the Global repo is left to that repo.
- **Errors.** `DecisionTableError(code, message)` (a `ValueError`); table files fail at load,
  calls at expansion with the node named. `E_DMN_SHAPE` (row width, bad file) and the
  #96 codes `E_DMN_ARG_UNKNOWN` / `E_DMN_ARG_TWICE` are added (renamed `E_CALL_ARG_UNKNOWN` /
  `E_CALL_ARG_TWICE` by RFC #101). "A list result used as one
  value" (`E_DMN_TYPE`) is not checked.
- **CHT extension library** (added 2026-11-23). The runner tells the input stage whether the
  output strategy evaluates tables itself (`decision_table_calls = True` on
  `XLSFormCHTStrategy`); then each expansion that is not a constant is kept as
  `DMN_CALL(inline expansion, table, policy, output, one argument per input)`, so the arguments
  are resolved and versioned like any operand. Other strategies never see `DMN_CALL`. CHT
  writes `cht:extension-lib('dmn-<project>.js', 'table', 'policy', 'output', input1, …)` (each
  field read once, instead of once per row inline) and `extension-libs/dmn-<project>.js`
  (`tricc_oo/serializers/dmn_js.py`: an ES5 evaluator and every table of the project, cells
  parsed; the same file for every intervention). A `null` argument is passed as `''`.
- **`IFS` / `CASE` datatype.** `TriccOperation.get_datatype` read a slice instead of the branch
  values; it now returns the type of the values.
- **Tests.** `tests/test_decision_tables.py`: the shared vectors (copied unchanged into
  `tests/data/decision_tables/`), the expansion evaluated against them, serialisation per
  strategy, errors, the editor's file format, parity with `drugs.js` (run with node; skipped
  without it), and end to end on `tests/data/projects/decision_tables/` (a project folder:
  tables need `tricc.yaml`) with `XLSFormStrategy` (inline), `XLSFormCHTStrategy` (library) and
  `OpenSRPStrategy`; the generated library run with node against the vectors, every cell form
  and `drugs.js`.

## Decisions

- 2026-11-20: hit policies `first` (default), `unique` and `rule_order` (list); `DMNFirst` /
  `DMNList` override at the call; no `last` or boolean "any": built from the list (@delcroip)
- 2026-11-23: output selection is `DMN('t.output', …)`; `DrugDosage` is a built-in alias, others
  are declared per project in `tricc.yaml` `aliases`; CHT `drugs.js` is dropped (the migration
  tool can be extended if a project needs it) — the RFC's recommendations, approved with the
  implementation request (@delcroip, in conversation)
- 2026-11-23: CHT evaluates the tables in a generated extension library by default, named per
  project (`dmn-<project>.js`); an inline CHT strategy can be added if the library causes
  problems (@delcroip, in conversation)
