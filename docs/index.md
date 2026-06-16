# TRICC Documentation

This documentation is organized for two audiences:

- Implementers and content authors who build clinical flows in draw.io.
- Developers who maintain or extend TRICC conversion logic.

## Documentation map

- [Getting Started](./getting-started.md): setup, environment, and first run.
- [CLI and Inputs](./cli-and-inputs.md): `build.py` flags, local files, and Google Drive inputs.
- [TRICC Elements](./tricc-elements.md): node catalog and what each element represents.
- [Processing Pipeline](./pipeline.md): how draw.io XML becomes output artifacts.
- [Visual Authoring Concepts](./visual-authoring-concepts.md): WHO-oriented authoring concepts, challenges, and implementation recommendations.
- [Troubleshooting](./troubleshooting.md): common failures and practical fixes.
- [Publishing with GitHub Pages](./github-pages.md): easiest way to publish docs.
- [Transformation Test Coverage](./testing/transformation-test-coverage.md): mapping of core transformation methods to test cases (especially useful with `YamlStrategy`).
- [OpenSRP / FHIR-Core Export](./open-srp-export.md): FHIR SDC + OpenSRP bundle export (`FHIRStrategy`, `OpenSRPStrategy`).

## Key behavior notes

- TRICC can ingest multiple inputs from `-i` using comma-separated values.
- For Google Drive URLs, authenticated download is attempted first, then fallback to direct download.
- Pages whose root node has `status="experimental"` are intentionally limited during processing.
- **Concept repeat:** nodes and activities may set `repeat=<integer>` for multiple independent
  captures of the same concept name; see [TRICC Elements](./tricc-elements.md#concept-repeat).
- **Rhombus edge labels:** out-edges accept `yes`/`no`/`follow`, empty (yes), and
  **integer factors** (`-1`, `+2`, …) that imply yes and feed `count` scoring; see
  [Edge labels](./tricc-elements.md#edge-labels-conditional-flow).
- **Strategy registry:** output/input strategies register via decorators; built-ins are
  imported in `tricc_oo/strategies/__init__.py` — see [CLI and Inputs](./cli-and-inputs.md#strategy-registration-and-lookup-new).

## Visual authoring framing

From your WHO material, this documentation now explicitly captures:

- Added value of CDSS authoring (dynamic, customizable, computable guidance).
- Multi-stakeholder collaboration model (SME, implementers, IT, MoH, sponsors).
- Segmented and layered authoring approach.
- Node/task intent by category (data capture, message, calculate, sequence).
- Practical implementation recommendations (small iterations, reuse, troubleshooting discipline).

## Sources used for this documentation

- Runtime and CLI logic in `tests/build.py`.
- Conversion logic in `tricc_oo/converters/xml_to_tricc.py`.
- Type mapping in `tricc_oo/converters/drawio_type_map.py`.
- Scratchpad library in `tricc_oo/tools/TRICCS-Scratchpad.xml`.

## Note on additional PDF material

`tricc_doc.pdf` appears image-based in this environment, so text could not be extracted automatically.  
When you share an OCR text export (or slide notes), this docs set can be merged with your existing narrative and examples.
