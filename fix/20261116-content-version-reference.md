# Content version is not available in FHIR / openSRP exports

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Approval** | Approved by Patrick on 2026-11-16 (in conversation). |
| **Branch target** | `fix/content-version-reference` / `develop` |
| **Scope** | `models` (`TriccOperator`), `converters/cql_to_operation`, `XLSFormStrategy`, `FHIRStrategy` → `OpenSRPStrategy` |
| **Related** | `feature/display-text-injection.md`, `feature/20260909-display-message-ast.md` (made `${REF}` in text a real reference) |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## 1. What went wrong

The Global Almanach child build to openSRP stops with
`Reference not found in codesystems: version in Note|label_disclaimer`. The disclaimer text ends
with `${version}` to show the content release. `version` is a hidden field the XLSForm exports add
on their own; no node in the diagram has that name, and the FHIR export has no equivalent.

## 2. Who is affected

Projects that show or use the content version, exported to FHIR or openSRP.

## 3. Expected vs actual

| | |
|---|---|
| **Expected** | An author can get the content version in any output through a calculate. |
| **Actual** | Only XLSForm has it, through an implicit field; FHIR / openSRP builds stop. |

## 4. How to reproduce

Build a note whose text contains `${version}` with `-O OpenSRPStrategy`.

## 5. Out of scope

- Reserving `version` (or any name) as an implicit reference. The author declares a calculate.
- A project-level semantic version from `tricc.yaml`.

---

# Part II — Fix approach

## 1. Root cause

No operator gives the content version. The XLSForm strategies inject a `version` row
(`XLSFormStrategy.inject_version`, `version()`), which an expression can name only because the row
is added after processing. Reference resolution in `visitors/tricc.py` rightly stops on a name
that matches no node when codesystems are passed (FHIR build).

## 2. Fix (rules)

1. New operator `TriccOperator.CONTENT_VERSION = "content_version"`, no operands, returns a
   string. CQL authoring name `GetContentVersion()`.
2. The author adds a calculate (e.g. `content_version`, expression `GetContentVersion()`) and
   writes `${content_version}` in text.
3. Rendering:
   - XLSForm / CHT: `version()`.
   - FHIR CQL: `Helper.GetContentVersion()`, defined in the Helper library as
     `define function GetContentVersion(): '<build version>'`.
   - FHIRPath (calculatedExpression): the string literal `'<build version>'`.
   - `<build version>` is the `version` string the strategy already passes to `export`
     (`%Y%m%d%H%M`).
4. Reference resolution is unchanged.

## 3. Code checklist

- [x] `models/base.py`: `CONTENT_VERSION`; string return type.
- [x] `converters/cql_to_operation.py`: `"GetContentVersion": TriccOperator.CONTENT_VERSION`.
- [x] `strategies/output/xls_form.py`: `tricc_operation_content_version` → `version()`.
- [x] `strategies/output/fhir_form.py`: CQL and FHIRPath renderers; `GetContentVersion` in
      `CQL_HELPER_TEMPLATE`, filled with the build version.
- [x] `docs/tricc-elements.md`, `docs/open-srp-export.md`: `GetContentVersion()`.
- [x] Global Almanach `L2/child/registration_formatted.drawio`: add the calculate, replace
      `${version}` in the disclaimer (separate repo).

## 4. Tests

- `GetContentVersion()` parses to `CONTENT_VERSION`.
- YAML fixture: calculate `content_version = GetContentVersion()`, note text
  `${content_version}`. FHIR: item `calculatedExpression` is the build version literal, Helper CQL
  defines `GetContentVersion`. XLSForm: calculation `version()`.

## 5. Acceptance criteria

The Global Almanach child + common build to `OpenSRPStrategy` completes, and the disclaimer shows
the build version.

---

## Open questions

1. Value: build timestamp (`%Y%m%d%H%M`) or `tricc.yaml` version when present?
   **Recommendation:** build timestamp now, as CHT does.

## Decisions

- 2026-11-16: no reserved `version` reference; the diagram declares a calculate calling
  `GetContentVersion()` (Patrick, in conversation).
