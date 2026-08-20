# StructureMap FML compile on push (HAPI parse, no hand-written extract JSON)

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | current TRicc / OpenSRP worktree |
| **Related** | `feature/20260813-concepttype-structuremap.md`, `docs/open-srp-export.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` + `push-to-fhir.sh` |
| **Approval** | 2026-08-17 conversation (user asked for a TRicc fix plan; chose compile-from-`.map` over a second JSON extract emitter). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability).

---

# Part I — Issue analysis

## 1. What went wrong

Submitting the demo OpenSRP Questionnaire (`e2f37a54-…`) logged:

```
Loaded StructureMap/965e5a22-… groups=2 rules=1
Group : extract
  rule : bundleType
StructureMap extraction produced 0 resources
```

The companion `.map` already walked items and created Observations. The published JSON did not.

## 2. Why it happens

OpenSRP / HAPI executes `StructureMap.group[]` from the FHIR JSON in the store. It never compiles `text.div` or a sibling `.map`.

TRicc wrote complete FML and a **summary** JSON (`extract` + stub `extractItems`, no leaf groups, no `src.item` walk). That summary was documented as intentional in `feature/20260813-concepttype-structuremap.md` §6. The assumption is wrong for FHIR-Core.

The JPA server (`opensrp/hapi-fhir-jpaserver-starter`) also does **not** compile FML on PUT. `$transform` applies a stored map; `$convert` is JSON ↔ XML.

## 3. What authors and implementers should see after the fix

- FML (`.map`) remains the only mapping we author and debug.
- `push-to-fhir.sh` compiles each sibling `.map` with HAPI `StructureMapUtilities.parse` and PUTs that JSON.
- A failed compile **blocks** upload of the stub (no more silent empty extract).
- Android is unchanged: it still loads compiled `group[]`.

## 4. Out of scope

- Hand-building leaf `create('Observation')` JSON groups in Python.
- A custom HAPI server operation / Matchbox to accept FML on PUT.
- Android `parse(text.div)` fallback.
- Completing Task-map JSON (planning-only; same compile hook applies if a `.map` exists).

---

# Part II — Fix approach

## 5. FML dialect (HAPI)

Dispatch uses an FML `where` clause, matching `cdss-client-registration.map`:

```
item as q where(linkId = 'demo_is_happy') then {
  q.answer as answer then extract_demo_is_happy(answer, src, bundle);
} "extract_demo_is_happy";
```

Not `item.where(linkId = '…').answer` (FHIRPath method; HAPI’s FML parser rejects it).

`uses … as produced` becomes `uses … as target`.

Observation values use polymorphic ``answer.value : boolean`` / ``: string`` /
``: Coding`` written to ``tgt.value``. HAPI ``getProperty`` does not expose
``valueBoolean`` on ``QuestionnaireResponse.item.answer`` or Observation.

proposed / AcceptDiag add `and answer.valueBoolean = true|false` on the `where`.

## 6. Compile on push

`compile-structuremap.sh` + `CompileStructureMap.java`:

1. `StructureMapUtilities.parse(fml, name)` with `SimpleWorkerContext.fromNothing()`.
2. Overlay identity from the JSON shell (`id`, `url`, `meta`, extensions, …).
3. Fail the push if parse fails or a StructureMap has a sibling `.map` that cannot be compiled.

## 7. Code checklist

- [x] `converters/fhir/structuremap.py` — HAPI FML dialect
- [x] `tests/test_strategies/test_fhir_structuremap.py`
- [x] `templates/opensrp/compile-structuremap.sh` + `CompileStructureMap.java`
- [x] `templates/opensrp/push-to-fhir.sh` fail-closed compile
- [x] Copy new helpers from `OpenSRPStrategy._copy_push_scripts`
- [x] Docs: this file, feature §6, `docs/open-srp-export.md`

## 8. Acceptance

1. TRicc does not grow a parallel JSON extract emitter.
2. Demo extract FML compiles under HAPI parse; group count includes extract + extractItems + leaf groups.
3. Push without a successful compile cannot publish the stub map.
4. Submit of Questionnaire `e2f37a54-…` extracts Observations for answered extractable items.
