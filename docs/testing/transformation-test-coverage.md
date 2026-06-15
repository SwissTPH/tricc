# TRICC Transformation Logic — Test Coverage Guide

**Goal**: Provide focused, regression-friendly test coverage for the *core transformation engine* of TRICC (the logic that turns a raw graph of nodes/edges into a fully processed model with correct relevance, calculates, inheritance/versioning, diagnosis ordering, etc.).

This document maps the key methods/functions involved in the transformation pipeline to recommended test cases.

**Important principles**:
- One good YAML fixture (or small set of fixtures) can cover **tens of methods** at once.
- The primary vehicle for these tests is the **YAML input strategy** (`YamlStrategy`) + direct inspection of the resulting `TriccProject` / activities after `process_pages` / `execute_linked_process`.
- Existing draw.io-based integration tests and output strategy tests provide secondary coverage.

---

## 1. Transformation Pipeline Overview

The main transformation phases (called after raw input parsing) are:

1. **Graph Linking & Traversal** (`execute_linked_process`, `linking_nodes`, `process_pages`)
2. **Calculate Loading & Expression Generation** (the heart of the engine)
3. **Inheritance / Versioning**
4. **Relevance / Applicability Propagation**
5. **Diagnosis & Proposed Diagnosis Handling**
6. **Helper / Utility Functions** (used pervasively)

The central orchestrator is `load_calculate` (in `visitors/tricc.py`).

---

## 2. Detailed Method Coverage & Recommended Test Cases

### 2.1 Graph Linking, Traversal & Basic Processing

| Method / Function                        | Location                        | Responsibility                              | Key Test Cases (YAML or drawio)                  | Notes |
|------------------------------------------|---------------------------------|---------------------------------------------|--------------------------------------------------|-------|
| `execute_linked_process`                | `strategies/input/base_input_strategy.py` | Top-level orchestration of multi-process / multi-activity graphs | `basic_flow_with_calc.yaml`, real multi-page drawio | Entry point for most tests |
| `linking_nodes`                         | `strategies/input/drawio.py` (reused) | Walks the graph, resolves goto/link, wires prev/next | Any multi-activity or goto test | Critical for cross-activity behavior |
| `process_pages`                         | `strategies/input/drawio.py`    | Triggers calculate loading on a page       | All YAML fixtures                               | — |
| `set_prev_next_node` / `replace_node`   | `visitors/tricc.py`             | Maintains the doubly-linked graph          | Every fixture                                   | Pervasive |
| `walkthrough_goto_node` / `walkthrough_link_out_node` | `strategies/input/drawio.py` | Cross-activity / cross-page navigation     | Tests with `goto`, `link_in/out`                | — |

**Recommended focused test**: A YAML file with 2–3 activities + one `goto` + one `link_out`.

---

### 2.2 Calculate Loading & Expression System (Core Engine)

This is the most important area for regression testing.

| Method / Function                          | Location                  | Responsibility                                      | Recommended Test Cases |
|--------------------------------------------|---------------------------|-----------------------------------------------------|------------------------|
| `load_calculate`                           | `visitors/tricc.py:249`   | Main orchestrator — processes relevance + triggers calculate generation | **All YAML fixtures** (especially those with `calculate` and `rhombus`) |
| `process_reference`                        | `visitors/tricc.py:678`   | Handles remote references, CQL fetching, reference rewriting | YAML with `remote_reference` or complex CQL |
| `generate_calculates`                      | `visitors/tricc.py:533`   | Creates derived calculate nodes from selects, rhombi, etc. | `basic_flow_with_calc.yaml` + select + rhombus cases |
| `get_node_expressions`                     | `visitors/tricc.py:126`   | Builds the full relevance/calculate expression tree | Any fixture with `relevance` or conditional edges |
| `get_node_expression` + term helpers (`get_calculation_terms`, `get_rhombus_terms`, `get_count_terms`, `get_add_terms`, ...) | `visitors/tricc.py` (multiple) | Low-level expression term construction | `minimal_decision.yaml`, count/add heavy clinical diagrams |
| `add_used_calculate` / `get_max_named_version` | `visitors/tricc.py`     | Used during calculate deduplication & reference tracking | Complex calculation graphs |
| `clean_coalesce` (in XLSFormStrategy)      | `strategies/output/xls_form.py` | Expression cleanup for output | Any calculate-heavy fixture + XLS output validation |

**High-value YAML test cases**:
- `basic_flow_with_calc.yaml` (simple calculate)
- `minimal_decision.yaml` (rhombus + reference)
- A new fixture: `inheritance_calculate_chain.yaml` (multiple versions of the same named calculate)

---

### 2.3 Inheritance & Versioning (Critical for Clinical Safety)

| Method / Function                  | Location                  | Responsibility | Recommended Test Cases |
|------------------------------------|---------------------------|----------------|------------------------|
| `set_last_version_false`           | `visitors/tricc.py:148`   | Marks older versions of a node as `last=False` and assigns increasing `version` | **Must-have dedicated test** |
| `get_version_inheritance`          | `visitors/tricc.py:161`   | Merges applicability/relevance/calculate from all previous versions of a node | **High priority** |
| `get_versions` / `version_filter`  | `visitors/tricc.py`       | Finds prior versions scoped by `(name, repeat)` | `test_concept_repeat.py`, inheritance YAML fixtures |
| `get_repeat` / `propagate_activity_repeat` | `models/base.py`, `xml_to_tricc.py` | Concept repeat slot resolution and activity propagation | `test_concept_repeat.py`, `concept_repeat_activity_inherit.yaml` |
| `is_factor_edge_label` / `process_factor_edge` / `get_factor_terms` | `xml_to_tricc.py`, `visitors/tricc.py` | Rhombus/select factor edges → `TriccNodeFactor` (if path then factor else 0) | `test_rhombus_factor_edge.py`, clinical scoring draw.io |
| `get_last_version`                 | `visitors/tricc.py:96`    | Finds the most recent prior version | Same |
| `get_max_version`                  | `visitors/tricc.py:76`    | Internal max version helper | Covered by above |

**Recommended test approach**:
Create YAML fixtures that deliberately create name collisions across activities (e.g. two different "is_adult" calculates or two "final_diagnosis" nodes). This is extremely hard to do reliably with draw.io.

---

### 2.4 Relevance, Applicability & Skip Logic

| Method / Function                          | Location | Responsibility | Test Coverage |
|--------------------------------------------|----------|----------------|---------------|
| `get_applicability_expression`             | `visitors/tricc.py:2158` | Combines activity-level + node-level applicability | YAML with `applicability` at activity root |
| `get_prev_instance_skip_expression`        | `visitors/tricc.py:2168` | Handles multi-instance activity skipping | Multi-instance activity tests |
| `get_process_skip_expression`              | `visitors/tricc.py:2187` | Process-level skip conditions | Multi-process diagrams |
| `get_end_expression`                       | `visitors/tricc.py:2221` | End-of-process expressions | Any fixture with `end` nodes of different processes |
| `get_prev_node_expression`                 | `visitors/tricc.py:2379` | Core relevance builder from prev_nodes | Every fixture with conditional flow |

---

### 2.5 Diagnosis & Proposed Diagnosis

| Method / Function                        | Location | Responsibility | Recommended Tests |
|------------------------------------------|----------|----------------|-------------------|
| `export_proposed_diags` / `export_diags` | `visitors/tricc.py` | Collects diagnosis nodes across the graph | Dedicated diagnosis YAML or drawio |
| `create_determine_diagnosis_activity`    | `visitors/tricc.py:2295` | Builds the synthetic "determine-diagnosis" activity | End-to-end diagnosis ordering test |
| `get_select_accept_reject_options`       | `visitors/tricc.py:2275` | Builds Yes/No/Follow options for diagnostic acceptance | Diagnosis + select_yesno cases |
| `get_diagnostic_node` / `get_accept_diagnostic_node` | ... | Node construction helpers | Covered by above |

---

### 2.6 Important Cross-Cutting Helpers

- `is_ready_to_process` + `is_prev_processed` (loop & readiness detection)
- `stashed_node_func` + `check_stashed_loop` (the stashing mechanism for out-of-order processing)
- `get_activity_wait` / `get_bridge_path` (artificial synchronization nodes)
- `merge_expressions` (used during inheritance)
- `parse_expression` + `transform_cql_to_operation` (expression parsing)
- `add_concept` / data dictionary population (side effect during processing)

These are usually exercised indirectly by the higher-level methods above.

---

## 3. Current Test Assets (as of 2026-06)

### YAML Fixtures (under `tests/data/yaml/`)
- `basic_flow_with_calc.yaml` — Foundational calculate + simple flow
- `select_with_options.yaml` — Option wiring + select nodes
- `minimal_decision.yaml` — Rhombus + reference expression + conditional edges

**Gap**: We currently lack dedicated fixtures for:
- Multi-process + diagnosis ordering
- Complex count/add/rhombus expression trees
- Applicability at activity level

**Now covered** (as of 2026-06):
- `inheritance_versioning_basic.yaml` — basic name collision + versioning
- `inheritance_relevance_merge.yaml` — relevance + expression merging across versions + rhombus using the inherited name
- `concept_repeat_activity_inherit.yaml` — activity-level `repeat` propagation

### Existing Python Tests
- `tests/test_concept_repeat.py` — Concept repeat versioning, skip logic, activity propagation, export suffixes
- `tests/test_fhir_repeat.py` — FHIR repeat extensions and Helper CQL accessors
- `tests/test_rhombus_factor_edge.py` — Integer (+/-) factor labels on rhombus out-edges
- `tests/test_strategies/test_opensrp_strategy.py` — OpenSRP / FHIR pipeline (FSH, PlanDefinition, smoke build)
- Limited deep coverage of `visitors/tricc.py` beyond the fixtures above

---

## 4. Recommended Testing Strategy Going Forward

1. **Primary**: YAML fixtures + small Python test helpers that load a YAML, run the full pipeline, and assert on the resulting node state (`relevance`, `calculates`, `last`, `version`, `prev_nodes`, etc.).
2. **Secondary**: Snapshot-style assertions on the expressions produced after `load_calculate`.
3. **Integration**: Run the same YAML fixtures through full output strategies (XLSForm, FHIR, OpenSRP) when we want to regression-test the entire pipeline.

**Priority order for new YAML fixtures**:
1. Inheritance/versioning scenarios (highest clinical risk)
2. Complex calculate + rhombus expression trees
3. Multi-activity diagnosis + proposed diagnosis flows
4. Activity-level applicability + multi-instance behavior

---

## 5. How to Use This Document

- When adding a new transformation feature or fixing a bug in `visitors/tricc.py`, add or extend a YAML test case and update this page.
- Before releasing, review this matrix to ensure no critical method is only covered by opaque large draw.io files.
- Use this as a checklist when doing major refactors of the expression or inheritance logic.

**Recommended helper**: Use `tests/helpers.py` (`load_yaml_project`, `assert_last_version`, etc.) to keep test code short and readable.

---

**Last updated**: 2026-06 (concept repeat, rhombus factor edges, strategy registry, FHIR repeat helpers)

**Owner**: Core engine maintainers

---

*This document is intended to be living — update it as the transformation logic evolves.*