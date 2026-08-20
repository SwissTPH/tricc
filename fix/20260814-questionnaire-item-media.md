# Question / answer illustration images → SDC itemMedia / itemAnswerMedia

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `feature/zscore` / `develop` |
| **Related** | `docs/desing/FHIRcore.md`, `docs/open-srp-export.md`, `docs/planning/FHIR-Output-Strategy-Remediation-Plan.md`, `docs/tricc-elements.md`, `fix/20260818-item-media-binary-display.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |
| **Approval** | Requested and approved for direct implementation in the 2026-08-14 conversation (cross-repo with `openSRP-fhircore/android`, which confirmed the openSRP mobile app already renders these extensions via the Android FHIR SDK's `data-capture` library). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

*Audience: clinical authors, guideline developers, implementers.*

## 1. What went wrong

Authors can already attach an illustration image to a question box, or to an individual
answer-choice box, in draw.io — by connecting an image-decorator box to it with an edge (the
same authoring convention used for `hint-message`/`help-message` boxes; see
"Enrichment elements" in `docs/tricc-elements.md`). That image is faithfully parsed and already
reaches the **XLSForm/ODK/CHT** output (as an ODK `media::image` column) and the **OpenMRS**
output (`questionOptions.imageUrl`).

The **FHIR SDC / openSRP** output silently dropped it. The generated `Questionnaire` never
mentioned the image at all — not on the question, not on the answer option — even though the
image had been correctly captured from the same drawio source. Forms deployed to openSRP/FHIR
Core therefore could never show the illustrations that the identical drawio source already shows
in ODK/CHT builds.

## 2. Expected behaviour

- An image attached to a **question** box renders as an illustration above/alongside that
  question in the openSRP questionnaire UI.
- An image attached to an **individual answer choice** box (e.g. a male/female icon on a "Sex"
  question) renders next to that specific radio/checkbox option.
- No new draw.io authoring convention — this is the existing image-decorator-box mechanism,
  simply completed on the FHIR/openSRP export side.

## 3. Limitations

- **Images only.** The openSRP mobile app's questionnaire renderer (Android FHIR SDK
  `data-capture` library) only supports the `IMAGE` MIME category for `itemMedia`/
  `itemAnswerMedia` — audio/video attachments in this position are logged and silently not
  rendered by that library today. Video/audio illustration is out of scope for this fix.
- Draw.io author-attached images become **FHIR `Binary` resources** included in the exported
  package (base64 `data`, referenced via `Attachment.url = "Binary/<id>"`) — not inline
  `Attachment.data` — matching the pre-existing (previously-unpopulated) `Binary` scaffolding in
  `FHIRStrategy`/`OpenSRPStrategy` (`self.binaries`, the Composition "Binaries" section). Deploying
  these forms requires the `push-to-fhir.sh`/Postman flow to actually PUT the new `binary/*.json`
  files, same as any other resource in the package.
- This is exporter-side only: it does not change how images are authored in draw.io, and does not
  touch the (unrelated, already-working) XLSForm/OpenMRS image support.

---

# Part II — Fix approach

## 4. Root cause

`node.image`/`opt.image` (`Optional[str]`, a file name like `"<md5-hash>.png"`, populated during
drawio parsing by `xml_to_tricc.enrich_node`/`get_image`/`add_image_from_style`) was never read by
`FHIRStrategy.generate_base()` — the function that builds a `Questionnaire.item` and its
`answerOption` list. Separately, `FHIRStrategy.binaries: List[dict]` was declared but nothing ever
appended to it, and `OpenSRPStrategy.generate_composition()`'s "Binaries" Composition section
(keyed off `self.binaries`) was consequently always empty.

The actual image bytes (base64) are not reachable from an output strategy via the filesystem
(`media_path` is a parse-time-only local variable, never stored on `project` or threaded to output
strategies) — but they *are* already available in memory via `project.images`
(`List[Dict[str, str]]`, entries `{"file_path": <filename>, "image_content": <base64>}`),
accumulated once per parsed activity in `xml_to_tricc.get_activity_details`/`process_edges`. That
list was previously a write-only, unread accumulator.

## 5. Extensions

[SDC `itemMedia`](http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-itemMedia) on
`Questionnaire.item` (illustrates the question):

```json
{
  "url": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-itemMedia",
  "valueAttachment": {
    "contentType": "image/png",
    "url": "Binary/3f9a1c...-uuid"
  }
}
```

[SDC `itemAnswerMedia`](http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-itemAnswerMedia)
on an `answerOption` entry's own `extension` list (illustrates that choice):

```json
{
  "valueCoding": {"code": "demo.male", "display": "Male"},
  "extension": [
    {
      "url": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-itemAnswerMedia",
      "valueAttachment": {
        "contentType": "image/png",
        "url": "Binary/2a7e5b...-uuid"
      }
    }
  ]
}
```

Both attachments reference a `Binary` resource added to the exported package:

```json
{"resourceType": "Binary", "id": "3f9a1c...-uuid", "contentType": "image/png", "data": "<base64>"}
```

## 6. Pipeline / emission rules

- `FHIRStrategy._get_project_image_content(file_name)` — lazily indexes `project.images` into a
  `{file_path: image_content}` dict (built once, cached on `self._project_image_index`).
- `FHIRStrategy._register_image_binary(file_name)` — for a given `node.image`/`opt.image` file
  name: derives `contentType` from the file extension (`image_content_type()` in
  `questionnaire_item_mapper.py`; normalizes `jpg`→`jpeg`, `svg`→`svg+xml` — the extension already
  came verbatim from the drawio-embedded `image=data:image/<subtype>,...` style fragment, so no
  further mapping is needed), looks up the base64 payload via `_get_project_image_content`, and
  appends a `Binary` dict to `self.binaries` — **once per distinct file name** (idempotent via
  `self._image_binary_ids` cache; the same image reused across multiple questions/options doesn't
  duplicate the Binary). Id is a deterministic UUID5 (`fhir_resource_id(form_key, "Binary",
  file_name)`), consistent with every other resource id in this strategy (stable across
  re-exports for idempotent PUT).
- Missing content-type or missing image content both **log a warning and skip** (no extension,
  no Binary) — never raise. This matches the existing "not supported"-style warning in
  `xml_to_tricc.enrich_node` for images attached to an incompatible node type.
- `generate_base()`: after building the item's `extensions` list, appends an `itemMedia`
  extension when `node.image` resolves; when building each `answerOption` entry, attaches an
  `itemAnswerMedia` extension (in that option's own `extension` list) when `opt.image` resolves.
- `OpenSRPStrategy._write_image_binaries()` (called from `export()`, alongside the existing
  `_write_image_binaries` for question/answer illustrations) writes each entry of
  `self.binaries` to `<form>/binary/Binary-<slug>.json`. The Composition "Binaries" section
  already listed these by id (pre-existing code, previously always empty).

## 7. Code checklist

- [x] `tricc_oo/converters/fhir/questionnaire_item_mapper.py` — add `SDC_EXT_ITEM_ANSWER_MEDIA`
      constant, `image_content_type()`, `build_item_media_extension()`,
      `build_item_answer_media_extension()`.
- [x] `tricc_oo/strategies/output/fhir_form.py` — `_project_image_index`/`_image_binary_ids`
      state; `_get_project_image_content()`, `_register_image_binary()`,
      `_build_item_media_extension()`, `_build_item_answer_media_extension()`; wire into
      `generate_base()`'s item-extension and answerOption-building code.
- [x] `tricc_oo/strategies/output/opensrp.py` — `_write_image_binaries()`, called from `export()`.
- [x] Tests: `tests/test_strategies/test_fhir_item_media.py`.

## 8. Tests

- Question node with `.image` → `itemMedia` extension referencing a `Binary/<id>` URL; matching
  `Binary` appended to `strategy.binaries` with the right `contentType`/`data`.
- Answer option with its own `.image` → `itemAnswerMedia` extension on that option's `extension`
  list; content type normalization (`.jpg` → `image/jpeg`) verified.
- Same image file name reused by a question and one of its options → registered once (one
  `Binary`, both extensions reference the same `Binary/<id>`).
- No `.image` on node/option → no `itemMedia`/`itemAnswerMedia` extension, no `Binary` added
  (other unrelated extensions, e.g. `questionnaire-itemControl`, are untouched).
- `.image` set but no matching `project.images` entry (defensive/edge case) → warning logged,
  skipped, no crash.

`python -m pytest tests/test_strategies/test_fhir_item_media.py -v` — 5/5 passing. Full suite
(`python -m pytest tests/`) run alongside: no new failures introduced (5 pre-existing failures in
`test_concept_repeat.py`/`test_goto_*` were already present before this change, unrelated to FHIR
output).

## 9. Acceptance criteria

- A drawio question/option with an attached image, run through `OpenSRPStrategy`, produces a
  Questionnaire item/answerOption carrying the itemMedia/itemAnswerMedia extension and a
  corresponding `binary/*.json` file in the export package, referenced correctly by id.
- No regression to existing XLSForm/OpenMRS image handling (untouched by this fix) or to any other
  FHIR/OpenSRP export test.
