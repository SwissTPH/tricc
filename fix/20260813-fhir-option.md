## OpenSRP: `QuestionnaireItem item is not allowed to have initial value or initial expression for groups or display items`

Symptom:

- Android FHIR Data Capture throws at `$populate` / form render:
  `IllegalStateException: QuestionnaireItem item is not allowed to have initial value or initial expression for groups or display items`.

Cause:

- SDC forbids `initial` and `sdc-questionnaire-initialExpression` on `group` and `display` items
  (notes, activity/start containers). Auto-dedup used to attach those extensions whenever
  `get_fhir_resource()` defaulted the node to Observation.

Fix:

- Re-export with current `OpenSRPStrategy`. Dedup `initialExpression` is only attached to
  answerable Observation/Condition questions; a sanitizer strips any leftover before write.
- Confirm the Questionnaire has no `initial` / `initialExpression` on items whose `type` is
  `group` or `display` before pushing to the FHIR server.


## OpenSRP notes never appear when a select option is ticked

Symptoms:

- Multi-select / choice relevance or hidden option-flags stay false after the matching
  choice is selected (e.g. “Now eat !” never shows when Hungry is ticked).

Cause (fixed 2026-08-13):

- Choice answers are stored as `answer.valueCoding`, not a bare string. Expressions of
  the form `'demo.hungry' in %resource.item.where(linkId='select_why').answer` compare
  a string to the whole answer element and evaluate empty/false.
- A top-level-only `%resource.item.where(...)` also misses questions nested in groups.

Expected emission (FHIRStrategy / OpenSRPStrategy):

```text
'demo.hungry' in %resource.repeat(item).where(linkId='select_why').answer.valueCoding.code
```

See `fix/20260813-fhirpath-choice-answers.md`. If an older package still has the
`.answer` membership test, rebuild with a current TRICC.

## A select option always shows even though it has relevance

Symptoms:

- An option (e.g. “Angry”) is drawn with a `relevance` condition but the OpenSRP
  form always lists it.

Cause (fixed 2026-08-13):

- Option relevance was dropped on FHIR export. It is now
  `answerOptionsToggleExpression` on the parent question (true → option enabled).

See `fix/20260813-option-relevance-toggle.md`. Rebuild the package.