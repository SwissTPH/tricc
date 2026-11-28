# Retrievals of medication: one drug per read, from its latest valid prescription

| Field             | Value |
| ----------------- | ----- |
| **Status**        | Implemented (2026-11-25, RFC #75; approved 2026-11-25) |
| **Branch target** | `feature/retrievals` → `develop` |
| **Scope**         | `converters/retrieval.py`, `FHIRStrategy` (`converters/fhir/populate_helper.py`, `repeat_helper.py`), `converters/fhir/concept_mapper.py`, `XLSFormCHTStrategy` |
| **Related**       | `feature/20261109-project-retrievals.md` (#78, the retrieval dictionary this extends), SwissTPH/tricc-frontend#31 (mirror the catalogue entries into `@tricc/core` `terminology/retrieval.ts`), #76 (`LatestDate`, reused for request / dispense dates), #104 (implied reads: `#metformin@`, `#metformin@P6M.dosage`, `#metformin@P6M.dispensed`, `#metformin@encounter.date` call these functions without a dictionary entry), `feature/20260812-medication-request-dispense-node.md` (parked: *writing* MedicationRequest / Dispense; this RFC *reads* them) |
| **RFC**           | SwissTPH/tricc#75 |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

### The problem

Chronic-care flows (CombaScale diabetes / hypertension, `SwissTPH/combacal-plus` `dm_int`) need to
know what the patient is currently taking before deciding to continue, updose or switch treatment:

- is the patient on treatment at all (`t_dm_tx`, `t_aht_tx`);
- which drugs (`t_dm_drugs`, `t_aht_drugs`, a multi-select): one read per drug since the
  rework (a list of the active drugs is out of scope);
- at which dose (`t_metfin_dose`, `t_amlohct_dose`): the dosage of the prescription still open;
- whether a drug was already prescribed or dispensed **in this encounter** (the diabetes visit is
  split in 3 forms: history → request medication → dispense), else **when** it was last
  prescribed / dispensed.

In CHT these come from the last report that holds the field, with no time limit. In FHIR they are
MedicationRequest / MedicationDispense resources, not Observations. The retrieval dictionary (#78)
reads observations and conditions only, so a medication retrieval reads nothing.

### What changes for an author

- A retrieval reads **one drug**: its concept is the drug (no wildcard: without a concept the
  read cannot know it is a medication). It reads the patient's prescriptions of that drug, in
  the current encounter or within the `period` of a history read, and every field reads the
  **latest valid prescription** (validity rule below):
  - **active** (the default, `Latest`; also `Exists`): a valid prescription exists, yes / no;
  - **Count**: number of valid prescriptions;
  - **dosage**: the dosage instruction;
  - **drug**: the drug code actually prescribed (differs from the concept only when the concept
    groups several drugs);
  - **duration**: how many days it is prescribed for;
  - **quantity**: the quantity prescribed;
  - **dispensed**: the quantity dispensed so far against that prescription;
  - **Date of the latest record** (#76): when it was prescribed.
- Without a dictionary entry, the same reads are written `#metformin@` (active now),
  `#metformin@P6M.dosage`, `#metformin@P6M.dispensed`, and for this visit
  `#metformin@encounter.date` (#104).
- "Prescribed but not dispensed" is not a read: authors write a calculate,
  `#metformin@P6M.quantity > #metformin@P6M.dispensed`.
- Drug concepts are expected to be CIEL codes (names such as `metfin` are CHT names kept for now).

### Out of scope

- Writing prescriptions / dispenses (the parked node-type spec).
- Stock / availability.
- Legacy "Prefilled value" nodes: they move to the retrieval dictionary (tricc-frontend#31).
- A list of the active drugs (all drugs, or a class): a later CQL library function, not a read.

---

## Part II — Technical specification

### 1. Design

- `concept_mapper.get_fhir_resource`: `medication` / `drug` / `treatment` already map to
  `MedicationRequest`; add `dispense` → `MedicationDispense`.
- Catalogue entries in `RETRIEVAL_FUNCTIONS` (`tricc_oo/converters/retrieval.py`) and
  `@tricc/core` `terminology/retrieval.ts`, contexts `encounter` / `history`, all needing
  `reads` (the drug), MedicationRequest concepts only (`check_reads_resource`):

| Function | #104 field | Value type | Returns | FHIR source |
|---|---|---|---|---|
| `Latest` (a drug's default) | `active` / `value` | `boolean` | a valid request exists | the validity rule |
| `Exists` / `Count` | `exists` / `count` | `boolean` / `integer` | unchanged, over the valid requests | |
| `LatestDate` (#76) | `date` | `dateTime` | when the latest valid request was written | `authoredOn` |
| `Dosage` | `dosage` | `string` | the dosage instruction | coded `dosageInstruction.doseAndRate.type`, else `dosageInstruction.text` |
| `Drug` | `drug` | `coded` | the drug code prescribed | `medication[x]` (or the referenced `Medication.code`) |
| `Duration` | `duration` | `integer` (days) | how long it is prescribed for | `effectiveDosePeriod` (R4: `dosageInstruction.timing.repeat.boundsPeriod`) length, else `dispenseRequest.validityPeriod` |
| `Quantity` | `quantity` | `decimal` | quantity prescribed | `dispenseRequest.quantity` |
| `Dispensed` | `dispensed` | `decimal` | quantity dispensed so far | sum of completed MedicationDispense `quantity` with `authorizingPrescription` = the request; 0 when none |

- **Validity rule** (which requests are read):
  - status `active`;
  - **no window** (`null`): valid **now**: now is inside `effectiveDosePeriod`; without one,
    inside `dispenseRequest.validityPeriod` (an open start / end counts as unbounded; neither
    period: valid);
  - **window** (e.g. `P6M`): the same period overlaps `[Now() - P6M, Now()]`;
  - `encounter`: the requests of the current encounter, valid now.
  Compared to the day. The Helper is FHIR R4 (`FHIR_VERSION` 4.0.1): `effectiveDosePeriod` is
  R5, so the dose period is the first `dosageInstruction.timing.repeat.boundsPeriod`.
- `populate_helper`: the concept's records define (`"#metformin@P6M:records"`, #104 §4) holds
  its valid requests, latest `authoredOn` first; each field reads `First(…)` of it through a
  Helper function in `cql_helper_populate_block()`:

```cql
define function MedicationRequestPeriod(M MedicationRequest):
  Coalesce(MedicationRequestDosePeriod(M), M.dispenseRequest.validityPeriod)

define function PeriodOverlaps(P FHIR.Period, startTime DateTime, endTime DateTime):
  (P.start.value is null or P.start.value same day or before endTime)
    and (P.end.value is null or P.end.value same day or after startTime)

define function IsValidMedicationRequest(M MedicationRequest, startTime DateTime, endTime DateTime):
  M.status = 'active'
    and PeriodOverlaps(MedicationRequestPeriod(M), startTime, endTime)

define "#metformin@P6M:records":
  ("HistoryMedicationRequests") M
    where MedicationRequestHasCode(M, 'metformin') and IsValidMedicationRequest(M, Now() - 6 months, Now())
    sort by authoredOn.value desc
```

  (`Now(), Now()` for no window and for the encounter, whose source is
  `"EncounterMedicationRequests"`.) Field accessors: `MedicationRequestDosage`,
  `MedicationRequestCode`, `MedicationRequestDuration`, `MedicationRequestQuantity`,
  `MedicationRequestDispensed`.
- MedicationDispense concepts (`dispense` concept type): `Latest` / `Exists` / `Count` /
  `LatestDate` read completed dispenses (`whenHandedOver`); the prescription fields are not
  offered. Dispenses no longer count as "on treatment": they only feed `dispensed`.
- Code match on `medicationCodeableConcept` (and `Medication.code` for `medicationReference`), with
  the concept's own system (CIEL or the project system), never a hard-coded one.
- CHT (`XLSFormCHTStrategy`): contact summary key `<name>` like every catalogue function, listed
  in `<form>.contact-summary.json` under the drug's group (`active`, `dosage`, `quantity`,
  `dispensed`…). CHT reports have no dispense-to-prescription link: the export warns that the
  deployment's contact summary must provide `dispensed`.

### 2. Validation and errors

- A prescription field (`Dosage`, `Drug`, `Duration`, `Quantity`, `Dispensed`) on a concept that
  is not a MedicationRequest → `TriccRetrievalError` (`E_RETRIEVAL_READ_UNSUPPORTED` for an
  implied read).
- Warning when `Dosage` reads a select_multiple concept.

### 3. Tests

- `tests/test_strategies/test_fhir_helper_cql_compile.py`: the helpers compile.
- `retrieval_cql_expression` unit tests per function × context for MedicationRequest and
  MedicationDispense.
- Data cases: active request → read; stopped request → ignored; request whose period ends before
  the window → ignored (pinned on the Helper text where no CQL engine runs).
- A fixture calculate `Retrieve('metformin', 'P6M', 'quantity') > Retrieve('metformin', 'P6M',
  'dispensed')`, built for FHIR and CHT.
- tricc-frontend: `retrieval.test.ts` for the new entries.

### 4. Phases

1. MedicationRequest `Latest` / `Exists` / `Count` / `ActiveDrugs`.
2. `OpenDosage` and `LatestDate` (after #76).
3. MedicationDispense.
4. Rework (2026-11-25): one drug per read, the validity rule, the prescription fields;
   `ActiveDrugs`, `OpenDosage` and the dispense fallback removed.

---

## Open questions

None.

## Decisions

- 2026-11-19: Reworked on top of the retrieval dictionary (#78 / tricc-frontend#31): retrieval
  catalogue functions instead of a dispatch on populate nodes; dates reuse #76 `LatestDate`.
- 2026-11-25: Dosage: a code when the request carries a coded `dosageInstruction.doseAndRate`, else `dosageInstruction.text`. (@delcroip)
- 2026-11-25: ~~"On treatment" also counts a completed dispense within the period when no active request exists.~~ Dropped by the rework below. (@delcroip)
- 2026-11-25: New catalogue functions, not `custom` retrievals. (@delcroip)
- 2026-11-25: Approved for implementation with #75, #76 and #104 on one branch (@delcroip)
- 2026-11-25: Rework: a read names one drug (no wildcard); fields `active` (default), `dosage`,
  `drug`, `duration`, `quantity`, `dispensed` read the latest valid MedicationRequest
  (status active, dose period else validity period: now without a window, overlapping the
  window else). `ActiveDrugs` (every open prescription), `OpenDosage` and the dispense fallback
  are removed; "prescribed but not dispensed" is a calculate; a list of active drugs is a later
  library function. (@delcroip)
