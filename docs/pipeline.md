# Processing Pipeline

## 1) Input collection

`tests/build.py` parses CLI args, resolves inputs, and loads file content strings.

For URLs (Google Drive), it downloads to temp first, then reads local content.

## 2) XML parsing

`DrawioStrategy` calls `read_drawio` (`tricc_oo/parsers/xml.py`), which parses the full XML payload via `lxml`.

The parser expects draw.io XML (`<mxfile ...>`). Non-XML or HTML content fails early.

## 3) Page/activity creation

`create_activity` in `tricc_oo/converters/xml_to_tricc.py`:

- resolves root node (`start` or `activity_start`)
- creates activity object
- loads edges and nodes
- runs `process_edges` (interprets arrow labels: yes/no, factors, conditions)
- enriches nodes (hints/help/media)
- runs `propagate_activity_repeat` when `activity_start.repeat` is set
- assigns process/start-page metadata

## 4) Experimental page control

When root status is experimental, detailed activity processing is skipped/limited by design.

This allows draft pages to stay in the model without entering full downstream generation.

## 5) Graph linking

`DrawioStrategy.linking_nodes` wires page graph semantics:

- normal next/prev links
- `goto` traversal and activity instances (`instance > 0` / `0`), or snippet injection when `instance == -1`
- `link_out` to `link_in` resolution
- loop warnings and edge validation

## 6) Output strategy execution

After project graph creation, selected output strategy runs (`-O`).

Built-in output strategies (registered in `tricc_oo/strategies/__init__.py`):

| Strategy class | Purpose |
|----------------|---------|
| `XLSFormStrategy` | Standard ODK XLSForm |
| `XLSFormCDSSStrategy` | CDSS-oriented XLSForm variant |
| `XLSFormCHTStrategy` | Community Health Toolkit (CHT) XLSForm |
| `XLSFormCHTHFStrategy` | CHT + HF combined variant |
| `HTMLStrategy` | HTML form preview |
| `DHIS2Strategy` | DHIS2 program export |
| `OpenMRSStrategy` | OpenMRS form export |
| `FHIRStrategy` | FHIR SDC (Questionnaire, Library/CQL, StructureMap, ValueSet) |
| `OpenSRPStrategy` | FHIR-Core / OpenSRP bundle (extends `FHIRStrategy`) |

Lookup by name: `get_output_strategy("XLSFormCHTHFStrategy")` or pass the class directly in tests.
List registered names: `list_output_strategies()` from `tricc_oo.strategies.registry`.
