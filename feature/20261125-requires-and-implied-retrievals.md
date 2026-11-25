# Prerequisites (`requires`) within an encounter, and implied retrievals across encounters

| Field             | Value |
| ----------------- | ----- |
| **Status**        | Implemented (2026-11-25, RFC #104, phases 1–3; phase 4 is the tricc-frontend mirror) |
| **Branch target** | `feature/retrievals` → `develop` |
| **Scope**         | `models/project_config` (`TriccInterventionConfig.requires`), `YamlStrategy` (`YamlActivity.requires`), `strategies/input/base_input_strategy` (`link_project`, `attach_library_calculates`), `converters/retrieval`, `converters/fhir/populate_helper`, `converters/fhir/repeat_helper`, `visitors/tricc` (versions), `FHIRStrategy` → `OpenSRPStrategy`, `XLSFormStrategy` → `XLSFormCDSSStrategy` → `XLSFormCHTStrategy` → `XLSFormCHTHFStrategy` |
| **Related** | #101 (calculate functions: a required concept is a version, so a parameter's fallback concept finds it). `feature/20261109-project-retrievals.md` (retrieval nodes, contexts, periods; implied retrievals are generated entries). `feature/20260929-cql-populate-wiring.md` (encounter populate reads). `feature/20261111-block-params-and-start-node.md` §8.1, §8.4 (`requires` declared, "read, not used yet"). #76 (`LatestDate`: the `.date` field) and #75 (medication reads: `.drugs`, `.dosage`). #103 (`sys.code` references: a qualified retrieval waits for it). #98 (`Retrieve` in the function catalogue; no new grammar). tricc-frontend `feature/20261014-answer-options-in-cql.md` (the `Answer('code')` pattern this follows). Frontend mirror (requires pickers; `#name` / `#concept@period.field` shown for `Retrieve(…)` as a readable chip, with suggestions; rewrite on save; validation): SwissTPH/tricc-frontend, to open. |
| **RFC**           | SwissTPH/tricc#104 |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

### The problem

A visit is often split into several forms: registration, triage, then consultation. A later
form needs values collected earlier in the same visit (weight, danger signs), but has no way
to say so. Authors either ask again or add a retrieval for each value by hand. Across visits it
is the same: reading "the last weight in the past three months" needs a dictionary entry per
concept and per period, even though it is always the same kind of read.

### What changes for an author

- **Within a visit.** An intervention lists the interventions it **requires** (they come earlier
  in the same visit), and an activity can list the concepts it requires. A required value is
  read from the visit's record at the start of the intervention, so any expression can use it
  as if it had been collected in this form. If the form collects or computes the same concept
  again, the newer value is used from that point on, like any other new version.
- A required intervention must exist in the project; a required concept must be a project
  concept.
- **Across visits.** A value from earlier visits can be used directly in an expression,
  without a dictionary entry. The editor shows it as `#weight@P3M`: the last `weight` recorded
  in the past three months. It behaves like a retrieval the author would have written (latest
  value, earlier visits, period of three months). Without a period, `#weight@` reads the last
  value ever recorded.
- A field after a dot reads something else about that record: `#weight@P3M.date` (when it was
  last recorded), `.exists`, `.count`, and for medicines `.drugs` and `.dosage`. `.value` is the
  default and may be left out. The editor only offers the fields that make sense for the
  concept, and shows the read as a sentence ("Date of the latest weight, past 3 months").
- Within the visit, the concept itself is usually used (through `requires`). `@encounter`
  reads the current visit's record instead of a period, for what the concept alone does not give:
  `#metformin@encounter.date` (when it was prescribed in this visit), `.drugs`, `.dosage`,
  `.count`.
- Dictionary retrievals keep showing as `#age_months`. Both are saved as a plain function call
  (`Retrieve(…)`), as answers are saved as `Answer('code')`, so the saved text is standard CQL.
- The data needs view (#101) shows these reads as `requires` or `retrieval`.

### Out of scope

- Ordering forms or interventions in the visit (`requires` does not schedule anything).
- `requires` on a drawio activity (no field there today); the intervention's `requires` covers it.
- Custom reads: use the retrieval dictionary.
- A retrieval of a concept from another code system (`sys.code`): waits for #103.

---

## Part II — Technical specification

### 1. Declaring prerequisites

- **Intervention** (`TriccInterventionConfig.requires`, tricc.yaml): ids of project
  interventions. An id that matches no `interventions[].id`: `E_REQUIRES_UNKNOWN`. A required
  intervention provides the concepts of the inputs and persisted calculates of its activities
  (resolved after all activities are loaded). A cycle (A requires B requires A) is allowed:
  each side reads only what the record holds.
- **Activity** (`YamlActivity.requires`): concept references (code or `{system, code}`). Not a
  project concept: `E_REQUIRES_UNKNOWN`.
- Both are "read, not used yet" today; this RFC uses them.

### 2. Required concepts are the first version

In `BaseInputStrategy.link_project`, before `process_pages`, each required concept the
intervention references becomes an **encounter read**: a `TriccNodePopulate` with
`context="encounter"` and `source=<concept>` (`populate_source_concept`), named by the concept
and hung at the start of the intervention (the start page, like the retrieval nodes in
`attach_library_calculates`). It is processed first, so it is the first version of the concept:

- a reference before any redefinition resolves to it (`get_last_version`);
- a node of the current intervention with the same name is a later version, as with several
  calculate versions today; references after it get the newer one, and inheritance merges them
  as it does for a populate today.

Only concepts that are referenced become nodes (as for retrievals). Each output writes the node
as it writes an encounter populate today (FHIR / OpenSRP: Helper encounter define; XLSForm /
CHT: a populate input).

### 3. Retrievals as a function: `Retrieve`

A quoted CQL identifier accepts every character, so meaning carried inside one (`"#…"`, `"…@…"`)
can collide with a real name. Retrievals are therefore saved as a function call, and the `#`
forms are only how the editor shows them (as `Answer('code')` edges are):

| Editor shows | Saved as | Meaning |
| ------------ | -------- | ------- |
| `#age_months` | `Retrieve('age_months')` | dictionary retrieval `#age_months` |
| `#weight@P3M`, `#"weight"@P3M` | `Retrieve('weight', 'P3M')` | implied: latest `weight` in the past 3 months, earlier encounters |
| `#weight@` | `Retrieve('weight', null)` | implied, no window: latest `weight` ever recorded |
| `#weight@P3M.date` | `Retrieve('weight', 'P3M', 'date')` | implied: date of the latest `weight` in the past 3 months |
| `#metformin@encounter.date` | `Retrieve('metformin', 'encounter', 'date')` | implied: date of the `metformin` record in the current encounter |
| `#weight@P3M.value` | `Retrieve('weight', 'P3M')` | same as `#weight@P3M` (the editor saves the default without the field) |

**Fields.** The optional third argument names what is read; each maps to a retrieval catalogue
function (`RETRIEVAL_FUNCTIONS`), offered only for the resources it supports (the resource comes
from the concept's `conceptType`, `get_fhir_resource`):

| Field | Function | Resources | Value type | From |
| ----- | -------- | --------- | ---------- | ---- |
| `value` (default) | `Latest` | all | the concept's | today |
| `date` | `LatestDate` | Observation, Condition, Procedure, MedicationRequest / Dispense | `dateTime` | #76 |
| `exists` | `Exists` | all | `boolean` | today |
| `count` | `Count` | all | `integer` | today |
| `drugs` | `ActiveDrugs` | MedicationRequest | `coded` (multi) | #75 |
| `dosage` | `OpenDosage` | MedicationRequest | `string` | #75 |

A field whose function is not implemented yet (before #76 / #75) or not valid for the resource:
`E_RETRIEVAL_READ_UNSUPPORTED`. New catalogue functions add a field name; the syntax does not
change.

- **Arguments are literals.** One argument: a dictionary code (without `#`). Two or three: a
  project concept, a window — an ISO-8601 period (`_DURATION_RE`, the format of the dictionary
  `period`), `null` (no window) or `'encounter'` (the current encounter) — and optionally a field
  (default `value`). The argument count tells a dictionary
  `#weight` from a concept `weight`, so they never clash. A non-literal argument:
  `E_RETRIEVAL_STATIC`. Fields apply to implied reads only: a dictionary entry names its own
  function.
- **Special function.** `Retrieve` is a build-time function in the function catalogue (#98,
  `reads: history`; today `stored_data_functions.json`). `cql_to_operation` keeps its
  arguments as codes, never as form nodes (like `GetRepeatedValue`, `CONCEPT_REF_FIRST_ARG`).
  `retrieval_refs` / `used_retrieval_codes` collect it:
  - one argument → `#<code>`, read from the dictionary as today;
  - two or three → an implied entry synthesised by `read_project_retrievals`:
    `Retrieval(code="#weight@P3M.date", context="history", function="LatestDate",
    reads_code="weight", period="P3M")` (no period for `null`; `context="encounter"` and no
    period for `'encounter'`, a context every timed function already supports; `Latest` and no
    `.value` suffix for the default field), with `reads_data_type` / `reads_concept_type` from the concept, so
    the Helper picks the resource as for a dictionary entry.
  The call then resolves to the `TriccNodeRetrieval`; exports are unchanged. The generated code
  (`#weight@P3M`, `#weight@P3M.date`) and export name (`r_weight_P3M`, `r_weight_P3M_date`;
  no window `#weight@` → `r_weight_any`, `#weight@encounter` → `r_weight_encounter`) are
  internal: authors never write them. Equal reads share one node.
- **Editor.** The chip label is built from the catalogue labels: `#weight@P3M.date` →
  "Date of the latest weight, past 3 months"; hovering shows the saved call. Typing `#` suggests
  concepts and dictionary retrievals, `@` common windows (this visit, 1 week, 3 months, 1 year,
  any time),
  `.` the fields valid for the concept's resource. `.value` is accepted when typed and saved
  without the field.
- **CHT** reads every retrieval from `instance('contact-summary')/context/<name>`; an implied
  retrieval needs that key, listed by the CHT export like a dictionary retrieval's.
- **Legacy `"#name"`** keeps being read as a dictionary retrieval. The editor rewrites it to
  `Retrieve('name')` when it saves; docs show only `Retrieve`.
- **Qualified concepts** (`Retrieve('sys.code', 'P3M')`) follow #103: `sys.code` as in the SCV
  serialisation, falling back to the default CodeSystem when `sys` is not one (`resolve_scv`).
  Until #103 lands, the concept is looked up in the default CodeSystem only.

### 4. Export: one read per record

Implied reads multiply retrievals (`#weight@P3M`, `#weight@P3M.date`, `#weight@P3M.count`), and
the encounter reads of §2 add more. Today each one calls a Helper function
(`GetHistoryObservationValueSince(code, since, …)`, `GetObservations(code)`) that runs its own
`[Observation]` / `[Condition]` / `[Procedure]` retrieve and filters by code in `where`
(`repeat_helper.py`). Engines cache a `define`'s result within one evaluation, not a function
call with arguments, so each item and retrieval queries the record again. The export aggregates
them:

- **One retrieve per resource and scope.** The Helper library gets one define per resource type
  and scope it needs, e.g. `define "EncounterObservations"` (current encounter, final / amended /
  corrected) and `define "HistoryObservations"` (the patient's, same statuses); likewise
  Conditions, Procedures, and MedicationRequest / Dispense (#75). Every Helper function and
  retrieval define reads from these defines instead of a bare `[Observation]`. The static Helper
  functions read every pair, so all pairs are written; an engine evaluates a define only when an
  expression reaches it, so an unused pair costs nothing.
- **One list per concept and window.** Reads that share concept, scope and window share one
  define, `define "#weight@P3M:records"`: the matching resources sorted by date, latest first.
  The fields are derived from it: `value` = `First(…).value` (typed as today), `date` =
  `First(…).effective` (#76's mapping per resource), `exists` = `exists …`, `count` = `Count(…)`.
  The retrieval nodes keep one define each (`"#weight@P3M"`, `"#weight@P3M.date"`), now a
  one-line read of the shared list.
- **Items reference defines, not functions.** A prefilled item's `initialExpression` names a
  define (`Helper."#weight@P3M"`), never a Helper function call with arguments, so the engine's
  define cache applies. Populate nodes and encounter reads (§2) follow the same rule: one
  generated define per concept read (`"@weight"` for the encounter), replacing
  `Helper.GetObservationValue('weight')` in the item.
- **CHT.** The contact summary is computed once per contact, so reads are already aggregated
  there. The CHT export lists the keys it needs grouped by concept and window (one lookup per
  concept, its fields side by side) in `<form>.contact-summary.json` next to the form, so the
  deployment's contact-summary code reads each concept once.
- **XLSForm / CDSS** read no database: unchanged.

How many queries an engine runs in the end (one per evaluation or per item) depends on the
engine; the output capability statements (#102) can record it.

### 5. Validation and errors

- `E_REQUIRES_UNKNOWN` (intervention or concept).
- `E_RETRIEVAL_READ_UNSUPPORTED` (a field not implemented or not valid for the concept's
  resource).
- `E_RETRIEVAL_UNKNOWN` (one argument, not in the dictionary; today's `TriccRetrievalError`),
  `E_RETRIEVAL_IMPLIED_CONCEPT` (not a project concept), `E_RETRIEVAL_IMPLIED_PERIOD` (not an
  ISO-8601 duration), `E_RETRIEVAL_STATIC` (an argument that is not a literal).

### 6. Tests

YAML fixtures in `tests/data/yaml/` and `tests/test_requires.py`:

- an unknown required intervention or concept fails;
- a required concept referenced before any redefinition resolves to the encounter read; after a
  redefinition, to the new version; inheritance merges them;
- an unreferenced required concept builds no node;
- #101: a function parameter whose fallback concept is required finds it;
- `Retrieve('age_months')` and legacy `"#age_months"` give the same node;
- `Retrieve('weight', 'P3M')` builds one retrieval node with `history` / `Latest` / `P3M` and
  exports per strategy (FHIR Helper define with a `Now() - 3 months` window, XLSForm
  `r_weight_P3M`, CHT contact-summary key); `Retrieve('weight', null)` has no window;
- `Retrieve('weight', 'P3M')` used twice builds one node; the form's own `weight` node is not
  read by it;
- `Retrieve('weight', 'P3M', 'value')` gives the same node as `Retrieve('weight', 'P3M')`;
  `'date'`, `'exists'`, `'count'` give their own nodes and functions;
  `Retrieve('weight', 'encounter')` builds an `encounter` context retrieval with no period; `'drugs'` on an
  Observation concept fails; `'date'` fails until #76 lands;
- unknown code, unknown concept, bad period and a non-literal argument fail;
- aggregation: the Helper library has one retrieve per resource / scope used; `value`, `date`
  and `count` of the same concept and window share one `:records` define; no item
  `initialExpression` calls a Helper function with arguments; the Helper still compiles
  (`test_fhir_helper_cql_compile.py`);
- CHT: the required contact-summary keys are grouped by concept and window.

### 7. Phases

1. `requires` validation and encounter reads as first versions.
2. `Retrieve` (dictionary and implied, fields `value` / `exists` / `count`), legacy `"#name"`
   kept; `date` with #76, `drugs` / `dosage` with #75.
3. Export aggregation (shared retrieves, `:records` lists, items on defines), existing
   populate reads included.
4. Frontend mirror (display, typing, rewrite on save).

---

## Open questions

None. Deferred: qualified concepts in `Retrieve` wait for #103.

## Decisions

- 2026-11-24: `requires` lists prerequisites gathered in the same encounter; a required concept
  is read from the encounter record at the start of the intervention, as its first version.
  An intervention's `requires` must name a project intervention. (@delcroip)
- 2026-11-24: Retrievals are saved as `Retrieve('code')` (dictionary) and
  `Retrieve('concept', 'P3M' | null)` (implied, latest in the period or ever); the editor shows
  `#code` / `#concept@P3M`. No meaning inside quoted identifiers, no grammar change. (@delcroip)
- 2026-11-24: Qualified concepts wait for #103 (`sys.code`, default CodeSystem when `sys` is
  not one). (@delcroip)
- 2026-11-25: An implied read takes an optional field, `#concept@period.field` →
  `Retrieve('concept', 'P3M', 'field')`, default `value` (`.value` accepted). Fields map to
  catalogue functions (`date` #76, `drugs` / `dosage` #75), offered per resource. The window may be `@encounter` (the
  current visit's record), for reads the concept alone does not give. (@delcroip)
- 2026-11-25: Exports aggregate reads: one retrieve per resource and scope, one list per concept
  and window with the fields derived from it, items referencing defines rather than Helper
  function calls; CHT keys grouped per concept. (@delcroip)
- 2026-11-25: Approved for implementation with #75, #76 and #104 on one branch (@delcroip)
