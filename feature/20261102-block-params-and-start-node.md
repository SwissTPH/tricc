# Block and activity parameters, static decisions, dead-concept handling and extension points

| Field             | Value |
|-------------------|-------|
| **Status**        | Rev 2 approved 2026-10-29 (Patrick); **phases 1–5 Implemented 2026-11-03** (blocks inlined at linking, the interim of §18.7). Phases 6–9 not started. **Rev 3 (§18, closed blocks) Draft, 2026-11-02** |
| **Branch target** | TBD |
| **Related**       | `feature/goto-snippet-injection.md` (the `instance = -1` mechanism this generalizes and replaces), `feature/concept-repeat.md` (`repeat = -1` local-only capture, which snippet injection relies on), `feature/advanced-merge-calc.md` (same-name versioning after multi-inject), `../tricc_frontend/feature/20260825-guided-authoring.md` (the authoring surface that consumes this), `../tricc_frontend/feature/20261028-blocks-tab-and-params.md` (frontend counterpart of rev 2) |
| **Origin**        | Drafted during `tricc_frontend` v1 planning, 2026-08-25. Rev 2 extends it with call-site-defined parameters on processes, static decisions, dead-concept resolution and extension points. |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

## What changed in rev 2

| # | Change | Where |
|---|--------|-------|
| 1 | Parameters behave like **function parameters**: any activity (process or page) or block can have them; values come from `args` on a `block`/`goto` or, at the root, from the **intervention's `args`**; an unbound parameter is **inherited** from the caller, and a value set at a call overrides it only below that call. The list is **computed** from the call graph and saved the same as declared entries. Declaration moves from a `block_start` attribute to a page-level `params` section, surfaced in draw.io as a `parameters` node | §2, §3 |
| 2 | New primitive types `boolean` and `choice`; primitive parameters are registered as concepts in the calculate data dictionary | §2, §5 |
| 3 | **Static decisions**: decision nodes whose logic is resolved at import from parameters, pruning unused paths | §7 |
| 4 | **Dead-concept detection**: concepts referenced downstream but no longer produced in the exported scope are pulled from the project dictionary as generated inputs; processes/blocks can declare **prerequisites** | §8 |
| 5 | **Extension points**: a block may be empty on the authoring side and be filled by the output strategy | §9 |
| 6 | Placeholder rendering becomes context-sensitive (quoted in expressions, raw in text) | §4 |
| 7 | Pipeline gains an instantiate-fold-prune step before linking, and a dead-concept step before wait injection | §11 |
| 9 | draw.io attribute names are `param.<name>`, not `param:<name>` (2026-11-02, Patrick): `:` makes `param` an undeclared XML namespace prefix, so the drawing does not parse | §2, §3 |
| 8 | Renamed 2026-11-02 (Patrick): a reusable module is a **block** everywhere, as in the frontend. Node types `block_start` and `block` (were `snippet_start` / `snippet`, still read by the YAML input); file renamed from `20260825-snippet-params-and-start-node.md` | all |

* * *

## Part I — Business description

### The problem

Snippet injection (`feature/goto-snippet-injection.md`) lets an author reuse a module by copying its content inline. It works, and it has a hard limit: **every copy is identical**.

Take measuring a temperature. The clinical shape is always the same — ask the site, take the reading, constrain the plausible range, flag a fever. But the site differs, the plausible range differs with it, and the resulting flag has to be a distinct field. Today that means drawing the module once per variation and maintaining each copy separately. The same is true of a danger-sign screen applied to different age bands, a scoring block applied to different symptom sets, or a follow-up prompt with a different interval.

Reuse that cannot vary is not reuse. Authors copy diagrams instead, and the copies drift.

Three further problems appear as soon as modules become configurable:

- **One diagram, many deployments.** An author designs every path a module could take (for example rectal and axillary measurement, or a facility with and without a lab) but a given questionnaire should only contain the paths that deployment uses. Today unused paths ship in the form as dead questions.
- **Concepts that lose their producer.** When a path is removed, a concept it produced may still be read further down, or by a follow-up task that assumes an earlier intervention happened. With the current processing, a node referencing a concept produced inside the exported interventions waits for it. If the producer was removed, it would wait forever.
- **Steps that only the export knows how to build.** Some steps (an AI-assisted summary, a device integration) are not drawn as clinical logic at all. The author needs a named place in the flow where an output strategy plugs its own behaviour in.

### The proposal

**Parameters work like function parameters.** A block or an activity (a process or a page) says what varies about it — a concept, a threshold, a label, a name fragment, a yes/no switch. Values come from the call (`args` on a `block` node or a `goto`) or, at the top of the chain, from the `args` of the intervention. A parameter nobody binds at a call is **inherited** from the calling activity, so the list of parameters an activity needs is computed from what it calls, and a value set at a call overrides the inherited one only for what is called below it. Inside the module, **placeholders** mark where values land, and they may appear in expressions, labels and field names.

> `measure_temperature(site: "axillary", threshold: 37.5)`
> `measure_temperature(site: "rectal", threshold: 38.0)`

produces two independent sets of fields with distinct names and thresholds, from one definition.

**Static decisions prune paths at import.** A decision whose logic depends only on parameters is resolved when the module is instantiated. The branches not taken, and everything reachable only through them, are removed before the questionnaire is built. The author still sees and edits all paths.

**Dead concepts are caught and resolved.** After pruning (and for any concept whose producer is outside the exported scope), the converter detects concepts that are still needed but no longer produced. By default it pulls them from the project dictionary as generated inputs in a prerequisites group. A process or block can also declare its **prerequisites** explicitly, which documents "this assumes X was done before" and triggers the same mechanism.

**Blocks become a declared thing.** Today a module is inlined because a *caller* wrote `instance = -1` on a `goto` (a "snippet"). A **dedicated block start node** replaces it: a module declares itself reusable, and callers simply call it. `instance = -1` keeps working, deprecated.

**A block may be empty.** An empty block is an **extension point**: a named, parameterized slot with a declared contract (what it needs, what it produces) that the export strategy fills.

### Why this matters beyond convenience

It is what makes a **library of guided building blocks** possible. Once a module declares "I am a reusable danger-sign screen, and these are my three parameters", an authoring tool can offer it in a palette, ask for the values in a form, and insert it correctly. Static decisions let one library block serve several facility profiles without shipping dead questions, and dead-concept handling keeps those pruned forms coherent.

### Limitations

- A block remains an independent clone per call, not a live shared subgraph. Editing the module changes future conversions, not already-exported forms.
- Parameters are resolved at import. They are authoring-time values, not runtime ones; a parameter cannot depend on an answer given during the encounter. A static decision therefore can never use patient or context data (see §7).
- Pruning is local to the module or process instance it happens in; it never removes the module's boundary (§7.5).
- Blocks do not recurse. A block may call another block; a cycle is an error.
- A generated prerequisite input asks for a value that previously came from somewhere the export no longer contains. It is an input, not a recomputation (see open questions).

* * *

## Part II — Technical specification

### 1. Node types and page kinds

Four additions to `TriccNodeType` (`tricc_oo/models/base.py`):

| Type            | Role |
|-----------------|------|
| `block_start` | Declares a page as a reusable module. Replaces `activity_start` on block pages. Carries optional metadata (`extension`, `requires`, `provides`, §8, §9). |
| `block`       | Calls a block, supplying arguments. Replaces `goto` + `instance = -1`. |
| `parameters`    | **draw.io surface only.** Declares the page's parameters. Valid on activity, process (`activity_start`) and block (`block_start`) pages, at most one per page. Not a flow node: no edges, not part of the graph, consumed at load into the page-level `params`. |

No new decision type is introduced: static decisions are the existing decision node (`rhombus`) with `static: true` (§7.3).

A page rooted by `block_start` is a **template**, not an activity: it is never a process start, never appears in `project.start_pages`, and is not converted on its own.

### 2. Parameter declaration

Parameters work like **function parameters**. Any activity (a process or a page), and any block, can have them. Two kinds of entry end up in a page's parameter list, and they are **saved the same way**:

- **declared**: written by the author on the page;
- **computed**: a parameter a callee needs that is not bound at the call, so it bubbles up to the caller (§3.3).

The list is therefore usually short or empty on an activity: most of it is computed from what the activity calls.

Canonical form: a page-level `params` section. In the frontend's activity YAML it sits at activity level beside `applicability`; in a block file, beside `nodes` and `edges`:

```yaml
id: measure-temperature          # block page
params:
  - name: site
    type: choice
    options: [axillary, rectal, oral]
    required: true
  - name: threshold
    type: number
    default: 37.5
  - name: use_rectal_path
    type: boolean
    default: false
  - name: concept
    type: concept
    required: true
nodes: [...]
edges: [...]
```

The frontend's activity YAML carries codes only: for primitive parameters the label, hint and translations live on the parameter's concept in the CodeSystem (§5). `label` and `description` in a `params` entry are accepted for draw.io and tests, and used as a fallback when no concept text exists.

Parameter types:

| `type`       | Accepts | Creates dictionary concept (§5) | Substitutes as |
|--------------|---------|:---:|----------------|
| `boolean`    | `true` / `false` | yes | boolean literal |
| `number`     | literal number | yes | numeric literal |
| `string`     | literal text | yes | text (quoted in expression context, §4) |
| `choice`     | one of the declared `options` | yes | the option code (quoted in expression context) |
| `name`       | identifier fragment (`[a-z0-9_]+`) | no | validated identifier fragment |
| `concept`    | `{system, code}` or a code in the project's code systems | no | concept reference |
| `expression` | a CQL expression | no | the expression, parenthesized |

`boolean`, `number`, `string`, `choice` are the **primitive** types, which are also what the authoring tool offers by default. `name`, `concept` and `expression` are substitution-only advanced types.

`expression` is the general case and the one that needs care: a substituted expression is **parenthesized on insertion**, so `threshold: a + b` inside `{{threshold}} * 2` cannot silently re-associate.

A parameter with `required: true` and no `default` must be bound somewhere up the call chain (a call site, or the intervention's `args`). Otherwise the build fails at load, naming the chain from the root activity to the page that needs it (§3.2).

**draw.io.** A `parameters` shape on an activity, process or block page holds one attribute per parameter, `param.<name>`. The value is either JSON (full form) or a shorthand:

```
param.site            = choice(axillary|rectal|oral)!
param.threshold       = number=37.5
param.use_rectal_path = boolean=false
param.concept         = concept!
param.note            = {"type":"string","description":"Free text","label":{"en":"Note"}}
```

Shorthand grammar: `type[(opt1|opt2|...)][!][=default]`, where `!` means required. Anything that needs `label` or `description` uses JSON. At load, the shape is folded into the page's `params`; two parameters with the same name are an error naming the page.

### 3. Binding: arguments, inheritance and override

#### 3.1 Call sites

A `block` node, or a `goto` to an activity or process, may carry arguments. An argument value is either a **literal** (coerced by the declared type) or a **reference** `{{caller_param}}` to a parameter of the calling page (rename or pass-through):

```yaml
- id: n-temp-ax
  type: block
  link: measure-temperature          # block_start.name, or the page id
  args:
    site: axillary
    threshold: 37.5
    concept: { system: "http://tricc.org/CodeSystem/tricc", code: "body_temperature" }
  repeat: 1

- id: g-malaria
  type: goto
  link: malaria-workup
  args:
    use_rdt: true
    setting: "{{care_setting}}"      # reference to this page's own parameter
```

**draw.io.** One attribute per argument on the `block` or `goto` shape, named `param.<name>`, value a literal or `{{ref}}`:

```
param.site      = axillary
param.threshold = 37.5
param.setting   = {{care_setting}}
```

#### 3.2 Environment, inheritance and override

Every instantiation has an **environment**: parameter name → value. At a call, each effective parameter `p` of the callee (§3.3) takes its value from the first of:

1. the call-site argument for `p`;
2. the **caller's environment**, if the caller has a parameter of the same name (**inheritance**);
3. the callee's `default`.

If none applies and `p` is required, the build fails, naming the chain from the root to the call site.

- The environment at the root of a chain is seeded from the **intervention's `args`** (§3.4).
- **Override.** An argument at a call replaces the inherited value **only for the callee and what it calls**. The caller's own environment is unchanged. Overriding an inherited value is an edge case, but it is supported so there is a path forward when it happens. The frontend flags it (see the frontend spec).
- **Identity is the name.** The same name along a call chain is the same parameter. Its type (and, for `choice`, its options) must match, otherwise `E_PARAM_CONFLICT` names both declarations. A `{{ref}}` argument is the escape hatch when two names should be linked.
- Pruned calls (§7) still count for computing parameters; only values decide pruning, never the parameter set.

#### 3.3 Effective parameters (computed)

For a page, `effective(page)` is its own declared parameters, plus, for every call `c` it contains, the callee's effective parameters that `c` does not bind with a literal. A reference argument `{{x}}` adds `x` to the caller's effective set, with the type of the callee parameter it feeds. Because it is computed from the call graph and not from values, it is the same whichever branches pruning later removes. Cycles are already errors.

The library treats the computed set as authoritative. The saved `params` section is read as declarations, so a saved list that is missing computed entries is fine, and a saved entry no longer produced by anything downstream is reported as `W_PARAM_UNREFERENCED` (declared, but referenced in no placeholder, no static condition and no call below). The frontend uses the same rule to flag orphans (frontend spec §5.3).

The entry that carries the type, options and default for a name is the **deepest declaration** along the chain. Callers that re-state it must agree (`E_PARAM_CONFLICT`).

Instantiation key: `(page, instance, bound values of its effective parameters)`. A page with no effective parameters behaves exactly as today. Two paths that reach the same page with different values produce two independent clones, with private instance bands keeping names unique (§10). That is not an error, and neither is the same name built twice: it is the same concept (§10).

#### 3.4 Intervention level

The intervention is where values enter the chain. It is an implementation vehicle that lists activities (processes and pages); its `args` seed the environment of every activity it lists:

```yaml
interventions:
  - id: young-infant
    name: young_infant
    activities: [vital-signs, weight-measurement, yi-tests]
    start: { on: demand, condition: "AgeInDays() < 60" }
    args:
      lab_available: true            # reaches every activity below that has or inherits `lab_available`
    requires: [triage]               # scope for dead concepts, §8.1
```

A name in `args` that no activity of the intervention has or inherits is an error. The same activity listed by two interventions with different `args` becomes two clones.

The intervention's `args` and `requires` exist **only in the YAML structure** (`tricc.yaml`; `TriccInterventionConfig` gains both keys, since it currently ignores unknown keys). draw.io projects have no intervention-level values; their values come from `param.*` on call shapes and from defaults.

The intervention `start` condition is not derived from parameters in v1. It stays the author's responsibility to keep it consistent with the content (ideally it would come from the content, with extra manual conditions allowed so they are not lost when processes or activities are reworked).

#### 3.5 Rules

- `link` resolves against `block_start.name` first, then page id.
- Missing required argument or unresolved required parameter → error at load, naming the chain.
- Argument for a name the callee neither declares nor inherits → error, not a warning. Silently ignoring it is how a typo becomes a wrong export.
- Type mismatch (`choice` value not in `options`, non-numeric `number`, `boolean` other than `true|false`) → error naming the call site.
- `{{ref}}` to a name the caller neither declares nor can compute → error.

### 4. Placeholders

Syntax: `{{param}}`.

Deliberately distinct from the two existing interpolations, which it must never be confused with:

| Syntax                                           | Meaning | Resolved |
|--------------------------------------------------|---------|----------|
| `${field_name}`                                  | Display-text injection of another node's **answer** (`feature/display-text-injection.md`) | At runtime, in the form |
| `TriccReference` / concept name in an expression | A reference to another node's value | During graph processing |
| **`{{param}}`**                                  | **A block or process argument** | **At instantiation, before parsing** |

Permitted in: `name`, `label`, `hint`, `help`, `constraint_message`, `relevance`, `calculate`, `expression`, `constraint`, `reference`, `save`, `min`, `max`, option `name`/`label`, edge `value`, and the condition of a static decision.

Not permitted in: `id`, `type`, `process`, `instance`.

**Context-sensitive rendering (new in rev 2).** Attributes split into *expression attributes* (`relevance`, `calculate`, `expression`, `constraint`, `min`, `max`, edge `value`, decision conditions) and *text attributes* (the rest).

| Parameter type | In a text attribute | In an expression attribute |
|----------------|--------------------|----------------------------|
| `string`, `choice` | raw text | quoted literal, escaped |
| `number`, `boolean` | text of the value | literal |
| `name` | identifier fragment | identifier fragment |
| `concept` | display code | concept reference |
| `expression` | not allowed | parenthesized expression |

`{{param|raw}}` forces raw rendering in an expression attribute (for example to build a name fragment inside an expression), and is validated like `name`.

### 5. Parameters as dictionary concepts

Every primitive parameter is registered in the **calculate data dictionary** as a concept of kind `parameter`:

- code `param_<owner>_<name>` (`<owner>` = the activity, process or block holding the deepest declaration; computed entries reuse that concept and create none of their own), type `boolean | number | string | choice`, with the label, options and default of the declaration;
- it documents the parameter for data-dictionary consumers and lets authoring tools offer it in expression and condition pickers;
- the dictionary entry is the **declaration**. The value lives on each call site, so the entry carries no value;
- it is **not emitted into the form** by default. A project/export option `emit_params: true` emits one hidden constant `calculate` per instantiation (`param_<owner>_<name>_<instance>`), so a form can record which configuration built it.

The authoring tool writes these entries. The library also synthesizes any that are missing at load, so a draw.io-only project gets the same dictionary. Entries are deduplicated by code, and removing a parameter removes its entry (with a warning if an expression elsewhere still references the code).

**The calculate dictionary** is found by, in order (2026-11-03, Patrick): the CodeSystem tagged `meta.tag` `{system: "http://tricc.org/fhir/CodeSystem/codesystem-role", code: "calculate"}`; tricc.yaml `calculate_code_system` (url, id or name); a CodeSystem named `calculate` or `<default>-calculate`; else a new `calculate` CodeSystem, which carries the tag.

Inside a template, parameters are referenced through `{{name}}`, not through the concept code; the concept exists for tooling and documentation, so that there is exactly one way to read a value in a diagram.

### 6. Substitution point

**Templates are parsed lazily, per instantiation.** This now covers block templates *and* any activity or process with effective parameters (§3.3).

A page's node attributes are retained as **raw strings** at load when the page has effective parameters. Placeholder substitution is textual, applied to the clone, and only then are expressions parsed by the normal `parse_expression` / `load_expressions` path. Static folding (§7) runs on the parsed clone.

The alternative — parse once and graft argument expression trees onto placeholder nodes — was considered and rejected for v1. It requires a `TriccPlaceholder` operand threaded through the expression system, makes `name` substitution a special case anyway (names are not expressions), and makes divergence between "what the template says" and "what got instantiated" much harder to debug. Lazy parsing keeps one code path: substitute text, then parse as any other node.

Consequence, stated because it is a real cost: **a template is not validated on its own.** Its expressions are only checked when something instantiates it. Mitigations:

- `validate()` instantiates each template once per distinct call site (and each activity or process once per distinct set of bound values), so any reachable template is checked in a normal build.
- A template that nothing calls is reported as a warning. A call site that sits in a **pruned** region still counts as a use, and is dry-instantiated for dead-concept harvesting (§8.2).
- Authoring tools may lint a template by binding placeholders to synthetic values of the declared type (`tricc_frontend` does this).

### 7. Static evaluation and pruning

#### 7.1 What is static

An expression is **static** if, after substitution, it references only literals, resolved parameter values, and pure operators/functions. Anything that touches a node, a concept value, patient or encounter context (`today()`, `now()`, age, any `TriccReference`, any concept code) is **non-static**.

This answers the open question from the proposal: patient/context-related functions never fold. A static decision cannot depend on them.

#### 7.2 Partial evaluation

Folding is semantics-preserving partial evaluation:

| After substitution | Result |
|--------------------|--------|
| `'rectal' = 'rectal'`, `1 > 2`, `not true` | constant (`true`, `false`, `false`) |
| `true and X` | `X` |
| `false and X` | `false` (X dropped) |
| `true or X` | `true` |
| `false or X` | `X` |
| `X` where X is non-static | unchanged |

Folding only simplifies; it never changes what the expression means at runtime, so applying it to ordinary expressions is always safe.

#### 7.3 One mechanism, two strictness levels

Recommendation (resolving the "new node vs normal rhombus" question): **do not add a new decision type.** Use one folding mechanism and expose it two ways.

| Level | Marker | Behaviour |
|-------|--------|-----------|
| **Static decision** (strict) | decision node with `static: true` (draw.io: attribute `static = true`, rendered with a distinct style) | Condition **must** fold to a constant. Otherwise error `E_STATIC_UNRESOLVED`, naming the node and the non-static reference. This is the author's explicit statement "this is a configuration choice". |
| **Opportunistic folding** | none | Any decision condition, edge condition or `relevance` that folds fully or partially (§7.2) is folded. A condition that does not fold is left as is. No error. |

The strict form exists for readability and safety: it tells a human reader and a linter "this branch is chosen at build time", and it catches the mistake of using a patient value in a configuration choice. The opportunistic form means a parameter that appears in an ordinary condition does the right thing without extra markup.

Scope in v1: decision nodes and their outgoing edge conditions/`value`s, and `relevance` of nodes, including an activity's applicability expression. A `relevance` or applicability that folds to `true` is dropped, to `false` removes the node (for an activity, the whole call).

#### 7.4 Pruning algorithm

Run per template instance, after substitution and parsing, **before linking**:

1. Fold every static decision, then every decision/edge/relevance condition (opportunistic).
2. A fully folded decision is **resolved**: its outgoing edges are kept or dropped by the folded value (`yes`/`no`, or the edge whose `value` matches a `choice`/`string` result; an `else` edge is kept when no value matches). The decision node itself is removed, and its predecessors are rewired to the kept successors.
3. Dropped edges are removed. **Reachability** is computed from the entry over the surviving edges; nodes unreachable from the entry are pruned. A node with another surviving incoming edge stays, losing only the dropped edge (re-joining paths are preserved).
4. Before anything is discarded, the pruned nodes are **recorded** in a side structure (`instance.pruned`) with the concepts they define and the call sites (`block`, `goto`) they contain (§8.2).
5. A pruned `block`/`goto` is not followed during linking. Nothing inside it is instantiated for the real graph.

#### 7.5 Boundary rule

Pruning is **local to the instance** and never crosses its boundary. The block's exit bridge (or the process end) is always kept. If pruning left no surviving path to it, the entry is connected straight to the exit (pass-through) and a warning `W_STATIC_EMPTY_PATH` names the call site. Pruning therefore cannot silently delete the nodes after the call in the parent.

#### 7.6 Visibility

Every build writes a prune report: per call site, the static decisions and the value each resolved to, the nodes and concepts removed, and any pass-through warnings. The frontend shows the same result as a preview (see the frontend spec).

### 8. Dead concepts and prerequisites

#### 8.1 Definitions

An **intervention** is an implementation vehicle: it lists the activities (processes and pages) that make up a guideline or track, and has a start condition. Its **scope** is itself plus the interventions it names in `requires`:

```yaml
requires: [triage]      # interventions whose products are in scope for this one
```

Declaring scope explicitly means a concept is only called out-of-scope when it really is, instead of whenever no intervention of the build happens to produce it. Entries in `requires` may also be concepts, with the meaning of §8.4. A node's **inputs count as part of its intervention**: a concept captured by an input node in the scope, on surviving paths, is *produced*.

For every reference to a concept in a surviving node (relevance, calculate, expression, constraint, `${}` interpolation, edge condition), classify the concept:

| Class | Condition | Treatment |
|-------|-----------|-----------|
| **live** | produced by a node in the intervention's scope | current behaviour: the referencing node waits for it |
| **dead / pruned** | produced only by nodes pruned in this build (from `instance.pruned`) | resolved by policy (below) |
| **dead / out of scope** | exists in the project dictionary, produced neither by the intervention nor by one listed in its `requires` | resolved by policy (below) |
| **unknown** | not in the dictionary | existing error |

Dead concepts are resolved **before** wait injection. Otherwise a node would wait for a concept whose producer was pruned and never be reachable.

#### 8.2 Harvesting

Concepts produced by pruned regions are collected from `instance.pruned`. For a pruned call site, the callee is **dry-instantiated** (substitute and parse, no linking, no export) only to harvest the concept codes it would define. Dry instantiation does not count toward validation errors beyond those it would also raise in a real instantiation.

#### 8.3 Policy

```yaml
on_missing: input        # input | default | error
```

- `input` (default): generate an input node from the project dictionary entry (type, label, options, constraints), flagged `generated: prerequisite`, placed in a `prerequisites` group at the start of the first process of the intervention that references it. One generated input per concept per form; later references reuse it (cross-intervention placement: open question 2).
- `default`: use the dictionary default value for the concept (a constant calculate); error if the concept has none.
- `error`: fail the build, listing concept and consumers.

Set as a project/export default, with a per-concept override (`on_missing` column or attribute in the dictionary).

#### 8.4 Declared prerequisites

`block_start` and process pages may declare concepts they assume were produced earlier:

```yaml
requires:
  - { system: "http://tricc.org/CodeSystem/tricc", code: "malaria_rdt_result" }
```

Declared prerequisites join the reference set even if no expression mentions them literally (the typical case is a follow-up task that presumes an earlier intervention). They go through the same classification and policy, and are documented in the prune/dead-concept report and as a `note` on the generated input.

#### 8.5 Report

Each build writes a dead-concept report: concept, reason (`pruned` | `out_of_scope` | `declared`), consumers, applied policy, generated node id. Same destination as the prune report.

### 9. Extension points (empty blocks)

A block page whose body is empty (just `block_start` and its exit) is an **extension point**. Its `block_start` carries the contract:

```yaml
id: ai_summary
type: block_start
extension:
  handler: ai_summary          # key looked up in the output strategy
  requires: [ ... ]            # concepts it consumes
  provides: [ ... ]            # concepts it produces
```

with its page-level `params` as usual. Resolution at link time, in order:

1. The active output strategy has a handler registered for `handler` → the handler expands the call.
2. Otherwise, if the block has an authored body → the body is used (the authored fallback).
3. Otherwise → `extension.on_unfilled`: `skip` (default; entry bridges straight to exit, with a warning), or `error`.

Handler interface (indicative):

```python
class BlockExtension(Protocol):
    def expand(self, ctx: ExtensionContext, call: TriccNodeBlock,
               args: dict[str, Any]) -> BlockExpansion | None: ...

class BaseOutputStrategy:
    def register_extension(self, handler: str, ext: BlockExtension) -> None: ...
```

`BlockExpansion` returns nodes and edges in the normal internal model, which then go through the same clone/link/bridge path as any block. Handlers that need strategy-native output instead of nodes are out of scope for v1 (open question).

`provides` participates in dead-concept classification: a concept an extension declares as provided counts as **produced** only if the extension was actually expanded. If it was skipped, the concept becomes dead and is resolved by policy (§8). `requires` joins the reference set like §8.4.

### 10. Name uniqueness

Injection today gives each clone a private instance band (`900000+`, `feature/goto-snippet-injection.md`), which keeps export names unique but opaque — `fever_flag_Ii_900001`.

With parameters:

- If the author uses a placeholder in `name`, the substituted name is used as-is: `fever_{{site}}` → `fever_axillary`. Readable, stable across rebuilds, and meaningful in a data dictionary.
- If not, the existing instance-band behaviour is unchanged.
- Two call sites producing the **same** substituted name is **not** an error (2026-11-02, Patrick): it is the same concept. At node level the copies are versions of one concept (instances are ignored on nodes: a later copy is not asked again once captured). A `goto` to an activity handles the same case by reuse (one activity instance between a bridge and a wait per call site).
- A block used several times therefore names its fields by what the uses are: **different things** → a parameter in the name (an existing one, or a dedicated `name`-typed one such as `prefix`); **the same concept collected once** → the same names; **the same concept collected again** → the same names and a `repeat` slot per call ([concept repeat](concept-repeat.md)).
- Substituted names are validated against the identifier rules and passed through `clean_name`.
- Generated prerequisite inputs take the concept's dictionary name; they never take an instance band.

### 11. Pipeline

```
Load:
  block_start page → registered in project.blocks, NOT project.pages
  page with params   → node attributes retained raw (unparsed)
  parameters shape   → folded into page.params
  block / goto     → recorded with link + args (param.* attributes); no bridge/wait injection for blocks

Resolve parameters (before instantiation, from the intervention root down the call chain):
  compute effective params bottom-up (§3.3), then bind top-down: call arg > inherited > default (§3.2)
  validate (required, type, unknown, choice options, E_PARAM_CONFLICT)

Instantiate (per block call site and per (page, instance, bound values)):
  clone template with unique ids, private instance band
  substitute {{param}} (context-sensitive rendering)
  parse expressions (load_expressions / parse_expression)
  fold static decisions, then opportunistic folding            (§7)
  prune unreachable nodes, record them in instance.pruned      (§7.4)
  register parameter concepts in the calculate dictionary      (§5)

Link (walkthrough_block_node, generalizing walkthrough_goto_node's -1 branch):
  follow surviving nodes only; pruned call sites are not followed
  resolve extension points (handler → authored body → on_unfilled)   (§9)
  apply block.repeat if set
  linking_nodes(clone, local processed_nodes)
  ends → single exit bridge; block_start → entry bridge; empty path → pass-through (§7.5)
  import nodes/edges/calculates/groups into parent; never import end/activity_end
  rewire: *→block → entry; block→* → exit; remove block node
  sync_prev_next_from_edges on imported ids
  continue linking from entry on parent

Resolve dead concepts (after link, BEFORE wait injection):
  classify references (live / dead-pruned / dead-out-of-scope / unknown)
  add declared prerequisites and extension `requires`
  apply on_missing policy; generate prerequisite inputs         (§8)

Existing wait injection, then export.
```

Cycle detection: a block call stack is carried through instantiation; revisiting a template already on the stack is an error naming the cycle. Dry instantiation for harvesting (§8.2) uses the same stack.

### 12. Deprecating `instance = -1`

- `goto` with `instance = -1` continues to work, resolving through the new path, and logs a deprecation warning naming the goto and suggesting the `block` equivalent.
- A page rooted by `activity_start` that is only ever reached by `instance = -1` is treated as an implicit template (with no parameters). No diagram needs editing to keep converting.
- Removal is not scheduled here. It happens once authoring tools emit `block`/`block_start` and the existing corpus has been migrated, in its own spec.

### 13. Code checklist

File paths are indicative; adjust to the actual layout.

| File | Change |
|------|--------|
| `tricc_oo/models/base.py` | `TriccNodeType.block_start`, `.block`, `.parameters` |
| `tricc_oo/models/tricc.py` | `TriccNodeBlockStart`, `TriccNodeBlock` (`link`, `args`); page-level `params`, `requires`, `extension`; `static` flag on the decision node; `TriccIntervention.blocks` |
| `tricc_oo/models/params.py` | New — `ParamSpec`, argument validation, substitution engine (context-sensitive rendering) |
| `tricc_oo/models/static_eval.py` | New — static-expression classifier and partial evaluator (§7.1, §7.2) |
| `tricc_oo/visitors/prune.py` | New — folding, branch selection, reachability pruning, `instance.pruned` record |
| `tricc_oo/visitors/dead_concepts.py` | New — classification, harvesting, policy, generated prerequisite inputs, report |
| `tricc_oo/converters/drawio_type_map.py` | Shapes + attributes: `block_start`, `block`, `parameters`, `param.*`, `static` |
| `tricc_oo/converters/xml_to_tricc.py` | Route `block_start` pages to `project.blocks`; fold `parameters` shape into `params`; retain raw attributes; parse `param.*` args on `block`/`goto` |
| `tricc_oo/strategies/input/drawio.py` | `walkthrough_block_node`; generalize the `instance == -1` branch; per-instance process binding; cycle detection |
| `tricc_oo/strategies/input/yaml.py` | Page-level `params`, `requires`, `extension`; `args`; `static`; `TriccInterventionConfig` gains `args` and `requires` |
| `tricc_oo/strategies/output/base_output_strategy.py` | `validate()` instantiates each template/instance once; `register_extension`; report output |
| `docs/tricc-elements.md` | Document the three new types, placeholder syntax and rendering, the interpolation table, `static`, `requires`, `extension` |
| `docs/visual-authoring-concepts.md` | Blocks as the reuse mechanism; static decisions and prerequisites in the layered model |

### 14. Tests

Parameters and substitution

- Parameter validation: missing required, unknown argument, type mismatch, `choice` outside options, default applied.
- Substitution across every permitted attribute, including `name`, option labels and edge values.
- Context-sensitive rendering: a `string` param is quoted in `relevance` and raw in `label`; `|raw` override.
- `expression`-typed argument is parenthesized — `{{t}} * 2` with `t = "a + b"` evaluates as `(a + b) * 2`, asserted at the operation-tree level, not by string comparison.
- Two instantiations of one template produce independent, correctly-named node sets. Two uses building the same name are the same concept (versions, asked once); a `repeat` slot per use collects it again.
- Effective parameters: a callee param not bound at the call appears in the caller's computed list; a literal arg removes it; a `{{ref}}` arg adds the referenced name to the caller; the set is identical whichever branches pruning removes.
- Inheritance and override: an unbound param takes the caller's value; a call-site arg overrides it for the callee subtree only and leaves the caller's environment unchanged; call arg > inherited > default.
- `E_PARAM_CONFLICT` for the same name with a different type or choice options along a chain; `W_PARAM_UNREFERENCED` for a saved entry nothing uses.
- A saved `params` list that omits computed entries behaves exactly like one that includes them.
- Intervention `args` seed every listed activity; a name nothing below has or inherits raises; one activity under two interventions with different `args` yields two clones with distinct names.
- A required parameter with no default and no binding raises, naming the chain from root to call site.
- draw.io `parameters` shape (JSON and shorthand) and `param.*` call attributes produce the same model as the YAML form.
- Lazy parsing: a template with a placeholder in a position that is not valid CQL/TRICC syntax until substituted still loads; it fails only if instantiated with an argument that leaves it invalid.
- Cycle detection.

Static decisions and pruning

- Every row of the §7.2 table, asserted at the operation-tree level.
- A static decision referencing a patient/context value raises `E_STATIC_UNRESOLVED`; the same condition on an ordinary decision is left untouched.
- Branch selection for boolean, `choice` (matching `value`) and `else`.
- Re-joining paths: a node reachable from both a pruned and a kept branch survives.
- Boundary rule: all paths pruned → pass-through and `W_STATIC_EMPTY_PATH`; nodes after the call in the parent are untouched.
- Pruned `block`/`goto` are not linked and not exported, but still count as a use for the orphan-template warning.
- Parameter values `true` vs `false` yield two different exports from one diagram, differing only by the pruned paths.

Dead concepts

- Concept produced in a pruned path and read downstream: no wait node is created, a prerequisite input is generated, with the dictionary type, label and options.
- Concept produced by an input node in a surviving path: live, existing wait behaviour unchanged (regression).
- `on_missing: default` with and without a dictionary default; `on_missing: error` lists consumers.
- Declared `requires` with no literal reference still produces the input; one generated input per concept per form.
- Unknown concept keeps the existing error.

Extension points

- Handler registered: expansion goes through the normal link path.
- No handler, authored body present: body used.
- No handler, empty body: `skip` pass-through with warning; `error` fails.
- `provides` concept becomes dead when the extension is skipped, and is resolved by policy.

Regression and end to end

- `instance = -1` regression: every existing block fixture converts byte-identically and emits a deprecation warning.
- A parameterized block exports correctly under `XLSFormStrategy` and `FHIRStrategy`; a static-pruned variant exports without the dead questions.

### 15. Acceptance criteria

- Blocks, activities and processes declare parameters; values come from `args` on `block`/`goto` and from the intervention's `args`; unbound parameters are inherited from the caller, and a call-site value overrides only below that call.
- The list of parameters an activity needs is computed from its calls and gives the same result whether entries were saved or not.
- Placeholders substitute in expressions, labels and names, with context-appropriate quoting.
- Placeholder-derived names are readable and stable across rebuilds.
- Missing/unknown arguments, unresolved required parameters and type conflicts along a chain are errors that name the call site or the chain.
- `expression` arguments cannot re-associate.
- A static decision removes the branches not taken and everything reachable only through them; an unresolvable static decision is an error.
- Pruning never removes a module boundary; empty paths pass through with a warning.
- A concept whose producer was pruned or is out of scope never causes an infinite wait: it is resolved by `on_missing` and appears in the dead-concept report.
- Declared prerequisites generate inputs when not produced in scope.
- An empty block is filled by a registered strategy handler, falls back to its authored body, or follows `on_unfilled`.
- Every existing `instance = -1` diagram converts unchanged, with a deprecation warning.
- Templates are validated at least once per build, orphan templates are reported, and block cycles are detected.

### 16. Implementation phases

1. Node types, models, `project.blocks`, page-level `params`, parameter/argument validation, `parameters` shape.
2. Substitution engine (context-sensitive) + lazy template parsing, including parameterized activities and processes; effective-parameter computation and binding (§3.2, §3.3).
3. `walkthrough_block_node`, process-instance binding, cycle detection.
4. draw.io + YAML input surfaces (`param.*`, `parameters`, `args`).
5. Parameter dictionary concepts (§5).
6. Static evaluator, static decisions, pruning, prune report.
7. Dead-concept resolution, `requires`, generated prerequisites, report.
8. Extension points and strategy handler registration.
9. `instance = -1` routed through the new path, with deprecation; template validation in `validate()`; docs.

Phases 1 to 4 are independent of 6 to 8 and can ship first.

### 17. Open questions

1. **Recompute vs ask.** A dead concept that is a `calculate` in the dictionary and whose operands are all live could be recomputed instead of asked. Worth a `recompute` policy in v1, or later?
2. **Where prerequisites live with several interventions.** One generated input per concept per form, in the first process of the referencing intervention, is the proposal. Should they instead be placed once per project and referenced across interventions?
3. **Shared evaluator.** The frontend previews pruning. Should it call the Python evaluator through a backend endpoint, or reimplement §7.2 with shared test vectors?
4. **Extension handlers that emit native output.** v1 handlers return nodes and edges. Do we need handlers that emit strategy-native artifacts (a raw XLSForm row, a FHIR extension) directly?
5. **`relevance` folding scope.** Included for `relevance` in v1 (§7.3). Should `calculate`, `constraint` and group relevance fold too?
6. **Parameter concept in forms.** `emit_params` is off by default (§5). Is recording the configuration in the form useful enough to keep?
7. **`requires` vs `follows`.** Intervention scope is declared with `requires` (§8.1). Is a separate `follows` worth having for an intervention that continues from an earlier encounter (as `continue_with` does), where the earlier products would be prerequisite inputs rather than same-visit waits?
8. **Implicit inheritance by name.** Same name along a chain means same parameter. It is convenient and function-like, but an accidental name match is silent apart from the type check. Is `E_PARAM_CONFLICT` enough, or should inheritance be opt-in per parameter (`inherit: true`)?
9. **Clone count.** Instantiating per distinct set of bound values (§3.3) can multiply clones of a large shared activity. Is a build-time warning above a threshold enough?

Out of scope for this spec (decided): the intervention `start` condition does not use parameters. Interventions stay an implementation vehicle; keeping `start` coherent with the content is the author's job, ideally derived from the content with extra manual conditions kept.

### 18. Rev 3 — closed blocks (Draft, 2026-11-02)

Source: Patrick, 2026-11-02. A block becomes a **closed unit**: it reads only what it is given,
it says what it gives back, and it stays a single node of the graph until the export inlines
it. Supersedes the parts of §3, §6, §10 and §11 that it contradicts once approved.

#### 18.1 What a block may contain and read

- **Nodes:** inputs, display nodes, calculates, sequence nodes (decisions, factors, counts, …)
  and `block` nodes (a block may use other blocks; a cycle stays an error). No `goto`, no
  `start` / `activity_start` / `end`: a `goto` inside a block is an error (`E_BLOCK_GOTO`).
- **References:** its parameters (`{{p}}`), its own nodes, functions and library calculates,
  provided none of them **retrieves stored data** (patient or encounter data, earlier answers,
  history). An outside node name, or an expression that retrieves stored data, is an error
  (`E_BLOCK_SCOPE`) naming the reference. Retrieval is known from the operation tree (§18.5).
- **Data from outside comes in through the arguments.** An argument may be an **expression
  evaluated at the use, in the caller's scope** (for example `age: AgeInDays()` or
  `weight: "weight"`). Parameters are therefore of two kinds at a use:
  - *static*: a literal; rendered into the block as in §4, and the only kind static decisions
    (§7) fold on;
  - *dynamic*: an expression; evaluated once at the use (a private calculate of the caller),
    and read inside the block through `{{p}}`.

#### 18.2 Outputs

- By default every inner **input and calculate** of a block is an **output**: visible outside
  the block, by its (rendered) name.
- The block's settings may list `outputs: [<inner node names>]` (the frontend offers a picker
  of the inner nodes). Then only those are outputs.
- An inner node that is not an output is **private**: its export name gets a private
  per-use suffix, it gets no dictionary concept, and a reference to it from outside the block
  is an error (`E_BLOCK_PRIVATE`).

Only outputs take part in the same-name handling of §10 (versions merged by name across
uses). A private node is only read inside its block, so its export name may be anything
unique.

#### 18.3 Concepts

Each use's outputs get a dictionary concept **at linking**, unless a concept or another node of
that name already exists (the project dictionary wins, as in §5).

#### 18.4 Pipeline: blocks are injected at export

- At load, a block use stays a `block` node of the caller's graph, with its arguments. Nothing
  is inlined.
- Each block instance (one per distinct set of bound static values) is **linked on its own**,
  in parallel with the pages, from its parameters.
- At walkthrough, a block use is **ready** when its previous nodes are processed and its
  dynamic arguments are resolvable (the same rule as a calculate and its references). Outside
  references to an output resolve to that instance's output node.
- Linking stores the instance's linked **inner graph on the block use**.
- **Relevance has two levels**, as for an activity: the relevance of the use (the path that
  reaches it) and the relevance inside the block. The export combines them.
- **Export.** The base output strategy first looks for a handler registered for the block
  (a strategy-specific block, an extension point §9). Without one, it falls back to injecting
  the stored inner graph at the use. An empty inner graph with no handler is an error. A block
  marked `external: true` has no fallback: an output strategy without a handler for it fails.
- Because a block is only a node until the export, an **external block** (from another project,
  or an extension point filled by the output strategy) is handled like any other block.

#### 18.5 Retrieving stored data

- `FUNCTION_MAP` (`converters/cql_to_operation.py`) records, per CQL function, whether it
  retrieves stored data (for example `GetRepeatedValue`, the history and populate readers).
- A CQL function that is not in `FUNCTION_MAP` (today `NATIVE` with the function name) becomes
  a new operator **`NATIVE_CQL`**, serialized like `NATIVE`. It carries the same flag, from a
  list of the CQL helper functions that retrieve (`AgeInDays()` and the like).
- `TriccOperation` gains a boolean `retrieves_stored_data`, set by the parser, and a method
  `get_stored_data()`: true when the operation's own flag is set or any child operation's
  `get_stored_data()` is.

#### 18.6 Decisions (Patrick, 2026-11-02)

1. Retrieval: §18.5.
2. Relevance: two levels (use and inside the block), combined at export (§18.4).
3. Same-name merge across uses: outputs only; private nodes get any unique export name.
4. Export: block handler registry, else injection of the inner graph stored at linking; error
   on an empty inner graph, and on an `external` block no strategy handles.
5. `AgeInDays()` and `populate` nodes retrieve stored data, so they are not allowed inside a
   block (`E_BLOCK_SCOPE`): such data comes in as an argument, or the block is really an
   activity.

#### 18.7 Order of work

Phases 1–5 are finished and shipped first, with blocks inlined at linking as an interim.
Rev 3, once approved, replaces only that step (inner graph stored at linking, injected at
export); the block file format does not change.
