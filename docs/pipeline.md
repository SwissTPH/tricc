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

Display text with `${field}` tokens is converted to concatenate operations at **input load**
for display models only (see `feature/display-text-injection.md`).

## 6) Calculate load, versioning, and inheritance

Core walk in `tricc_oo/visitors/tricc.py` (`load_calculate` and related):

1. **`set_last_version_false`** — renumbers export-name peers so ODK field names stay unique
   (`_Vv_n`; `_Rr_n` only when `repeat > 1`). Peers with `repeat <= 1` (including `-1`) share one pool.
2. **`get_versions` / `version_filter`** — prior nodes for the same `(name, repeat)`.
3. **`get_version_inheritance`** — merges **all** prior versions into the current node’s
   expression / relevance / save calculate (advanced merge; see `feature/advanced-merge-calc.md`):
   - `GET_INHERITED_VALUE` for multi-version display/calculate values
   - datatype-aware `merge_expressions` (boolean OR, numeric coalesce/plus, …)
   - origin-signature grouping when calculate formulas differ
   - `repeat=-1` excluded as source and receiver of value inheritance
   - `populate` with `context=history` skips value inheritance
4. **Relevance / skip** — same-slot prior captures can suppress re-asking; different `repeat` slots do not.
5. **`process_reference` / `process_operation_reference`** — resolve refs; for value expressions,
   multi-version display models expand to `GET_INHERITED_VALUE` (newer-first). Relevance keeps a
   single last-version ref. `GET_REPEATED_VALUE` (authored as `GetRepeatedValue`) pins resolution
   to one capture slot, or to any slot (latest so far) when the slot argument is omitted.

## 7) Output strategy execution

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

`GET_INHERITED_VALUE` serializes as **`coalesce(...)`** in XLSForm/CHT strategies.
`GET_REPEATED_VALUE` serializes its resolved concept operand only — an explicit repeat slot is a
resolution-time filter and never reaches the exported expression.

### Output walk contract

`BaseOutPutStrategy.execute()` runs four node walks, then writes and validates:

```text
process_base        → generate_base
process_relevance   → generate_relevance
process_calculate   → generate_calculate
process_export      → generate_export
export / validate
```

Each `generate_*` callback is invoked with `node`, `processed_nodes`, `stashed_nodes`, `process`, and `warn`. The walker keeps a mutable `process` list (default `["main"]`) and forwards it on every recursive step, including nested activity roots, groups, dangling calculates, options, and post-activity `next_nodes`. XLSForm relevance is still written during export (`generate_relevance` is a no-op there). FHIR/OpenSRP keep assembling CQL, StructureMaps, PlanDefinition, and Composition **after** these walks — those artifacts are not produced by the node walker.

See `feature/20260824-output-walk-context.md`.
