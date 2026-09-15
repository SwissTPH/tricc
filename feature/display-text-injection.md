# Display text injection (`${REF}`) — Feature Specification

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `feature/adv_merge_calc` / `develop` |
| **Related** | ODK/CHT label injection; `feature/20260909-display-message-ast.md` (message AST); FHIR dynamic text; multi-version refs via `feature/advanced-merge-calc.md` |
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

1. At form load, TRICC parses HTML into a **message tree** (`TriccMessage`) and splits `${REF}`
   tokens as interpolation leaves. Markdown is produced from that tree at export — HTML is never
   markdownified before the split. See `feature/20260909-display-message-ast.md`.
2. During processing, referenced fields are resolved (including versioned names) via
   `get_references()` / `replace_node` on the tree.
3. **ODK / CHT** export walks the tree to Markdown with `…${export_field_name}…` so the form
   engine injects values at display time. Bold/italic wrap the whole phrase, including the token.
4. **FHIR** keeps the same static Markdown in `item.text` and emits a concatenate FHIRPath
   expression at serialize time from complete literal runs (the in-memory type is never Concatenate).

## Benefits

- Dynamic notes and messages without hand-maintained calculate rows for ODK.
- Correct export names when concepts are versioned or repeated.
- One authoring syntax; strategy-specific rendering.

## Limitations

- Tokens are bare field names (`${age}`), not full expressions (`${age + 1}`).
- Formatting is a small HTML subset (bold, italic, breaks, lists). See
  `feature/20260909-display-message-ast.md`.

---

# Part II — Technical Specification

## Scope

| In scope | Out of scope |
|----------|--------------|
| `TriccNodeDisplayModel` and subclasses | `TriccNodeCalculateBase`, rhombus, factor, wait, etc. |
| Parse at **input load** only | Re-parse in `process_reference` / `is_ready_to_process` |
| Intermediate: `TriccMessage` AST (`feature/20260909-display-message-ast.md`) | Per-segment HTML clean; Concatenate as the stored message type |
| Resolve via `process_operation_reference` | Full JS template evaluation |

## Pipeline

```text
raw display HTML/text → TriccMessage (HTML parse + ${REF})
  → process_reference resolves refs
  → ODK: Markdown + ${export}  |  FHIR: static Markdown + serialize-time concatenate
```

## Code checklist

- [x] `tricc_oo/visitors/text_injection.py` — parse + load_display_text + ODK serialize
- [x] Model types accept ops on display text fields
- [x] draw.io + YAML: load only for DisplayModel
- [x] `process_reference`: resolve display text ops
- [x] XLSForm TRAD path uses ODK serialize
- [x] Tests

## Acceptance criteria

1. Note label `Age is ${age}` becomes a `TriccMessage` at load.
2. Processing resolves `age` to the node; ODK label is `Age is ${<export_name>}`.
3. Calculates/rhombus labels are not converted to a message AST.
4. Existing tests still pass.
