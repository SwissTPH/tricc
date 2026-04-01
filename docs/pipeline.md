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
- enriches nodes (hints/help/media)
- assigns process/start-page metadata

## 4) Experimental page control

When root status is experimental, detailed activity processing is skipped/limited by design.

This allows draft pages to stay in the model without entering full downstream generation.

## 5) Graph linking

`DrawioStrategy.linking_nodes` wires page graph semantics:

- normal next/prev links
- `goto` traversal and activity instances
- `link_out` to `link_in` resolution
- loop warnings and edge validation

## 6) Output strategy execution

After project graph creation, selected output strategy runs (`-O`):

- XLSForm variants
- CHT variants
- OpenMRS / FHIR / HTML / DHIS2 (availability varies by maturity)
