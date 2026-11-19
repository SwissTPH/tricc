# Evaluate constant expressions at build time

| Field             | Value                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------- |
| **Status**        | Approved (2026-11-19, in conversation)                                                  |
| **Branch target** | `feature/python-constant-eval` → `develop`                                              |
| **Scope**         | `models`, `converters/cql_to_operation`, `strategies/input/param_build` (new visitor)   |
| **Related**       | `20261111-block-params-and-start-node.md` §18.8 point 1 (expression arguments, which this makes foldable); `fix/20261117-fhir-boolean-zscore-display-types.md` (PR #84: `@retrieve` on CQL function declarations) |
| **RFC**           | SwissTPH/tricc#86                                                                       |

---

## Part I — Business description

### The problem

A block argument is fixed only when it is written as a plain value (`38`, `'axillary'`). An
expression that always gives the same result, such as `{{threshold}} + 0.5` or `37 + 1`, is
treated like one that reads the patient's data. The build then adds a hidden calculate that the
form computes every time, and refuses the argument wherever a fixed value is needed (a node
name, a static decision). The author has to work out the value by hand.

### What changes for an author

- An argument that uses no collected data gets its value at build time. It's then a fixed
  value: no hidden calculate, and accepted where only fixed values fit.
- "No collected data" means no inputs and no stored data. A calculate is allowed when it reads
  no collected data either, recursively.
- A project function says whether it reads recorded data with the `@retrieve` tag of its
  declaration in the project's CQL libraries. `@retrieve: true`, or no tag: it does (or may),
  like an input. `@retrieve: false`: it is static, but the build cannot run it, so the form
  computes it; the output must support the function, or the export fails.
- An expression that reads no collected data but uses an operator the build can't evaluate,
  or a function no library declares, is computed in the form, as before, with a warning
  naming it.
- Where only a fixed value fits (a node name, a label once the block is built, a static
  decision), an argument the build can't evaluate is an error saying why.

### Out of scope

- Folding calculates, relevances or rhombus conditions in the exported forms (a possible later
  phase, see Open questions).
- Partial folding: replacing the constant parts of an argument that can't be folded whole
  (`Bmi({{w}} * 2, 1.7)` → `Bmi(140, 1.7)`). It needs a writer from parsed expressions back to
  CQL text; a later RFC.
- `Today()` and `Now()`: never constant (§7.1 of the block spec).

---

## Part II — Technical specification

### 1. Design

- New visitor `tricc_oo/visitors/constant_eval.py`:
  `evaluate_constant(expression, resolve) -> TriccStatic`.
  - A `TriccStatic` (not a `TriccReference`) is its value.
  - A `TriccReference` goes through `resolve(name)`. A calculate that reads no collected data
    is evaluated recursively, with a cycle guard. Anything else (an input, a select, an unknown
    name) raises `TriccNotConstant`.
  - A `TriccOperation` is evaluated from its operands through a table
    `TriccOperator -> Python function`, starting with: `and`, `or`, `not` (CQL three-valued,
    None is null), comparisons, `+ - * /` (division by zero is null), `if`, `concatenate`, `abs`,
    `min`, `max`, `round`, `istrue`, `isfalse`, `exists`.
  - Stored-data functions (`get_stored_data()`), `today`, `now`: `TriccNotConstant`.
  - A function called as written (`native`): looked up with `functions(name)`, the project's
    declaration (`cql_library.function_signature`, PR #84). `@retrieve: true`:
    `TriccNotConstant`, and so is a declaration without the tag (assume the worst). Not
    declared: `TriccEvalUnsupported(name)`. An explicit `@retrieve: false`: its arguments are checked like any operand; evaluating it raises
    `TriccEvalDeferred(name)` (a `TriccEvalUnsupported`): static, computed by the form.
  - Any other operator: `TriccEvalUnsupported(operator)`.
  - The check pass collects unsupported operators and undeclared functions over the whole
    tree and raises the first after it, so the outcome does not depend on operand order.
  - The whole expression is checked for collected data first: an unsupported operator only
    fails an expression that would otherwise be constant (`case when "weight" > 0 …` stays
    dynamic).
  - A null result returns None; the argument then keeps its calculate (bound as None, the
    parameter would take its default).
- `bind` (`models/params.py`): after rendering an expression argument, try `evaluate_constant`.
  - A value: bind it as a literal (`coerce_value`), with no calculate.
  - `TriccNotConstant`: dynamic, as today.
  - `TriccEvalDeferred`: computed by the form (its `arg_` calculate), no warning.
  - `TriccEvalUnsupported`: warning `W_ARG_EVAL`, then dynamic, as if it read collected data.
  - Either way, where a fixed value is needed, `E_ARG_DYNAMIC_STATIC` gives the reason.
  - `fold_argument` returns the value or an `Unfolded(reason)`.
- `resolve` for arguments: the calculates of the rendered calling page. The input strategy
  gives them through a new optional `ParamBuild` hook, `calculates(rendered) -> {name:
  expression}` (`_yaml_calculates`, `drawio_calculates`); a name given twice maps to None.
  `ParamBuild._resolver` passes it to `bind(..., resolve=)`.
- Intervention `args` are folded too (no resolver): `37 + 1` is accepted there.
- `functions` for arguments: `ParamBuild._function`, over `project.function_signatures`
  (filled by `load_libraries` before the pages are built), passed to `bind(..., functions=)`.

### 2. Validation and errors

- `W_ARG_EVAL` (warning): an argument reading no collected data uses an operator the build
  can't evaluate or an undeclared function; kept dynamic. The message names the call chain, the parameter and
  the operator or function.
- `TriccNotConstant` is never shown to the author: it only means "keep it dynamic".

### 3. Tests

- `tests/test_constant_eval.py`, operator table:
  - each supported operator, null propagation, division by zero;
  - a reference to an input fails; a reference to a constant calculate, nested, is evaluated;
  - a cycle is detected.
- `tests/test_block_calls.py`:
  - `{{t}} + 1` binds the number, with no `arg_` calculate;
  - a folded value is accepted for a parameter used in a node name;
  - an unsupported operator warns `W_ARG_EVAL` and stays dynamic, or gives
    `E_ARG_DYNAMIC_STATIC` with the reason where a fixed value is needed;
  - `@retrieve: true` / no tag (dynamic) / `false` (computed by the form), no warning;
    undeclared: warning; in a project with a `libraries` file.

### 4. Phases

1. Visitor and operator table, unit tests.
2. Use in `bind`, with the resolver over the calling page's calculates.
3. Docs: `docs/tricc-elements.md` (block arguments).

---

## Open questions

None.

## Decisions

- 2026-11-19: approved in conversation (@delcroip).
- 2026-11-19: ~~an unsupported function in a constant argument stops the build
  (`E_ARG_EVAL`)~~ revised the same day: warning `W_ARG_EVAL` and kept dynamic (assume the
  worst) (@delcroip).
- 2026-11-19: a function's static/dynamic marker is the `@retrieve` tag of its CQL `external`
  declaration (PR #84); `false` is the default. An undeclared function is treated like
  `@retrieve: false`: not data, but not evaluable, so warned and kept dynamic.
- 2026-11-19: a function declared `@retrieve: false` is static: no warning; the build has no
  implementation, so the form computes it, and an output that doesn't support it fails the
  export. A label or name needs the value at build time, so it fails there with the reason
  (@delcroip).
- 2026-11-19: a declaration without `@retrieve` is dynamic (assume the worst); only an explicit
  `@retrieve: false` makes a function static. This reverses the "default false" of PR #84 for
  this use (@delcroip).
- 2026-11-19: partial folding of an argument's constant parts is wanted, as a later RFC (it
  needs a TRICC expression → CQL writer) (@delcroip).
- 2026-11-19: folding calculates and conditions in the exported forms is deferred to a later
  RFC, behind the same visitor.
- 2026-11-19: numbers are Python `Decimal`; a whole result is given back as `int`, else `float`.
- 2026-11-19 (implementation): data is checked before operators; a null result keeps its
  calculate.

