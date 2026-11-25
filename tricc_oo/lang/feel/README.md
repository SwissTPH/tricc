# FEEL grammar (decision-table cells)

| File                  | Origin                                                                                       |
| --------------------- | -------------------------------------------------------------------------------------------- |
| `FEEL_1_1.g4`         | Apache KIE [incubator-kie-drools](https://github.com/apache/incubator-kie-drools) release `10.2.0`, `kie-dmn/kie-dmn-feel/src/main/antlr4/org/kie/dmn/feel/parser/feel11/FEEL_1_1.g4`. **Untouched.** |
| `tricc_feel.g4`       | `grammar tricc_feel; import FEEL_1_1;` plus `TriccText` (TRICC's `'text'`). Only its **lexer** is generated and kept. |
| `TriccFeelParser.g4`  | TRICC parser over that lexer: the DMN simple unary tests (DMN 1.6 chapter 10, rules #7–#18).   |
| `cells.json`          | the shared test vector (cell, column type, values that pass / fail, or the error code).        |

Licence of `FEEL_1_1.g4`: Apache-2.0 (© The Apache Software Foundation).
sha256 `24894fb287f3eef1256cc3bb94b2991e098cbf3b4ca78508b77471dfd62fcdde`.

The upstream parser rules carry Java (`@parser::header`, `helper.*` actions, Java predicates):
importing them generates a Python or TypeScript parser that does not compile. Its lexer has no
actions, so TRICC uses it and writes its own parser.

## The cell subset

| Cell                     | Meaning                                          |
| ------------------------ | ------------------------------------------------ |
| `-`                      | any value, also "not entered"                    |
| `null` / `not(null)`     | not entered / entered                            |
| `< 5`, `>= -2.5`, `= 3`  | comparison (number columns)                      |
| `[1..5)`, `(0..10]`      | range; a square bracket includes the bound       |
| `5`, `'yes'`, `true`     | equal to                                         |
| `1, 3, [5..7)`           | any of                                           |

Type checks (a range on a text column, a text in a number column) are in the visitor, with the
codes `E_DMN_CELL` (syntax) and `E_DMN_TYPE` (value vs column type). TRICC's `'text'` is FEEL's
`"text"` (`../meaning.json`).
