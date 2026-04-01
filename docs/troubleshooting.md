# Troubleshooting

## XMLSyntaxError at line 1, column 2

Error:

- `lxml.etree.XMLSyntaxError: StartTag: invalid element name, line 1, column 2`

Typical cause:

- Input is not draw.io XML (often downloaded HTML page).

Checks:

- Open downloaded file and verify first tag is `<mxfile` or XML declaration.
- If first lines show `<!DOCTYPE html>` or `<html>`, the download source is wrong.

## Google Drive download returns HTML

Symptoms:

- Logs show `Attempting direct download (fallback for public files)`.
- Converted temp `.drawio` is actually HTML.

Causes:

- Auth path not active (missing libs or missing credentials).
- Service account has no access to that file.

Fixes:

- Confirm `auth/google.json` is valid service account JSON.
- Confirm Google libs are installed in active Python env.
- Share Drive file directly with service account `client_email`.

## Service account format error

Symptom:

- `missing fields client_email, token_uri`

Fix:

- Replace file with real service-account key JSON from Google Cloud.

## "File not found" for URL input

Common reasons:

- URL format is unsupported by extractor.
- Extracted id is wrong.
- Access denied despite valid id.

Use file URL style:

- `https://drive.google.com/file/d/<FILE_ID>/view`

## Windows dependency build failures (`cffi`, `numpy`)

Symptoms:

- Meson/compiler errors, `cl` not found.

Fix options:

- Prefer Python version with available wheels (commonly 3.12 for this stack).
- Upgrade `pip`, `setuptools`, `wheel`.
- Install Visual Studio Build Tools (Desktop development with C++) if source build is unavoidable.
