# Run an activity once per encounter on openSRP: record it as a Procedure

| Field             | Value |
| ----------------- | ----- |
| **Status**        | Implemented (2026-11-17, RFC #81) |
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
- When an activity is called from more than one form and a form shows it, that form saves a
  record for the visit that says "this activity, with this repeat, was done". That record is a
  FHIR **Procedure** whose code is the activity's code.
- The other forms of the visit read those records when they open. An activity, with a given
  repeat, that was already done in this visit is skipped. Whichever form runs first does it.

### Out of scope

- Skipping an activity done in an **earlier visit**. Only the current encounter counts.
- Changing the CHT / XLSForm behaviour.
- Saving the answers inside the activity: they are saved as today (Observations / Conditions).

---

## Part II — Technical specification

### 1. Design

**a. Same rule inside one Questionnaire.** `get_prev_instance_skip_expression`
(`tricc_oo/visitors/tricc.py`) was only called from the XLSForm serializer
(`tricc_oo/serializers/xls_form.py`, group relevance). `FHIRStrategy.generate_relevance`
(`tricc_oo/strategies/output/fhir_form.py`) now composes, for an activity group
(`_compose_activity_group_relevance`), applicability and the previous-instance skip, and caches
the result so `_effective_relevance` (and any inlined copy) returns it. *Earlier* is the
depth-first order of the groups in the Questionnaire (`_group_position`), not the relevance walk
order, which can reach a later call first; the function takes the earlier instances as
`past_instances`. Instances in **another** Questionnaire are left out here and handled by (b, c).

**b. Save "activity shown" as a Procedure.** Only for an activity whose instances are in more
than one Questionnaire (`_activity_groups_by_base`); one used in a single Questionnaire needs
nothing more than (a). Each of those Questionnaires gets, per activity code and repeat slot, one
hidden boolean `<code>_done` item (`<code>_Rr_<n>_done` for slot `n != 1`), added after the
export walk (`_add_activity_done_items`). Its `calculatedExpression` is "one of the activity's
groups here is shown", i.e. their whole `enableWhenExpression`:

```
<code>_done = (sequence logic and not earlier same-repeat group here)   # (a), OR over the groups
              and not <code>_done_prev                                  # (c)
```

A group skipped because the activity was done earlier in the encounter is not shown, so it
writes no second Procedure.

A new extraction kind `procedure` (`build_procedure_extraction_rule`,
`converters/fhir/structuremap.py`) dispatches only when the answer is `true` and writes:

```
Procedure
  status    = completed
  code      = <activity code>
  subject   = QuestionnaireResponse.subject
  encounter = QuestionnaireResponse.encounter
  performed = QuestionnaireResponse.authored
  extension = TRICC_OBSERVATION_REPEAT_EXT, only when repeat != 1
              (fml_repeat_extension_on_target, converters/fhir/repeat_helper.py)
```

Its group is `extract_procedure_<code>` (`_rule_group_name`), so it never merges with an
Observation group of the same code.

**c. Read it back.** In the same Questionnaires, when another one holds an instance with the same
repeat, a hidden boolean `<code>_done_prev` item gets the CQL `initialExpression`
`ActivityDone_<linkId>` = `Helper.GetEncounterProcedureValue('<code>', <repeat>)`, and
`(… linkId='<code>_done_prev' … = true).not()` is ANDed into each of the activity's groups there.
The read-back goes both ways: the process order of a visit is not fixed, so whichever form runs
first records the activity and the other skips it.

`GetEncounterProcedureValue(code, repeatIndex)` and `GetHistoryProcedureDate(code)` are the #74
helpers (`cql_helper_repeat_block`, `converters/fhir/repeat_helper.py`): a Procedure counts when
`status = completed` and its outcome is not *Unsuccessful* (`385671000`, matched by code across
any system, `fix/20260914-cql-retrieve-codesystem.md`). `resolve_populate_reference`
(`converters/fhir/populate_helper.py`) dispatches `Procedure` concept types to them, typed
`boolean` (encounter) and `date` (history).

**d. Activity code.** The name of the activity's start node (else the activity name), of the base
activity. A code missing from the project terminology uses `{base_url}/CodeSystem/tricc`, like
any other concept. No concept is added at export: project CodeSystems are written when the input
is loaded, before any output strategy runs.

### 2. Validation and errors

- An activity with no code: warning; only the rule inside the Questionnaire (a) applies.
- Two activities with the same code: error logged; neither is recorded nor read back, since they
  would skip each other. The export goes on.
- A group relevance that cannot be written in FHIRPath: warning; no `<code>_done` for it (no
  record rather than a wrong one).

### 3. Tests

- Fixtures: `tests/data/yaml/activity_called_twice.yaml` (two calls in one process),
  `activity_called_across_processes.yaml` (triage and history-and-physical),
  `activity_code_clash.yaml` (two activities, one code).
- `tests/test_activity_procedure_dedup.py`: the second same-repeat group negates the first, as
  in XLSForm; no `_done` for a single-Questionnaire activity; `<code>_done` equals the group
  enableWhen; the Procedure FML group; the `_done_prev` populate and its CQL define; the group
  negates it; the code clash; the repeat extension and group naming of a procedure rule.
- `tests/test_populate_context.py`: Procedure dispatch and types (#74).
- `tests/test_strategies/test_fhir_helper_cql_compile.py`: the Procedure helpers, their
  encounter scoping and the "done" rule.

### 4. Phases

1. (a) Same rule inside one FHIR Questionnaire.
2. #74 helpers, the encounter one taking a repeat index.
3. (b) Procedure extraction of `<code>_done`.
4. (c) Read-back populate and enableWhen; docs in `docs/open-srp-export.md`.

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
- 2026-11-17 (implementation): `<code>_done` also carries the read-back term. Without it, a
  call skipped because another form already did the activity would still write a Procedure;
  with it, `_done` is exactly "the group is shown". The read-back goes both ways, since the
  process order of a visit is not fixed.
- 2026-11-17 (implementation): only activities used by more than one Questionnaire get
  `_done` / `_done_prev`, one pair per code and repeat slot per Questionnaire.
- 2026-11-17 (implementation): no concept is added to the CodeSystem at export (they are
  written at load); a missing code uses `{base_url}/CodeSystem/tricc`. Supersedes the first line
  above until the load step adds activity concepts.
- 2026-11-17 (implementation): the "Unsuccessful" outcome is matched by code alone, like every
  code in the Helper library. `GetHistoryProcedureDate` has no lookback period (as
  `GetHistoryConditionValue`); the #74 open point stays open.
