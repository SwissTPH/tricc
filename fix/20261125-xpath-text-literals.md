# XLSForm family: text written into XPath goes through one sanitation function

| Field | Value |
|-------|-------|
| **Status** | Implemented (approved 2026-11-25, in conversation) |
| **Branch target** | `fix/xpath-text-literals` → `develop` |
| **Scope** | `XLSFormStrategy` → `XLSFormCDSSStrategy` → `XLSFormCHTStrategy` → `XLSFormCHTHFStrategy` (calculations, `relevant`, `constraint`, `choice_filter`; CHT `cht:extension-lib(...)` arguments) |
| **Related** | `fix/20261012-yaml-edge-labels.md` (introduced `xpath_literal` for static operands), `feature/20261123-decision-tables.md`, `feature/20261123-dmn-instance-lookup.md`, `feature/lang-and-capabilities` branch (FEEL `'it''s'` cells, kept out of the shared vectors until this lands) |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Issue analysis

### Symptoms

A text value that holds an apostrophe, such as a diagnosis named *Child's cough*, can make
the ODK and CHT forms invalid. ODK Validate rejects the form:

```
Invalid calculate for the bind attached to "${dx_list}" : Couldn't understand the expression
starting at this point: ...h  = 1, 'Child'͎s"dry" cough,'...
```

Most text already works: a text constant compared with a question, a select option named
`it's`, a decision table cell `'it\'s'`. A few places in the exporter still put quotes around
a value by hand, and those break as soon as the value holds the same quote.

The case was found while writing the shared decision-table cell vectors: a text cell with an
apostrophe failed in the instance lookup test and was kept out of the vectors.

### Who is affected

Authors of XLSForm, CDSS, CHT and CHT HF forms whose content holds an apostrophe in:

- a diagnosis display text listed by `DiagnosisList(...)`;
- the table or output name of a decision table call in CHT (`cht:extension-lib(...)`);
- the text argument of a `selected(...)` test written with a non-text value, or the field
  argument of `GetChoiceName(...)`.

### Expected vs actual

| Expected | Actual |
| -------- | ------ |
| `if(${dx} = 1, concat('Child', "'", 's "dry" cough,'), '')` | `if(${dx} = 1, 'Child's "dry" cough,', '')`: the form does not load |
| `cht:extension-lib('dmn-p.js', "child's", 'first', 'dose', …)` | `cht:extension-lib('dmn-p.js', 'child's', …)` |
| `jr:choice-name(${sel}, '${sel}')` and, for a static argument, a valid literal | a static argument is quoted twice: `jr:choice-name(${sel}, ''opt'')` |

### How to reproduce

1. Build `tests/data/projects/xpath_text_literals` with `-O XLSFormStrategy` or
   `-O XLSFormCHTStrategy`: ODK Validate rejects `dx_list`.

### Out of scope

- An author-written XLSForm expression (a `custom` retrieval's `text/x-xlsform`) is copied
  as written.
- The FEEL / CQL doubled-quote form `'it''s'` is not read by the cell and CQL parsers on
  `develop`; that is the `lang-and-capabilities` work. The tests here use `'it\'s'`, which
  `develop` reads.
- DrawTRICC refuses an option name holding a quote, so the fixture project keeps plain option
  names; the option case is tested on a node built in the test.
- Option names of a `select_multiple` become calculate names (`quote's` is an invalid
  XLSForm name). That is a naming problem, not an XPath literal; left for another issue.

---

## Part II — Fix approach

### 1. Root cause

`tricc_oo/converters/utils.py` `xpath_literal(value)` writes an XPath 1.0 string literal
(XPath has no escapes: the quote the value lacks, else `concat(...)`). It is used by
`converters/tricc_to_xls_form.py` `get_export_name` for a `TriccStatic` or select option
operand, which covers every operand that goes through `get_tricc_operation_operand`. A few
writers bypass it and quote by hand:

| Place | What is written | Source of the value | Action |
| ----- | --------------- | ------------------- | ------ |
| `strategies/output/xls_form.py` `tricc_operation_diagnosis_list` (`'{display},'`) | diagnosis display text | CodeSystem `display` (project) | **fixed**: `xpath_literal(f"{display},")` |
| `strategies/output/xlsform_cht.py` `table_call_expression` (`f"'{v}'"`) | table id, hit policy, output name | decision table (project) | **fixed**: `xpath_literal(v)` for the three |
| `strategies/output/xls_form.py` `tricc_operation_selected` (`"'" + str(s) + "'"`, and `s.name` unquoted) | a non-text value, a select option | project | **fixed**: `xpath_literal(...)` |
| `strategies/output/xls_form.py` `tricc_operation_native` `GetChoiceName` (`'{…}'`) | the field argument (`${name}`) as a string | project field (an operand already written) | **fixed**: `xpath_literal(...)`; a static argument is no longer quoted twice |
| `tests/test_dmn_instance.py` `_literal` (`f"'{value}'"`) | the input value of the lookup test | test vectors | **fixed**: `xpath_literal(...)` |
| `strategies/output/xlsform_cht.py` `table_call_expression` library name | `dmn-<slug>.js` | `library_name()`: a slug made by tricc | left: fixed identifier |
| `serializers/dmn_instance.py` `_bound`, `input_predicate` (`k='{kind}'`), `lookup_expression` (`instance('{list_name}')`) | kind markers `a n v e t f r`, `n i x`; `dmn_<id>` with `[^A-Za-z0-9_]` replaced | tricc | left: fixed identifiers. Cell values go in the instance (choices sheet), not the XPath |
| `strategies/output/xlsform_cht.py` `retrieval_expression` | `context/<name>` path step | retrieval name | left: a path step, not a literal |
| `strategies/output/xlsform_cht.py` `get_cht_input` (`./source = "user"`) | constant | tricc | left |
| `converters/tricc_to_xls_form.py` `get_export_name`, plain `str` operand | written as is | expression fragments built by tricc (`"''"`, `string-length(choice_filter)=0`) | left: by convention a plain `str` operand is XPath already |
| `''` empty-string defaults (`OPERATOR_COALESCE_FALLBACK`, `tricc_operation_case/ifs/list_if`, `isnull`) | `''` | tricc | left |

### 2. Fix

Rule: every text value written into an XPath expression by the XLSForm family goes through
`xpath_literal`. No hand-written `"'" + x + "'"` / `f"'{x}'"` around a value that comes from
the project (labels, option names, codes, display texts, table cells, call arguments,
constants). Fixed identifiers produced by tricc may stay as they are (listed above).

### 3. Code checklist

- [x] `XLSFormStrategy.tricc_operation_diagnosis_list`: display through `xpath_literal`.
- [x] `XLSFormCHTStrategy.table_call_expression`: table id, policy, output through `xpath_literal`.
- [x] `XLSFormStrategy.tricc_operation_selected`: option and non-text values through `xpath_literal`.
- [x] `XLSFormStrategy.tricc_operation_native` (`GetChoiceName`): field argument through `xpath_literal`.
- [x] `tests/test_dmn_instance.py` `_literal` through `xpath_literal`.
- [x] Docstrings on the touched public functions.

### 4. Tests

Each fails on `develop` 61905ed unless noted.

- `tests/data/decision_tables/cells.json`: string cells `'it\'s'` and `'it\'s "x"'` (the
  `concat` branch). On `develop`, `test_every_cell_form_reads_like_the_evaluator` fails on them
  with `lxml.etree.XPathSyntaxError: Invalid expression` (the `_literal` helper).
- `tests/test_xpath_text_literals.py`:
  - every string cell vector through the real writer (`get_tricc_operation_expression` /
    `table_call_expression` of a kept `DMN_CALL`), XLSForm and CDSS, inline and from the
    instance (`decision_table_max_inline_rows = 0`), evaluated with lxml (passes on
    `develop`: these paths already used `xpath_literal`; it guards them);
  - `DiagnosisList`, the CHT `extension-lib` head, `selected` and `GetChoiceName` with an
    apostrophe and a double quote: the expression parses with lxml and reads back the value;
  - end to end: `tests/data/projects/xpath_text_literals` built with `XLSFormStrategy` and
    `XLSFormCHTStrategy`; every calculation, `relevance`, `constraint` and `choice_filter`
    parses as XPath with lxml (after `${x}` → a path), and pyxform converts the form (ODK
    Validate when java is present).

### 5. Acceptance criteria

- No hand-quoted project value left in the XLSForm family (the table above).
- The fixture project builds and validates with `XLSFormStrategy` and `XLSFormCHTStrategy`.
- Full `pytest` green; no new flake8 warnings on touched lines; no regression-suite case
  changes output.

---

## Open questions

None.

## Decisions

- 2026-11-25: one sanitation function, `xpath_literal`, for every text value written into
  XPath by the XLSForm family; fixed tricc identifiers may stay (user, in conversation).
- 2026-11-25: the cell vectors use `'it\'s'`; `'it''s'` goes back into the shared vectors
  with the FEEL reader on `feature/lang-and-capabilities`.
