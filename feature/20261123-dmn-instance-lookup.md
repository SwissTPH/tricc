# Large decision tables as ODK secondary instances; zscore on decision tables

| Field             | Value |
| ----------------- | ----- |
| **Status**        | Implemented (2026-11-24; approved 2026-11-23, in conversation) |
| **Branch target** | `feature/dmn-instance-lookup` → `develop` (after `feature/decision-tables`, PR #99) |
| **Scope**         | `XLSFormStrategy` → `XLSFormCDSSStrategy` → `XLSFormCHTStrategy`, `FHIRStrategy`, `converters/decision_table`, `models` (`project_config`, `base`), `data/anthro` |
| **Related**       | `feature/20261123-decision-tables.md` (RFC #85: the tables, the inline expansion, the CHT library), `feature/cdss-zscore.md` (superseded by this spec: zscore tables and their secondary instance) |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

### The problem

In ODK a decision table is written into the form as one long condition per row. Each input is
read again for each row. That is fine for a dosing table of ten rows, but a growth chart has
hundreds of rows (weight-for-age: 135 points per sex), which makes the expression too long.

Zscore has its own lookup, written separately for each export: a list of chart rows in ODK, an
extension library the project must provide in CHT, nothing in FHIR. The ODK form also lacked
part of what ODK needs to read the list.

### What changes for an author

- Nothing in the expressions. A large table is read from a list attached to the form instead of
  being written inline. A table with more than **10 rows** is large; `tricc.yaml` can change
  the number:

  ```yaml
  decision_table_max_inline_rows: 10   # 0: always the list; a big number: always inline
  ```

- `Zscore('wfa', sex, age_in_days, weight)` and `Izscore(…)` are built on a decision table
  (`wfa`: inputs `sex` and age, outputs `l`, `m`, `s`). The table ships with TRICC; a project
  table with the same id replaces it. `DMN('wfa.m', sex, age)` reads one value directly.
- Every export computes zscore: ODK reads the list, CHT the generated `dmn-<project>.js`,
  FHIR the inline expansion. The CHT `wfa.js` library is no longer needed.

### Out of scope

- Calls inside a repeat, in list mode: the form field is read from the list's context. Not
  needed today; the inline mode works there.
- Choosing the mode in the table file: that format is shared with the editor.
- Other charts than `wfa` (they are data files of the same shape).

---

## Part II — Technical specification

### 1. Mode choice

`XLSFormStrategy.decision_table_calls = True`, so ODK and CDSS receive the kept `DMN_CALL`
(inline expansion, table, policy, output, arguments), like CHT. `table_call_expression` emits
the inline expansion when the table has at most `project.decision_table_max_inline_rows`
rows (`tricc.yaml` key, default 10), the list lookup otherwise. CHT keeps its library.

### 2. List encoding

The table becomes the choice list `dmn_<table>` (also the instance id). A list cell (`a, b`)
becomes one item per value (the cartesian product when several cells are lists). Columns:

| Column | Content |
|---|---|
| `name`, `label` | `r<row>` or `r<row>_<n>`; the label repeats the name (a select needs labels) |
| `i<k>_k` | test of input `k`: `a` any, `n` null, `v` not null, `e` equal (text), `t` / `f` true / false, `r` number range |
| `i<k>_lo_k`, `i<k>_hi_k` | for `r`: `n` no bound, `i` inclusive, `x` exclusive |
| `i<k>_lo`, `i<k>_hi`, `i<k>_eq` | the bound or the text |
| `o<j>` | output `j` |

A comparison is a range with one bound; a number `= v` is `[v..v]`. pyxform leaves empty cells
out of the items, so a column is only read when the item's flag says it is set.

The predicate is the same for every item, built per input from the kinds the column uses
(an input whose column is all `-` is left out). With `R` the argument and `N` its number
(`int(R)` for an integer column, as inline):

```
(i0_k='a' or (i0_k='n' and R='') or (i0_k='v' and R!='') or (i0_k='e' and R=i0_eq)
 or (i0_k='r' and R!='' and (i0_lo_k='n' or (i0_lo_k='i' and N>=i0_lo) or (i0_lo_k='x' and N>i0_lo))
                       and (i0_hi_k='n' or (i0_hi_k='i' and N<=i0_hi) or (i0_hi_k='x' and N<i0_hi))))
```

`t` / `f` use the inline equality test on `true` / `false`. Result:

| Policy | XPath |
|---|---|
| `first`, `unique` | `instance('dmn_t')/root/item[pred][1]/o0` |
| `rule_order` | `join(' ', instance('dmn_t')/root/item[pred]/o0)` |

Under `rule_order`, two values of one list cell that can both match would give the output
twice: refused (`E_DMN_LIST_OVERLAP`). Under the other policies a duplicate is harmless.

**Instance in the form.** At export, each table read in list mode adds its items to the
choices sheet and one hidden `select_one dmn_<table>` (`relevant` `false()`), so every pyxform
version writes the instance into the XForm.

### 3. Zscore

`data/anthro` builds `wfa` as a `DecisionTable` (inputs `sex` string, `x` decimal; outputs
`l`, `m`, `s` decimal; one `first` row per LMS point: `'male'`, `[y_min..y_max)`). The
expansion resolves a table id missing from the project against these built-in tables, so
`DMN('wfa.l', …)` works too. `ZSCORE(table, sex, x, y)` and `IZSCORE(table, sex, x, z)`
are expanded at the same stage into the WHO formula, with three lookups (`'t.l'`, `'t.m'`,
`'t.s'`, policy `first`): `((y/m)^l − 1) / (s·l)` and `m·(z·s·l + 1)^(1/l)`. The formula is
written with the arithmetic operators, so `ZSCORE` / `IZSCORE` are the only zscore operators
and no strategy serialises them. The exponent is a new generic `TriccOperator.POWER`:

| Strategy | Serialisation |
|---|---|
| XPath (ODK, CDSS, CHT) | `pow(a, b)` |
| FHIRPath | `(a).power(b)` |
| CQL | `Power(a, b)` |

The arithmetic writers (XLSForm, CQL, FHIRPath) bracket an operand that is itself arithmetic:
they joined operands with the operator, so `("a" + "b") / 2` was written `a + b div 2`.

The CDSS choice injection (`inject_used_zscore_tables`), `get_zscore_params`, the CHT
`wfa.js` calls and the LMS columns of `CHOICE_MAP` are removed. A table that is not a literal
fails with `E_DMN_TABLE_NOT_STATIC`.

### 4. Validation and errors

`E_DMN_LIST_OVERLAP` (new). The others are those of the decision-tables spec.

### 5. Tests

- The shared vectors evaluated against the list lookup: the predicate run on the encoded items
  by a small XPath evaluator in the test, for every cell form and policy.
- Mode switch: 10 rows inline, 11 rows list; the threshold from `tricc.yaml`; the choices rows
  and the hidden select in the `.xlsx`; ODK Validate passes on the project fixture.
- Zscore: the expansion against WHO values (newborn median ≈ 0; `Izscore(…, 0)` = `m`); ODK
  (list), CHT (library, run with node) and OpenSRP (FHIRPath) builds.

### 6. Phases

1. Threshold, list encoding, hidden select, tests.
2. Built-in `wfa` table, `ZSCORE` / `IZSCORE` expansion, removal of the old zscore code, tests.
3. Docs: `docs/tricc-elements.md`, `docs/tricc.yaml.template`.

---

## Open questions

None.

## Implementation notes

- **Spelling.** `Zscore` / `Izscore`, the names of `feature/cdss-zscore.md`, parsed as unknown
  native functions (only `ZScore` / `iZScore` were mapped): both spellings now map to the
  operators.
- **Brackets.** The bracketing of nested arithmetic also fixes authored expressions such as
  `("a" + "b") / 2`, which every XLSForm, CQL and FHIRPath export wrote without brackets.
- **CHT** reads l, m and s with three library calls each; `l` appears twice in the formula, so
  a `Zscore` is four reads (the same in the ODK lookup).
- **FHIR** has no list mode: a table is written inline, so a `Zscore` there is very long
  (about 420 kB per field on `wfa`). A table of more than 50 rows written inline is logged as a
  warning. A lookup in a resource contained in the Questionnaire would be the FHIR analogue of
  the instance; not done here.
- **Tests.** `tests/test_dmn_instance.py` evaluates the lookups with lxml (XPath 1.0 plus the
  JavaRosa functions the forms use): the shared vectors, every cell form, list cells, and the
  dose and zscore computed from the XForm pyxform writes for the fixture project (ODK Validate
  runs when Java is installed). `tests/test_cdss_zscore.py` keeps the LMS data tests.

## Decisions

- 2026-11-23: ODK reads tables of more than 10 rows (configurable) from a secondary instance,
  declared through a hidden select; zscore is a decision table read by every export; the work
  goes in a follow-up PR to #99 (@delcroip, in conversation)
