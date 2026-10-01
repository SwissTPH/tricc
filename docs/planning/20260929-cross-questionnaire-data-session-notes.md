# Carrying data between questionnaires (openSRP) — session notes, 2026-09-29

Working notes from one investigation-and-fix session: how a value captured in one
questionnaire (the participant's weight in **Diabetes**) can be used by another
(**Hypertension Followup**) for the same patient without being asked again. Everything done,
found, changed and left open is recorded here so the work can continue from this file.

Formal specs produced by the session (status **Approved**, not yet Implemented — the
on-device acceptance run is pending):

- `feature/20260929-cql-populate-wiring.md` — `cqf-library`, `depends-on`, `encounterid`,
  populate `source`, history `period` window, no extraction of populate nodes, warning.
- `fix/20260929-cql-initial-expression-on-device.md` — why CQL `initialExpression` never
  filled an item on device, and the export rules that fix it.

---

## 1. Where things stand (end of session)

| | State |
|---|---|
| Approach (Patrick's suggestion: CQL library + `$evaluate`, check EmCare / SMART-CMR) | **Sound.** Same design as EmCare/SMART-CMR. Proven end to end on the tablet. |
| Server `$evaluate` | **Not available** on the openSRP server (plain HAPI 6.1.3, no Clinical Reasoning). CQL runs on the device. |
| Diabetes → Hypertension, same care session | **Works on the tablet** (weight 63.4 kg entered in Diabetes appeared in Hypertension), first with a hand-patched package, later with a clean TRICC export. |
| Previous visit → Diabetes (hidden `t_weight` via `context=history` + `source`) | **Blocked by a fhircore bug** (null CQL results are applied as empty `initial` values, which changes in-form logic and hid the weight section). Fix identified, not applied. |
| TRICC code changes | Done on branch `feature/project-level-config`, **uncommitted**. 541 tests pass (2 pre-existing failures, see §6). |
| fhircore changes | None made. Needed changes listed in §5. |

---

## 2. What was investigated, in order

### 2.1 Server
- `194.182.171.88/fhir` is HAPI 6.1.3. `metadata` lists no `Library/$evaluate`,
  `Questionnaire/$populate` or `PlanDefinition/$apply`; calling them returns
  `400 not-supported`. openSRP evaluates CQL on the device, so this is expected.
- The `demo` user sees 0 Patients / Observations / QuestionnaireResponses (gateway ACL or no
  synced data) — real device data could not be inspected server-side.

### 2.2 Local CQL server (Docker)
- `docker run … hapiproject/hapi:latest` with `hapi.fhir.cr.enabled=true` on port 8099
  (container `tricc-hapi-cr`, in-memory H2). Seeded the Hypertension libraries, a patient,
  and weight Observations shaped exactly like the Diabetes extraction map writes them.
- Findings, in the order they blocked evaluation:
  1. **Library not found** — the engine takes the library name from the last segment of the
     canonical URL; TRICC put the UUID there (`…/Library/6dc3a855…`).
  2. **Helper CQL did not compile** — unparenthesised function-call query sources,
     FHIRPath `.where()`, `skip`/`take`, `sort by` on a choice type (runtime error),
     `exists()` on a single Condition.
  3. **One invalid define broke the whole segment library** — `Calc_next_visit` used bare
     XLSForm names (`warn_symp`, `bp_status`, …) and XLSForm date arithmetic.
  4. **`$populate` only uses `cqf-library`** — with only `cqlInputResources` the item stayed
     empty; with `cqf-library` it was filled.
- With those fixed: `GetHistoryObservationValue('weight_c', …)` → 72.5 (latest), 80
  (previous). The encounter-scoped accessor only sees the current visit. HTN's populate read
  `t_weight`, which nothing writes → null.

### 2.3 Device side — code reading (fhircore fork `~/Documents/code/opensrp-fhircore`, android-fhir)
- The Android SDK evaluates `initialExpression` as **FHIRPath only** (ignores `language`).
- The fork has a CQL prefill path (commit `1a5bb44c3`,
  `QuestionnaireViewModel.evaluateCqlInitialExpressions`): runs only when the Questionnaire
  has `cqf-library`; passes `encounterid` (Encounter from launch context) and `patient`;
  calls `FhirOperator.evaluateLibrary` once per library with **all** expressions; writes
  results into `item.initial`. Upstream fhircore does not have this.
- Nothing reads `sdc-questionnaire-cqlInputResources`.
- Libraries must be in the **KnowledgeManager**, which is only filled from resources listed in
  the **app manifest** (`Composition?identifier=cdss`) via `ConfigurationRegistry.addOrUpdate`.
- Alternatives found: `variable` + `x-fhir-query` + `calculatedExpression` (works without CQL),
  and config `PREPOPULATE` action parameters.

### 2.4 EmCare / SMART-CMR (web research)
- `WorldHealthOrganization/smart-emcare-cmr` (Cameroon), `smart-ccc` (global EmCare), built by
  **pyfhirsdc** (SwissTPH; "pyDTMN" was not found — probably pyfhirsdc).
- Pattern: every answer extracted as an Observation (code = data element, encounter, timestamp);
  `emcarebase.cql` (lookup functions, `encounterid` parameter, `GetHistoricObservation(code,
  nbdays)`); `emcarecombineddataelements.cql` = the "huge library", one define per data
  element; per-questionnaire library including it; Questionnaire has `cqf-library`; items use
  `initialExpression` `text/cql-identifier` = define name; Libraries carry CQL **and ELM**,
  `relatedArtifact depends-on`, `id = name = URL tail`.
- The EmCare app calls `fhirOperator.evaluateLibrary(url, patient, expressions,
  Parameters(encounterid))` before rendering — the same thing the fhircore fork does.

### 2.5 Tablet runs (Samsung SM-T725, `org.smartregister.opensrp` 2.2.2 debug + `.qa`)
Driven over adb (screenshots, UI dump, taps, filtered logcat). PIN entered by the user.

| Step | Result on device |
|---|---|
| Unpatched package | CQL path never runs (no `cqf-library`). |
| Hand-patched HTN (cqf-library, name URLs, fixed Helper, no `Calc_next_visit`, weight via history) | `CqlIncludeException: Could not load source for library …` — Library not in KnowledgeManager. |
| + app manifest "Libraries" section (HTN) | Library loads; `Could not resolve call to operator Exists with signature (FHIR.Condition)` — app translator (cql-to-elm 3.12.0) stricter than the local one. |
| + Helper fix re-uploaded | Still the old error: re-login did not refresh the library (**fhircore bug**, §5). *Settings → Sync configuration* did. |
| + missing define | `Could not resolve expression reference 'Calc_next_visit'` — one missing name fails every expression of the form. Stub added. |
| + all defines present | CQL succeeds; `Mismatching question type STRING and answer type date for date_last_vis` → "Unable to load form". |
| + every define cast to its item type | **HTN weight field pre-filled with 63.4** (entered in Diabetes the same session). |
| Clean TRICC export (no hand patches), HTN | Weight shown in HTN (user-verified). |
| Clean export, Diabetes, weight field | Empty — by design: Dedup reads the **current visit** only and Diabetes is the first form. |
| Diabetes with `t_weight` `context=history source=weight_c period=P3M` | Nothing at first: Diabetes Libraries were not in the app manifest. Added (manifest v9). |
| After manifest v9 + sync configuration | CQL now runs for Diabetes, but the "Update participant's history" section (with Weight) disappeared: fhircore applies **null** CQL results (data-absent-reason) as empty `initial` values, which changed `warn_symp`. See §5 item 1. |

Other device findings:
- Start care is a **multi-select** of Interventions, all ticked by default; each project's
  registration fires the same `registration` named event, so the chooser listed identical
  `questionnaire-registration` entries (fixed in TRICC: titles are now "<project> – <Process>").
- The Hypertension form is only offered after Diabetes within the same care session; the
  session creates the Encounter after the first submission (first form has `encounter=null`).
- Form opening with CQL takes ~20 s (on-device CQL→ELM translation every open).

---

## 3. What changed in TRICC (branch `feature/project-level-config`, uncommitted)

| File | Change |
|---|---|
| `tricc_oo/converters/fhir/repeat_helper.py` | Helper CQL valid for cql-to-elm 3.12 (parenthesised sources, CQL query for repeat index, `First(Skip(…))`, comparable sort keys, `is not null`); new `GetHistoryObservationSince` / `GetHistoryObservationValueSince` (history window). |
| `tricc_oo/converters/fhir/cql_value.py` (new) | `ValueAsString/Decimal/Integer/Boolean/Date/Coding` Helper functions; `wrap_cql_for_item_type`; accessor detection. |
| `tricc_oo/converters/fhir/populate_helper.py` | `source` attribute (`populate_source_concept`); ISO duration → CQL window (`cql_lookback_start`); history populate emits `GetHistoryObservationValueSince`. |
| `tricc_oo/converters/fhir/structuremap.py` | Populate nodes are not extracted (were re-recording carried-over values dated today). |
| `tricc_oo/converters/drawio_type_map.py`, `tricc_oo/models/calculate.py` | `source` attribute on `populate` / `input`. |
| `tricc_oo/strategies/output/fhir_form.py` | Library `url` = CQL name (id stays UUID), `relatedArtifact depends-on`, `encounterid` parameter; single `_attach_cql_initial_expression` (type cast, no CQL on `answerOption` items); node references in CQL read via Helper typed accessors instead of bare names; `is true` on text uses `ToBoolean`; XLSForm date-as-days and `format-date` emitted as CQL; undefined `cql-identifier`s removed; orphan pruning keeps referenced defines; unpersisted-populate-concept warning; titles "<project> – <Process>". |
| `tricc_oo/strategies/output/opensrp.py` | `cqf-library` on Questionnaires with CQL; library canonical taken from the Library (`url`). |
| `tests/test_cql_initial_expression.py` (new), `tests/tools/CqlCompile.java` (new) | 14 tests incl. an optional real compile with cql-to-elm (`TRICC_CQL_TRANSLATOR_CP`). |
| `tests/test_populate_input_merge.py`, `tests/test_populate_context.py`, `tests/test_fhir_repeat.py` | New `source`/window/no-extract tests; two expectations updated to the windowed emission; Helper template gets `value_helpers`. |
| `docs/open-srp-export.md`, `docs/tricc-elements.md` | `cqf-library`, canonicals, typing, deployment steps (manifest, *Sync configuration*); populate `source` / history. |
| `feature/20260914-cql-populate-wiring.md` → `feature/20260929-cql-populate-wiring.md` | Renamed (dated), Approved, validation findings, new §4–7. |
| `fix/20260929-cql-initial-expression-on-device.md` (new) | Approved. |

Verification of a clean Hypertension export (`~/Downloads/bp_int (6)/bp_int`) and Diabetes
export (`~/Downloads/dm_int`): Helper and segment libraries **0 errors** with cql-to-elm 3.12.0;
every CQL `initialExpression` define's result type matches its item (HTN 189, Diabetes 84);
no undefined names; no CQL on `answerOption` items.

---

## 4. What changed outside the repo

### Server `https://194.182.171.88/fhir` (app `cdss`) — all with the user's approval
| Resource | Change | Rollback |
|---|---|---|
| `Composition/bb241830-3b97-56d1-830e-7cba5ccdc1f9` (app manifest) | v8: added section "Libraries" (HTN Helper `20d32e83…`, HTN registration `6dc3a855…`). v9: + Diabetes Helper `febcf12b…`, Diabetes registration `70b8247c…`. | PUT `tests/output/session-20260929/manifest-backups/cdss-composition-v7-original.json` (or v8). Keeping v9 is required for CQL prefill to work. |
| HTN `Questionnaire/4cfc07d7…`, `Library/20d32e83…`, `Library/6dc3a855…` | Hand-patched versions uploaded during testing (`tests/output/session-20260929/hand-patched-htn/`); later the user pushed a clean TRICC export. | Re-export + `push-to-fhir.sh`. |
| Diabetes `Questionnaire/246ca3eb…`, `Library/febcf12b…`, `Library/70b8247c…` | Pushed by the user (16:34 UTC) from the edited `dm_int.drawio`. | — |

### Diagrams
- `~/Downloads/dm_int/dm_int.drawio`: node `t_weight` (`nav_input_19`) now has
  `context="history" source="weight_c" period="P3M"`. Backup:
  `~/Downloads/dm_int/dm_int.drawio.bak-20260929`. Nothing else changed.
- `~/Downloads/bp_int (6)/bp_int/bp_int.drawio` (Hypertension): **not** edited yet — it has the
  same `t_weight` node.

### Tablet
- Debug app: app manifest re-synced (*Settings → Sync configuration*); knowledge store now
  holds the 4 libraries. Several test Diabetes submissions for patient "Ruky R"
  (`e28d0317…`), weights 63.4 and 120 kg.

### Local
- Docker container `tricc-hapi-cr` (HAPI + Clinical Reasoning, port 8099) — still running;
  `docker rm -f tricc-hapi-cr` when done.
- `tests/output/session-20260929/` (git-ignored): manifest backups, hand-patched HTN, and the
  test tools (`tools/fhir.sh` authenticated server calls via the HTN `.env`, `ui.sh` adb UI
  helper, `ev.py`/`putlib.py` for `$evaluate` on the local HAPI, `Tr.java`/`Types.java` +
  `cp.txt` = cql-to-elm 3.12.0 classpath from the Gradle cache).

---

## 5. Open issues and next steps

### fhircore (needed)
1. **Null CQL results become empty `initial` values** — `applyCqlExpressionResultsToInitial`
   checks `cqlResultValue != null`, but cqf-fhir returns a null define as a primitive with no
   value plus a `data-absent-reason` extension. Fix (one line, not yet applied):
   ```kotlin
   if (cqlResultValue != null && !cqlResultValue.isEmpty) {
   ```
   Then rebuild/install the debug APK and redo the test (below). This is the current blocker.
2. **Changed Libraries are not re-indexed on login** when the data sync already stored them
   (`_lastUpdated` incremental config fetch). Workaround: *Settings → Sync configuration*.
   Fix in `ConfigurationRegistry` (always re-index `MetadataResource`s, or compare the
   knowledge-store file).
3. **Upstream / keep the CQL prefill feature** (commit `1a5bb44c3`).
4. Optional: evaluate expressions individually (one bad name blanks the form); log successes;
   accept `valueReference` in `cqfLibraryUrls()`; use ELM when shipped (speed).
5. If selects must carry over: set answers in the QuestionnaireResponse after populate instead
   of `initial` (SDK que-11 forbids `initial` with `answerOption`).

### Deployment
- Every project's Libraries must be listed in the app manifest. Consider a TRICC-generated
  wiring script (like `tests/output/demo_prepopulate/wire-demo-into-cdss-manifest.sh`).

### TRICC
- Apply the same `t_weight` edit to `bp_int.drawio` (Hypertension) if it should read the last
  visit too.
- Decide, with the clinical authors, which of the other `t_*` nodes (84 warnings in Diabetes)
  should carry over, from which concept (`source`) and within which `period`.
- Visible "already asked" prefill (`Dedup_*`) is current-visit only by design; a history
  fallback for visible fields was discussed and **not** chosen (it would re-record old values
  as new).
- `enableWhen` is FHIRPath-only: values from other forms can drive skip logic only through a
  hidden CQL-prefilled item.
- Populate references inside other CQL expressions are still untyped (may not compile in
  other projects); run the compile check on cohort_fup / imci exports too (CI step).
- Emit ELM alongside CQL (speed; fhircore docs expect it).
- Longer term: one project-level data-element library (Patrick's "huge library") and a shared
  concept dictionary across projects (carry-over matches by concept code).
- Commit the work (branch decision pending: stay on `feature/project-level-config` or move to
  a dedicated branch). After the on-device acceptance run, set both specs to `Implemented`.

### Acceptance test to redo (after fhircore fix 1)
1. Tablet: *Settings → Sync configuration*, force-stop, open the app (PIN).
2. Start care → tick **only** Diabetes → open → enter weight **120** → save.
3. New care session → only Diabetes → open, **leave weight empty**.
4. Expect the "Update participant's history" section to show and the red "weight … outside the
   expected range of 30-100 kg" warning to appear (it is driven by `weight`, which falls back
   to the carried-over `t_weight` = 120). The visible Weight field stays empty by design.

---

## 6. Reference

Commands (repo root):
```bash
uv run --with pytest python -m pytest tests/ -q --ignore=tests/test_output_walk_reentry.py
# known unrelated: 2 failures in tests/test_not_available_options.py; test_output_walk_reentry.py
# does not import (missing tests.test_nav_ladder_relevance)

TRICC_CQL_TRANSLATOR_CP="$(cat tests/output/session-20260929/tools/cp.txt)" \
  uv run --with pytest python -m pytest tests/test_cql_initial_expression.py -v

uv run python tests/build.py -i ~/Downloads/dm_int/ -o tests/output/ -O OpenSRPStrategy
uv run python tests/build.py -i ~/Downloads/'bp_int (6)'/bp_int/ -o tests/output/ -O OpenSRPStrategy
cd "tests/output/<Project>" && ./push-to-fhir.sh
```

Ids:
| Resource | id |
|---|---|
| App manifest (cdss Composition) | `bb241830-3b97-56d1-830e-7cba5ccdc1f9` |
| HTN Questionnaire / Helper / registration Library | `4cfc07d7-4b3f-5291-9518-f651cb0f45f8` / `20d32e83-7dc8-5f5f-a95b-a846e648231f` / `6dc3a855-2431-55c3-92a9-e3398a2ee830` |
| Diabetes Questionnaire / Helper / registration Library | `246ca3eb-e534-5dba-b075-b71a5c7a4e8d` / `febcf12b-7c6b-5337-963c-9d23cfa72d37` / `70b8247c-0372-5303-9594-37796a7747ea` |
| Test patient | `e28d0317-cc90-4787-adb0-ee5c9844f1e9` ("Ruky R") |

Device knowledge-store check (debug build only):
`adb shell run-as org.smartregister.opensrp ls -l files/km/Library/`

---

## 7. Update 2026-09-30

- **fhircore null-result fix** made on a new branch `fix/cql-initial-null-results` of
  `~/Documents/code/opensrp-fhircore` (uncommitted): a primitive CQL result with no value
  (data-absent-reason) is no longer applied as `initial`. Built
  (`./gradlew :quest:assembleOpensrpDebug`). **Not installed:** the build was signed with
  `~/.config/.android/debug.keystore`, the installed app with `~/.android/debug.keystore`
  (`INSTALL_FAILED_UPDATE_INCOMPATIBLE`). Re-sign with the latter and `adb install -r` keeps the
  app data; uninstalling would wipe un-synced data.
- **Concept alignment across Diabetes and Hypertension.** Names already match between the two
  diagram sets for every shared concept (`weight_c`, `height_c`, `aht_dxs`, …) — nothing to
  rename. 42 `t_*` nodes are actually read by the flows; the rest are declared but unused.
  Applied to both diagrams (backups `*.drawio.bak-20260930`):
  - `t_X` read by a flow, `X` present in either project → `context="history" source="X"`,
    `period` = `P3M` (weight, BMI), `P5Y` (height), `P10Y` (statuses, dates) — to be reviewed
    clinically. Diabetes 28 nodes, Hypertension 29.
  - Status calculates `X` read back by a `t_X` → `concept_type="observation"` (saved at every
    visit). Diabetes 17 calculates, Hypertension 18 (20 nodes).
  - TRICC fix: `concept_type` added to the calculate model (was accepted by the drawio type map
    but crashed the load). Spec §8.
- Clean exports of both: 0 cql-to-elm 3.12 errors, 0 type mismatches (86 / 122 CQL
  expressions); statuses extracted (15/17, 18/18 — the 2 missing are not in the Diabetes
  form); tests 543 pass (+2), same 2 unrelated failures.
- **Blockers** (no source in either project, or not implemented):
  - `sex`, `age` (read by both flows): come from registration / Patient; the Helper's
    `GetPatientValue` returns null (not implemented) and the codes differ (`sex = '1'` vs
    `Patient.gender = 'female'`).
  - `t_ckd`, `t_mi_stat`, `t_stroke_stat`, `t_sterilized`, `t_date_cohort_bsl`, `t_bg_cat`,
    `t_aht_se_conf`, `t_dm_se_conf`: no node computes them in either project (another form,
    e.g. CESI / cohort).
  - Multi-selects (`aht_drugs`, `dm_drugs`, `cesi_type`): saved as one Observation per option,
    so a history read returns one option only. Not wired.
  - Value conventions: flows compare carried values with XLSForm-style codes (`'1'`, `'yes'`);
    booleans come back as `'true'`/`'false'`. Checks such as `"t_warn_symp" = '1'` may not match.

### 7.1 On-device result (2026-09-30, 11:05)

- Fixed fhircore installed (re-signed with `~/.android/debug.keystore`, `adb install -r`, user
  approved; no production data on the tablet). Both projects re-exported and pushed
  (7 resources each; Diabetes Subscriptions 403 as before). Sync configuration refreshed all 4
  libraries.
- **Diabetes, new session, nothing typed:** "Update participant's history" is shown again
  (null-result fix works); the out-of-range weight warning appears — `weight` fell back to
  `t_weight` = 120 kg saved yesterday; "registered as Current Smoker previously" appears
  (`t_smok_stat = '1'` carried). No CQL errors in logcat.
- Not caused by carry-over (already there before): `recent_warn_symp_n` has no condition in the
  export (always shown); `last_hiv_stat_n` inherits the smoker note's condition from the flow and
  shows an empty value (no HIV status ever recorded).
- **Hypertension, new session:** opens without errors, but "Update participant's history" (with
  the weight) is hidden. Its condition is `warn_symp … value = false`, while `warn_symp` is exported
  as a **string** item holding a boolean from `initial_symp` or the carried `t_warn_symp` — a
  FHIRPath typing problem in the export (same class as the `'1'`/`'yes'`/`'true'` convention
  blocker). Needs its own `fix/` spec: type calculates such as `warn_symp` boolean and compare
  carried text values consistently.

### 7.2 Sex / age from the Patient record (2026-09-30)

- Diagrams (backups `*.drawio.bak-20260930-sex`): `("sex" = 'female' or "sex" = '1')` →
  `("sex" = 'female')` (FHIR `Patient.gender` code) in `relevance_2` / `relevance_3` of both
  projects; `sex` and `age` nodes got `context="patient"`.
- TRICC (spec §9): `context=patient` now reads the Patient: `sex`/`gender` → `Helper.PatientGender`
  (`Patient.gender.value`), `age` → `Helper.AgeInYears`, `birthdate`/`dob` → `Helper.PatientBirthDate`;
  typed results (`ToString(AgeInYears)` for the text item). Other names stay null with a warning.
- Verified: both exports 0 errors / 0 type mismatches; local HAPI with a female patient born
  1970: `Calc_sex = female`, `Calc_age = "56"`, `'female'` test true. Tests 547 pass.
- Note: test patient "Ruky R" on the tablet is 5 days old, so the menarche / pregnancy sections
  (age ≥ 10) stay hidden for her regardless; an adult female test patient is needed to see them.

### 7.3 Multi-select carry (2026-09-30)

- Each ticked option is already extracted as its own Observation (`heart_failure`, `stroke`, …);
  the flows read options that way (`t_heart_failure`), already wired.
- Added whole-list carry (spec §10): Helper `GetHistoryObservationCodesSince(code, since)`
  returns all option codes of the latest answer, space-separated; used automatically when a
  history populate's `source` is a select_multiple (or `data_type="select_multiple"`).
  Verified on local HAPI: two drugs on 09-25 + one older → `"metformin glibenclamide"`.
- Diagrams (backups `*.drawio.bak-20260930-multi`): `t_aht_drugs` / `t_dm_drugs` (`P1Y`),
  `t_cesi_type` (`P10Y`) wired in both. No flow reads these three yet, so the export drops them
  as unused; they become active as soon as a condition uses them.
- Tests 551 pass; both exports 0 errors.

### 7.4 `warn_symp` as a boolean (2026-09-30)

- Diagrams (backups `*.drawio.bak-20260930-warn`): every comparison of `warn_symp` /
  `initial_symp` rewritten from XLSForm codes to booleans (`= '1'` → `is true`, `!= '1'` →
  `is not true`, `= '2'` → `is false`, `= ''` → `is null`, `!= ''` → `is not null`) — 78 in
  Diabetes, 63 in Hypertension; the carried text `t_warn_symp` is compared with `= 'true'`;
  `warn_symp = if "initial_symp" is not null then "initial_symp" else ("t_warn_symp" = 'true')`.
- TRICC (fix spec §8): an `if`/`ifs`/`case` calculate whose every branch is boolean is exported as
  a `boolean` item (it stayed `string`, so `value = false` never matched and hid "Update
  participant's history"). A status calculate declared `concept_type="observation"` is saved
  whether true or false (hidden boolean flags were saved only when true, so a resolved status
  would have been read back as active). Option flags keep "only when true".
- Result: `initial_symp`, `warn_symp`, `recent_warn_symp` are boolean items in both forms;
  conditions read `…warn_symp…value = false`; `warn_symp` extracted with its value. Both exports
  0 cql-to-elm errors; tests 553 pass; both projects pushed. **Tablet check pending** (not connected):
  Sync configuration, then open Hypertension — "Update participant's history" should show.

### 7.5 On-device result after the `warn_symp` fix (2026-09-30, 14:03)

- First run: "Update participant's history" shown in Hypertension, but every CQL prefill failed:
  `InvalidOperatorArgument: Expected a list with at most one element` — the new `sex`/`age`
  accessors used the implicit `Patient` singleton, and fhircore passes the patient in its data
  bundle while it is also in the local DB (duplicate). Reproduced on HAPI by passing the patient in
  `data`. Fixed: Helper `PatientRecord = First([Patient])`; `PatientGender` / `PatientBirthDate`
  from it; `AgeInDays/Months/Years = CalculateAgeIn*(PatientBirthDate)`. Guard test added
  (no implicit `Patient.` in the Helper). All 122 HTN expressions evaluate with the duplicate.
- Second run (tablet, PIN 1234): Hypertension opens with no CQL errors; "Update participant's
  history" shown; **"BMI: 20" displayed with Weight and Height empty** — computed from carried
  values. Tests 554 pass; both projects pushed.
