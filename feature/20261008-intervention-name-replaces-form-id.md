# Intervention `name` replaces `form_id`; activity `name`

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `feature/20260907-project-config.md` (Implemented; superseded in part), `feature/20260915-intervention-start.md` (Implemented; superseded in part), `../tricc_frontend/feature/20261008-codes-and-activity-settings.md` §2.3 (source of this spec) |
| **Strategy** | All output strategies (XLSForm, CHT, HTML/OpenMRS, DHIS2, SPICE, FHIR, OpenSRP, TestSpec); `DrawioStrategy`, `YamlStrategy` |
| **Source** | Patrick, 2026-10-08 (later: "the name in tricc is what I meant by code; use name instead"): "`form_id` is a remnant of previous approaches. I would rather have an activity code, a process, and an intervention code. `tricc_oo` should adapt." Also: "the notion of intervention is new in `tricc_oo`; `form_id` should have been removed when it was added." |
| **Approval** | Approved 2026-10-08 (Patrick) |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This is debt cleanup, not a new capability. Interventions made the intervention the form, so
a form name written on one drawing is redundant.

---

## Part I — Business description

Today the name of every generated form (the XLSForm file and its `form_id` setting, the CHT
form, the DHIS2 program, the FHIR Questionnaire and StructureMap ids, …) comes from `form_id`
on the main start shape of one drawing. That fitted the time when one drawing was one form.

A project now declares interventions in `tricc.yaml`, and the form belongs to the
intervention. So each level gets its own identifier:

| Level | Identifier | Used for |
|-------|------------|----------|
| Intervention | `name` (new; defaults to the intervention `id`) | The form name in every output |
| Process | `process` (unchanged) | Which part of the encounter a page starts |
| Activity | `name` (YAML: new, optional; draw.io: the root shape's `name`, as today) | The activity's stable name in outputs |

**Projects with an `interventions:` list.** The intervention `name` names the form. A
`form_id` still written on a drawing or a YAML activity is ignored, and the build warns once
per distinct value: `form_id is ignored when interventions are declared; set interventions[].name`.
To keep today's form names, copy the old `form_id` into `name` (the app does this on import).

**Older projects** (a single drawing or YAML file, or a `tricc.yaml` without
`interventions:`). Nothing changes: the main start's `form_id` names the form. When there is
none, the project title (as a slug) is used instead of failing or falling back to a fixed name.

**Limits.** `form_id` is not removed from the readers, so old drawings keep working; it is only
deprecated in the docs.

---

## Part II — Technical specification

### 2.1 Config and model

- `TriccInterventionConfig` (`models/project_config.py`) gets `name: Optional[str]`, stripped,
  empty → `None`.
- `TriccIntervention.intervention_name() -> str` is the one place outputs read the form name:
  - **Intervention set** (`TriccIntervention.config` is not `None`): `intervention.name or
    intervention.id`. Every `form_id` found on a loaded root (`start_pages`, `pages`) is
    reported with the warning above, once per distinct value per build (cached on the
    project, so a strategy calling it many times does not repeat it).
  - **No intervention** (implicit single intervention): the first non-empty
    `root.form_id` of `start_pages["main"]`, then of the other start pages in their order;
    else `slugify(project.title)`. This is the only `form_id` reader left.
  - Returns `""` only for an empty title slug; callers keep their current final default
    (`"openmrs_form"`, `"dhis2_program"`, `"fhir-form"`, …) for that case.

### 2.2 Inputs

- `YamlActivity` gets `name: Optional[str]` and `intent: Optional[str | Dict[str, str]]`
  (localized plain-language twin of `applicability`; informational, stored on the activity,
  not exported).
- `YamlActivity._defaults` no longer copies `form_id` onto start nodes. `YamlActivity.form_id`
  stays as legacy input: the loader sets it on the main start root only when the root has none
  (so implicit mode still sees it), and `YamlNode.form_id` stays on `start` nodes.
- Activity `name`: the YAML activity `name` when set. Otherwise the current source is kept (draw.io: the root
  shape's `name` through `_get_name`; YAML: the title slug) — see open question 1.
- `form_id` is dropped from the `start` attributes in `drawio_type_map.py`;
  `create_root_node` already reads it directly from the shape.
- `BaseInputStrategy` (combined main start, `base_input_strategy.py:77`) keeps copying the
  first process root's `form_id`: that is legacy input feeding implicit mode, not an output.

### 2.3 Outputs

Replace every `root.form_id` read with `project.intervention_name()`:

| File | Today | After |
|------|-------|-------|
| `xls_form.py` `export`, `validate` | `start_pages["main"].root.form_id`, else exit(1) | `intervention_name()`; exit(1) only if empty |
| `xlsform_cht.py` `export`, `validate` | `start_pages[processes[0]].root.form_id`, else exit(1) | same |
| `html_form.py` | `root.form_id or "openmrs_form"` | `intervention_name() or "openmrs_form"` |
| `openmrs_form.py` `__init__`, `export` | activity attr (always the default) / `root.form_id or "openmrs_form"` | `intervention_name() or "openmrs_form"` |
| `dhis2_form.py` `__init__`, `export` | same pattern, `"dhis2_program"` | same |
| `spice.py` | `root.form_id` | `intervention_name() or "spice_form"` |
| `fhir_form.py` `resolve_form_id` (→ `opensrp.py`, `structuremap.py`) | `root.form_id or "fhir-form"` | `intervention_name() or "fhir-form"` |
| `visitors/xform_pd.py` | receives the CHT form id | unchanged (receives the name) |
| `test/base_test_strategy.py` `form_id()`, `test_spec.py` | first root `form_id` | `intervention_name()` |

StructureMap / Library / PlanDefinition ids are already `(form key, process)`; the form key is
now the intervention name.

Side effect: `openmrs_form.py` and `dhis2_form.py` `__init__` read `form_id` off the activity
(not its root), so they always used the default name. They now use the intervention name.

### 2.4 Docs

- `docs/tricc.yaml.template`: add `name:` to the intervention examples; note `form_id` is
  deprecated.
- `docs/cli-and-inputs.md`, `docs/tricc-elements.md`: `form_id` deprecated, pointer to
  `interventions[].name`; `TestSpecStrategy` file name is `<intervention name>.form-model.json`.
- `feature/20260907-project-config.md`, `feature/20260915-intervention-start.md`: add
  "Superseded in part: the intervention `name` names the form; `form_id` is legacy-only."

### 2.5 Tests

- Unit: `intervention_name()` — name wins; id fallback; implicit `form_id`; implicit title
  slug; warning once per distinct value with interventions.
- Inline intervention fixtures (`test_concept_merge.py`, `test_mixed_input_strategies.py`,
  `test_project_terminology_libraries.py`, `test_yaml_concept_texts.py`) move their start
  `form_id` to `interventions[].name` (same value). Outputs unchanged.
- New: interventions + `name` + stray `form_id` → warning logged; output file named by `name`.
- `tests/data/yaml/*.yaml` and `tests/data/*.drawio` declare no interventions, so they keep
  `form_id` and cover implicit mode. The regression suite (`TRICC_REGRESSION=1`) must be
  unchanged.
- A YAML activity `name` sets `activity.name`; without it, the title slug.

### 2.6 Out of scope

q-display, message AST JSON, `not_available` parent on YAML, project-level activities.

### 2.7 Open questions

| # | Question | Recommendation |
|---|----------|----------------|
| 1 | The frontend spec says the activity name falls back to `_get_name(id)`. Today it is the root `name` (draw.io) or the title slug (YAML), and it reaches outputs (group names). Switching the fallback changes every regression baseline. | Keep the current fallback; only a set YAML activity `name` changes it. Revisit when the frontend stops writing a start `name`. |
| 2 | "Once per distinct value": per build of one intervention, or per process run? | Per intervention build (cached on the project). A shared activity in two interventions warns twice, once per form. |
| 3 | Implicit mode without `form_id`: XLSForm/CHT used to exit(1); now they use the title slug (`My project` → `my_project`). | Accept; it matches the frontend spec. |

### 2.8 Implementation notes (2026-10-08)

- `TriccIntervention.intervention_name()` (`models/tricc.py`) is the single reader; the
  warning set is `TriccIntervention.ignored_form_ids`.
- Regression baselines refreshed for `yaml__concept_repeat_activity_inherit__*` only: that
  fixture has no main start, so every export used to fail (`TriccNodeActivityStart` has no
  `form_id`); it now builds as `my_project` (open question 3). All other 129 baselines are
  unchanged.
- The four inline intervention fixtures moved their start `form_id` to
  `interventions[].name`; their outputs were compared before / after (timestamps masked):
  58 files, no difference.
- `tests/test_intervention_name.py` covers 2.1, 2.2 and the output names (XLSForm, CHT,
  FHIR, OpenSRP).
- `tests/build.py -d` was already parsed but unused; documented as deprecated.
- Revised the same day (Patrick): no new `code` key. tricc already has `name`, so the
  intervention and the YAML activity use `name`; draw.io keeps the root shape's `name`.
- `TriccProject` renamed `TriccIntervention` (Patrick, 2026-10-08): one instance is built per
  `tricc.yaml` intervention, so the form name is read per intervention. `TriccProject`
  stays as a deprecated alias. `TriccProjectConfig` (the whole `tricc.yaml`) keeps its name.
- `TriccIntervention.intervention` renamed `config` (it holds the `tricc.yaml` entry,
  `TriccInterventionConfig`); `start.intervention` (the follow-up parent id) is unchanged.
