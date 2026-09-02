# Choice `=` code literal only works on a *direct* select reference

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | `fix/20260824-fhirpath-choice-equality.md`, `fix/20260824-fhirpath-select-multiple-membership.md`, `fix/20260817-choice-membership-and-group-relevance.md`, `feature/20260819-boolean-choice-orientation.md`, `feature/20260821-get-repeated-value-operation.md` |
| **Strategy** | `FHIRStrategy` / `OpenSRPStrategy` |
| **Approval** | 2026-09-02 conversation (user: “CQL to FHIRPath not working for select, ex. `"FUP" = 'option_1'` won’t handle `"FUP"` as a select”, then “implement the fix”). |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

This file lives under `fix/` (issue analysis + fix approach), not `feature/` (new capability).

---

# Part I — Issue analysis

## 1. Symptom

An author writes CQL equality against a select and the exported expression never
becomes true, so the gated question never appears / the calculate never fires:

```
"FUP" = 'option_1'
```

`fix/20260824-fhirpath-choice-equality.md` fixed this for the *direct* case, and
that case is verified working on current `feature/segment`:

```
%resource.item.where(linkId='start').item.where(linkId='FUP')
  .answer.where($this.value.code = 'option_1').exists()      ✅
```

It still fails whenever the select operand reaches `EQUAL` **indirectly**, or when
the select is exported as something other than a `choice` item. Reproduced with
`tests/build.py -I YamlStrategy -O FHIRStrategy` on the current tree:

| Authored CQL | Item shape | Exported (broken) |
|---|---|---|
| `"FUPYN" = 'yes'` | `select_yesno` → native `boolean` item | `…answer.where($this.exists()).value = 'yes'` |
| `"FUPYN" != 'no'` | same | `…value != 'no'` (always true) |
| `'yes' in "FUPYN"` (SELECTED) | same | `(…value = 'yes')` |
| `GetRepeatedValue('FUP') = 'option_1'` | `select_one` read back by slot | `…where(linkId='FUP').answer = 'option_1'` |
| `last_fup = 'option_1'` where `last_fup` is `GetRepeatedValue('FUP')` | hidden calculate item, type `string` | `…linkId='last_fup').answer.where($this.exists()).value = 'option_1'` |
| any select equality that falls back to CQL (`initialExpression`) | Observation `value[x]` is a `CodeableConcept` (see the extract map) | `Helper.GetObservationValue('FUP') = 'option_1'` |

In every row the left-hand side yields a boolean, a whole `answer` element, or a
`CodeableConcept`, and the right-hand side is a bare code string — the comparison
is empty/false for every answer the clinician can give.

## 2. Why it happens

Choice awareness is decided in one place, `_is_choice_reference`, and only from
two facts: the operand *is* a `TriccNodeSelect` instance, or the operand’s
`linkId` resolves to a Questionnaire item of type `choice` / `open-choice`.

- A **yes/no select** is deliberately *not* a choice: it is exported as a native
  `boolean` item (`feature/20260819-boolean-choice-orientation.md`), so
  `_is_boolean_item_reference` short-circuits `_is_choice_reference` and the
  operand is wrapped as `.value`. Nothing maps the authored option code
  (`'yes'` / `'no'` / `'1'` / `'0'`) to `true` / `false`:
  `_yesno_option_boolean_literal` is only consulted when the operand is a
  `TriccNodeSelectOption` **object**, and CQL parses `'yes'` to a `TriccStatic`
  string (`cql_to_operation.visitStringLiteral`).
- A **`TriccOperation` operand** (`GET_REPEATED_VALUE`, `GET_INHERITED_VALUE`, …)
  is excluded by `_should_wrap_first`, so no `.value.code` suffix is added and
  `_rewrite_choice_code_equality` (which matches on a trailing `.value.code = '…'`)
  has nothing to rewrite. The comparison lands on the raw `.answer` collection.
- A **calculate that carries a select value** is exported as a `string` item, so
  the codedness of the value it copied is lost for any later reference to it.
- The **CQL emitters** (`tricc_operation_equal`, `tricc_operation_selected`,
  `tricc_operation_contains`) have no coded handling at all: they compare
  `Helper.GetObservationValue(code)` — a `CodeableConcept`, since the extract map
  writes `answer.value : Coding -> tgt.value = create('CodeableConcept')` — to a
  CQL string. This path is taken whenever `_collect_calculate_references` finds no
  reference captured in the same Questionnaire (loaded/populate values,
  cross-segment references).

Evidence that this is not theoretical: the checked-in real export snapshot
`tricc_oo/strategies/output/templates/opensrp/cohort_fup_fhir_output/` contains
`…linkId='symp_yn').answer.where($this.exists()).value = 'yes'` and
`…linkId='cervical_cancer_tx')…value = 'yes'`, both `boolean` items.

## 3. What authors and implementers should see after the fix

Writing `question = option` (or `option in question`) in CQL works for every
select, whatever the exporter renders it as: a yes/no toggle, a choice list, a
value read back with `GetRepeatedValue`, a calculate that carries a coded value,
or a value only reachable through CQL. No diagram change.

## 4. Out of scope

- Comparing two select answers to each other.
- Making a calculate that carries a coded value keep a `choice`/coding type in
  the Questionnaire (worth its own spec; here we only need equality to work).
- Non-FHIR strategies (XLSForm/CHT already use `selected()`).

---

# Part II — Fix approach

## 5. Formal rules

**R1 — yes/no code literals become boolean literals.** In `EQUAL`, `NOT_EQUAL`,
`SELECTED` and `CONTAINS`, when one operand is a yes/no boolean item
(`_is_boolean_item_reference`) and the other is a code literal whose lowercased
value is in `_YESNO_TRUE_MARKERS` / `_YESNO_FALSE_MARKERS`, emit the unquoted
`true` / `false` literal instead of the quoted code. `SELECTED` / `CONTAINS` on a
boolean item stay a scalar `= true` / `= false` comparison, never `.value.code`
membership.

**R2 — choice-ness follows the operation, not just the reference.** Choice
detection walks a `TriccOperation` operand to the reference it reads
(`GET_REPEATED_VALUE`, `GET_INHERITED_VALUE`, `PARENTHESIS`, `COALESCE`,
`GET_HISTORY_VALUE` — first/any coded leaf), so an equality against such an
operand emits the R1/membership form of `fix/20260824-fhirpath-choice-equality.md`
on the answer collection it produced.

**R3 — CQL coded equality uses codes, not strings.** *Deferred, not
implemented — see §8.* In CQL a select answer is an `Observation.value[x]`
CodeableConcept, so comparing the Helper accessor with a code string is never
true. The correct emission has to be validated against the CQL translator
OpenSRP uses before it ships: a Library that fails to translate takes the whole
form down, which is worse than the wrong-but-inert comparison. Only the yes/no
part of R1 applies to the CQL path (a yes/no answer is a `valueBoolean`).

**R3b — membership needs an answer collection.** The membership form may only be
applied to an operand expression that still yields `…answer` elements. An
operand already reduced to a code — `COALESCE` unions `.value.code` members and
takes `.first()` — keeps a plain `=`; `.first().where($this.value.code = '…')`
on a code string is always false. The inheritance union
(`(a.answer | b.answer).where($this.exists()).first().value.code`) *is* an
answer collection under its `.value.code` tail, and keeps the membership form it
already had.

**R4 — non-choice equality unchanged.** Integer / decimal / date / string items
keep `.where($this.exists()).value = …` and the numeric handling of
`fix/20260824-fhirpath-numeric-arithmetic.md`.

## 6. Code checklist

All in `tricc_oo/strategies/output/fhir_form.py` unless stated otherwise.

- [x] `_value_source_reference`: resolve a value-forwarding operand
      (`PARENTHESIS`, `COALESCE`, `GET_REPEATED_VALUE`, `GET_INHERITED_VALUE`,
      `GET_HISTORY_VALUE`) to the item it reads; called first by
      `_is_choice_reference` and `_is_boolean_item_reference` (R2).
- [x] `_code_literal_operand` / `_yesno_boolean_literal` / `_boolean_item_operands`:
      map an authored yes/no code to a boolean literal, either operand order (R1).
- [x] `_coded_operand_pair`: pick out `(choice operand, code literal)`, and
      require the operand to still be an `…answer` collection (`_ANSWER_COLLECTION`)
      so a code-scalar operand keeps plain `=` (R3b).
- [x] `_fhirpath_equality` behind `tricc_operation_fhirpath_equal` / `_not_equal`:
      coded membership before the scalar wrap, so an operation operand no longer
      depends on `_should_wrap_first` / the `_rewrite_choice_code_equality` regex
      (which stays as the fallback for the shapes it already covered).
- [x] `tricc_operation_fhirpath_selected`: yes/no literal mapping on the boolean
      branch.
- [x] `_cql_equality` behind `tricc_operation_equal` / `_not_equal`, and
      `tricc_operation_selected`: yes/no literal mapping only.
- [ ] R3 (CQL CodeableConcept membership) — deferred, see §8.
- [x] Tests: `tests/test_strategies/test_fhir_select_operand_equality.py`
      (unit per rule + end-to-end) and
      `tests/data/yaml/select_operand_equality.yaml`.
- [x] Docs: this file + `docs/open-srp-export.md` (choice / yes-no equality).

## 7. Acceptance

1. `EQUAL(FUPYN, 'yes')` on a `select_yesno` emits `…value = true`, and never
   `value = 'yes'`; `NOT_EQUAL(FUPYN, 'no')` emits `…value != false` (or the
   equivalent `= true`).
2. `'yes' in FUPYN` emits the same scalar boolean comparison, not
   `.answer.where($this.value.code = 'yes')`.
3. `EQUAL(GetRepeatedValue('FUP'), 'option_1')` emits
   `….answer.where($this.value.code = 'option_1').exists()`.
4. `EQUAL(FUP, 'option_1')` on a `select_one` / `select_multiple` keeps the
   behaviour of `fix/20260824-fhirpath-choice-equality.md` (no regression).
5. ~~A select equality that falls back to CQL emits a code comparison over the
   `CodeableConcept`~~ — deferred (§8). CQL keeps its previous output apart from
   the yes/no boolean literal.
6. `EQUAL(age, 5)` and string equality are unchanged.
7. `python -m pytest tests/` passes.
8. `COALESCE` / inheritance-union equality is byte-identical to before the fix.
9. Exporting `tests/data/demo.drawio`, `etat.drawio` and `combacal.drawio` with
   `FHIRStrategy` gives Questionnaires byte-identical to pre-fix output (none of
   them authors the affected shapes), and 100 of 1008 enumerated
   operand × literal × operator shapes change — all of them intended.

1-4 and 6-9 hold: 406 tests pass (386 before, 20 added).

## 8. Deferred / still open

**CQL coded equality (R3).** A first revision emitted
`exists((<value> as FHIR.CodeableConcept).coding Cd where Cd.code = '<code>')`
from the CQL `equal` / `not_equal` / `selected` / `contains` emitters. It was
backed out before landing: it rewrote 260 of the enumerated shapes, none of the
repo's sample forms exercise it (so nothing here proves the emitted CQL
translates), and an untranslatable Library breaks the form at populate time. To
land it, validate the emission against the translator OpenSRP uses — the
`compile-structuremap.sh` toolchain in `templates/opensrp/` is the natural place
to add a CQL translate step — then re-enable it with the tests in
`TestCqlCodedEqualityIsLeftAlone` inverted.

**`SELECTED` on a code-scalar operand.** `SELECTED(COALESCE(v2, v1), 'code')`
emits `….first().where($this.value.code = 'code').exists()`, which is always
false for the same reason as R3b. This predates the fix (`_choice_membership_expr`
only strips a trailing `.value.code`) and is left as-is here; R3b guards only
the equality path.

**Calculate-carried choice values.**

`<calculate> = 'option_1'`, where the calculate carries a select's value
(`last_fup: GetRepeatedValue('FUP')`), still exports
`…linkId='last_fup').answer.where($this.exists()).value = 'option_1'`. The
reference *is* the calculate item, and that item is typed `string` with a
`calculatedExpression` of `…linkId='FUP').answer` — so nothing at the reference
says "coded". Fixing it means giving such a calculate a coded item type (and
matching extraction), which is §4 out-of-scope here. Authors can compare the
select directly, or use `GetRepeatedValue('FUP') = 'option_1'` inline, both of
which this fix handles.
