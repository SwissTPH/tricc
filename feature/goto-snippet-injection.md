# Goto snippet injection (`instance = -1`) — Feature Specification

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `feature/adv_merge_calc` / `develop` |
| **Related** | Activity `goto`, multi-instance activities, bridge/wait scaffolding |
| **Authoring surface** | draw.io `instance` attribute on `goto`; YAML `instance: -1` |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business Description

## Overview

Authors can reuse a flowchart **module** (another activity/tab) in two ways:

1. **Nested activity** (default) — `goto` starts that activity as its own instance; completion is synchronized with a wait gate.
2. **Snippet injection** (new) — `goto` with **`instance = -1`** copies the module’s content into the calling activity as if it had been drawn inline.

Snippet mode is for reusable building blocks that should share the same form context (same activity/group scope) rather than appear as a nested sub-activity.

## Authoring

On a `goto` shape (or YAML `goto` node):

| `instance` | Behaviour |
|------------|-----------|
| `1` (default) or positive `n` | Nested activity instance `n` (shared when the same `n` is reused) |
| `0` | Auto-unique nested activity instance |
| **`-1`** | **Inject as snippet** (inline into caller; no nested activity) |

Example intent:

```text
Main flow → [goto module, instance=-1] → continue
Module:    start → questions / calculates → end
Result:    Main flow → module content → continue  (same activity)
```

## Benefits

- Reuse modules without nested activity / wait machinery.
- Injected fields live in the parent activity (simpler export grouping).
- Multiple `-1` gotos to the same module each get a fresh copy.

## Limitations

- Target should be a normal **activity** tab (`activity_start` / `activity_end`), not a main form `start` page.
- Each snippet injection is an independent clone (not a live shared subgraph).
- Only applies to **`goto`**, not to `activity_start.instance`.

---

# Part II — Technical Specification

## Scope

| In scope | Out of scope |
|----------|--------------|
| `TriccNodeGoTo.instance == -1` | `instance=-1` on `activity_start` |
| draw.io load + YAML input | Sharing one node set across injections |
| Flatten sequence + calculate nodes into parent | Snippet of main `start` process pages (v1) |
| Entry/exit bridges; remove goto | Changing positive/`0` instance semantics |

## Pipeline

```text
Load:
  draw.io get_nodes: if goto.instance == -1 → do NOT inject bridge+wait
  (keep prev → goto → next edges)

Link (walkthrough_goto_node):
  if instance == -1:
    clone target activity (unique IDs; do not register as pages instance for navigation)
    apply goto.repeat if set
    clone from template with private instance band (900000+)
    **linking_nodes(clone, local processed_nodes)** — do not share caller processed set
    ends → single exit bridge first; activity_start → entry bridge
    import nodes/edges/calculates/groups into parent; never import end/activity_end
    rewire edges: *→goto → entry; goto→* → exit; remove goto
    **sync_prev_next_from_edges** on imported ids (edges are source of truth)
    continue linking from entry on parent (full re-walk of snippet)
  else:
    existing make_instance + replace_node(goto, activity) path
```

## Graph result

```text
prev(of goto) → entry_bridge → … module nodes … → exit_bridge → next(of goto)
```

No `TriccNodeGoTo`, no nested `TriccNodeActivity` for that call, no `TriccNodeWait` for that goto, and **no leftover `TriccNodeEnd` / `TriccNodeActivityEnd`** from the module on the parent (a single exit bridge replaces them so activity-completion detection is not triggered early).

## Code checklist

- [x] `visitors/tricc.py` — `inject_activity_as_snippet` (+ start/end → bridge helpers)
- [x] `strategies/input/drawio.py` — branch in `walkthrough_goto_node`
- [x] `converters/xml_to_tricc.py` — skip bridge+wait when `instance == -1`
- [x] `strategies/input/yaml.py` — register `goto` node type
- [x] Tests + YAML fixture
- [x] `docs/tricc-elements.md` / `docs/pipeline.md`
- [x] Model note on `TriccNodeGoTo.instance`

## Acceptance criteria

1. `instance=-1` inlines target activity content into the parent activity.
2. Entry is a bridge from goto predecessors; exit is a merged bridge to goto successors.
3. Goto is removed; no wait for that goto; no activity_end pollution on parent.
4. `instance >= 0` behaviour unchanged.
5. Unit tests cover YAML multi-activity fixture.

## Implementation phases

1. Helpers + walkthrough branch  
2. Load-time skip of bridge+wait  
3. YAML + tests  
4. Docs + status → Implemented  
