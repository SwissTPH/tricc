# Retrievals: read the date of the last record, not only its value

| Field             | Value |
| ----------------- | ----- |
| **Status**        | Approved (2026-11-25, RFC #76) |
| **Branch target** | `feature/retrievals` → `develop` |
| **Scope**         | `converters/retrieval.py`, `FHIRStrategy` (`converters/fhir/populate_helper.py`, `repeat_helper.py`), `XLSFormCHTStrategy` |
| **Related**       | `feature/20261109-project-retrievals.md` (#78, the retrieval dictionary this extends), SwissTPH/tricc-frontend#31 (retrieval RFC; mirror the catalogue entry into `@tricc/core` `terminology/retrieval.ts`), #74 (Procedure helpers), #75 (medication dates reuse this function), #104 (implied reads: `#weight@P3M.date` → `Retrieve('weight', 'P3M', 'date')` calls `LatestDate` without a dictionary entry) |
| **RFC**           | SwissTPH/tricc#76 |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

### The problem

Flows decide on **when** something was last recorded as much as on its value: re-ask the menarche
group after 120 days, "warning symptoms reported less than 7 days ago", "weight measured on …",
"date of last visit". The CombaScale diabetes flow has 30 such prefilled dates (`t_date_last_vis`,
`t_date_weight`, `t_date_mi`, …). CHT stores each as its own field: the form saves `today()` next
to the value. In FHIR the date is already on the record (`Observation.effective`,
`Condition.onset` / `recordedDate`, `Procedure.performed`), so a separate "date" concept is
redundant.

Since the retrieval dictionary (#78), an author can read the **latest value** of a concept, whether
a record **exists**, or **how many** there are, in the encounter or the history. There is no way
to read **when** the last record was made.

### What changes for an author

- The retrieval dictionary gets one more function for encounter and history: **Date of the
  latest record**.
- `#date_weight` becomes "history, Date of the latest record, reads `weight`" instead of a concept
  of its own.
- Retrievals of procedures (`Latest`, `Exists`, `Count`, and the new date) work the way they
  already do for observations and conditions.
- Without a dictionary entry, the same read is written `#weight@P3M.date` in an expression
  (#104).

### Out of scope

- A `read` attribute on legacy "Prefilled value" nodes. Those nodes move to the retrieval
  dictionary (tricc-frontend#31); this RFC only extends the dictionary.
- Medication specifics (#75).

---

## Part II — Technical specification

### 1. Design

- New catalogue entry `LatestDate`: contexts `encounter`, `history`; needs `reads`; uses
  `period`; value type `dateTime`. Added to `RETRIEVAL_FUNCTIONS` in
  `tricc_oo/converters/retrieval.py` and to `@tricc/core` `terminology/retrieval.ts`
  (label "Date of the latest record").
- `populate_helper.retrieval_cql_expression`: the resource comes from
  `get_fhir_resource(retrieval.reads_concept_type, …)`, as today. Mapping:

| Resource | `encounter` | `history` (`since` = period window or `null`) |
|---|---|---|
| Observation | `LatestObservationTime(code, null)` restricted to the encounter (new `GetEncounterObservationTime(code)`) | `LatestObservationTime(code, since)` (exists in `repeat_helper.py`) |
| Condition | new `GetEncounterConditionDate(code)` | new `GetHistoryConditionDate(code, since)`: `Coalesce(onset as dateTime, recordedDate)` of the latest not refuted condition |
| Procedure | new `GetEncounterProcedureDate(code)` | `GetHistoryProcedureDate(code)` (#74), with a `since` argument added |

- Procedure for the existing functions: `Latest` / `Exists` on a Procedure reuse
  `GetEncounterProcedureValue` / `GetHistoryProcedureDate is not null`; `Count` counts completed,
  not Unsuccessful procedures. Today a Procedure concept falls through to the Observation branch.
- `Retrieval.value_type` gives `dateTime`, so `populate_value_type` and the Questionnaire item type
  follow without new code.
- CHT (`XLSFormCHTStrategy`): reads the contact summary key `<name>` like every catalogue
  function; a warning says the CHT app must expose that date.

### 2. Validation and errors

- `LatestDate` without `reads` → `TriccRetrievalError` (existing "needs `reads`" rule).
- `LatestDate` on a resource with no date mapping (e.g. MedicationRequest before #75) →
  `unsupported(retrieval, strategy)`.

### 3. Tests

- `tests/test_retrieval*.py`: one retrieval per (resource × context) for `LatestDate`; FHIR output
  holds the expected Helper call; Procedure `Latest` / `Exists` / `Count`.
- `tests/test_strategies/test_fhir_helper_cql_compile.py`: the new helpers compile.
- tricc-frontend: `retrieval.test.ts` accepts `LatestDate` in encounter / history only.

### 4. Phases

1. Observation and Condition `LatestDate`.
2. Procedure for every timed function.

---

## Open questions

None.

## Decisions

- 2026-11-19: Reworked on top of the retrieval dictionary (#78 / tricc-frontend#31): a catalogue
  function instead of a `read` attribute on populate nodes; `exists` is already covered by
  `Exists`.
- 2026-11-25: Name `LatestDate`, read next to `Latest` in the picker. (@delcroip)
- 2026-11-25: Encounter `LatestDate` (time of the record in this visit) is supported. (@delcroip)
- 2026-11-25: Condition date: `onset`, falling back to `recordedDate`. (@delcroip)
- 2026-11-25: Approved for implementation with #75, #76 and #104 on one branch (@delcroip)
