# Display text injection (`${REF}`) — Feature Specification

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `feature/adv_merge_calc` / `develop` |
| **Related** | ODK/CHT label injection; FHIR CONCATENATE export; multi-version refs via `feature/advanced-merge-calc.md` |
| **Authoring surface** | draw.io attributes + YAML fixtures |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business Description

## Overview

Authors can embed field values in user-facing text using ODK/JS-style tokens:

```text
Patient is ${age} years old
```

Supported on **display** nodes only (notes, questions, options, and other `TriccNodeDisplayModel` types) in:

- `label`
- `hint`
- `help`
- `constraint_message`
- `required_message`

**Not** supported on calculates, rhombus, or other non-display logic nodes.

## Behaviour

1. At form load, TRICC cleans HTML on the full string, then converts tokens into a structured concatenate expression.
2. During processing, referenced fields are resolved (including versioned names).
3. **ODK / CHT** export rewrites the text to `…${export_field_name}…` so the form engine injects values at display time.
4. **FHIR and other strategies** use the structured concatenate expression (they do not rely on `${}` in labels).

## Benefits

- Dynamic notes and messages without hand-maintained calculate rows for ODK.
- Correct export names when concepts are versioned or repeated.
- One authoring syntax; strategy-specific rendering.

## Limitations

- Tokens are bare field names (`${age}`), not full expressions (`${age + 1}`).
- HTML is cleaned on the **whole** attribute before tokens are split (required for balanced markup).

---

# Part II — Technical Specification

## Scope

| In scope | Out of scope |
|----------|--------------|
| `TriccNodeDisplayModel` and subclasses | `TriccNodeCalculateBase`, rhombus, factor, wait, etc. |
| Parse at **input load** only | Re-parse in `process_reference` / `is_ready_to_process` |
| Intermediate: `TriccOperator.CONCATENATE` | Per-segment HTML clean |
| Resolve via `process_operation_reference` | Full JS template evaluation |

## Pipeline

```text
raw display text → remove_html(full) → parse ${REF} → CONCATENATE
  → process_reference resolves refs
  → ODK: serialize to ${export}  |  FHIR: tricc_operation_concatenate
```

## Code checklist

- [x] `tricc_oo/visitors/text_injection.py` — parse + load_display_text + ODK serialize
- [x] Model types accept ops on display text fields
- [x] draw.io + YAML: load only for DisplayModel
- [x] `process_reference`: resolve display text ops
- [x] XLSForm TRAD path uses ODK serialize
- [x] Tests

## Acceptance criteria

1. Note label `Age is ${age}` becomes CONCATENATE at load after HTML clean.
2. Processing resolves `age` to the node; ODK label is `Age is ${<export_name>}`.
3. Calculates/rhombus labels are not converted to injection CONCATENATE.
4. Existing tests still pass.
