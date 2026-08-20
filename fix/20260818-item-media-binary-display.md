# itemMedia Binary references are not rendered by openSRP

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260814-questionnaire-item-media.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` + openSRP Android `ReferenceUrlResolver` |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## 1. What went wrong

`demo_m_cat` ("Does a cat helps") is a `display` item with SDC `itemMedia` pointing at
`Binary/0eadaee6-1965-5862-ba94-fab36b971abf`. The Binary exists in the export package and
is listed on the Composition. The question text shows; the illustration does not.

The Android FHIR SDK `data-capture` library (openSRP's `org.smartregister:data-capture`)
renders `itemMedia` only if:

1. `Attachment.data` is present (decoded locally), **or**
2. `Attachment.url` is an `http://` / `https://` URL (`ca.uhn.fhir.util.UrlUtil.isValid`)
   — then it calls `UrlResolver.resolveBitmapUrl`, which openSRP implements as a raw HTTP GET.

A relative FHIR reference `Binary/<id>` fails (2) before the app resolver is invoked.
`itemAnswerMedia` is stricter still: it requires `Attachment.data` and never follows a URL.

Separately, even a working Binary lookup would usually miss: image Binaries were not
stamped with the app-id `meta.tag`, and they live on the TRICC Composition, not the
shell app Composition that `fetchNonWorkflowConfigResources` downloads.

## 2. Expected behaviour

A question or answer option with an attached illustration shows that image in the
openSRP questionnaire UI, offline, without requiring a separate HTTP image host.

## 3. Out of scope

- Changing draw.io authoring.
- Downsampling large source images (the demo cat PNG is ~850 KB / ~1.1 MB base64).
- Patching the forked `data-capture` library's `UrlUtil.isValid` gate.

---

# Part II — Fix approach

## 4. Emission rules

`itemMedia` / `itemAnswerMedia` `valueAttachment` carries **only**:

- `contentType` — e.g. `image/png`
- `url` — `Binary/<id>` plus the matching package Binary (bytes live there)

Inline `Attachment.data` is not emitted. One picture can appear on several
questionnaires without duplicating the payload. openSRP rewrites the relative
URL to `{fhirBase}/Binary/{id}` at render time so SDC will call the app
`UrlResolver`. Answer-option media is inlined from the local Binary in memory
because the SDK never follows a URL there.

OpenSRP also stamps app-id `meta.tag` on image Binaries so FHIR sync
(`_tag=app-id`) can retrieve them.

## 5. Android

`QuestionnaireMediaResolver` rewrites `Binary/<id>` to an absolute FHIR URL.
`ReferenceUrlResolver.resolveBitmapUrl` loads that Binary from `FhirEngine`
only — same as Questionnaire / PlanDefinition, there is no render-time
server fetch. Image Binaries arrive via FHIR sync (`_tag=app-id`).
Non-Binary image URLs still use `fetchImage`.

## 6. Tests

- Exporter: `itemMedia` / `itemAnswerMedia` have `url` + `contentType` and no `data`.
- Package Binary still carries the payload and the app-id tag.
- Android: relative URL is rewritten; present `data` is kept; answer media is inlined.
