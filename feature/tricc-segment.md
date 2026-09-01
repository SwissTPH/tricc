# TriccSegment — main-start activity container

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Related** | tricc_og careplan hierarchy (`Project → Intervention → Segment → Activity → Task`) |

A **segment** is a `TriccNodeActivity` whose root is a **main start** (`TriccNodeMainStart` / `type: start`). Distinct class so process pages (registration, triage, `main`, …) can be told apart from reusable activity pages (`activity_start`).

The main start **stays a node** (`TriccNodeMainStart`); it is the segment's `root`. That matches tricc_oo's existing graph (prev/next on nodes) rather than tricc_og, where the start *is* the container.

## Construction

`node_container_for_root(root, **kwargs)` returns `TriccSegment` if `root` is `TriccNodeMainStart`, otherwise `TriccNodeActivity`. Used by drawio, YAML, the determine-diagnosis page, and the linked-process wrapper.

## Project index

`TriccProject.segments: Dict[process, List[TriccSegment]]` — authored main-start pages only. `pages` / `start_pages` are unchanged.

## Export

`TriccNodeType.segment` is treated like `activity` (group / skipped as a Questionnaire item).
