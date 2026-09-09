# Intervention `start`: on-demand launch and follow-up tasks (`tricc.yaml`)

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Related** | `feature/20260907-project-config.md` (Implemented — adds `interventions`; this spec replaces its `kind` / `applicability` keys), `feature/careplan.md` (Draft — **superseded by this spec on approval**), `feature/careplan-intervention-plandefinition.md`, `feature/opensrp-register.md`, `feature/populate-context.md`, `docs/open-srp-export.md`, `docs/cli-and-inputs.md` |
| **Strategy** | `XLSFormCHTStrategy` (+ `XLSFormCHTHFStrategy`), `OpenSRPStrategy`. Other strategies build the forms and ignore `start`. |
| **Approval** | — |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business description

*Audience: clinical authors, guideline developers, implementers.*

## 1. What this is

An intervention in `tricc.yaml` today only says *which drawings* it is made of. It does
not say **when a health worker can start it**. Two cases matter:

- **On demand** — a button in the app. Available to a patient who meets a condition
  (e.g. under 5 years). Started at any time.
- **Follow-up** — a form that becomes **due some time after another form was
  submitted**, only when that first form says so (e.g. "pneumonia → revisit in 3 days").
  It shows up as a task, has a window, and disappears once done.

This spec adds one `start` block per intervention that describes this. The same YAML
drives CHT (app form + task) and OpenSRP (PlanDefinition / ActivityDefinition), so the
clinical logic is written once.

It replaces the `kind` and `applicability` keys introduced by
`feature/20260907-project-config.md`, and supersedes the drawing-level `schedule` node of
`feature/careplan.md`.

## 2. File shape

```yaml
title: Almanach Global

interventions:
  - id: pediatrics
    title: Pediatrics
    activity: [common/*, child/*]
    start:
      on: demand
      condition: "AgeInMonths() < 60"

  - id: pediatrics_followup
    title: Pediatrics follow-up
    activity: [common/*, followup/*]
    start:
      on: follow_up
      intervention: pediatrics
      condition: "classification = 'pneumonia'"
      due: 3 d
      window:
        before: 0 d
        after: 4 d
```

`start` may also be a **list** when one intervention is both on demand and a follow-up.

## 3. Keys

| Key | Meaning | Required |
|-----|---------|----------|
| `on` | `demand` (button) or `follow_up` (task after another form). | yes |
| `intervention` | Id of the parent intervention whose **submission** starts the clock. | when `on: follow_up` |
| `condition` | CQL boolean. Who is eligible (`demand`) or whether this follow-up is needed (`follow_up`). Omitted = always. | no |
| `due` | How long after the parent submission the follow-up is due. UCUM time quantity, units `s`, `min`, `h`, `d`, `wk`, `mo` only: `3 d`, `2 wk`, `6 mo`, `12 h`. Stored internally in seconds. | when `on: follow_up` |
| `window.before` / `window.after` | How long before / after `due` the task is visible. Default `0 d` / `0 d` (visible on the due day only). | no |

Not allowed: `due` / `window` / `intervention` with `on: demand`.

**Anchor.** The clock starts when the parent form is **submitted**. Starting from a date
answered in the parent form, or from a registration event, is future work.

**Resolution.** A follow-up task is resolved when its form is submitted within the window.
After `window.after` passes, it expires. Nothing else resolves it.

**Condition language.** `condition` is CQL, the same dialect used in draw.io rhombus and
calculate labels. For a follow-up it may reference export names of the **parent** form
(`classification`, `p_weight`) and patient functions (`AgeInMonths()`). For an on-demand
form it may reference patient attributes only (age, sex, contact-level flags).

## 4. What each strategy produces

| | `on: demand` | `on: follow_up` |
|---|---|---|
| **CHT** | XLSForm as today. `condition` → `context.expression` of `{form_id}.properties.json`, in JavaScript over `contact`. | Follow-up XLSForm as today, plus: a hidden calculate in the **parent** form computing `condition` in ODK logic; `{form_id}.js` (existing task module shape) whose `appliesIf` reads that calculate, `events` from `due` / `window` in days, `resolvedIf` = follow-up report exists for that parent report. Parent answers the follow-up needs are injected as hidden inputs, as the pause mechanism does today. |
| **OpenSRP** | Intervention PlanDefinition as today. `condition` → applicability `condition` (`text/cql`) on the wrapper action (replaces `applicability`). | The parent PlanDefinition gains an action with `relatedAction` (`after-end` + `offsetDuration` = `due`), `condition` = CQL, timing bounds from `window`, and `definitionCanonical` → an ActivityDefinition of kind `Task` whose focus is the follow-up Questionnaire. `$apply` yields the CarePlan + Task. |
| **XLSForm / ODK, OpenMRS, DHIS2, FHIR (plain)** | Form built; `start` ignored with an info log. | Same. |

## 5. Worked example

Pediatrics classifies pneumonia. The follow-up should appear 3 days later and stay 4 more
days.

- CHT: `pediatrics.xlsx` gets a hidden `start_pediatrics_followup` calculate
  (`${classification} = 'pneumonia'`). `pediatrics_followup.js` appliesIf checks that field
  is `'true'`; `events: [{days: 3, start: 0, end: 4}]`; opening the task pre-fills the
  follow-up `inputs` from the pediatrics report.
- OpenSRP: `PlanDefinition/pediatrics` has an extra action "Pediatrics follow-up",
  `relatedAction: {actionId: <pediatrics action>, relationship: after-end, offsetDuration: 3 d}`,
  condition `classification = 'pneumonia'`, → `ActivityDefinition/pediatrics_followup`
  (kind Task). Submitting Pediatrics produces a Task due in 3 days with a 0/4-day window.

## 6. Limitations

- Anchor is parent submission only (no "from a date field", no registration event).
- CHT `on: demand` conditions are limited to what can be rendered as JavaScript over
  `contact`: comparisons, and/or/not, age functions, static values, contact fields. Anything
  else fails the CHT build with a clear message.
- CHT follow-up `condition` may only reference export names present in the parent form (it
  is evaluated inside that form). CQL that needs history (`Diagnosis()` over past
  encounters) works on OpenSRP, and fails the CHT build.
- No recurring / periodic schedules (that was `careplan.md` `mode: periodic`; deferred).
- Chains (follow-up of a follow-up) are allowed by the shape; each link is independent.
- `kind` and `applicability` are removed; a file still using them fails with a message
  pointing to `start`.

---

# Part II — Technical specification

*Audience: developers.*

## 1. Schema (`tricc_oo/models/project_config.py`)

```text
TriccInterventionStart
  on: Literal["demand", "follow_up"]
  intervention: Optional[str]       # required iff on == "follow_up"
  condition: Optional[str]          # CQL boolean
  due: Optional[TriccDuration]      # required iff on == "follow_up"
  window: TriccStartWindow = {before: 0, after: 0}

TriccStartWindow
  before: TriccDuration = 0 s
  after: TriccDuration = 0 s

TriccDuration                       # parsed from "3 d", "2 wk", "12 h"; stored as seconds (int)

TriccInterventionConfig
  id, title, description, activity  # unchanged
  start: List[TriccInterventionStart] = [ {on: demand} ]   # scalar or list in YAML
  # removed: kind, applicability
```

Validation (all build errors):

- `on: demand` with `intervention` / `due` / `window` set.
- `on: follow_up` without `intervention` or `due`.
- `intervention` not an id in the same `tricc.yaml`, or equal to its own id.
- `kind` / `applicability` present → `"kind/applicability were replaced by start: — see feature/20260907-intervention-start.md"`.
- Duration: negative, unit not in UCUM set, or unparsable.
- `condition` must parse with `transform_cql_to_operation` (fail early, at config load).

## 2. Duration parser (`tricc_oo/converters/duration.py`, new)

Input: `"<number> <unit>"`, restricted to the UCUM time subset
`s`, `min`, `h`, `d`, `wk`, `mo` (`mo` = 30 d — document the approximation).
No years (`a`), no other UCUM units; anything else is a config error naming the
allowed list. Output: seconds (int).
Helpers: `to_days(seconds, round_up=True)` for CHT `events`; `to_fhir_duration(seconds)` →
`{"value": n, "unit": "d", "system": "http://unitsofmeasure.org", "code": "d"}` (pick the
largest unit that divides exactly; default days).

## 3. Runner (`tricc_oo/runner.py`)

Jobs stay one per intervention. Add a **project-wide pass** after all interventions in a
strategy have been built, because follow-ups touch the parent's artifacts:

1. Build every intervention as today (independent `TriccProject`s). Keep each
   `TriccProject` + output strategy instance in a map by intervention id.
2. For each intervention with `start.on == "follow_up"`, call
   `output_strategy.link_follow_up(parent_ctx, child_ctx, start)` on the **parent's**
   strategy instance. Strategies not implementing it inherit a no-op that logs at info.

`TriccProject.intervention` keeps carrying the `TriccInterventionConfig`.

## 4. Condition rendering

`condition` → `transform_cql_to_operation` → `TriccOperation`. Then per strategy:

| Use | Renderer | Reference resolution |
|-----|----------|----------------------|
| OpenSRP (both cases) | raw CQL string as today | none (CQL library resolves) |
| CHT `follow_up` | existing XLSForm XPath renderer, as a `calculate` row appended to the **parent** survey, name `start_<child_id>` | references must be export names in the parent `df_survey`; otherwise error |
| CHT `demand` | new `tricc_oo/serializers/js_expression.py`: renders `AND/OR/NOT`, comparisons, `TriccStatic`, `AGE_*` (→ `ageInMonths(contact)` etc. from `nools-extras`), `TriccReference` → `contact.<name>`; anything else raises `NotImplementedError` with the operator name | contact fields |

## 5. CHT emission (`tricc_oo/strategies/output/xlsform_cht.py`, `visitors/xform_pd.py`)

**On demand.** Write `{form_id}.properties.json`:

```json
{"title": "...", "context": {"person": true, "place": false, "expression": "<js>"}}
```

Only when `condition` is set; otherwise no file (today's behaviour).

**Follow-up** (`link_follow_up`):

1. Append `start_<child_id>` calculate to the parent `df_survey`; rewrite `{parent_form_id}.xlsx`.
2. Compute hidden inputs: export names referenced by the child form (`populate` nodes with
   `context: encounter`, or names in the child's `inputs` group) that exist in the parent
   survey. Reuse `get_tasksstrings` for the `content[...] = getField(report, ...)` lines.
3. Write `{child_form_id}.js` with `get_task_js`, extended with parameters:
   `applies_field` (`start_<child_id>`), `days`, `start`, `end`, `parent_form_ids`. The
   `appliesIf` becomes `getField(report, '<applies_field>') === 'true'`; the commented
   `events` block uses the computed days; `resolvedIf` unchanged
   (`isFormArrayHasSourceId` on the child form id).
4. Remove the `kind == "task"` warning.

Day conversion: `days = ceil(due / 86400)`, `start = ceil(window.before / 86400)`,
`end = ceil(window.after / 86400)`.

## 6. OpenSRP emission (`tricc_oo/strategies/output/opensrp.py`)

**On demand.** `generate_intervention_plandefinition`: replace the `applicability` lookup
with the first `start` entry whose `on == "demand"`; same `condition` emission.

**Follow-up** (`link_follow_up` on the parent strategy):

1. Add to the parent PlanDefinition wrapper action a child action:
   - `id`: `fhir_resource_id(parent, "action", child_id)`, `title`: child title
   - `condition`: applicability, `text/cql`, from `start.condition` (if set)
   - `relatedAction`: `[{actionId: <parent's last process action id>, relationship: "after-end", offsetDuration: to_fhir_duration(due)}]`
   - `timing` (`timingTiming.repeat`): `boundsDuration` = `due + window.after`; extension
     `tricc-window-before` for `window.before` (FHIR Timing has no "show early" concept —
     document).
   - `definitionCanonical`: `{base_url}/ActivityDefinition/{child_ad_id}`
2. Emit `ActivityDefinition/{child_ad_id}`: `kind: Task`, `status: active`,
   `code` = tricc concept for the child intervention, `dynamicValue` setting `Task.focus`
   to the child Questionnaire canonical, `Task.reasonReference` to the parent QR.
   Write under `activity-definition/`; add to the manifest / FSH like PlanDefinitions.
3. Relax `validate()`: ActivityDefinition is allowed as `definitionCanonical` **only** on
   follow-up actions (not on the Start-care path). Keep the existing guard for others.
4. Remove the `kind == "task"` warning.

Verification item (before Approved → Implemented): confirm on a fhircore build that
`$apply` of this PD creates a Task with `executionPeriod` derived from `relatedAction`
+ `timing`, and that the Task launches the child Questionnaire. If fhircore needs a
different shape (e.g. Task via StructureMap as `generate_task_structuremap` does today),
adapt step 2 and record the decision here.

## 7. Code checklist

- [ ] Schema + validators; remove `kind` / `applicability` with migration error.
- [ ] `tricc_oo/converters/duration.py` UCUM → seconds, days, FHIR Duration.
- [ ] CQL parse at config load.
- [ ] `BaseOutputStrategy.link_follow_up` no-op + runner second pass.
- [ ] CHT: `properties.json` context expression; JS renderer subset.
- [ ] CHT: parent calculate, hidden inputs, `{child}.js` from `get_task_js` with new params.
- [ ] OpenSRP: PD follow-up action + ActivityDefinition + validate relaxation.
- [ ] Docs: `docs/cli-and-inputs.md`, `docs/tricc.yaml.template`, `docs/open-srp-export.md`;
      amend `feature/20260907-project-config.md` (in place) to point here; mark
      `feature/careplan.md` Superseded.
- [ ] Tests (see §8).

## 8. Tests

- Schema: scalar vs list `start`; `demand` with `due` fails; `follow_up` without parent fails;
  unknown parent fails; `kind` present fails with pointer.
- Duration: `3 d`, `2 wk`, `12 h`, `6 mo`, `90 min`, `30 s` → seconds; days rounding;
  FHIR Duration shape; `1 a` and non-time units fail.
- CHT demand: `AgeInMonths() < 60` → `properties.json` with `ageInMonths(contact) < 60`;
  unsupported operator fails.
- CHT follow-up (two YAML fixture forms): parent gets `start_<child>` calculate with the
  expected XPath; child `.js` contains `appliesIf` on that field and `days: 3, start: 0,
  end: 4`; hidden inputs lines for shared export names; condition referencing an unknown
  parent name fails.
- OpenSRP follow-up: PD has the action with `relatedAction.offsetDuration = 3 d`,
  CQL condition, `definitionCanonical` → AD; AD file written; `validate()` passes.
- Existing project-config tests updated for the removed keys.

## 9. Implementation phases

1. Schema, duration parser, CQL-at-load, on-demand `condition` on CHT (`properties.json`)
   and OpenSRP (replaces `applicability`). Remove `kind`.
2. CHT follow-up: runner second pass, parent calculate, `{child}.js`, hidden inputs.
3. OpenSRP follow-up: PD action + ActivityDefinition, after the fhircore verification.

## 10. Acceptance criteria

- Almanach-style project with `pediatrics` + `pediatrics_followup` builds on
  `XLSFormCHTStrategy` and `OpenSRPStrategy` from one `tricc.yaml`, producing the artifacts
  in §4 with no hand edits beyond pasting the `.js` module export into the app's `tasks.js`.
- A `tricc.yaml` without `start` behaves exactly as today (on demand, no condition).
- Full test suite passes.
