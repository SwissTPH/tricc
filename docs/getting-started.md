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

Supported URL patterns are handled in `tests/build.py`:

- `https://drive.google.com/file/d/<FILE_ID>/...`
- `https://drive.usercontent.google.com/download?id=<FILE_ID>`

For restricted files:

- Place credentials at `auth/google.json` (service account JSON format).
- Share the file with the service account `client_email`.

## Output strategy selection

Use `-O` to select a strategy class (examples in codebase include `XLSFormStrategy`, `XLSFormCHTStrategy`, and others).

```bash
python tests/build.py -i "./uploads" -o "./out" -O XLSFormCHTStrategy
```

## Modeling mindset (recommended)

- Author by segment rather than as one huge diagram.
- Reuse existing activities whenever possible.
- Keep each iteration small: update, convert, test.
- Read warnings/errors first when troubleshooting conversion.
