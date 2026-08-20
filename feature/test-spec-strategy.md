# Feature: TestSpecStrategy — machine-readable form model for automated testing

- **Status:** Approved (2026-08-14) — implemented in `tricc_oo/strategies/test/test_spec.py`
- **Author:** Marco Pereira
- **Created:** 2026-08-14
- **Related:** `docs/testing/transformation-test-coverage.md`

---

## Part I — Business

### Problem

TRICC converts clinical draw.io flows into deployable artifacts (XLSForm for ODK/Enketo and
CHT). Today the only way to know whether the *deployed* form behaves as the clinical author
intended is for a person to open it in a browser and click through it. That check is:

- not repeatable — nobody re-clicks 360 questions after every rebuild;
- not traceable — a defect found in the field cannot be tied back to a diagram element;
- not automatable — CI runs `pytest` on the transformation layer only, never on the artifact.

The consequence is that content regressions (a relevance that stopped firing, an option value
that was renamed, a constraint that now rejects a valid date) are found by health workers
rather than by CI.

### Why the existing outputs are not enough

An external test harness could, in principle, read the generated `.xlsx` and the
`<system>_codesystem.json`. In practice three pieces of information are lost:

1. **Question ↔ answer linkage.** The CodeSystem emits every select option as a *separate flat
   concept* with no reference back to its question — no `answerOption`, no ValueSet
   (`init_valueset()` in `converters/datadictionnary.py` is defined but never called). A
   harness therefore cannot know which values are legal for a given question without
   re-implementing `list_name` matching against the `choices` sheet.
2. **Graph structure.** `edges`, `end` nodes, activity boundaries and diagnosis nodes do not
   survive into the XLSForm. Without them a test generator cannot compute *which answers are
   needed to reach a given clinical outcome*, so every scenario would have to enumerate all
   inputs by hand.
3. **Expression provenance.** The `.xlsx` contains a relevance string but nothing that says
   which concepts it depends on in a machine-readable way, nor which TRICC node it came from.
   This is exactly what a failure report needs in order to say *why* a question was hidden
   instead of merely *that* it was.

### Proposal

Add an output strategy that emits, alongside the normal XLSForm, a single
`<form_id>.form-model.json`: a runtime-agnostic description of the generated form, keyed by
**post-mangling export name** so it aligns exactly with what the deployed form uses.

### Value

- Enables an automated browser test suite over deployed ODK/CHT forms.
- Failure reports become clinically readable ("`other_dis` was hidden; its relevance depends on
  `cesi_type`, which was `["blindness"]`") rather than DOM-level.
- Gives content authors a coverage baseline: one scenario per `end` node and per diagnosis.
- Zero impact on existing outputs — the strategy is additive and opt-in via `-O`.

### Non-goals

- Not a replacement for `YamlStrategy` unit fixtures; this validates the *artifact*, not the
  transformation.
- Does not execute XPath. Expression evaluation stays the runtime's job — the model only
  records expressions and their references.
- Does not deploy anything. Publishing to ODK Central / CHT is the harness's concern.

### Acceptance criteria

1. `python tests/build.py -i tests/data/demo.drawio -o out/ -O XLSFormCHTStrategy -T TestSpecStrategy`
   produces the usual CHT artifacts **byte-identical to a run without `-T`**, plus
   `<form_id>.form-model.json`.
2. Every `exportName` in the model appears in the `survey` sheet `name` column, and vice versa
   for all non-structural rows.
3. Every select node's `options[].value` appears in the `choices` sheet for that `list_name`.
4. `relevanceRefs` for a node is exactly the set of `${...}` names in its relevance.
5. Against a CHT build, contact-summary and input bindings are recorded and `runtime` is `cht`.
6. A duplicate export name is reported in `diagnostics.duplicateNames` rather than silently
   passed through.
7. Running with `-T` but no `-O` change leaves every existing output byte-identical.

---

## Part II — Technical

### A third kind of strategy

TRICC gains a **test strategy** alongside input and output strategies. A test strategy runs
*after* an output strategy and emits non-deployable material derived from that same build.

```
tricc_oo/strategies/test/__init__.py
tricc_oo/strategies/test/base_test_strategy.py   BaseTestStrategy
tricc_oo/strategies/test/test_spec.py            TestSpecStrategy
```

```bash
python tests/build.py -i flow.drawio -o out/ -O XLSFormCHTStrategy -T TestSpecStrategy
```

Three alternatives were considered:

| Option | Verdict |
|---|---|
| Standalone output strategy on `BaseOutPutStrategy` | **Rejected.** Export names are produced *during* export (`_Vv_`, `_Ii_`, `_Rr_`, the `load.` prefix, group-collision counters). A separate pass computes its own names and drifts silently from the deployed form, breaking every selector. |
| Subclass of each output strategy (`TestSpecCHTStrategy(XLSFormCHTStrategy)`) | **Rejected.** Correct names, but requires a twin class per output flavour, and you build with a different `-O` than you deploy with. Nothing enforces that the twin's artifact is identical. |
| Post-export test strategy | **Chosen.** The deployable artifact comes from the output strategy the user actually selected; the model is derived from the same in-memory run, so names cannot drift and the artifact under test is the artifact shipped. |

### Registry

`tricc_oo/strategies/registry.py` gains `TEST_STRATEGIES`, `register_test_strategy(name)`,
`get_test_strategy(name_or_cls)` and `list_test_strategies()`, mirroring the existing pair.
Per `AGENTS.md`, the class must be imported in `tricc_oo/strategies/__init__.py` for the
decorator to run.

### Contract with the output strategy

`BaseTestStrategy.__init__(project, output_path, output_strategy=None)`.

A test strategy **may read**, all optionally:

- `output_strategy.df_survey` — the final `survey` frame
- `output_strategy.df_choice` — the final `choices` frame
- `output_strategy.output_path`, `output_strategy.processes`

It **must not write** to any of them, and must treat everything else on the output strategy as
private. `BaseTestStrategy` exposes these through `survey_frame`, `choice_frame`,
`survey_rows_by_name()` and `choices_by_list()` so the coupling is a named surface rather than
attribute-poking, and degrades to an empty result when `output_strategy` is `None`.

`build.py` wraps the call in a `try/except`: a failing test emitter logs an error but never
invalidates a good build.

### The survey sheet is the source of truth

The model is built **one entry per shipped survey row**, enriched from a node index, rather
than by walking the graph and hoping the walk covers the sheet.

This is not a stylistic choice. By the time an output strategy has finished, `next_nodes` is
largely empty: on a real 990-row ETAT form, a breadth-first walk from the process roots
reaches **14 nodes and 2 edges**. Graph-first construction silently dropped 98% of the form
while reporting no error. `BaseTestStrategy.all_nodes()` therefore unions the walk with every
activity's `nodes` and `calculates` collections, and that index only *enriches* rows.

Entries with no locatable node are marked `hasNode: false` and counted in
`diagnostics.withoutSemantics`. They remain usable — the sheet supplies type, relevance,
constraint and calculation, which is what the runtime executes — they just lack concept
metadata.

By the time a test strategy runs, `get_export_name()` has been called for every exported node
and cached on `node.export_name`, so names in the index match the sheet. That is the property
which makes post-export placement correct rather than merely convenient.

### Options come from the shipped choice list

Node and sheet can disagree, and the sheet wins. A yes/no select carries `true`/`false` on the
node but is written to `choices` as `1`/`0` via `BOOLEAN_MAP`, and the rendered form uses the
latter — on the ETAT form that affected **54 selects**, every one of which would have handed
the harness an option matching no control.

The node still supplies labels and `isNone`. Disagreements beyond that boolean mapping are
recorded in `diagnostics.optionMismatches` rather than silently corrected, because they mean
expressions written against the authored values can never fire. The first real run found one:
`etat_triage_s008` ships a list whose labels are s008's but whose values are `etat.triage.s007.*`.

### Runtime flavour

`runtime` is `"cht"` when the output strategy is `XLSFormCHTStrategy` /
`XLSFormCHTHFStrategy` or a subclass, else `"odk"`. It is inferred from the strategy that
actually ran, not fixed on the test strategy, so the harness picks its driver from what was
really produced.

### Schema (`formModelVersion: 1`)

```jsonc
{
  "formModelVersion": 1,
  "formId": "demo",
  "title": "...",
  "version": "202608141530",
  "strategy": "TestSpecStrategy",
  "outputStrategy": "XLSFormCHTStrategy",  // what actually produced the artifact
  "runtime": "odk",                       // "odk" | "cht", inferred from the above
  "generatedAt": "2026-08-14T15:30:00Z",
  "nodes": [{
    "exportName": "cesi_type",            // selector key — post-mangling
    "conceptCode": "cesi_type",           // CodeSystem code
    "triccType": "select_multiple",
    "odkType": "select_multiple list_cesi_type",
    "dataType": "Coded",                  // CodeSystem property
    "conceptType": "Question",            // CodeSystem property
    "datatype": "string",                 // node-level datatype
    "label": "What is the diagnosis?",
    "group": ["cesi_gr_2"],
    "activity": "act_L9nMK4aCJk...",
    "required": true,
    "readOnly": false,
    "default": null,
    "relevance": "coalesce(${cesi},'')=1",
    "relevanceRefs": ["cesi"],
    "constraint": null,
    "constraintRefs": [],
    "calculation": null,
    "calculationRefs": [],
    "listName": "list_cesi_type",
    "options": [{"value": "...", "label": "...", "isNone": false}],
    "min": null, "max": null,
    "repeat": 1, "instance": 1, "version": 1, "isLastVersion": true,
    "isInput": false, "isCalculate": false, "binding": null
  }],
  "edges":     [{"from": "a", "to": "b", "label": "yes"}],
  "ends":      [{"exportName": "end_referral", "process": "main", "label": "..."}],
  "diagnoses": [{"exportName": "dx_x", "label": "...", "severity": null, "priority": null}],
  "inputs":    [{"exportName": "load_t_ckd", "binding": "../inputs/contact/t_ckd"}],
  "populates": [{"exportName": "x", "binding": "instance('contact-summary')/context/x"}],
  "choices":   {"list_cesi_type": [{"value": "...", "label": "..."}]},
  "diagnostics": {
    "duplicateNames": [],     // ambiguous name-based selectors
    "unresolvedRefs": [],     // expression references nothing that exists
    "missingFromModel": [],   // shipped row absent from the model
    "withoutSemantics": [],   // row present, but no TRICC node located
    "optionMismatches": []    // authored options != shipped choice list
  }
}
```

`*Refs` are computed with `re.findall(r"\$\{([^}]+)\}", expression)`, deduplicated and sorted.
This is exact rather than heuristic: by export time all references have already been
serialised into `${export_name}` form by the XLSForm serializer.

`edges` are read from `node.prev_nodes` / `node.next_nodes` on the observed nodes, restricted
to pairs where both endpoints were exported.

### Failure modes and handling

| Condition | Handling |
|---|---|
| Duplicate export name | recorded in `diagnostics.duplicateNames`; not fatal (parent strategy already only logs it) |
| Node observed but absent from `survey` | `diagnostics.missingFromSurvey` |
| Reference to an unknown name | `diagnostics.unresolvedRefs` |
| Label is a multi-language dict | first configured language, else first value |
| Label is a `TriccOperation` (text injection) | `str()` of the operation |

The model is written even when diagnostics are non-empty, so the harness can assert on them.

### Testing

`tests/test_test_spec_strategy.py`, using the existing YAML fixture helpers
(`tests/helpers.py::load_yaml_project`):

1. Pure helpers: `expression_refs`, `label_text`, `group_path`, `required_flag`.
2. Registry wiring: `-T TestSpecStrategy` resolves, and the class is *not* an output strategy.
3. `select_with_options.yaml` → options captured with the correct `listName`, and every option
   value exists in the shipped `choices` sheet.
4. `minimal_decision.yaml` → `relevanceRefs` matches the `${...}` names; `missingFromSurvey`
   and `missingFromModel` are both empty.
5. `basic_flow_with_calc.yaml` → calculates carry `calculation` + `calculationRefs`.
6. **The `.xlsx` is byte-identical before and after the test strategy runs.**
7. Degraded mode: no output strategy → still emits a model, with empty `choices`.

No Java / ODK Validate dependency is added, so `.github/workflows/tests.yml` needs no change.

### Documentation to update on implementation

- `docs/cli-and-inputs.md` — document `-T` and the test-strategy table.
- `docs/pipeline.md` — note the post-export stage and the additional artifact.
- `docs/testing/transformation-test-coverage.md` — link to the harness repo.
- `AGENTS.md` — mention the third strategy kind next to the node-type checklist.
