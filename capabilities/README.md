# Output capability statements

One npm package per output strategy (feature/20261125-output-capabilities.md), each with its
own version, `CHANGELOG.md` and `statement.json`, checked by `statement.schema.json` (a copy
ships with tricc_oo in `tricc_oo/data/capabilities/`).

| Package                            | Strategy               | Extends                       |
| ---------------------------------- | ---------------------- | ----------------------------- |
| `@tricc/capabilities-xlsform`      | `XLSFormStrategy`      |                               |
| `@tricc/capabilities-xlsform-cdss` | `XLSFormCDSSStrategy`  | `-xlsform`                    |
| `@tricc/capabilities-xlsform-cht`  | `XLSFormCHTStrategy`   | `-xlsform-cdss`               |
| `@tricc/capabilities-xlsform-cht-hf` | `XLSFormCHTHFStrategy` | `-xlsform-cht`              |
| `@tricc/capabilities-fhir`         | `FHIRStrategy`         |                               |
| `@tricc/capabilities-opensrp`      | `OpenSRPStrategy`      | `-fhir`                       |

A statement names `TriccOperator` operators with the contexts where the output writes them
(`form`; FHIR: `inline` = FHIRPath, `library` = CQL), catalogue functions
(`tricc_oo/lang/functions.json`), retrieval and prefill contexts, data types, features and
limits. A child (`extends`) lists only what it `add`s and `remove`s; `package.json` depends on
the parent with the same range.

`tests/test_output_capabilities.py` feeds every operator, catalogue function and retrieval
context to each strategy's writer: the statements cannot drift from the code. Bump a package's
version (and its `CHANGELOG.md`) on any change to its statement.

Publishing (`npm publish` per folder, to npmjs and GitHub Packages) is a separate release task.
