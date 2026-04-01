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
