# Project configuration file (`tricc.yaml`)

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `docs/cli-and-inputs.md`, `docs/tricc-elements.md` (image enrichment), `feature/tricc-segment.md`, `feature/careplan.md`, `feature/opensrp-register.md` |
| **Strategy** | Project load + all output strategies |
| **Approval** | Approved 2026-09-07 |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

Supersedes `feature/20260903-project-config.md` (and the 2026-09-02 image-only draft).

---

# Part I — Business description

*Audience: clinical authors, guideline developers, implementers.*

## 1. What this is

A TRICC project folder includes a `tricc.yaml` next to its drawings. That file is the
**project identity**: name, which converter version to use, how to export, tunable
parameters, and the **interventions** in this programme.

Today every `.drawio` in the `-i` folder is one implicit intervention. Almanach Global
is the counter-example: one project, two algorithms (**pediatrics** and **young
infants**) that **share** `common/` drawings and each add their own folder
(`child/`, young-infant equivalent). Each intervention is a different *set of files*,
not a different named page inside one giant graph.

## 2. Proposed file shape

```yaml
title: Almanach Global

input_strategy: DrawioStrategy
output_strategies:
  - XLSFormStrategy
  - XLSFormCHTStrategy

parameters:
  tricc_version: "1.7.3"
  image_max_width: 1200
  image_max_height: 1200

interventions:
  - id: pediatrics
    title: Pediatrics
    kind: both
    applicability: "AgeInMonths() >= 2"
    description: IMCI for children from 2 months to 5 years
    activity:
      - common/*
      - child/*
  - id: young_infants
    title: Young infants
    kind: both
    applicability: "AgeInMonths() < 2"
    description: IMCI for young infants under 2 months
    activity:
      - common/*
      - young_infant/*
```

`title`, `input_strategy`, `output_strategies`, `interventions` are top-level.
Tunable key/value pairs live only under `parameters`.

## 3. Title

| Level | Field | Used for |
|-------|--------|----------|
| Project | `title` | Package / project name (Almanach Global) |
| Intervention | `title` | Form title for that intervention (Pediatrics) |

`description` is longer prose for catalogues / implementers, not the short header.

## 4. `tricc_version`

`parameters.tricc_version` is the **converter** that must build this content
(the installed `tricc-oo` version). It is not the XLSForm settings `version`
(that stays a build timestamp unless we add a separate content-version later).

If the installed converter is not **exactly** that version, the build **fails**
(1.7.3 content on 1.8.0 fails). Omitted key = no check.

## 5. Strategies

- One `input_strategy`. Default: `DrawioStrategy`.
- One or more `output_strategies`, run in list order.
- CLI `-I` / `-O` override the file when passed. `-O` **replaces** the YAML list.

## 6. Parameters

Flat `key: value`. Known keys:

| Key | Meaning | Default |
|-----|---------|---------|
| `tricc_version` | Required `tricc-oo` version | omitted = no check |
| `image_max_width` | Pixel cap (`0` / omitted = none) | no cap |
| `image_max_height` | Pixel cap (`0` / omitted = none) | no cap |

Unknown keys are kept and ignored until something reads them.

Per-image override on a draw.io object: `max_width` / `max_height` (Edit Data).
Missing inherits the parameter; `0` means unlimited on that side.

## 7. Interventions

Each entry is one exportable algorithm.

| Field | Meaning |
|-------|---------|
| `id` | Stable machine name (`pediatrics`). Unique in the project. Used in output paths / form ids. |
| `title` | Short form title. |
| `kind` | `on_demand` \| `task` \| `both`. |
| `applicability` | CQL **boolean expression** (who this intervention is for). Optional. |
| `description` | Longer text. Optional. |
| `activity` | List of path globs (relative to the project root) and/or Google Drive file or folder URLs. Required when interventions are listed. Pages inside those files already declare `start` vs `activity_start`; one list covers both. Renamed from `segment` on 2026-09-07; the old key fails with a pointer. |

**`kind`** is launch style, not FHIR extraction `kind`:

| Value | CHT (this feature) | OpenSRP (this feature) |
|-------|--------------------|------------------------|
| `on_demand` | Contact / app form | Today’s Start care PlanDefinition |
| `task` | Task form + `tasks.js` | **Not implemented here** — warn and skip (separate piece of work) |
| `both` | Both CHT artifacts | Same as `on_demand` for OpenSRP, plus CHT task artifacts |

**Paths.** Globs are relative to the folder that contains `tricc.yaml`.
`common/*` means every `.drawio` sitting **directly** in `common/`
(`common/registration.drawio`, `common/shared.drawio`). It does **not** pick up
files in a nested folder (`common/labs/blood.drawio`). If that folder exists,
add another line (`common/labs/*`). Same glob may appear on several
interventions (`common/*` on both pediatrics and young infants).

An `activity` line may also be a Google Drive **file** or **folder** URL
(same shapes as `tests/build.py -i`). Mix them with local globs. Drive
folders are one level only (no nested Drive folders). Downloads go under
`{ -o }/.tricc-drive-cache`. Restricted files need a service-account JSON
(`TRICC_GOOGLE_AUTH`, `{project}/auth/google.json`, or the TRICC checkout
`auth/google.json`). A Drive URL that yields no matching files fails the
build the same way an empty local glob does.

**Build model.** Each intervention is its **own conversion** of the files its
globs resolve to. Shared files are read twice (once per intervention), not
merged into one `start_pages` map. That is how two algorithms can both include
a `registration` process from `common/` without colliding.

Today `-i some/dir` only loads **top-level** files (it does not enter
`common/` or `child/`). With `interventions`, `-i` is the project root and
the globs decide which nested files belong to which build. Files on disk that
no glob matches are ignored.

If `interventions` is omitted, behaviour stays as today: all matching files
under `-i` (current non-recursive rule) are one implicit on-demand intervention.

## 8. Applicability (CQL)

`applicability` is a CQL boolean expression, evaluated by the **runtime that
understands CQL** (OpenSRP / FHIR PlanDefinition condition). Example:

```cql
AgeInMonths() >= 2
```

It is the outer “does this algorithm apply to this patient”, not a replacement
for rhombus / start-node relevance inside the drawings.

XLSForm / generic ODK cannot run CQL. CHT tasks decide “show this task?” with a
JavaScript `appliesIf`, not CQL. This feature therefore:

- writes `applicability` onto the **OpenSRP** PlanDefinition condition;
- still **builds** the CHT/ODK forms for that intervention;
- does **not** hide those CHT/ODK forms from the wrong age group.

Who sees the CHT form/task stays an app/config concern until a later feature
translates or duplicates this expression for CHT.

## 9. Limitations

- Not the CarePlan scheduler (`feature/careplan.md`).
- OpenSRP Task / planning launch is **out of scope** (separate work).
- No `tricc.yaml` → no behaviour change.
- Google Drive `-i` (no `tricc.yaml`) still has no local globs unless a local
  project root is also passed. Drive URLs **inside** `activity:` are supported.

## 10. Output folders (CLI `-o`, not a YAML key)

There is **no** output path in `tricc.yaml`. `output_strategies` is only the list
of exporters. The directory is the existing CLI `-o` flag.

Layout:

```text
<cli -o>/
  XLSFormStrategy/
    pediatrics/
    young_infants/
  XLSFormCHTStrategy/
    pediatrics/
    young_infants/
```

Example: `python tests/build.py -i ./almanach -o ./build` writes
`./build/XLSFormCHTStrategy/pediatrics/`.

---

# Part II — Technical specification

*Audience: developers.*

## 1. Discovery

| `-i` value | Config path |
|------------|-------------|
| Local directory | `{dir}/tricc.yaml` (also `tricc.yml`) |
| Local file | `{parent}/tricc.yaml` |
| Comma-separated local inputs | First local directory, else parent of first file. Warn if later folders differ. |
| Google Drive URL only | No config file |

Missing file = today’s defaults. Broken YAML / bad types fail the build.

## 2. Schema

```text
TriccProjectConfig
  title: str = "My project"
  input_strategy: str = "DrawioStrategy"
  output_strategies: List[str] = []
  parameters: Dict[str, Any] = {}
  interventions: List[TriccInterventionConfig] = []

TriccInterventionConfig
  id: str
  title: str
  kind: Literal["on_demand", "task", "both"] = "on_demand"
  applicability: Optional[str] = None   # CQL boolean expression
  description: Optional[str] = None
  activity: List[str]                   # local globs and/or Google Drive URLs, at least one
```

- `parameters.image_max_width` / `image_max_height`: int, `0`/missing = no cap;
  negative → build error.
- `parameters.tricc_version`: must **equal** installed `tricc-oo` version.
- Duplicate intervention `id` → build error.
- Empty `activity` list, or a glob / Drive URL that matches nothing → build error.
- Legacy `segment` key → build error naming `activity`.
- Unknown strategy names → existing registry error.
- `options_threshold` is not a setting; do not add it.

## 3. Orchestration

1. Load `tricc.yaml` from the `-i` project root.
2. Enforce `tricc_version`.
3. Resolve input / output strategies (CLI wins).
4. If `interventions` is empty: current file collection + one export.
5. Else, for each intervention:
   - Resolve globs → file list (dedupe paths within that intervention).
   - Parse + `load_calculate` into a **fresh** `TriccProject` (do not reuse
     mutated graphs across interventions).
   - Apply image caps at parse time (`add_image_from_style`).
   - Set `project.title` from YAML project `title`; form title from
     intervention `title`.
   - For each output strategy, `execute()` into
     `{cli -o}/{strategy}/{intervention_id}/`.
     OpenSRP: emit on-demand PlanDefinition; if `kind` is `task` only, log a
     warning (task launch is other work). CHT: honour `kind`.
   - OpenSRP PlanDefinition wrapper `condition`: CQL from `applicability`
     when present (`text/cql`). Not applied to CHT/ODK form relevance.

Image bytes are per intervention parse (same source file may resize once per
build; result is identical if caps match).

## 4. Glob resolution

- Base directory = directory of `tricc.yaml`.
- Patterns are POSIX-style (`common/*`, `child/assessment.drawio`).
- `*` does not cross `/` (`common/*` ≠ `common/labs/*`).
- A pattern starting with `https://` must be a Google Drive file or folder URL
  (`drive.google.com/file/d/…`, `drive.usercontent.google.com/download?id=…`,
  `drive.google.com/drive/folders/…`, `drive.google.com/open?id=…`). Other
  HTTPS URLs fail the build.
- Drive downloads land in `{cli -o}/.tricc-drive-cache`. Folder listing is
  one level (no nested Drive folders). Filter by the same extensions as local
  globs. Helpers live in `tricc_oo/converters/google_drive.py`.
- Match `.drawio` for DrawioStrategy; `.yaml`/`.yml` for YamlStrategy.
- Do not follow the current `list_local_folder_files` “top-level only” rule
  when resolving intervention globs.

## 5. Image resize

Unchanged: fit-inside-box, never upscale, original bytes if already fitting,
PNG lossless re-save, JPEG quality 90 keep JPEG, SVG untouched, hash of
written bytes, Pillow dependency.

## 6. Code checklist

- [x] Pydantic config load from `-i`.
- [x] `tricc_version` gate.
- [x] Strategy resolution + multi-output + per-intervention dirs.
- [x] Glob file collection per intervention; independent parse.
- [x] Image caps + per-object override.
- [x] CHT `kind`; OpenSRP on-demand only + CQL `condition`.
- [x] Docs: `docs/cli-and-inputs.md`.
- [x] Tests: no file; version mismatch; glob union (`common/*` + `child/*`);
      two interventions sharing `common/*`; image cap; empty glob fails;
      Drive URLs in `activity:` (mocked, mixed with local globs).

## 7. Implementation phases

1. Config load, `title`, `parameters` (version gate + image caps).
2. Multi-strategy export dirs.
3. Per-intervention glob builds (independent `TriccProject`).
4. CHT `kind` + OpenSRP CQL applicability on the existing on-demand PD.
5. OpenSRP Task launch — **not this feature**.

Implementation follows this spec (Implemented 2026-09-07). OpenSRP Task launch remains out of scope.
