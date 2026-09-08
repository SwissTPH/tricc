# CLI and Inputs

Local clinical projects should use the **`tricc` command** after installing
`tricc-oo`. `python tests/build.py` is the development harness (Google Drive,
launch.json debug matrix).

## Main flags

- `-i`, `--input`: required input (file, directory, or supported URL).
- `-o`: output directory.
- `-I`: input strategy class (default `DrawioStrategy`).
- `-O`: output strategy class. Overrides `tricc.yaml` `output_strategies` when passed.
  Default without a project file: `XLSFormCHTStrategy` (`tests/build.py`).
- `-T`: test strategy class (optional). Runs after the output strategy and adds test
  material without changing the deployable artifact. See [Test strategies](#test-strategies--t).
- `-d`: form id.
- `-l`: log level shortcut (`d`, `i`, `w`).
- `-D`: download directory.

## Project file (`tricc.yaml`)

If `-i` is a directory (or a file), TRICC looks for `tricc.yaml` / `tricc.yml` in that
folder. The file is optional. When present it names the project, pins the converter
version, lists output strategies, optional image pixel caps, and **interventions**
(each a glob of drawings). See `feature/20260907-project-config.md`.

Copy [docs/tricc.yaml.template](./tricc.yaml.template) **into the clinical project
folder** (Almanach, etc.) as `tricc.yaml`. That project is not part of this repo.

With `tricc-oo` installed, run from that folder (no `tests/build.py`):

```bash
tricc -o ./build
```

`-i` defaults to the current directory. `python tests/build.py` remains the
Google Drive / debug harness.

Example:

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
```

- **CLI `-I` / `-O` win** when passed; `-O` replaces the YAML list (does not append).
- **`parameters.tricc_version`** must equal the installed `tricc-oo` version, or the
  build fails. Omit the key to skip the check.
- **Image caps** apply when extracting pictures from draw.io (`0` / omitted = no cap).
  A single image object may set `max_width` / `max_height` (Edit Data) to override
  one side; `0` means unlimited for that side.
- **Each intervention is a separate conversion** of its globs. `common/*` listed on
  two interventions is read twice. `*` is one folder level (`common/labs/x.drawio`
  needs `common/labs/*`). An `activity` line may also be a Google Drive file or
  folder URL (mixed with local globs). Downloads go under `{ -o }/.tricc-drive-cache`.
  Restricted Drive needs `TRICC_GOOGLE_AUTH` or `auth/google.json`.
- **Output path is still `-o`**, not a YAML key. With interventions:

  `{ -o }/{strategy}/{intervention_id}/`

  Without interventions, a single strategy still writes directly into `-o` (same as
  today). Several strategies without interventions write `{ -o }/{strategy}/`.
- **`applicability`** is CQL, attached to the OpenSRP PlanDefinition condition. CHT
  and ODK forms are still built; they do not evaluate that CQL.
- **`kind: task` on OpenSRP** is not implemented here (warning, on-demand PD still
  emitted). CHT still writes the XLSForm.

## Input behavior

`-i` supports comma-separated values. Each input is processed independently:

- Local directory: all `.drawio` files inside are added.
- Local file: accepted only if path exists and ends with `.drawio`.
- Google Drive file or folder URL: downloaded first (see below). With
  `interventions` in `tricc.yaml`, put Drive URLs in `activity:` instead of `-i`.

## Google Drive download flow

1. Try authenticated download via `TRICC_GOOGLE_AUTH`, `{project}/auth/google.json`,
   `{cwd}/auth/google.json`, or the TRICC checkout `auth/google.json`, using Drive
   API scope `drive.readonly`.
2. If auth is unavailable or fails, fallback to direct download.

Important:

- Fallback can return HTML pages for restricted files.
- HTML downloads later fail XML parse with `lxml.etree.XMLSyntaxError`.

## Practical input recommendations

- Prefer absolute local paths during debugging.
- For restricted Drive links, verify service-account sharing before run.
- Test one input at a time before comma-joining many inputs.

## YAML test input strategy

For unit tests, regression testing of core transformations (inheritance, calculate
loading, relevance, etc.), and creating minimal reproducible examples, use the
`YamlStrategy` input strategy (`-I YamlStrategy`).

Example:

```bash
python tests/build.py -i tests/data/yaml/my_test_case.yaml -o out/ -I YamlStrategy
```

YAML files are plain text, git-friendly, and much easier to review than draw.io
files when the goal is to exercise the internal transformation engine rather than
clinical authoring.

See `tricc_oo/strategies/input/yaml.py` for the supported format and current
limitations. The YAML strategy is intentionally a *supplement* to draw.io, not
a replacement.

## Strategy registration and lookup (new)

Strategies are now registered declaratively using decorators:

```python
from tricc_oo.strategies.registry import register_input_strategy, register_output_strategy

@register_input_strategy("MyStrategy")
class MyStrategy(BaseInputStrategy):
    ...
```

Recommended way to obtain a strategy (works with both names and direct classes):

```python
from tricc_oo.strategies.registry import get_input_strategy, get_output_strategy

InputCls = get_input_strategy("YamlStrategy")      # by name
OutputCls = get_output_strategy(MyOutputClass)     # direct class (great for tests)
```

This replaces the old fragile `globals()[name]()` pattern and makes the system
much more testable and extensible.

Built-in strategies are eagerly imported in `tricc_oo/strategies/__init__.py` so their
`@register_*` decorators run at import time. If a strategy name is reported as
**unknown** at runtime, ensure its module is imported there (or import it yourself
before calling `get_output_strategy`).

### Registered input strategies

| Name | Class |
|------|-------|
| `DrawioStrategy` | Default draw.io XML input |
| `YamlStrategy` | YAML fixtures for transformation tests |

### Registered output strategies

| Name | Class |
|------|-------|
| `XLSFormStrategy` | Standard ODK XLSForm |
| `XLSFormCDSSStrategy` | CDSS XLSForm |
| `XLSFormCHTStrategy` | CHT XLSForm |
| `XLSFormCHTHFStrategy` | CHT HF XLSForm |
| `HTMLStrategy` | HTML export |
| `DHIS2Strategy` | DHIS2 export |
| `OpenMRSStrategy` | OpenMRS export |
| `FHIRStrategy` | FHIR SDC export |
| `OpenSRPStrategy` | OpenSRP / FHIR-Core bundle |
| `BaseOutPutStrategy` | Abstract base (not for CLI use) |

## Test strategies (`-T`)

A **test strategy** is a third kind of strategy, alongside input and output. It runs *after*
the output strategy and emits non-deployable material describing the build that just happened.
It never changes the deployable artifact, so what you test is exactly what you deploy.

```bash
python tests/build.py -i flow.drawio -o out/ -O XLSFormCHTStrategy -T TestSpecStrategy
```

| Name | Emits |
|---|---|
| `TestSpecStrategy` | `<form_id>.form-model.json` — export names, types, options, relevance/constraint/calculation references, edges, end and diagnosis nodes |

The output of `-O XLSFormCHTStrategy -T TestSpecStrategy` is identical to `-O
XLSFormCHTStrategy` plus one JSON file. If a test strategy raises, the error is logged and the
build still succeeds.

The model is consumed by the browser test harness, which drives the deployed form in
ODK/Enketo and CHT. See `feature/test-spec-strategy.md` for the schema and the contract a test
strategy has with the output strategy.

### Writing a test strategy

```python
from tricc_oo.strategies.registry import register_test_strategy
from tricc_oo.strategies.test.base_test_strategy import BaseTestStrategy


@register_test_strategy("MyTestStrategy")
class MyTestStrategy(BaseTestStrategy):
    def execute(self):
        for node in self.walk_nodes():      # same instances the output exported
            ...
        rows = self.survey_rows_by_name()   # the final `survey` frame, read-only
```

`BaseTestStrategy` gives you `walk_nodes()`, `survey_rows_by_name()`, `choices_by_list()`,
`survey_frame`, `choice_frame`, `output_strategy_name` and `form_id()`. Everything else on the
output strategy is private. Remember to import the class in `tricc_oo/strategies/__init__.py`
so the decorator runs.

Discover at runtime:

```python
from tricc_oo.strategies.registry import list_input_strategies, list_output_strategies
print(list_output_strategies())
```
