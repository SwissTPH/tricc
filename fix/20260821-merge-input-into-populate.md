# Merge `TriccNodeInput` into `TriccNodePopulate` (one node type for pre-loaded values)

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `feature/populate-context.md`, `fix/20260821-output-pass-calculate-readiness.md`, `fix/20260820-opensrp-inherited-value.md`, `docs/open-srp-export.md`, `docs/tricc-elements.md` |
| **Strategy** | Model / parser change; affects `FHIRStrategy`, `OpenSRPStrategy`, `XLSFormStrategy` + CHT/CDSS |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Issue analysis

## 1. Symptom

```
WARNING - No FHIR item type mapping for TRICC type 'input', defaulting to 'string'
          (questionnaire_item_mapper.py:199)
```

8 times on the global almanach, all during the **export / StructureMap** phase. Behind the
warning, three registries disagree about what an `input` node is:

| Phase | Behaviour today |
|---|---|
| `generate_base` | `TriccNodeType.input` is in `SKIP_NODE_TYPES` → **no Questionnaire item** |
| `generate_calculate` | `input` is not in `CALCULATE_NODE_TYPES`, and `TriccNodeInput` is not a `TriccNodePopulate` → early return → **no `initialExpression`, no CQL define** |
| `generate_export` | `build_extraction_rule` still emits a rule (`structuremap.py:170` → the warning) → **the StructureMap writes back an Observation for a linkId that exists in no Questionnaire** |

The value is never loaded, never shown, never computable — but extraction claims to extract it.

## 2. Root of the mess: two node classes for one concept

`TriccNodeInput` (`models/calculate.py:67`, `tricc_type = input`, drawio `odk_type="input"`,
attributes `save` / `reference` / `data_type` / `concept_type` / `repeat`) and
`TriccNodePopulate` (`tricc_type = populate`, same attributes **plus** `context` and `period`)
are siblings under `TriccNodeFakeCalculateBase`. `TriccNodePopulate` is the newer, richer model;
the rename that introduced it — to stop the confusion with the data-entry `TriccNodeInputModel`
family — was never completed, so authored content still lands on `TriccNodeInput`.

Semantically they are the same thing, and neither is a question: both are always hidden, both
exist only to fetch context or historical data, and in the XLSForm strategies both are collected
late in the process by `XLSFormCDSSStrategy.export_inputs` and emitted into the CHT `inputs`
block rather than the survey flow.

The code already says so: every isinstance check in the pipeline pairs them —
`xml_to_tricc.py:152`, `:201`, `:648`, `visitors/tricc.py:1295`, `xlsform_cdss.py:221`. Only
four places treat `TriccNodeInput` alone:

| Site | Input-only behaviour |
|---|---|
| `tricc_to_xls_form.py:93` | export name gets a `load.` prefix (`load.<name>`) |
| `fhir_form.py:1080` | a *reference* to an input resolves to `get_observation_cql_accessor_for_node` |
| `questionnaire_item_mapper.py:182` | `is_default_or_odk_input()` — **dead code, no callers** |
| `questionnaire_item_mapper.py` registries | `input` in `SKIP_NODE_TYPES`, absent from `NODE_TYPE_TO_FHIR` / `CALCULATE_NODE_TYPES` |

## 2b. How the value actually reaches a CHT form (checked against the exporter)

CHT injects external data into an app form two ways, and the exporter uses both:

**(1) The `inputs` group.** `get_cht_input` builds `begin_group inputs` (relevance
`./source = "user"`) with `user` and `contact` subgroups (`xlsform_cht.py:52-325`). CHT fills
`inputs/contact` from the contact doc when the form is opened from a contact or a task, and a
task's `modifyContent` can add further keys to the form content. The exporter already hardcodes
this for its own fields — `../inputs/user/contact_id`, `../inputs/user/facility_id`,
`../inputs/user/name`, `../inputs/contact/_id`, `../inputs/contact/sex`,
`../inputs/contact/patient_name`.

**(2) The contact-summary instance.** `instance('contact-summary')/context/<key>`, built by
`get_cht_contact_summary_expression`. Nothing passes through `inputs`; a single `calculate` row
reads the value. This is the only route for anything derived from previous reports, since a CHT
form cannot query reports itself.

What each node type emits today:

| | row inside `inputs/contact` | top-level `calculate` row |
|---|---|---|
| `input` | `<name>` — must match the source **doc field** name (`get_input_line`) | `load.<name>` → `../inputs/contact/<name>` (`get_input_calc_line`) |
| `populate` | `<export_name>` (`get_input_line` with `row[1]` overridden, `xlsform_cht.py:250-256`) | `<export_name>` → contact-summary expression (`get_populate_calc_line`) |

Three conclusions:

1. **The `load.` calculate is not a CHT requirement.** `${<name>}` resolves to a field nested in
   `inputs/contact` on its own — pyxform resolves the path. The extra row exists only as a
   namespace shim: the inputs field name is dictated by the source doc, so if the same concept is
   also asked as a question in the form, two nodes would share one name. It is needed exactly
   when the value arrives through mechanism (1).
2. **For mechanism (2) both the inputs row and any `load.` row are pointless** — the value never
   passes through `inputs`. The hidden `inputs/contact/<export_name>` row currently emitted for
   populate nodes is a copy of the `input` behaviour and is what makes its name collide with its
   own calculate row.
3. **The populate CHT path has never run.** `get_populate_calc_line` returns **16 columns where
   `SURVEY_MAP` has 19**, so `df_input.loc[…] = …` raises
   `ValueError: cannot set a row with mismatched columns` (`xlsform_cht.py:498`). Every CHT export
   of a project containing a populate node crashes:

   ```
   python tests/build.py -i tests/data/yaml/populate_patient.yaml -I YamlStrategy -O XLSFormCHTStrategy
   → ValueError: cannot set a row with mismatched columns
   ```

   (`get_input_line`, `get_input_calc_line` and the populate override are all 19 — only the
   populate calc row is short.) `tests/test_populate_context.py` only unit-tests the expression
   string, never the row, which is why this went unnoticed. **This is a blocking prerequisite for
   the merge**: once every legacy `input` node becomes a populate node, the crash would hit CHT
   exports that work today (the global almanach's `XLSFormCHTHFStrategy` build has 8 such nodes).

## 3. Expected behaviour

One node type for pre-loaded values (`TriccNodePopulate`), authored either as `populate` or as
the legacy `input` drawio keyword. It exports as a hidden item whose value is fetched once —
CQL `initialExpression` for FHIR/openSRP, the CHT inputs/contact-summary binding for XLSForm —
and never as a question.

## 4. Out of scope

- Renaming the drawio `input` keyword itself: existing diagrams keep using `odk_type="input"`.
- `TriccNodeInputModel` and its subclasses (the real data-entry questions) — untouched.
- Per-use-case CQL variants for how a given populate node is fetched (`context` already covers
  patient / facility / location / practitioner / encounter / history; fine-tuning later).
- Fixing the raw-CQL-string calculation that plain `XLSFormStrategy` writes for populate nodes
  (pre-existing; `expression_reference = TriccStatic(resolve_populate_reference(node))`).

---

# Part II — Fix approach

## 5. Fix rules

**R1 — parse `input` into `TriccNodePopulate`.** In `drawio_type_map.TYPE_MAP`, the
`TriccNodeType.input` entry keeps its drawio keyword but takes `"model": TriccNodePopulate` and
the **union** of both attribute lists (i.e. gains `context`, `period`). `TYPE_MAP` is only used
to select elements by `odk_type` and to instantiate the model (`xml_to_tricc.get_all_nodes`), so
nodes authored as `input` simply carry `tricc_type = populate` from the model default.
`TriccNodeType.input` survives in the enum as the author-facing keyword only.

**R2 — preserve today's CQL semantics for migrated nodes.** When the drawio keyword is `input`
and the author set no `context`, default `context = "encounter"`. This is behaviour-preserving:
`GetEncounterValue(code, repeatIndex, period)` reduces to `GetObservationValue(code)` when
`repeatIndex` is null/1 and to `GetRepeatedValue(code, repeatIndex)` otherwise
(`populate_helper.py:158-160`) — exactly what `get_observation_cql_accessor(code, repeat)` emits
today (`repeat_helper.py:40-60`). `TriccNodePopulate`'s own default stays `patient`.

The emitted CQL text changes (`Helper.GetEncounterValue('x', null, null)` instead of
`Helper.GetObservationValue('x')`); the *value* does not, because the Helper function reduces to
exactly that call for the default slot. Defaults live in `TYPE_MAP[...]["defaults"]` and are
applied in the model constructor, not after `set_additional_attributes` — the model default
(`patient`) is indistinguishable from an unset attribute once the node exists, so an author-set
`context` still wins.

**R3 — delete the class.** Remove `TriccNodeInput` from `models/calculate.py`; collapse the
paired isinstance tuples to `TriccNodePopulate`; drop the Input branch at `fhir_form.py:1080` so
references route through `resolve_populate_reference`; delete the dead
`is_default_or_odk_input()`; remove `TriccNodeType.input` from `SKIP_NODE_TYPES` and from
`concept_mapper.py:217`'s Symptom-Finding list (populate is already handled there via
`xml_to_tricc.py:648`).

**R4 — CHT emission follows the data source, not the node class.** The naming question is not
"input vs populate", it is "does this value arrive through the `inputs` group or through
contact-summary". **Decision taken (2026-08-21):** `encounter` → `inputs` group, every other context →
contact-summary. This preserves both behaviours that exist today — legacy `input` nodes (now
`context=encounter`) keep their `../inputs/contact/<field>` binding and `load.` prefix, and
authored `populate` nodes keep contact-summary — so the only changed case is an authored
`populate` with `context=encounter`, which crashes today anyway. Flip the `encounter` row if your
deployments compute a contact-summary key for it instead (§6.1):

| `context` | CHT emission |
|---|---|
| `patient` | contact doc field → hidden row `inputs/contact/<concept name>` + `calculate load.<name>` = `../inputs/contact/<name>` (today's `input` behaviour) |
| `facility` / `location` / `practitioner` | user/facility fields already injected under `inputs/user/…` → same shape, bound under `inputs/user/` |
| `history` | derived from previous reports → contact-summary only: one `calculate <name>` = `instance('contact-summary')/context/<key>`, **no** inputs row |
| `encounter` | task-injected `inputs` field — **the implemented default** (this is what the legacy `input` nodes were) |

The `load.` prefix therefore survives only for the inputs-group cases, where a field of the same
concept name already exists — it is dropped for contact-summary-backed nodes, which need no
second name. This also removes the populate duplicate-name pair described in §2b.

Also note `serializers/xls_form.py:279-280`: `"input": ""` (no survey row) vs
`"populate": "calculate"` (survey calculate row). After the merge, migrated nodes gain the survey
row; confirm that is wanted for plain `XLSFormStrategy`, where a populate node's calculation is
currently the raw CQL accessor string.

**R4b — encounter accessors are resource-specific.** `GetEncounterValue` read an Observation
value whatever the node's `concept_type` was. The Helper now defines
`GetEncounterObservationValue(code, repeatIndex, period)` (the old body: `GetObservationValue` /
`GetRepeatedValue`, both already filtered on the `encounterid` parameter through
`GetObservations`, i.e. *this* encounter) and `GetEncounterConditionValue(code)` (delegating to
`GetConditionValue`, filtered the same way through `GetConditions`). `GetEncounterValue` stays as
a deprecated alias so previously generated libraries keep resolving.
`resolve_populate_reference` picks the accessor from `get_fhir_resource(concept_type, tricc_type)`,
and the same routing applies to `history` (`GetHistoryObservationValue` /
`GetHistoryConditionValue`).

**R5 — the FHIR export fix falls out.** No new registry entries are needed: `populate` is
already `(string, False, hidden=True)` in `NODE_TYPE_TO_FHIR`, already in
`CALCULATE_NODE_TYPES`, and already handled by the `TriccNodePopulate` branch of
`generate_calculate` (define + `initialExpression`). The type-mapping warning disappears, the
item exists, and extraction finally points at a real linkId.

## 6. Open questions

1. **Confirm the §5 R4 context → CHT mechanism mapping.** Which contexts does your deployment
   feed through `inputs` (contact doc / task `modifyContent`) and which through
   `contact-summary`? `history` is contact-summary-only by construction; `patient` is available
   both ways (the exporter's own `sex` / `patient_name` rows read `inputs/contact/…`).
2. **Should a populate node produce a FHIR extraction rule at all?** Writing a loaded value back
   creates a fresh Observation every encounter. Today both types do; the merge is a natural point
   to stop.
3. **`repeat` on migrated nodes** — populate passes it through `_repeat_cql_arg`; confirm the
   legacy `input` repeat semantics match.

## 7. Code checklist

- `tricc_oo/models/calculate.py` — [ ] delete `TriccNodeInput`.
- `tricc_oo/converters/drawio_type_map.py` — [ ] `input` entry → `TriccNodePopulate` + union of
  attributes (R1).
- `tricc_oo/converters/xml_to_tricc.py` — [ ] `input` keyword defaults `context="encounter"` (R2);
  [ ] collapse tuples at `:152`, `:201`, `:648`.
- `tricc_oo/visitors/tricc.py` — [ ] drop the import and collapse the tuple at `:1295`.
- `tricc_oo/converters/tricc_to_xls_form.py` — [ ] `:93` per R4.
- `tricc_oo/converters/fhir/questionnaire_item_mapper.py` — [ ] drop `input` from
  `SKIP_NODE_TYPES`; [ ] delete `is_default_or_odk_input`.
- `tricc_oo/converters/fhir/concept_mapper.py` — [ ] drop `TriccNodeType.input` from the
  Symptom-Finding tuple.
- `tricc_oo/strategies/output/fhir_form.py` — [ ] remove the `TriccNodeInput` branch (`:1080`)
  and the import.
- `tricc_oo/serializers/xls_form.py` — [ ] **blocking**: `get_populate_calc_line` returns 16 of
  19 columns (§2b.3) — fix before the merge lands, or every CHT export with a populate node
  crashes; [ ] emit the inputs row / `load.` calculate per R4 instead of unconditionally.
- `tricc_oo/strategies/output/xlsform_cht.py` — [ ] `:250-256` stop emitting an `inputs/contact`
  row for contact-summary-backed nodes (R4).
- `tricc_oo/strategies/output/xlsform_cdss.py` — [ ] collapse `export_inputs` tuple (`:221`).
- Tests — [ ] migrate `tests/test_fhir_repeat.py` and
  `tests/test_strategies/test_fhir_inherited_value.py` (both construct `TriccNodeInput`).
- Docs — [ ] `docs/tricc-elements.md`: `input` is a legacy alias of `populate`;
  [ ] `docs/open-srp-export.md`: pre-loaded values export as hidden CQL-populated items.

## 8. Tests

- [ ] YAML/drawio fixture with an `input`-keyword node → node is a `TriccNodePopulate` with
      `context == "encounter"`.
- [ ] Its FHIR export: hidden item exists, one `initialExpression` with a simple define name,
      define body equals the accessor the old `input` path produced (`GetObservationValue('<code>')`
      for repeat 1).
- [ ] No `No FHIR item type mapping for TRICC type 'input'` warning anywhere in the run.
- [ ] Its extraction rule targets a linkId present in its own Questionnaire (or none, per open
      question 2).
- [ ] A reference to it from another calculate produces the same CQL accessor as before the merge.
- [ ] **CHT export of a populate fixture completes at all** (regression for the 16/19 column
      crash) — `populate_patient` / `populate_encounter` / `populate_history` via
      `XLSFormCHTStrategy`, then pyxform-valid with unique names.
- [ ] contact-summary-backed node: exactly one row, the calculate; no `inputs/contact` row.
- [ ] inputs-backed node: hidden `inputs/contact/<name>` + `load.<name>` calculate reading it.
- [ ] `python -m pytest tests/` green; demo/etat/combacal exports for XLSForm, XLSFormCHT, FHIR,
      OpenSRP all still produce loadable output.

## 8b. Note: the export is not deterministic run-to-run

Comparing two builds of the *same* code on `tests/data/combacal.drawio` (CHT) shows differing
synthetic node names (`s_iqi_…_1_13` vs `_1_15`, `lki_…_61_2` vs `_61_4`) and row order for
same-named pairs. Only generated ids and ordering move; excluding those rows, the two runs are
identical. Any before/after comparison of exported artifacts therefore has to sort and drop
synthetic ids, or set `PYTHONHASHSEED`. Worth its own `fix/` — reproducible builds would make
regressions like the ones in this file far easier to see.

## 9. Acceptance criteria

- `grep -rn "TriccNodeInput\b" tricc_oo tests` returns nothing (only `TriccNodeInputModel`).
- Global almanach OpenSRP export: zero `'input'` type-mapping warnings; every pre-loaded-value
  node has a hidden item + one `initialExpression` + one define.
- No StructureMap rule references a linkId absent from its Questionnaire.
- Verified on the global almanach: 8 hidden `load_*` items with `initialExpression` (0 before),
  `initialExpression` 449 → 457, 89 `Helper.GetEncounterObservationValue(...)` calls, 0 legacy
  `GetEncounterValue` calls, 0 `'input'` type-mapping warnings; CHT-HF export carries the same 8
  nodes as `../inputs/contact/…` bindings.
- CQL emitted for a migrated node resolves to the same value as the old `input` path (R2:
  `GetEncounterValue(code, null, null)` reduces to `GetObservationValue(code)`).
- The CHT export of content with migrated nodes is unchanged (order-insensitive comparison —
  see the determinism note below).
