# MedicationRequest / MedicationDispense node type (parked)

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Branch target** | TBD — not scheduled, parked for a future pass |
| **Related** | `feature/20260812-intervention-order-and-dedup.md` (explicitly excludes MedicationRequest/MedicationDispense from its dedup work pending this spec) |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Why this exists

While implementing current-encounter dedup for Finding/Observation/Condition-typed data elements
(`feature/20260812-intervention-order-and-dedup.md`), the user asked for the same treatment on
MedicationRequest/MedicationDispense. Checked: neither resource has any presence in
`tricc_oo/converters/fhir/concept_mapper.py` or anywhere else in tricc_oo today — there is no
draw.io node type an author could use to produce a prescription or dispense record, so there is
nothing yet to dedup. Per the user, this needs its own node type first, designed as a separate
piece of work — parked here as a placeholder so the idea isn't lost, not implemented in this pass.

## Sketch (from the planning conversation — needs a full pass before Approval)

- A new node type derived from `odk_type: note` — the note's human-readable text becomes the
  prescription/dispense message shown to the user (e.g. "Give Amoxicillin 250mg 3x/day for 5
  days").
- Additional attributes carrying CQL expressions for structured fields other than the message
  itself — e.g. dose, rate, volume, frequency, duration — so the note can also drive real
  `MedicationRequest`/`MedicationDispense` extraction (dosage instructions, quantity) rather than
  being purely a display string.
- Eventual `CONCEPT_TYPE_TO_FHIR` entries for `MedicationRequest` (prescribe) and
  `MedicationDispense` (dispense) — today's `concept_mapper.py` already has `MedicationRequest` for
  `drug`/`medication`/`treatment` concept types, but no node type sets those on a message/note-like
  node, and `MedicationDispense` has no entry at all.
- Eventual dedup helpers mirroring `feature/20260812-intervention-order-and-dedup.md`'s Condition
  family (`GetMedicationRequests`/`GetMedicationRequestValue`/…, current-encounter-scoped by
  `encounterid`) once the node type exists and extraction is defined.

## Explicitly out of scope until this spec is Approved

- No node type, model, or `drawio_type_map.py` changes.
- No `concept_mapper.py` changes.
- No CQL helper changes for Medication*.
- No changes to `feature/20260812-intervention-order-and-dedup.md`'s dedup auto-wiring, which
  covers Observation/Condition only.

## Next steps

Needs a full Part I (business)/Part II (technical) pass — dosage/rate/volume attribute shape,
how a note-derived node interacts with existing `note` semantics, and the extraction FML for
MedicationRequest/MedicationDispense — before this can move to `Approved`.
