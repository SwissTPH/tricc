# DMN calls: named overrides with a trailing `Tuple{…}`, and `null` inputs

| Field             | Value                                                                       |
| ----------------- | --------------------------------------------------------------------------- |
| **Status**        | Implemented (2026-11-23; approved 2026-11-23, in conversation)              |
| **Branch target** | `feature/decision-tables` → `develop` (with RFC #85)                        |
| **Scope**         | `tricc_oo/converters/cql_to_operation.py`, the DMN expansion of #91          |
| **RFC**           | #96                                                                         |
| **Related**       | `feature/20261123-decision-tables.md` (RFC #85, implementation #91); frontend RFC SwissTPH/tricc-frontend#59 |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

Authors will be able to override one table input by name and keep the others from their
column concepts: `DMN('diazepam', Tuple{ weight: null })`. DrawTRICC writes this when an input is
only collected later than the call (the weight in Danger signs). The export must expand it to
the same lookup as the positional form, with `null` meaning "no value".

## Part II — Technical specification

- Parse a trailing CQL tuple selector as the last argument of `DMN`, `DMNFirst`, `DMNList` and
  their aliases (`DrugDosage`). The CQL grammar already parses `Tuple{ name: expr }`; the visitor
  must keep it as a named-argument map.
- Binding: positional arguments bind inputs in order; tuple keys bind by input name; unbound
  inputs take their column concept. Errors: unknown key, input bound twice (same codes as the
  frontend: `E_DMN_ARG_UNKNOWN`, `E_DMN_ARG_TWICE`).
- `null` (positional or in the tuple) is no value: conditions on that input do not match, `-`
  cells do; every output strategy must render it (see the YamlStrategy parity bug, point 6:
  `get_tricc_operation_operand` has no case for `None`).
- No reference is created for an input bound to `null`, so the walker never waits for it.
- Tests: the shared vectors from `tricc-frontend` `packages/core/src/decision-table/__vectors__/`
  gain named and `null` cases; copy them unchanged.

## Open questions

None.

## Implementation notes

- `cqlToXlsFormVisitor.visitTupleSelector` parses `Tuple{ k: v }` to `TriccOperator.TUPLE`
  (`[TriccStatic(k), v, …]`); the expansion (`tricc_oo/converters/decision_table.py`) reads it
  as the last argument only (elsewhere: `E_DMN_ARG_UNKNOWN`).
- `null` is bound as "no value" and folded at expansion with every other literal, so no
  operand is serialised for it and point 6 of the YamlStrategy parity bug does not arise for
  table calls.
- The frontend vectors (`tests/data/decision_tables/`) have no named / `null` call cases yet;
  the named and `null` cases are tested in `tests/test_decision_tables.py`. Add them to the
  shared vectors with SwissTPH/tricc-frontend#59 and copy them here unchanged.

## Decisions

- 2026-11-23: one trailing `Tuple{…}`, keys are input column names (@delcroip).
- 2026-11-23: approved with the implementation request (@delcroip, in conversation)
