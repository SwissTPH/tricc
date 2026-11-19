# CQL `initialExpression` never fills an item on device

| Field | Value |
|-------|-------|
| **Status** | Approved |
| **Branch target** | `feature/project-level-config` |
| **Related** | `feature/20260929-cql-populate-wiring.md` (Approved — `cqf-library`, `depends-on`, `encounterid` declaration; this fix makes the libraries it points at actually run), `fix/20260914-cql-retrieve-codesystem.md` (Implemented — retrieves match by code), `feature/20260812-intervention-order-and-dedup.md` (the `Dedup_*` defines), `fix/20260821-merge-input-into-populate.md` (populate accessors), `docs/open-srp-export.md` |
| **Origin** | 2026-09-29. Weight recorded in the Diabetes questionnaire never appeared in the Hypertension Followup questionnaire. Reproduced and fixed end to end on a tablet (fhircore 2.2.2 debug build with the CQL `initialExpression` path, cql-to-elm 3.12.0), on a local HAPI with Clinical Reasoning, and against the openSRP server. Approved by the user in session on 2026-09-29 ("apply the tricc changes"). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Issue analysis

### Symptom

A value recorded in one questionnaire (the participant's weight) should appear in the next
questionnaire for the same participant without being asked again. It never does: the
field is empty, in both openSRP builds, whether or not the earlier form was saved in the
same visit.

### What was actually wrong

The value was stored correctly — the Diabetes form writes a `weight_c` Observation with the
patient, the encounter and the date. Everything that should read it back failed, one layer
after another. Each layer hid the next, which is why the problem looked like "nothing
happens" rather than an error:

1. **The app never found the library.** A Questionnaire names its CQL library through
   `cqf-library`; TRICC only emitted `cqlInputResources`, which nothing in fhircore or the
   Android SDK reads. *(Fixed by the related feature spec.)*
2. **The library could not be resolved by name.** The CQL engine takes the library name
   from the end of its canonical URL. TRICC ended the URL with a UUID, while the CQL library
   is called `Hypertension-Followup-registration`.
3. **The shared Helper library did not compile.** Five constructs in it are not valid CQL
   (33 translator errors with the app's translator). Every form includes it, so every CQL
   expression in every TRICC form failed.
4. **One untranslatable define broke the whole form.** `Calc_next_visit` referred to other
   questions by their bare names (`warn_symp`, `bp_status`, …), which are not CQL
   identifiers. CQL compiles a library as a unit, and fhircore evaluates all of a form's
   expressions in one call, so this single define blanked all 227.
5. **Values of the wrong type crashed the form.** Once the CQL ran, it returned a date for a
   text item (`date_last_vis`); the SDK refuses a mismatched answer and the form shows
   "Unable to load form".

### Who is affected

Every openSRP export with at least one CQL `initialExpression` — i.e. any form with a
`populate` node, the automatic "already asked in this visit" prefill, or a calculate that
depends on data outside the form.

### Out of scope

- *Which* concept a populate node reads (the Hypertension form reads `t_weight`, which no
  form records): authoring, handled by the warning in the related feature spec.
- Loading libraries into the app (app manifest), and fhircore not refreshing a changed
  library on re-login: deployment / fhircore, not the exporter.
- Prefilling choice questions that use `answerOption`: the SDK forbids `initial` on those
  (que-11), so they are left unfilled (see §Semantics 5).

---

## Part II — Fix approach

### Evidence

| Check | Before | After |
|---|---|---|
| cql-to-elm 3.12.0 on the generated Helper | 33 errors | 0 |
| HTN segment library | fails (Helper + `Calc_next_visit`) | 0 errors |
| Define result type vs item type (227 items) | 7 non-choice mismatches, 220 untyped | 0 mismatches |
| Tablet: Diabetes weight 63.4 → HTN `weight_c` | empty | **63.4** |

### Semantics

1. **Library canonical ends in the CQL name.** `Library.url = {base_url}/Library/{name}`,
   where `name` is the CQL library identifier. `Library.id` stays the deterministic UUID
   (REST addressing and existing upserts are unchanged). Every reference to a Library by
   canonical — `cqf-library`, `cqlInputResources`, `PlanDefinition.library` — uses
   `Library.url`, never a URL rebuilt from the id.
2. **Helper CQL is valid CQL 1.5** (as accepted by cql-to-elm 3.12.0):
   - a function call used as a query source is parenthesised: `(GetObservations(code)) O`;
   - the repeat-index extension is read with a CQL query, not FHIRPath `.where()`:
     `singleton from (O.extension E where E.url = '…' return FHIRHelpers.ToInteger(E.value as FHIR.integer))`;
   - "Nth most recent" uses `First(Skip((query), n - 1))`, not `skip`/`take`;
   - sorting uses comparable system values: `sort by (effective as FHIR.dateTime).value desc`,
     `sort by recordedDate.value desc`;
   - a single Condition is tested with `is not null`, not `exists()`.
3. **Value conversion functions.** The Helper gains `ValueAsString`, `ValueAsDecimal`,
   `ValueAsInteger`, `ValueAsBoolean`, `ValueAsDate`, `ValueAsCoding`, each taking an
   `Observation.value[x]` choice and returning the system type, or `null` when the stored
   value cannot be that type.
4. **Every `initialExpression` define returns its item's type.** When a define is attached
   to an item:
   - an Observation-value accessor (`GetObservationValue`, `GetRepeatedValue`,
     `GetHistoryObservationValue`, `GetEncounterObservationValue`, `GetEncounterValue`) is
     wrapped in the `ValueAs*` function for the item type (`string`→`ValueAsString`,
     `decimal`→`ValueAsDecimal`, `integer`→`ValueAsInteger`, `boolean`→`ValueAsBoolean`,
     `date`→`ValueAsDate`, `choice`/`open-choice`→`ValueAsCoding`);
   - any other expression is converted only when its type is known and differs from the
     item's: a boolean, number or date (including a literal) into a `string` item takes
     `ToString(…)`, an integer into a `decimal` item `ToDecimal(…)`. An expression of
     unknown type is left as is — CQL has no `ToString(String)`.
5. **No CQL `initialExpression` on items with `answerOption`.** fhircore turns the result
   into `initial`, which the SDK forbids next to `answerOption` (que-11). Such items get no
   CQL `initialExpression` and no define; `answerValueSet` items keep it.
6. **No define references a bare item name.** In CQL, a reference to another node resolves
   to that node's own define (`Calc_<name>`) when one is already recorded in the same
   library; otherwise it reads the value the node recorded through the Helper, converted
   to the node's answer type — `Helper.ValueAsBoolean(Helper.GetObservationValue('<code>'))`
   for a boolean, `ValueAsString` for text **and for choices** (a select is compared with
   option codes, so `bp_status = 'considering'` now type-checks), `Helper.GetConditionValue`
   for a Condition concept. Previously the bare `linkId` produced invalid CQL that disabled
   every other expression in the form. A `Calc_*` define another kept define reads is not
   pruned as an orphan.
   Operators that forwarded XLSForm idioms verbatim are emitted as CQL:
   - `is [not] true/false` on a node read as text converts it with `ToBoolean(String)`
     (CQL has no `String is true`, nor `ToBoolean(Boolean)`);
   - `decimal-date-time(x)` is days since 1970-01-01:
     `ToDecimal(difference in days between @1970-01-01 and ToDate(x))`;
   - `date(n)` of a number is `@1970-01-01 + System.Quantity { value: ToDecimal(Truncate(n)), unit: 'day' }`
     (`ToDate(Decimal)` does not exist); of anything else, `ToDate(x)`;
   - `format-date(x, fmt)` is `ToString(x)` (ISO `yyyy-MM-dd`; CQL has no format argument).
7. **Every requested define exists.** Before a library is assembled, each `text/cql-identifier`
   expression left on the Questionnaire must name a define in that library; one that does
   not is removed from the item with a warning (a missing name fails the whole form on
   device).

8. **Conditional calculates with yes/no branches are boolean items.** *Added 2026-09-30,
   approved by the user in session.* An `if` / `ifs` / `case` calculate whose every value
   branch is boolean — a `true` / `false` literal, a boolean operation (comparison, `and`,
   `is true`, …), or a reference to another calculate that is itself boolean — is exported as a
   `boolean` item. Previously it stayed `string`, so its FHIRPath value never compared equal to
   `true` / `false` (e.g. `warn_symp`, whose `value = false` hid the "Update participant's
   history" section). Authors write such flags as booleans (`is true` / `is false` /
   `is null`), not with XLSForm codes (`'1'`, `'2'`, `''`).

### Code checklist

- [x] `tricc_oo/converters/fhir/repeat_helper.py` — §2 in `cql_helper_repeat_block`.
- [x] `tricc_oo/strategies/output/fhir_form.py`
  - [x] `CQL_HELPER_TEMPLATE` — `exists(GetHistoryCondition…)`, `ValueAs*` (§2, §3);
  - [x] `_make_library_resource` — `url` from `name` (§1);
  - [x] a single `_attach_cql_initial_expression(segment, item, name, expr)` used by
        populate, calculate and dedup: type wrap (§4), `answerOption` skip (§5);
  - [x] `get_tricc_operation_operand` — node references (§6); `is true`, date and
        `format-date` operators (§6);
  - [x] missing-define check before assembly (§7).
- [x] `tricc_oo/strategies/output/opensrp.py` — `_process_library_url` returns `lib["url"]` (§1).
- [x] `docs/open-srp-export.md` — library canonical, value conversion, answerOption rule.

- [x] `_expression_returns_boolean` covers conditionals with boolean branches (§8), test.

### Tests

- Helper CQL contains none of `GetObservations(code) O`, `.where(url`, `skip `, `take `,
  `sort by effective desc`, `exists(GetHistoryCondition`.
- `Library.url` ends in `Library.name`; `id` unchanged (UUID).
- A populate item of type `string` / `decimal` gets `Helper.ValueAsString(…)` /
  `Helper.ValueAsDecimal(…)`; a non-accessor define on a `string` item gets `ToString(…)`.
- A choice item with `answerOption` gets no CQL `initialExpression`.
- A define read by another kept define is not pruned as an orphan.
- Every `cql-identifier` on an exported Questionnaire has a matching define.
- Optional (skipped unless `TRICC_CQL_TRANSLATOR_CP` is set): the generated Helper and a
  segment library compile with zero errors under cql-to-elm.

### Acceptance criteria

1. A clean Hypertension Followup export, with `context=history` on the weight populate
   concept, prefills the weight recorded by the Diabetes form on device — no manual patch.
2. The generated Helper compiles with zero errors under cql-to-elm 3.12.0.
3. `python -m pytest tests/` passes.
