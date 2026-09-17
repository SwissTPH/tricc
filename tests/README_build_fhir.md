# build_fhir.py

Converts one or more drawio diagram(s) into FHIR output (Questionnaire, CQL
Library, StructureMap/FML, CodeSystems). It's a slimmed-down version of
`build.py` fixed to `DrawioStrategy` (input) and `FHIRStrategy` (output) —
no Google Drive support, no `-I`/`-O`/`-T` strategy switches.

## Setup

Run everything with `uv`, from the repo root, so the project's dependencies
and registered strategies resolve correctly (first run creates `.venv`
automatically):

```bash
uv run python3 tests/build_fhir.py -i <input> -o <output_dir>
```

## Usage

```
-i / --input   drawio file or folder path (MANDATORY)
-o / --output  output directory (MANDATORY)
-h / --help    print this menu
```

- `-i` can point to a single `.drawio` file or a folder containing several
  `.drawio` files (all of them are loaded into one project/build).
- `-o` is created if it doesn't exist.

## Examples

```bash
# single file
uv run python3 tests/build_fhir.py -i tests/data/demo.drawio -o tests/output/demo_fhir

# folder of drawio files
uv run python3 tests/build_fhir.py -i path/to/drawio_folder -o path/to/output_dir
```

## Output layout

```
<output_dir>/
├── <project_name>/
│   ├── questionnaire/
│   │   └── Questionnaire-<id>.json
│   ├── library/
│   │   ├── Library-<id>.json
│   │   └── <id>.cql
│   └── structure-map/
│       ├── StructureMap-<id>-extract.json
│       └── StructureMap-<id>-extract.map
├── <codesystem>_codesystem.json   # one per codesystem referenced (e.g. tricc, sym)
└── media-tmp/                     # extracted media assets, if any
```

## Notes

- Answer-option codes are deduplicated per codesystem, not per question. If
  two questions reuse the same numeric code (e.g. `1`, `2`, `97`) with
  different labels, the build logs a `Code N already exists with a
  different display` warning and keeps the first value seen — check the
  drawio numbering if this happens unexpectedly.
- "Pruned N unused hidden calculate item(s)" is expected cleanup, not an
  error — `FHIRStrategy` drops calculate-only items that ended up unused
  after relevance/calculate generation.
- For the full pipeline (other input/output strategies, test strategies,
  Google Drive input, etc.) use `tests/build.py` instead — see
  `docs/cli-and-inputs.md`.
