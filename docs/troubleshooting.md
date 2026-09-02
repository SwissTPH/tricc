# Troubleshooting

## XMLSyntaxError at line 1, column 2

Error:

- `lxml.etree.XMLSyntaxError: StartTag: invalid element name, line 1, column 2`

Typical cause:

- Input is not draw.io XML (often downloaded HTML page).

Checks:

- Open downloaded file and verify first tag is `<mxfile` or XML declaration.
- If first lines show `<!DOCTYPE html>` or `<html>`, the download source is wrong.

## Google Drive download returns HTML

Symptoms:

- Logs show `Attempting direct download (fallback for public files)`.
- Converted temp `.drawio` is actually HTML.

Causes:

- Auth path not active (missing libs or missing credentials).
- Service account has no access to that file.

Fixes:

- Confirm `auth/google.json` is valid service account JSON.
- Confirm Google libs are installed in active Python env.
- Share Drive file directly with service account `client_email`.

## Service account format error

Symptom:

- `missing fields client_email, token_uri`

Fix:

- Replace file with real service-account key JSON from Google Cloud.

## "File not found" for URL input

Common reasons:

- URL format is unsupported by extractor.
- Extracted id is wrong.
- Access denied despite valid id.

Use file URL style:

- `https://drive.google.com/file/d/<FILE_ID>/view`

## `missing label on edge` from rhombus

Symptom:

- `CRITICAL - missing label on edge in <activity> from rhombus <id>`
- Build exits during `process_edges` in `xml_to_tricc.py`.

Cause:

- A `rhombus` out-edge has a label TRICC does not recognise.

Supported rhombus out-edge labels:

- `yes` / `oui` — affirmative branch
- `no` / `non` — negative branch (exclusive)
- `follow` / `suivre` / `continue` — follow-through (rewires to rhombus path)
- *(empty)* — treated as yes
- **Integer factors** — `-1`, `+2`, `3`, etc. (implies **yes**; inserts a factor
  `calculate` when the value is not `1`, commonly used with `count` scoring nodes)

Fix:

- Relabel the edge in draw.io using one of the patterns above.

## Question re-asked or never re-asked unexpectedly

Symptoms:

- Same concept appears twice when you expected skip, or is skipped when you expected a second capture.

Checks:

- **Same `name` + same `repeat` (default `1`)** — second capture is normally skipped / inherits (encounter-wide).
- **Different `repeat` values** (e.g. `1` then `2`) — both can show; no cross-slot merge.
- **`repeat=-1`** — local-only: asked without inheriting prior values; does not feed global
  coalesce; **and is never skip-suppressed against another `repeat=-1` occurrence of the same
  concept** — two different callers each capturing the same `repeat=-1` node (e.g. via two
  separate `instance=-1` snippet injects of the same module) both get their own, independent
  capture. Only same `repeat` value **≥ 0** dedupes encounter-wide.
- See [Concept repeat](./tricc-elements.md#concept-repeat) and `feature/advanced-merge-calc.md`.

## Node after a repeated activity call never appears

Symptoms:

- Activity `B` is called twice (as two different instances, or as the same shared instance
  from two different callers) and a node placed right after the *second* call is silently
  missing from the export — not just hidden by relevance, but never emitted at all.

Cause:

- A `TriccNodeActivity`'s own `next_nodes` were previously never scheduled once its content
  finished processing (`walktrhough_tricc_node_processed_stached` in `visitors/tricc.py` had an
  unreachable branch for this). Fixed: the activity now schedules its own `next_nodes` the
  moment its `end`/`activity_end` is processed.
- This only matters when a node is wired as a **direct** `next_nodes` of the activity object
  itself. Diagrams authored in draw.io don't normally hit this: a `goto` with outgoing edges
  gets a `wait` node inserted (see [`wait`](./tricc-elements.md#logic-and-computation-elements))
  so the continuation is scheduled independently of the called activity's own completion — this
  also keeps two different callers of the same shared activity instance from leaking relevance
  into each other's continuation (see the `goto` `instance` note in
  [Navigation/linking elements](./tricc-elements.md#navigationlinking-elements)).

Checks:

- If the node after the call is missing entirely: confirm you're on a version with the
  `walktrhough_tricc_node_processed_stached` fix above.
- If the node appears but its relevance references the *other* caller's condition (or the
  called activity's own completion instead of the calling branch): the `wait`/bridge scaffolding
  may be missing for that call site — re-check the `goto`'s outgoing edges in the diagram.

## Duplicate ODK field names / export collisions

Symptoms:

- XLSForm validation complains about duplicate survey names; or calculated fields overwrite each other.

Checks:

- Multiple nodes with the same export base need unique `_Vv_n` (TRICC renumbers peers in
  `set_last_version_false`). Nodes with `repeat > 1` also get `_Rr_n`.
- `repeat=-1` and default `repeat=1` share the same export base pool — versions should still renumber.
- After diagram edits, re-run conversion; do not hand-edit export names in intermediate models.

## `${field}` shows as literal text in form

Symptoms:

- Note/label shows `${age}` instead of the value, or tokens never parse.

Checks:

- Injection applies only to **display** fields (`label`, `hint`, `help`, messages) on
  display models — not to calculate/rhombus labels.
- Token must be a bare field name (`${age}`), not an expression (`${age + 1}`).
- ODK/CHT rewrites to `${export_name}` after processing; FHIR uses concatenate expressions.
- See `feature/display-text-injection.md`.
- For scoring flows (rhombus → `count`), use a signed integer on the true branch
  instead of leaving the edge unlabeled with a non-standard text label.

See [TRICC Elements — Edge labels](./tricc-elements.md#edge-labels-conditional-flow).

## `Unknown output strategy`

Symptom:

- `ValueError: Unknown output strategy 'XLSFormCHTHFStrategy'` (or similar).

Cause:

- Strategy class not registered because its module was not imported before lookup.

Fix:

- Ensure the strategy module is listed in `tricc_oo/strategies/__init__.py`, or
  import it explicitly before `get_output_strategy`.
- Use the project venv: `.venv/bin/python tests/build.py ...`

## Windows dependency build failures (`cffi`, `numpy`)

Symptoms:

- Meson/compiler errors, `cl` not found.

Fix options:

- Prefer Python version with available wheels (commonly 3.12 for this stack).
- Upgrade `pip`, `setuptools`, `wheel`.
- Install Visual Studio Build Tools (Desktop development with C++) if source build is unavoidable.

## Conversion hangs after `# Create the graph from the start node`

Symptoms:

- No output, no error, no exit — the process just keeps running.
- Or, with a recent build, it stops after a few seconds with
  `CRITICAL - loop guard tripped: get_node_expression made 20001 recursive calls ...`.

Cause:

- Expression generation re-expanded the same sub-graph over and over. Typically a long chain of `goto`
  steps on one page, each guarded by a rhombus plus its `pnav_rel_*` display bridge: every step doubles
  the work, so the chain becomes exponentially expensive. A genuine dependency loop between two
  calculates produces the same failure.

Reading the failure:

- `... path (N levels, M calls)` lists the chain of nodes being expanded, newest last — the tail names
  where the conversion got stuck.
- `nodes revisited on that path (likely dependency loop)` names the nodes expanded more than once on the
  same path. Those are the ones to look at in draw.io.
- The Python stack trace that follows shows which stage requested the expression.

Fixes / next steps:

- Simplify the offending page: break a very long guarded `goto` chain into separate activities, or move a
  repeated rhombus condition into a single calculate the steps reference.
- Remove circular dependencies between calculates (A's condition referencing B and B's referencing A).
- If the project is genuinely that large and healthy, raise the budget (see below) — a healthy run of the
  reference projects peaks at ~20 calls and depth ~11, so the defaults leave a wide margin.

Guard budgets (environment variables, see `tricc_oo/visitors/loop_guard.py`):

| Variable | Default | Meaning |
|---|---|---|
| `TRICC_MAX_EXPRESSION_CALLS` | 20000 | expression expansions allowed per top-level node |
| `TRICC_MAX_EXPRESSION_DEPTH` | 100 | nesting depth allowed in expression expansion |
| `TRICC_MAX_LOOP_ITERATIONS` | 50000 | iterations allowed in the stashed-node loop |
| `TRICC_LOOP_GUARD_PDB` | unset | set to `1` to drop into `pdb` where the guard trips |

```bash
# inspect the stuck state interactively
TRICC_LOOP_GUARD_PDB=1 python tests/build.py -i my_project/ -o out/ -O FHIRStrategy -l d
```

Related: `fix/20260902-expression-recursion-hang-guard.md`.
