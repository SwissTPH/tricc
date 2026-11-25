# Retrievals of medication: on treatment, drugs, open dosage and last date

| Field             | Value |
| ----------------- | ----- |
| **Status**        | Approved (2026-11-25, RFC #75) |
| **Branch target** | `feature/retrievals` → `develop` |
| **Scope**         | `converters/retrieval.py`, `FHIRStrategy` (`converters/fhir/populate_helper.py`, `repeat_helper.py`), `converters/fhir/concept_mapper.py`, `XLSFormCHTStrategy` |
| **Related**       | `feature/20261109-project-retrievals.md` (#78, the retrieval dictionary this extends), SwissTPH/tricc-frontend#31 (mirror the catalogue entries into `@tricc/core` `terminology/retrieval.ts`), #76 (`LatestDate`, reused for request / dispense dates), #104 (implied reads: `#antidiabetic@.drugs`, `#metformin@P6M.dosage`, `#metformin@.date`, `#metformin@encounter.date` call these functions without a dictionary entry), `feature/20260812-medication-request-dispense-node.md` (parked: *writing* MedicationRequest / Dispense; this RFC *reads* them) |
| **RFC**           | SwissTPH/tricc#75 |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

### The problem

Chronic-care flows (CombaScale diabetes / hypertension, `SwissTPH/combacal-plus` `dm_int`) need to
know what the patient is currently taking before deciding to continue, updose or switch treatment:

- is the patient on treatment at all (`t_dm_tx`, `t_aht_tx`);
- which drugs (`t_dm_drugs`, `t_aht_drugs`, a multi-select);
- at which dose (`t_metfin_dose`, `t_amlohct_dose`): the dosage of the prescription still open;
- whether a drug was already prescribed or dispensed **in this encounter** (the diabetes visit is
  split in 3 forms: history → request medication → dispense), else **when** it was last
  prescribed / dispensed.

In CHT these come from the last report that holds the field, with no time limit. In FHIR they are
MedicationRequest / MedicationDispense resources, not Observations. The retrieval dictionary (#78)
reads observations and conditions only, so a medication retrieval reads nothing.

### What changes for an author

- A retrieval whose concept is a medication reads the patient's medication records, in the
  current encounter or within the `period` of a history read:
  - **Latest** / **Exists**: on treatment yes / no (an open prescription, or a dispense);
  - **Count**: number of open prescriptions;
  - **Active drugs**: the drug codes of the open prescriptions (for a multi-select);
  - **Open dosage**: the dosage of the open prescription for that drug;
  - **Date of the latest record** (#76): when it was last prescribed or dispensed.
- Without a dictionary entry, the same reads are written `#antidiabetic@.drugs`,
  `#metformin@P6M.dosage`, `#metformin@.date`, and for this visit
  `#metformin@encounter.date` (#104).
- Drug concepts are expected to be CIEL codes (names such as `metfin` are CHT names kept for now).

### Out of scope

- Writing prescriptions / dispenses (the parked node-type spec).
- Stock / availability.
- Legacy "Prefilled value" nodes: they move to the retrieval dictionary (tricc-frontend#31).

---

## Part II — Technical specification

### 1. Design

- `concept_mapper.get_fhir_resource`: `medication` / `drug` / `treatment` already map to
  `MedicationRequest`; add `dispense` → `MedicationDispense`.
- New catalogue entries in `RETRIEVAL_FUNCTIONS` (`tricc_oo/converters/retrieval.py`) and
  `@tricc/core` `terminology/retrieval.ts`, contexts `encounter` / `history`:
  - `ActiveDrugs`: needs `reads` (the drug class or a select concept), value type `coded`
    (multi-select);
  - `OpenDosage`: needs `reads` (the drug), value type `string`.
  Both are rejected (`unsupported`) on a non-medication resource.
- `populate_helper.retrieval_cql_expression`: a `MedicationRequest` / `MedicationDispense` branch
  next to the Condition one, calling new Helper functions in `cql_helper_populate_block()`:

| Function | `encounter` | `history` (`since`) |
|---|---|---|
| `Latest` / `Exists` | `GetEncounterMedicationRequestValue(code)`, or a completed dispense in the encounter | `exists(GetActiveMedicationRequests(code, since))`, or `exists(GetMedicationDispenses(code, since))` |
| `Count` | `Count(GetEncounterMedicationRequests(code))` | `Count(GetActiveMedicationRequests(code, since))` |
| `ActiveDrugs` | `GetEncounterMedicationCodes()`: codes of this encounter's open requests | `GetActiveMedicationCodesSince(since)` |
| `OpenDosage` | `GetEncounterMedicationDosage(code)` | `GetMedicationDosageSince(code, since)` |
| `LatestDate` (#76) | `GetEncounterMedicationRequestDate(code)` (`authoredOn`) / `GetEncounterMedicationDispenseDate(code)` (`whenHandedOver`) | `GetMedicationRequestDate(code, since)` / `GetLastMedicationDispenseDate(code, since)` |

MedicationDispense (`dispense` concept type): `Latest` / `Exists` / `Count` read completed
dispenses (`GetEncounterMedicationDispenses(code)`, `GetMedicationDispenses(code, since)`);
`ActiveDrugs` / `OpenDosage` read prescriptions only.

- "Open" request = `status = 'active'` (not `completed`, `stopped`, `cancelled`,
  `entered-in-error`), optionally bounded by `dispenseRequest.validityPeriod`.
- Code match on `medicationCodeableConcept` (and `Medication.code` for `medicationReference`), with
  the concept's own system (CIEL or the project system), never a hard-coded one.
- CHT (`XLSFormCHTStrategy`): unchanged, contact summary key `<name>` like every catalogue
  function.

### 2. Validation and errors

- `ActiveDrugs` / `OpenDosage` on a non-medication concept → `TriccRetrievalError`.
- Warning when `OpenDosage` reads a select_multiple concept.

### 3. Tests

- `tests/test_strategies/test_fhir_helper_cql_compile.py`: the helpers compile.
- `retrieval_cql_expression` unit tests per function × context for MedicationRequest and
  MedicationDispense.
- Data cases: active request → read; stopped request → ignored; request outside the period →
  ignored.
- tricc-frontend: `retrieval.test.ts` for the new entries.

### 4. Phases

1. MedicationRequest `Latest` / `Exists` / `Count` / `ActiveDrugs`.
2. `OpenDosage` and `LatestDate` (after #76).
3. MedicationDispense.

---

## Open questions

None.

## Decisions

- 2026-11-19: Reworked on top of the retrieval dictionary (#78 / tricc-frontend#31): retrieval
  catalogue functions instead of a dispatch on populate nodes; dates reuse #76 `LatestDate`.
- 2026-11-25: Dosage: a code when the request carries a coded `dosageInstruction.doseAndRate`, else `dosageInstruction.text`. (@delcroip)
- 2026-11-25: "On treatment" also counts a completed dispense within the period when no active request exists. (@delcroip)
- 2026-11-25: New catalogue functions (`ActiveDrugs`, `OpenDosage`), not `custom` retrievals. (@delcroip)
- 2026-11-25: Approved for implementation with #75, #76 and #104 on one branch (@delcroip)
