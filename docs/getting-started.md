# Getting Started

## Prerequisites

- Python environment compatible with project dependencies.
- Access to `.drawio` sources (local files or Google Drive links).
- For restricted Google Drive files: service account credentials.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies from `requirements.txt`.
3. Verify the runtime can import Google auth libraries if you use Drive URLs.

## First run (local file)

Example:

```bash
python tests/build.py -i "./uploads/test_workflow.drawio" -o "./out"
```

## First run (directory)

Example:

```bash
python tests/build.py -i "./uploads" -o "./out"
```

TRICC loads all `.drawio` files in that directory.

## Google Drive input

Supported URL patterns (CLI `-i` on `tests/build.py`, and `segment:` in `tricc.yaml`):

- `https://drive.google.com/file/d/<FILE_ID>/...`
- `https://drive.usercontent.google.com/download?id=<FILE_ID>`
- `https://drive.google.com/drive/folders/<FOLDER_ID>`
- `https://drive.google.com/open?id=<FOLDER_ID>`

For restricted files, a service-account JSON is tried in this order:

- `TRICC_GOOGLE_AUTH` (path to the JSON)
- `{project}/auth/google.json` (clinical project root)
- `{cwd}/auth/google.json`
- TRICC checkout `auth/google.json`

Share the file or folder with the service account `client_email`.

## Output strategy selection

Use `-O` to select a strategy class. Common examples:

| `-O` value | Use case |
|------------|----------|
| `XLSFormStrategy` | Standard ODK / XLSForm (default) |
| `XLSFormCDSSStrategy` | CDSS-oriented forms (e.g. ETAT, Adult ODK) |
| `XLSFormCHTStrategy` | Community Health Toolkit |
| `XLSFormCHTHFStrategy` | CHT + HF combined workflows |
| `FHIRStrategy` | FHIR SDC Questionnaire + CQL |
| `OpenSRPStrategy` | Full OpenSRP / FHIR-Core package |
| `OpenMRSStrategy` | OpenMRS |
| `DHIS2Strategy` | DHIS2 |
| `HTMLStrategy` | HTML preview |

```bash
python tests/build.py -i "./uploads" -o "./out" -O XLSFormCHTStrategy
```

Run from the project virtual environment (`.venv/bin/python`) so dependencies and
registered strategies match CI and VS Code `launch.json` configurations.

## Modeling mindset (recommended)

- Author by segment rather than as one huge diagram.
- Reuse existing activities whenever possible.
- Keep each iteration small: update, convert, test.
- Read warnings/errors first when troubleshooting conversion.
