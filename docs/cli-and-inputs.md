# CLI and Inputs

TRICC is commonly executed through `tests/build.py`.

## Main flags

- `-i`, `--input`: required input (file, directory, or supported URL).
- `-o`: output directory.
- `-I`: input strategy class (default `DrawioStrategy`).
- `-O`: output strategy class (default `XLSFormStrategy`).
- `-d`: form id.
- `-l`: log level shortcut (`d`, `i`, `w`).
- `-D`: download directory.

## Input behavior

`-i` supports comma-separated values. Each input is processed independently:

- Local directory: all `.drawio` files inside are added.
- Local file: accepted only if path exists and ends with `.drawio`.
- Google Drive URL: file id is extracted and downloaded to temp first.

## Google Drive download flow

1. Try authenticated download via `auth/google.json` and Drive API scope `drive.readonly`.
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

Discover at runtime:

```python
from tricc_oo.strategies.registry import list_input_strategies, list_output_strategies
print(list_output_strategies())
```
