# Snippet parameters and a dedicated snippet start node

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Branch target** | TBD |
| **Related** | `feature/goto-snippet-injection.md` (the `instance = -1` mechanism this generalizes and replaces), `feature/concept-repeat.md` (`repeat = -1` local-only capture, which snippet injection relies on), `feature/advanced-merge-calc.md` (same-name versioning after multi-inject), `../tricc_frontend/feature/20260825-guided-authoring.md` (the authoring surface that consumes this) |
| **Origin** | Drafted during `tricc_frontend` v1 planning, 2026-08-25, at the maintainer's request. Reviewed and owned here. |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

### The problem

Snippet injection (`feature/goto-snippet-injection.md`) lets an author reuse a module by copying
its content inline. It works, and it has a hard limit: **every copy is identical**.

Take measuring a temperature. The clinical shape is always the same — ask the site, take the
reading, constrain the plausible range, flag a fever. But the site differs, the plausible range
differs with it, and the resulting flag has to be a distinct field. Today that means drawing the
module once per variation, and maintaining each one separately. The same is true of any
parameterized construct: a danger-sign screen applied to different age bands, a scoring block
applied to different symptom sets, a follow-up prompt with a different interval.

Reuse that cannot vary is not reuse. Authors copy diagrams instead, and the copies drift.

### The proposal

Two changes.

**Snippets take named parameters.** A reusable module declares what varies about it — a concept, a
threshold, a label, a name fragment. Whoever uses the module supplies values. Inside the module,
**placeholders** mark where those values land, and they may appear in expressions, in labels, and
in field names.

So one temperature module, used twice:

> `measure_temperature(site: "axillary", threshold: 37.5)`
> `measure_temperature(site: "rectal",   threshold: 38.0)`

produces two independent sets of fields, with distinct names, distinct thresholds, and one
definition to maintain.

**Snippets become a declared thing.** Today a module becomes a snippet because a *caller* wrote
`instance = -1` on a `goto` — the module itself does not know it is reusable, and nothing declares
what varies about it. That is the wrong place for the decision, and there is nowhere to hang a
parameter list. A **dedicated snippet start node** replaces it: a module declares itself reusable
and declares its parameters, and callers simply call it.

`instance = -1` keeps working, deprecated, so no existing diagram breaks.

### Why this matters beyond convenience

It is what makes a **library of guided building blocks** possible. Once a module can declare "I am
a reusable danger-sign screen, and these are my three parameters", an authoring tool can offer it
in a palette next to the node types, ask for the three values in a form, and insert it correctly.
That is the difference between reuse for people who already know the diagram conventions, and
reuse for a clinician who does not.

### Limitations

- A snippet remains an independent clone per call, not a live shared subgraph. Editing the module
  changes future conversions, not already-exported forms.
- Parameters are substituted when the snippet is instantiated. They are authoring-time values, not
  runtime ones — a parameter cannot depend on an answer given during the encounter, though an
  expression it is substituted into certainly can.
- Snippets do not recurse. A snippet may call another snippet; a cycle is an error.

---

## Part II — Technical specification

### 1. Node types

Two additions to `TriccNodeType` (`tricc_oo/models/base.py`):

| Type | Role |
|------|------|
| `snippet_start` | Declares a page as a reusable, parameterized module and declares its parameters. Replaces `activity_start` on snippet pages. |
| `snippet` | Calls a snippet, supplying arguments. Replaces `goto` + `instance = -1`. |

A page rooted by `snippet_start` is a **template**, not an activity: it is never a process start,
never appears in `project.start_pages`, and is not converted on its own.

### 2. Parameter declaration

On `snippet_start`:

```yaml
- id: s-temp
  type: snippet_start
  name: measure_temperature
  label: { en: "Measure temperature" }
  params:
    - name: site
      type: string
      required: true
      description: "Measurement site, used in the field name and the question label"
    - name: threshold
      type: number
      default: 37.5
      description: "Reading at or above this counts as fever"
    - name: concept
      type: concept
      required: true
```

Parameter types:

| `type` | Accepts | Substitutes as |
|--------|---------|----------------|
| `string` | literal text | text |
| `number` | literal number | numeric literal |
| `name` | identifier fragment (`[a-z0-9_]+`) | validated identifier fragment |
| `concept` | `{system, code}` or a code in the project's code systems | concept reference |
| `expression` | a TRICC/CQL expression | the expression, parenthesized |

`expression` is the general case and the one that needs care: a substituted expression is
**parenthesized on insertion**, so `threshold: a + b` inside `{{threshold}} * 2` cannot silently
re-associate.

In draw.io, `params` is a JSON attribute on the `snippet_start` shape. In YAML it is the mapping
above.

### 3. Call site

```yaml
- id: n-temp-ax
  type: snippet
  link: measure_temperature          # snippet_start.name, or the page id
  args:
    site: axillary
    threshold: 37.5
    concept: { system: "http://tricc.org/CodeSystem/tricc", code: "body_temperature" }
  repeat: 1
```

- `link` resolves against `snippet_start.name` first, then page id.
- Missing required argument → error at load, naming the parameter and the call site.
- Argument for an undeclared parameter → error, not a warning. Silently ignoring it is how a typo
  becomes a wrong export.
- A parameter with a `default` and no argument uses the default.

### 4. Placeholders

Syntax: `{{param}}`.

Deliberately distinct from the two existing interpolations, which it must never be confused with:

| Syntax | Meaning | Resolved |
|--------|---------|----------|
| `${field_name}` | Display-text injection of another node's **answer** (`feature/display-text-injection.md`) | At runtime, in the form |
| `TriccReference` / concept name in an expression | A reference to another node's value | During graph processing |
| **`{{param}}`** | **A snippet argument** | **At instantiation, before parsing** |

Permitted in: `name`, `label`, `hint`, `help`, `constraint_message`, `relevance`, `calculate`,
`expression`, `constraint`, `reference`, `save`, `min`, `max`, option `name`/`label`, and edge
`value`.

Not permitted in: `id`, `type`, `process`, `instance`.

### 5. Substitution point

**Snippet templates are parsed lazily, per instantiation.**

A `snippet_start` page's node attributes are retained as **raw strings** at load. Placeholder
substitution is textual, applied to the clone, and only then are expressions parsed by the normal
`parse_expression` / `load_expressions` path.

The alternative — parse the template once and graft argument expression trees onto placeholder
nodes at clone time — was considered and rejected for v1. It requires a `TriccPlaceholder` operand
threaded through the expression system, it makes `name` substitution a special case anyway (names
are not expressions), and it makes divergence between "what the template says" and "what got
instantiated" much harder to debug. Lazy parsing keeps one code path: substitute text, then parse
exactly as any other node.

Consequence, stated because it is a real cost: **a snippet template is not validated on its own.**
Its expressions are only checked when something instantiates it. Mitigations:

- `validate()` instantiates each snippet once per distinct call site, so any reachable template is
  checked in a normal build.
- A template that nothing calls is reported as a warning, since nothing will ever validate it.
- Authoring tools may lint a template by binding placeholders to synthetic values of the declared
  type (`tricc_frontend` does this — `../tricc_frontend/feature/20260825-guided-authoring.md`).

### 6. Name uniqueness

Injection today gives each clone a private instance band (`900000+`,
`feature/goto-snippet-injection.md`), which keeps export names unique but opaque —
`fever_flag_Ii_900001`.

With parameters:

- If the author uses a placeholder in `name`, the substituted name is used as-is:
  `fever_{{site}}` → `fever_axillary`. Readable, stable across rebuilds, and meaningful in a
  data dictionary.
- If not, the existing instance-band behaviour is unchanged.
- Two call sites producing the **same** substituted name is an error naming both call sites — the
  author asked for two fields and would have got one, silently merged by the versioning machinery.

Substituted names are validated against the identifier rules and passed through `clean_name`.

### 7. Pipeline

```text
Load:
  snippet_start page → registered in project.snippets, NOT project.pages
                       node attributes retained raw (unparsed)
  snippet node       → recorded with link + args; no bridge/wait injection (as instance=-1 today)

Link (walkthrough_snippet_node, generalizing walkthrough_goto_node's -1 branch):
  resolve link → template
  validate args against params (required, type, unknown)
  clone template with unique ids, private instance band
  substitute {{param}} textually across permitted attributes
  parse expressions on the clone (load_expressions / parse_expression)
  apply snippet.repeat if set
  linking_nodes(clone, local processed_nodes)
  ends → single exit bridge; snippet_start → entry bridge
  import nodes/edges/calculates/groups into parent; never import end/activity_end
  rewire: *→snippet → entry; snippet→* → exit; remove snippet node
  sync_prev_next_from_edges on imported ids
  continue linking from entry on parent
```

Cycle detection: a snippet call stack is carried through instantiation; revisiting a template
already on the stack is an error naming the cycle.

### 8. Deprecating `instance = -1`

- `goto` with `instance = -1` continues to work, resolving through the new path, and logs a
  deprecation warning naming the goto and suggesting the `snippet` equivalent.
- A page rooted by `activity_start` that is only ever reached by `instance = -1` is treated as an
  implicit template. No diagram needs editing to keep converting.
- Removal is not scheduled here. It happens once authoring tools emit `snippet`/`snippet_start` and
  the existing corpus has been migrated, in its own spec.

### 9. Code checklist

| File | Change |
|------|--------|
| `tricc_oo/models/base.py` | `TriccNodeType.snippet_start`, `TriccNodeType.snippet` |
| `tricc_oo/models/tricc.py` | `TriccNodeSnippetStart` (`params`), `TriccNodeSnippet` (`link`, `args`); `TriccProject.snippets` |
| `tricc_oo/models/snippet.py` | New — `SnippetParam`, argument validation, substitution engine |
| `tricc_oo/converters/drawio_type_map.py` | Shapes + attributes for both types |
| `tricc_oo/converters/xml_to_tricc.py` | Route `snippet_start` pages to `project.snippets`; retain raw attributes; skip template linking |
| `tricc_oo/strategies/input/drawio.py` | `walkthrough_snippet_node`; generalize the `instance == -1` branch; cycle detection |
| `tricc_oo/strategies/input/yaml.py` | Both node types, `params`, `args` |
| `tricc_oo/strategies/output/base_output_strategy.py` | `validate()` instantiates each template once |
| `docs/tricc-elements.md` | Document both types, placeholder syntax, and the three interpolations table |
| `docs/visual-authoring-concepts.md` | Snippets as the reuse mechanism in the layered model |

### 10. Tests

- Parameter validation: missing required, unknown argument, type mismatch, default applied.
- Substitution across every permitted attribute, including `name`, option labels and edge values.
- `expression`-typed argument is parenthesized — `{{t}} * 2` with `t = "a + b"` evaluates as
  `(a + b) * 2`, asserted at the operation-tree level, not by string comparison.
- Two instantiations of one template produce independent, correctly-named node sets.
- Colliding substituted names raise, naming both call sites.
- Cycle detection.
- Lazy parsing: a template with a placeholder in a position that is not valid CQL/TRICC syntax
  until substituted still loads; it fails only if instantiated with an argument that leaves it
  invalid.
- `instance = -1` regression: every existing snippet fixture converts byte-identically and emits
  a deprecation warning.
- End-to-end: a parameterized snippet exports correctly under `XLSFormStrategy` and `FHIRStrategy`.

### 11. Acceptance criteria

- [ ] A module declares parameters and is instantiated with arguments from several call sites.
- [ ] Placeholders substitute in expressions, labels and names.
- [ ] Placeholder-derived names are readable and stable across rebuilds.
- [ ] Colliding names and missing/unknown arguments are errors that name the call site.
- [ ] `expression` arguments cannot re-associate.
- [ ] Every existing `instance = -1` diagram converts unchanged, with a deprecation warning.
- [ ] Templates are validated at least once per build, and orphan templates are reported.
- [ ] Snippet cycles are detected and reported.

### 12. Implementation phases

1. Node types, models, `project.snippets`, parameter/argument validation.
2. Substitution engine + lazy template parsing.
3. `walkthrough_snippet_node`, cycle detection, name-collision detection.
4. draw.io + YAML input surfaces.
5. `instance = -1` routed through the new path, with deprecation.
6. Validation of templates in `validate()`; docs.
