# Option relevance → SDC answerOptionsToggleExpression

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `feature/zscore` / `develop` |
| **Related** | `fix/20260813-fhirpath-choice-answers.md`, `docs/open-srp-export.md`, `docs/desing/FHIRcore.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |
| **Approval** | Requested in the 2026-08-13 conversation (option with `relevance` was exported unconditionally). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

*Audience: clinical authors, guideline developers, implementers.*

## 1. What went wrong

Authors can put a **relevance** condition on a single answer option (for example, show **Angry** on “Why?” only when “adding Angry ?” is yes). XLSForm already honours that as a choice filter.

The FHIR / OpenSRP Questionnaire listed every option unconditionally. The Angry choice always appeared, even when the filter question was no.

## 2. Expected behaviour

If an option has relevance, the form renderer **shows that option only when the condition is true**. Other options on the same question stay available.

No new draw.io attribute — this is the existing option `relevance`.

## 3. Limitations

- The SDC extension lives on the **question**, not on the option element. Options without relevance stay enabled (SDC default).
- Native yes/no questions are FHIR `boolean` and have no `answerOption` list, so option relevance does not apply there.
- Renderer must implement `answerOptionsToggleExpression` (OpenSRP / FHIR Data Capture SDC behaviour profile).

---

# Part II — Technical specification

## 4. Extension

[SDC `answerOptionsToggleExpression`](http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-answerOptionsToggleExpression)
on `Questionnaire.item`:

- `option` (1..*) — `valueCoding` matching the item’s `answerOption.valueCoding`
- `expression` (1..1) — FHIRPath boolean; **true → option enabled**, false/empty → disabled

```json
{
  "url": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-answerOptionsToggleExpression",
  "extension": [
    {"url": "option", "valueCoding": {"code": "demo.angry", "display": "Angry"}},
    {
      "url": "expression",
      "valueExpression": {
        "language": "text/fhirpath",
        "expression": "%resource.repeat(item).where(linkId='demo_filter').answer.where($this.exists()).value = true"
      }
    }
  ]
}
```

Options that share the same FHIRPath may be grouped into one extension (several `option` slices).

## 5. Pipeline

- Option `relevance` is already loaded (`set_additional_attributes` + `load_expressions`).
- Select options are not walked as Questionnaire items (`should_skip` / no own `linkId`).
- `generate_relevance` on the **parent select** must scan `node.options` and attach toggles, even when the select itself has no item-level relevance.
- Skip `true` / empty relevance (always shown). Emit literal `false` so the option stays disabled.
- Coding must match the emitted `answerOption` (CodeSystem code/display when present).

## 6. Tests

- Select with one option `relevance` → item has the toggle extension, matching `valueCoding.code`, FHIRPath from `convert_expression_to_fhirpath`.
- Select with no option relevance → no toggle extension.
- Demo rebuild: `demo.angry` toggled by `demo_filter`.
