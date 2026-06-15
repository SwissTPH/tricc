# FHIR Output Strategy Remediation Plan

> **2026-06 update:** Significant remediation has landed on `develop` since this plan was
> written — DEMO FHIR now produces Questionnaires, CQL libraries, FML mappings, ValueSets,
> repeat-aware Helper CQL, registered `FHIRStrategy` / `OpenSRPStrategy`, and passing unit
> tests. Treat the executive summary below as **historical context**; see
> [OpenSRP / FHIR-Core Export](../open-srp-export.md) and [FHIRcore.md](../desing/FHIRcore.md)
> for current behaviour. Remaining gaps (full StructureMap extraction, golden CQL validation,
> complete Binary/Composition packaging) are still tracked in the checklist sections.

**Date**: 2026-05-26  
**Context**: Review of `tricc_oo` FHIR outstrategy (`FHIRStrategy` + `OpenSRPStrategy` + `converters/fhir/*`) on `feature/fhir` branch.  
**Trigger**: User observed that "DEMO FHIR" launch config produces a (partial) Questionnaire + crude `.map` file, but nothing else (CQL, Libraries, proper StructureMaps, ValueSets, full layout, etc.).  
**Source Review**: Structured findings in `/tmp/grok-review-7cb278d4.md` (15 issues) + summary.

## Executive Summary

The current `FHIRStrategy` (and its `OpenSRPStrategy` subclass) delivers **only a very basic, flat Questionnaire** (with some `enableWhenExpression` FHIRPath via the relevance path) plus a naive FML stub. This matches what the user sees on DEMO runs via `.vscode/launch.json` ("DEMO FHIR" and "Matrix: Demo + FHIR" configurations).

All the ambitious claims in the class docstring, `OpenSRPStrategy` docstring, `docs/desing/FHIRcore.md` (v4), and `docs/open-srp-export.md` are **not yet implemented**:
- Real CQL Library generation + `calculatedExpression` / `initialExpression` wiring
- Proper StructureMap / FLM resources driven by `concept_type`
- ValueSets, Binaries (images + config), full Composition manifest
- Correct nested Questionnaire items using the (already-written but mostly-unused) mappers
- `validate()`, robust error handling, complete export layout + FSH for everything

**Root cause of partial success**: 
- `BaseOutPutStrategy` provides `process_*` methods that call the `generate_*` hooks via `stashed_node_func`.
- `FHIRStrategy` implements minimal `generate_base`, `generate_relevance`, `generate_calculate` (stub), `generate_export`, and `export`.
- `@abc.abstractmethod` markers on `validate` etc. are **decorative only** (base class does not inherit from `abc.ABC`).
- No code path ever populates `self.cql_libraries`, `self.structuremaps`, `self.valuesets`, `self.binaries`, or proper Library/StructureMap dicts.
- Mapper functions (`questionnaire_item_mapper`, `concept_mapper`) are imported but almost completely bypassed.

**Good news**: The visitor + hook architecture is sound. The converters are well-written and ready to be wired in. Basic relevance → FHIRPath already works on the DEMO graph. This gives a solid foundation for incremental delivery.

**Goal of this plan**: Turn the current skeleton into a working, spec-compliant FHIR SDC + CQL + extraction pipeline that produces a usable openSRP/fhircore package for real TRICC graphs, while fixing all high-severity issues from the review.

## Phased Remediation Plan

### Phase 0: Quick Wins & Hardening (1–2 days, low risk)
Make the existing path robust and visible so developers don't get silent incomplete output.

1. **Fix `_form_id` handling** (critical for OpenSRPStrategy)
   - File: `tricc_oo/strategies/output/fhir_form.py`
   - In `export()` (or better, early in `execute()` after reading `start_pages["main"]`), set `self._form_id`.
   - Make `OpenSRPStrategy.export` defensive (or call a parent helper first).

2. **Implement a real `validate(self)` in `FHIRStrategy`** (and call it from OpenSRP)
   - Minimum: presence checks on populated structures, warnings for empty questionnaires / missing libraries, basic linkId uniqueness.
   - Later: integrate `fhir.resources` or simple JSON Schema checks.
   - File: `tricc_oo/strategies/output/fhir_form.py` + update `opensrp.py:143`.

3. **Make `BaseOutPutStrategy` properly abstract**
   - Change `class BaseOutPutStrategy:` → `class BaseOutPutStrategy(abc.ABC):`
   - This will surface missing `validate` / `export` etc. at instantiation time (prevents silent partial runs).
   - File: `tricc_oo/strategies/output/base_output_strategy.py`

4. **Improve logging + early visibility**
   - At end of `FHIRStrategy.export` and `validate`, log counts: `# Questionnaires`, `# CQL defines`, `# Libraries`, etc.
   - Add a clear "FHIR export incomplete: only basic Questionnaire + FML stubs generated" warning if `cql_libraries` or `structuremaps` are empty.
   - File: `fhir_form.py`

5. **Remove obvious dead code / duplication**
   - Duplicate import of `get_export_name`.
   - Unused `cur_group`, `get_question_link`, `get_answer_value`, several fhirpath_* duplicates.
   - File: `fhir_form.py`

6. **Add a smoke test that actually runs the pipeline**
   - Extend `tests/test_strategies/test_opensrp_strategy.py` or add `tests/test_fhir_strategy.py`.
   - Load `tests/data/demo.drawio`, run `FHIRStrategy` + `OpenSRPStrategy` (with temp output dir), assert Questionnaire keys exist and at least one enableWhenExpression was generated.

**Success criteria**: "DEMO FHIR" launch produces the Questionnaire + `.map` **without surprises**, logs clearly state what is missing, and `_form_id` no longer crashes OpenSRP path. `validate()` runs without error.

### Phase 1: Questionnaire Completeness & Mapper Integration (4–7 days)
Make the Questionnaire output correct and use the code that already exists in the converters.

1. **Rewrite `generate_base` (and supporting item builders) to use the mappers**
   - Use `get_fhir_item_type`, `is_repeating`, `should_skip`, `is_hidden`, `is_calculate_type`, `get_display_type_extensions`.
   - Properly set `repeats`, `required`, `readOnly`, `answerValueSet` (when `use_value_sets=True`) vs `answerOption`.
   - Handle `TriccNodeDisplayCalculateBase` + hidden correctly via `build_hidden_extension`.
   - File: `fhir_form.py` (major refactor of `generate_base` + helpers).

2. **Support nesting / groups / activities**
   - Track `cur_group` (or a stack) properly.
   - When encountering activity_start / page / group-like nodes, create `type: "group"` items and recurse children under `.item`.
   - Use `get_process` (already imported) consistently for segmentation.
   - Align "segment" vs "process" terminology.

3. **Wire relevance & calculate through the mapper builders**
   - `generate_relevance`: call `build_enable_when_expression(...)` instead of manual dicts (or keep thin wrapper).
   - Fix `generate_calculate` signature (currently passes `(item, node)` to a function expecting `(cql_expr, library_name)`).
   - Decide CQL vs FHIRPath strategy per node type (per spec and mapper comments).

4. **Fix / complete the FHIRPath expression layer** (high priority because it already produces output)
   - Address all bugs from review: duplicate method definitions, `list.join`, unbalanced parens, double-underscore typo, inconsistent `_wrap_operand_if_needed` application.
   - Make wrapping logic (and `LIST_CONTEXT_OPERATORS`) applied uniformly.
   - Add unit tests for every operator + list vs scalar cases using real `TriccOperation` objects.
   - Files: `fhir_form.py` (expression methods 439–990), `tests/test_fhir_expressions.py` (new).

5. **Media, hints, choice orientation, itemControl, etc.**
   - Use the display_type → extension logic from the mapper.
   - Handle image nodes → `itemMedia` extension + Binary references (ties into Phase 4).

**Dependencies**: Phase 0.  
**Success**: On DEMO (and combacal/etat), the generated Questionnaire is nested where appropriate, uses correct item types + repeats + extensions, passes basic FHIR SDC validation, and the mapper code is actually exercised (not dead).

### Phase 2: CQL + Library Generation (the biggest value gap, 7–12 days)
This is the core missing feature for calculations, relevance that is too complex for FHIRPath, and `$populate` / `calculatedExpression`.

**Refined CQL Architecture (confirmed during implementation)**:
- One **Helper** library responsible for data access via FHIR resources (Observation/Condition/etc.) using concept names/codes.
- Thin **per-process** libraries that mainly contain named `define` statements (delegating to the Helper where possible).
- In the Questionnaire, use **simple define names** only in `calculatedExpression` / `initialExpression` (no library prefix).
- The Questionnaire declares its library/libraries at the top level.
- Avoid embedding raw questionnaire answer paths in CQL.

1. **Build CQL define population during `process_calculate` / `generate_calculate`**
   - Walk calculate nodes (and complex relevance) using `convert_expression_to_cql`.
   - Create named defines (e.g. `define "demo_happy_score": ...`).
   - Store in `self.cql_defines[segment]`.
   - Use the `CQL_HELPER_TEMPLATE` + `CQL_CHILD_TEMPLATE` (currently dead).

2. **Generate proper `Library` FHIR resources**
   - One helper library + one per process/Questionnaire.
   - Embed the CQL as `content[0].data` (base64) + `contentType: text/cql`.
   - Set correct `type`, `relatedArtifact`, profiles.
   - Populate `self.cql_libraries` (or a new `self.libraries` dict of FHIR dicts) and also write `.cql` source files for debugging.

3. **Wire the libraries into Questionnaires**
   - Add `initialExpression` / `calculatedExpression` using `build_initial_expression` / `build_calculated_expression` (with library name qualification) for the right nodes.
   - For OpenSRP: ensure `cqlInputResources` extension points at the Libraries.

4. **Expression fidelity & testing**
   - Align CQL output with what openSRP/fhircore + CQL engine expect (FHIRHelpers, Patient context, etc.).
   - Add golden-file or assertion tests for generated CQL on demo graph.

**Dependencies**: Phase 1 (need solid expression converter + node classification).  
**Success**: DEMO run produces at least one `.cql` file + Library JSON with real defines derived from the graph's calculate / count / add nodes. Questionnaires reference them.

### Phase 3: StructureMap / Data Extraction + Terminology (5–8 days)
Drive export by `concept_type` (the whole point of the `concept_mapper`).

1. **Implement `generate_export` properly**
   - Use `get_fhir_resource(concept_type, tricc_type)` and `get_fhir_value_field`.
   - Build real `StructureMap` dicts (or at least richer FML) per target resource (Observation, Condition, etc.).
   - Populate `self.structuremaps`, `self.fml_mappings` (as proper objects), and later `self.valuesets`.

2. **ValueSet generation from TRICC CodeSystems**
   - When `use_value_sets=True`, emit ValueSet resources + reference them from choice items.
   - Reuse existing CodeSystem output where possible.

3. **Integrate with existing terminology tools**
   - `converters/codesystem_to_ocl.py`, OCL models, etc.

**Dependencies**: Some overlap with Phase 1 (concept_type handling on nodes).  
**Success**: Generated StructureMap JSONs (and .map FML) that are meaningful, not just node-name passthrough. Composition references them.

### Phase 4: Full Packaging, Binaries, FSH, Layout, OpenSRP Polish (4–7 days)
Close the gap to a usable fhircore package.

1. **Implement Binary handling** (images from the drawio + the config Binary)
   - Populate `self.binaries` during graph walk.
   - `generate_binary_config` already exists in OpenSRP — wire it.

2. **Complete export writers in both strategies**
   - Create the documented subdirectories (`questionnaire/`, `library/`, `structure-map/`, `ValueSet/`, `binary/`, `fsh/`).
   - Move / extend the flat writes in `FHIRStrategy.export`.
   - Ensure OpenSRP calls super at the right time and augments.

3. **Guarantee FSH for every resource**
   - Use `resource_to_fsh` (already imported in OpenSRP) for everything, including in parent.

4. **Finish OpenSRP-specific generators**
   - Ensure PlanDefinition, Composition, wiring, and manifest are complete and reference everything produced by parent.

**Dependencies**: Phases 2–3 (need the resources to write).  
**Success**: A `demo_fhir/` (or `matrix/demo_fhir/`) directory that looks like a real openSRP package and can be loaded by fhircore tooling (even if some downstream validation fails).

### Phase 5: Validation, Robustness, Tests, Documentation (ongoing + 3–5 days dedicated)
1. **Real `validate()` implementations** (FHIR + OpenSRP) — structural, cross-reference, and (optionally) against FHIR IGs.
2. **Error handling & graceful degradation** in expression converters (many `NotImplementedError` today).
3. **Comprehensive test suite**
   - Unit: every operator, mapper function, FSH serializer edge case.
   - Integration: full pipeline on demo + one more complex diagram (combacal or etat) for both `FHIRStrategy` and `OpenSRPStrategy`.
   - Golden outputs or snapshot testing for the generated JSON/FSH/CQL (with review on changes).
4. **Update documentation**
   - `docs/desing/FHIRcore.md` — mark implemented items, note deviations.
   - `docs/tricc-elements.md` — ensure mapping table matches reality.
   - `docs/open-srp-export.md` and README examples for `-O FHIRStrategy` / `OpenSRPStrategy`.
   - AGENTS.md quick reference if needed.
5. **CI / quality**
   - Add FHIR matrix job to GitHub workflows if not present.
   - Run `flake8`, type checks (if mypy is used), and the new tests on every PR touching `tricc_oo/strategies/output/fhir*` or `converters/fhir/`.
6. **Performance / scaling notes** (large graphs, many activities).

**Dependencies**: All prior phases.  
**Success**: `python -m pytest tests/test_strategies/ -k fhir -v` is green. A full DEMO + Combacal FHIR run completes with rich output and clear validation logs. No silent partial results.

## Cross-Cutting Concerns & Risks

- **Expression system ownership**: Currently duplicated logic lives inside the strategy. Consider moving robust CQL/FHIRPath emitters to `converters/` (alongside `cql_to_operation.py`, `xpath_to_cql.py`) so other strategies or tools can reuse them.
- **Visitor / graph model fidelity**: Heavy reliance on `stashed_node_func` + `get_process`. Any changes to activity/segment logic must be coordinated.
- **Spec vs. reality**: The v4 spec is ambitious (full `$populate`, CQL everywhere, OCL long-term). Phase the work and update the spec doc as you go rather than letting it drift further.
- **Testing surface**: Real TRICC graphs have complex relevance/calculate/operations. Invest early in expression test fixtures.
- **Downstream consumers**: Changes here affect OpenSRP/fhircore users. Coordinate with them on breaking changes to generated resource shapes or naming.
- **Effort estimate (rough)**: 4–7 weeks for one focused developer to reach a solid v1 (Phases 0–4 + core tests). Can be parallelized (e.g. Questionnaire + expressions in parallel with CQL design).
- **Quick validation loop**: After each phase, run the "DEMO FHIR" and "Matrix: Demo + FHIR" launch configs + inspect `tests/output/...` + run any new tests.

## Recommended Next Steps (Immediate)

1. Apply Phase 0 items (especially `_form_id`, proper ABC base, `validate` stub + logging). This can be done in 1 PR.
2. Create the new test file `tests/test_fhir_strategy.py` with a pipeline smoke test (even if it only asserts "no crash + Questionnaire present" today).
3. Schedule a short design session on the CQL population approach (how to name defines, where to attach expressions, CQL vs FHIRPath decision table).
4. Wire the existing mappers in a small spike for one node type (e.g. select_one with display_type) to prove the path.

## Traceability to Review Issues

All 15 issues from the structured review map into the phases above:
- #1, #4, #6, #8, #9, #10 (core missing pieces + dead code) → Phases 0–4
- #2, #5, #7 (expression & calculate bugs) → Phase 1 + Phase 2
- #3 (`_form_id`) → Phase 0
- #11–15 (style, tests, integration gaps) → Phase 0 + Phase 5

Once the plan is executed, re-run the reviewer (or a fresh `/review --branch feature/fhir` focused on the FHIR files) to confirm closure.

---

**Owner**: (to be assigned)  
**Reviewers**: Original reviewer subagent + domain experts for CQL/FHIR SDC/openSRP.  
**Tracking**: Create GitHub issues or a project board with one epic per phase. Link back to this document.

This plan is actionable, respects the existing architecture, delivers incremental value (starting from the Questionnaire the user already sees), and directly addresses every major gap identified in the code review.