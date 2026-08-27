# Concept-level persistence mapping, and deprecation of `save`

| Field | Value |
|-------|-------|
| **Status** | Draft — **property shape is a proposal; see §8** |
| **Branch target** | TBD |
| **Related** | `feature/20260813-concepttype-structuremap.md` (the `conceptType` → resource mapping this extends), `feature/populate-context.md` (the read direction), `feature/20260812-intervention-order-and-dedup.md` (encounter-scoped helpers), `docs/desing/FHIRcore.md`, `../tricc_frontend/feature/20260825-terminology.md` (the authoring surface) |
| **Origin** | Drafted during `tricc_frontend` planning, 2026-08-26, from the maintainer's observation that `save` is eligible for deprecation. Reviewed and owned here. |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

### Where an answer lands

When a health worker answers a question, that answer has to become a real clinical record — a
measurement becomes an Observation, a classification becomes a Condition, a date of birth belongs
on the patient's own record.

Most of this already happens automatically. `feature/20260813-concepttype-structuremap.md` made
extraction follow the **concept class** already stored in the project's terminology: a concept
classed as a vital sign becomes an Observation, one classed as a diagnosis becomes a Condition.
The author does not say where an answer goes; the concept already knows.

### The gap

That mechanism handles resources whose payload *is* the concept — an Observation is
"this code, this value". It does not handle concepts that belong to a **named field of another
resource**.

Date of birth is the clearest case. It is not an observation about a patient; it is
`Patient.birthDate`. Today a concept classed `patient` maps to
`("Patient", …, "extension")` (`concept_mapper.py`) — everything demographic lands in a generic
extension rather than the field FHIR already defines for it. The same gap exists on the way back
in: `GetPatientValue('date_of_birth')` is generated for reading patient data, and nothing tells
that helper which element of `Patient` the code refers to.

So the proposal: **a concept may declare the resource and element path it corresponds to**, and
that one declaration serves both writing and reading.

### What this replaces: `save`

The `save` attribute predates all of this. It was introduced so an author could redirect a node's
value without drawing extra calculate nodes — the drawing surface was the constraint, and there
was no expression language capable of doing it another way.

Three things have changed:

1. **`conceptType` now drives extraction automatically.** The common case `save` was used for no
   longer needs saying.
2. **Concepts are authored properly.** `save` doubles as an ad-hoc concept-creation mechanism —
   `xml_to_tricc.py` splits `save` on `.` to synthesize a system and code. With a real terminology
   surface (`../tricc_frontend/feature/20260825-terminology.md`) a concept is created as a
   concept, not smuggled in through a node attribute.
3. **CQL expressions exist.** The redirection and derivation `save` was invented to avoid drawing
   are now written directly as expressions — which is clearer, reviewable, and works on every
   export target.

`save` is therefore **deprecated**: still read, so no diagram breaks, but no longer the way to say
where an answer lands, and no longer offered by authoring tools.

### Limitations

- Writing to a field of an existing resource is an **update**, not an extraction. Creating an
  Observation is additive and safe; setting `Patient.birthDate` overwrites a value that may have
  come from registration or from the national registry. This needs a deliberate policy (§5), and
  it is the main reason this is a spec rather than a patch.
- Only a small minority of concepts need this. Anything that is genuinely an observation or a
  condition should stay as it is.

---

## Part II — Technical specification

### 1. The property

Two new `CodeSystem.concept.property` entries, optional and expected to be rare:

| Property | Type | Meaning |
|----------|------|---------|
| `targetResource` | `code` | FHIR resource type — `Patient`, `Encounter`, `Condition`, … Overrides the `conceptType` → resource mapping when present. |
| `targetPath` | `string` | Element path **relative to the resource root**, in FHIRPath element syntax: `birthDate`, `gender`, `name.given`, `telecom.where(system='phone').value`. |

```jsonc
{
  "code": "date_of_birth",
  "display": "Date of birth",
  "property": [
    { "code": "conceptType",    "valueCode":   "patient" },
    { "code": "targetResource", "valueCode":   "Patient" },
    { "code": "targetPath",     "valueString": "birthDate" }
  ]
}
```

Design notes:

- **`targetPath` uses FHIR element names, not TRICC names.** `birthDate`, not `date_of_birth`. The
  concept's own `code` stays whatever the project calls it; the path is the FHIR contract, and
  keeping the two separate is the entire point of the mapping.
- **Both or neither.** `targetPath` without `targetResource` is an error — a path is meaningless
  without knowing what it is relative to. `targetResource` alone is legal and means "this resource
  type, default payload placement", which is what `conceptType` already gives.
- **Absent means today's behaviour**, unchanged, for every existing concept.

### 2. Write path

`tricc_oo/converters/fhir/structuremap.py` currently emits, per extracted item, a rule targeting
the resource's payload field (`data_type_field` from `CONCEPT_TYPE_TO_FHIR`).

With `targetPath` present:

- the FML rule targets that element path instead of the payload field;
- `targetResource` selects the group;
- the value is cast to the element's FHIR type, derived from the concept's `dataType` and the
  element definition. A mismatch — a `string` concept mapped to `Patient.birthDate` — is an error
  at export, naming the concept, because the alternative is a StructureMap that fails at runtime on
  a phone.

### 3. Read path

`resolve_populate_reference` (`populate_helper.py:125`) generates
`GetPatientValue('<code>')` and its siblings for `patient` / `facility` / `practitioner` /
`location` contexts. Those helpers currently have no way to resolve a code to an element.

With the property, the generated Helper CQL for each referenced master-context concept becomes a
real accessor:

```cql
define function GetPatientValue(code String):
  case
    when code = 'date_of_birth' then ToString(Patient.birthDate)
    when code = 'sex'           then ToString(Patient.gender)
    else null
  end
```

Generated only for concepts actually referenced by a `populate` node, keeping the Helper thin as
`docs/desing/FHIRcore.md` requires.

This is the strongest argument for putting the mapping on the concept rather than on the node: one
declaration makes both directions work, and read and write cannot drift apart.

### 4. Non-FHIR targets

The mapping is FHIR-shaped, so what other strategies do with it must be stated rather than left to
discovery:

| Strategy | Behaviour |
|----------|-----------|
| `XLSFormStrategy`, `XLSFormCDSSStrategy` | Ignored. No persistence model. |
| `XLSFormCHTStrategy` | Ignored for write. CHT's contact-summary read path is separate and unchanged. |
| `OpenMRSStrategy`, `DHIS2Strategy` | Ignored in this pass. Both have their own mapping conventions; extending this to them needs their own spec. |
| `FHIRStrategy`, `OpenSRPStrategy` | Full behaviour as above. |

A concept carrying `targetPath` in a project exported to a non-FHIR target produces an
**informational message**, not a warning — the author has not made a mistake, the target simply
cannot honour it.

### 5. Update semantics — needs a decision

Extraction creates resources. `targetPath` on a master-context resource means **modifying an
existing one**, and this spec should not choose the policy silently. Options:

- **(a) Write only when absent.** Never overwrite a value that already exists. Safe; means
  correcting a wrong date of birth through a form is impossible.
- **(b) Always write.** The form is authoritative for the encounter. Simple; a mis-tapped value
  overwrites registry data.
- **(c) Write with provenance**, retaining the previous value. Correct, and the most work.
- **(d) Refuse master-context writes in v1.** `targetPath` is read-only for `Patient` and friends;
  only Encounter-scoped resources accept writes.

**Recommendation: (d) for the first pass.** It delivers the read direction — which is the
concretely broken one today, since `GetPatientValue` cannot resolve anything — with no risk to
patient records, and leaves the write policy to be decided with a real use case in hand rather than
in the abstract.

### 6. Deprecating `save`

| Step | Behaviour |
|------|-----------|
| Load | `save` is read exactly as today. `xml_to_tricc.py:237` concept synthesis is retained. |
| Warn | A deprecation warning per node, naming it, with the suggested replacement — bind the concept directly, or express the derivation in CQL. |
| Authoring tools | `tricc_frontend` never writes `save` and does not offer it (`../tricc_frontend/feature/20260825-project-format.md` §3.1). |
| draw.io | `save` stays in `drawio_type_map.py` attribute lists; the palette stops advertising it. |
| Removal | Not scheduled here. It happens when the existing corpus is migrated, in its own spec. |

Nothing in the current corpus breaks, and nothing new acquires a dependency on it.

### 7. Code checklist

| File | Change |
|------|--------|
| `tricc_oo/models/ocl.py` / CodeSystem loading | Parse `targetResource` / `targetPath`; validate the pairing rule |
| `tricc_oo/converters/fhir/concept_mapper.py` | `resolve_concept_type` honours `targetResource`; expose `resolve_target_path` |
| `tricc_oo/converters/fhir/structuremap.py` | Path-targeted FML rules; type compatibility check |
| `tricc_oo/converters/fhir/repeat_helper.py` | Generate real `GetPatientValue` / `GetFacilityValue` / … bodies from mapped concepts |
| `tricc_oo/converters/fhir/populate_helper.py` | Unchanged call sites; error when a master-context populate names an unmapped concept |
| `tricc_oo/converters/xml_to_tricc.py` | `save` deprecation warning |
| `docs/tricc-elements.md` | Document the properties; mark `save` deprecated |
| `docs/desing/FHIRcore.md` | Master-context accessor generation |

### 8. Open questions

1. **Property naming.** `targetResource` / `targetPath` here; the maintainer's sketch was
   `parent` / `path`. `parent` reads as hierarchy rather than as a FHIR resource type, which is
   why this draft avoids it — but the call is not mine.
2. **Update policy** — §5. Recommendation is (d); it needs agreeing.
3. **Scope beyond FHIR.** Should OpenMRS and DHIS2 honour an analogous mapping, or keep their own?
4. **Property vs. `conceptType` precedence** when both imply a resource and they disagree. This
   draft says `targetResource` wins; it should be confirmed rather than assumed.

### 9. Tests

- Property parsing, including the both-or-neither rule.
- `targetResource` overriding `conceptType`.
- FML emission against an element path, with a type-mismatch error case.
- Generated `GetPatientValue` resolves mapped concepts and returns null for unmapped ones.
- A master-context `populate` naming an unmapped concept errors with an actionable message.
- Under recommendation (d), a `Patient` `targetPath` produces no write rule.
- Non-FHIR strategies ignore the properties and emit the informational message.
- Every existing fixture converts byte-identically — no concept in the corpus carries the
  properties yet, so this must hold trivially and is worth asserting.
- `save` still works, and warns.

### 10. Acceptance criteria

- [ ] A concept can declare its resource and element path.
- [ ] `GetPatientValue` and siblings resolve mapped concepts to real elements.
- [ ] A master-context `populate` on an unmapped concept fails with a message naming the concept.
- [ ] Extraction targets element paths where declared, with type checking.
- [ ] The update policy in §5 is decided and implemented as decided.
- [ ] `save` warns, still works, and is absent from authoring tools.
- [ ] Every existing export is byte-identical.

### 11. Implementation phases

1. Property parsing and validation.
2. Read path — master-context Helper accessor generation. **The broken thing today; do it first.**
3. Deprecation warning on `save`; docs.
4. Write path, once §5 is decided.
