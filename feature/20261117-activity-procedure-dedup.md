# Run an activity once per encounter on openSRP: record it as a Procedure

| Field             | Value |
| ----------------- | ----- |
| **Status**        | Approved (2026-11-17, RFC #81) |
| **RFC**           | #81 |
| **Branch target** | `feature/activity-procedure-dedup` → `develop` |
| **Scope**         | `FHIRStrategy` → `OpenSRPStrategy`, `visitors/tricc` (`get_prev_instance_skip_expression`), `converters/fhir` (`structuremap`, `concept_mapper`, `populate_helper`) |
| **Related**       | #74 (Procedure populate helpers, which this RFC reuses); `feature/20260812-intervention-order-and-dedup.md` (does the same thing for questions, not activities); `feature/concept-repeat.md` (repeat slots) |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

### The problem

An author can call the same activity from several places, for example "Danger signs" from triage
and again from the consultation. In the XLSForm / CHT export, a later call is skipped when an
earlier call of the same activity, with the same repeat, was already shown. The health worker
sees the activity once.

The openSRP (FHIR) export has no such rule:

- **Within one form**, each call of the activity is a separate group, and every call whose own
  condition is true is shown. The health worker can fill in the same activity twice.
- **Across forms**, openSRP makes one form per step of the visit (registration, triage,
  consultation…). A later form has no way to know that an earlier form already ran the
  activity, so it runs it again.

Questions already avoid this: an answer saved by an earlier form in the same visit is
pre-filled in the next one (`feature/20260812-intervention-order-and-dedup.md`). Activities do
not.

### What changes for an author

Nothing in the drawing. In the openSRP export:

- Within one form, the same rule as CHT applies: a later call of an activity is skipped when an
  earlier call with the same repeat was shown.
- When a form shows an activity, it saves a record for the visit that says "this activity, with
  this repeat, was done". That record is a FHIR **Procedure** whose code is the activity's
  code.
- A later form in the same visit reads those records when it opens. An activity, with a given
  repeat, that was already done in this visit is skipped.

### Out of scope

- Skipping an activity done in an **earlier visit**. Only the current encounter counts.
- Changing the CHT / XLSForm behaviour.
- Saving the answers inside the activity: they are saved as today (Observations / Conditions).

---

## Part II — Technical specification

### 1. Design

**a. Same rule inside one Questionnaire.** `get_prev_instance_skip_expression`
(`tricc_oo/visitors/tricc.py`) is only called from the XLSForm serializer
(`tricc_oo/serializers/xls_form.py`, group relevance). `FHIRStrategy._effective_relevance`
(`tricc_oo/strategies/output/fhir_form.py`) returns `activity.relevance` for an activity group
without it. Apply the same composition there (applicability, then the previous-instance skip),
so that the group's `enableWhenExpression` matches the XLSForm `relevant`. Earlier instances
that were exported in **another** Questionnaire are not in this one, so they are left out here
and handled by (c).

**b. Save "activity done" as a Procedure.** "Done" means the group was shown. For each
activity instance in a Questionnaire, add a hidden boolean calculate
`<activity export name>_done` whose `calculatedExpression` is the two parts of the group's
`enableWhenExpression` from (a):

```
<activity>_done = sequence logic (applicability and activity.relevance)
                  and not (earlier same-repeat instance in this Questionnaire was shown)
                                                      # get_prev_instance_skip_expression
```

The read-back term from (c) is left out: an activity skipped because an earlier Questionnaire
already did it must not write a second Procedure, and it does not need to.

Add a new extraction kind `procedure` to `classify_extraction`
(`converters/fhir/concept_mapper.py`) and a StructureMap rule
(`converters/fhir/structuremap.py`) that runs only when the value is `true` (the existing
`only_when_true` path) and writes:

```
Procedure
  status    = completed
  code      = <activity code> (project CodeSystem)
  subject   = patient
  encounter = current encounter
  performed = now
  extension = TRICC_OBSERVATION_REPEAT_EXT, only when repeat != 1
              (fml_repeat_extension_on_target, converters/fhir/repeat_helper.py)
```

The repeat slot is written exactly as on an Observation, so a CQL filter written for one works
for the other.

**c. Read it back in the next Questionnaire.** For each activity instance whose base activity
has an instance in an earlier process (`PROCESSES` order, `visitors/utils.py`), add a hidden
populate item whose `initialExpression` is
`Helper.GetEncounterProcedureValue('<activity code>', <repeat>)`. That helper comes from #74,
which is not on `develop` yet: `resolve_populate_reference`
(`converters/fhir/populate_helper.py`) still sends a `Procedure` target to the Observation
accessor. #74 lands first, and its encounter helper takes a repeat index the same way
`GetEncounterObservationValue(code, repeatIndex, period)` does (`null` for slot 1). AND the
negation of that populate item into the group's `enableWhenExpression`:

```
enableWhen(group) = applicability and own relevance
                    and not (earlier instance in this Questionnaire was shown)
                    and not (%resource…linkId='<activity>_done_prev'…answer = true)
```

The populate item is pruned like any other unused hidden calculate when nothing reads it.

**d. Activity code.** Use the activity's `name` (the code the YAML / drawio activity carries) as
the Procedure code in the project CodeSystem, with `concept_type: procedure`. If the CodeSystem
has no concept for it, add one at export, as for other generated concepts. Authors do not add
one per activity.

### 2. Validation and errors

- An activity with no `name` / code cannot be saved: log a warning and keep only the rule
  inside the Questionnaire (a).
- Two activities that resolve to the same code: export error, since they would skip each other.

### 3. Tests

- YAML fixture `tests/data/yaml/activity_called_twice.yaml`: one activity called from two
  processes (and twice within one process, once with another repeat).
- `tests/test_strategies/test_opensrp_strategy.py`:
  - inside one Questionnaire, the second same-repeat group's `enableWhenExpression` negates
    the first; another repeat is not negated.
  - the first Questionnaire has `<activity>_done` and a StructureMap rule creating a Procedure
    with the activity code, encounter and repeat.
  - the second Questionnaire's group negates the `GetEncounterProcedureValue` populate item.
- `tests/test_strategies/test_fhir_helper_cql_compile.py`: the helper with `repeat` compiles.

### 4. Phases

1. (a) Same rule inside one FHIR Questionnaire.
2. #74 lands, with the encounter helper taking a repeat index.
3. (b) Procedure extraction of `<activity>_done`.
4. (c) Populate and enableWhen in later Questionnaires; docs in `docs/open-srp-export.md`.

---

## Open questions

None.

## Decisions

- 2026-11-17: The Procedure code is the activity `name`. A `procedure` concept is added to the
  generated CodeSystem when it is missing. (@delcroip)
- 2026-11-17: "Done" means the group was shown. `<activity>_done` is the sequence logic AND
  `get_prev_instance_skip_expression`. (@delcroip)
- 2026-11-17: The repeat slot reuses the Observation repeat extension (`TRICC_OBSERVATION_REPEAT_EXT`).
  (@delcroip)
- 2026-11-17: #74 lands first. Checked in code: it is not on `develop`. Its encounter helper takes a
  repeat index. (@delcroip)
