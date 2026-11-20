# Form pages, one-level sections, and `asGroup` replacing `instance = -1`

| Field             | Value |
| ----------------- | ----- |
| **Status**        | Approved (2026-11-20, in conversation) |
| **Branch target** | `feature/questionnaire-pages` → `develop` |
| **Scope**         | `models`, `converters/xml_to_tricc`, `DrawioStrategy`, `YamlStrategy`, `FHIRStrategy` → `OpenSRPStrategy`, `XLSFormStrategy` (and subclasses) |
| **Related**       | `feature/goto-snippet-injection.md` (`instance = -1`, deprecated by this RFC; becomes `Superseded`); `feature/20261111-block-params-and-start-node.md` (blocks, the declared form of inlining); `feature/20261009-yaml-page-groups.md` (`container_page` groups, not pages); `fix/20261118-fhir-group-aware-sections.md` (the section walk order this builds on; not merged yet); mirror into `tricc-frontend/feature/` on approval (the two attributes in DrawTRICC, migration of `instance = -1`) |
| **RFC**           | #90 |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

## Part I — Business description

### The problem

A form exported from TRICC (FHIR Questionnaire or XLSForm) is one long scrolling form. On a tablet, a long
consultation (danger signs, then cough, then diarrhoea, then fever…) is hard to follow. The
author cannot say "show this activity on its own screen".

SDC supports this: a group marked as a **page** is shown on its own screen, with Next and
Previous buttons. Pages whose activity is not relevant are skipped. TRICC never emits it.

There is a second, related problem. An activity called from a GoTo becomes a group (a section of
the form). The only way to call it *without* a group, so that its questions appear inline in the
caller, is the `instance = -1` trick on the GoTo. That reuses a number meant for "which copy of
the activity" to mean "don't make a group". It is hard to explain and easy to get wrong.

### What changes for an author

Two yes/no settings:

- **`page`**, on an activity, a block, a GoTo, a block call or a group of questions (the frame
  drawn around questions): show it on its own page. The default is `false`.
- **`asGroup`**, on an activity or a GoTo that calls one: `true` (the default, as today) makes it a
  section; `false` puts its questions inline in the caller. **This replaces `instance = -1`.**

A setting on the GoTo wins over the one on the activity, for that call only. When two GoTos
open the same copy of an activity:

- if only one of them sets a value, that value applies to the copy;
- if they set different values, the export stops with an error naming both GoTos.

**Sections are one level deep.** In the FHIR form, an activity called from inside another
activity no longer appears as a section *inside* the caller's section. The caller's section
stops, the called activity gets its own section, and the caller continues in a new section after
it, as XLSForm groups already do. Two reasons:

- the Android renderer only pages top-level sections;
- an activity called from several places stays visible when it is reached from one of them,
  even if another caller was not reached. Today it is hidden with the caller's section.

The form is paginated as soon as one activity or group of the form has `page: true`:

- each such activity or group is a page (split around nested pages as above);
- questions outside any page, including those of activities without `page`, are gathered into
  default pages, in their order. The author never gets a screen per loose question.
- a group of questions without `page` stays a sub-heading inside its page or section.

Without any `page: true`, the form gets the same flat sections (one per activity) but no
pagination: one scrolling form, as today.

In XLSForm (CHT and the other XLSForm outputs), a page is a group shown as one screen
(`field-list`), so the same `page` setting works there too.

`instance = -1` keeps working for now, read as `asGroup: false` with a deprecation warning.
DrawTRICC rewrites it when the project is opened. One release later it becomes an error.

### Out of scope

- The meaning of other `instance` values (`0`: a new copy per call; `n`: a shared copy). They
  do not change.
- `repeat` and `repeat = -1` (local-only concept slots). They do not change.
- Page titles, progress bars, or a review page: renderer settings, not Questionnaire content.

---

## Part II — Technical specification

### 1. Design

**Model** (`tricc_oo/models`)

- `TriccNodeActivityStart`, `TriccNodeBlockStart`, `TriccNodeGoTo`, `TriccNodeBlock`:
  `page: Optional[bool] = None`.
- `TriccNodeActivityStart`, `TriccNodeGoTo`: `as_group: Optional[bool] = None`. `None` means
  "not set"; it is what lets a GoTo override or defer to the start node.
- `TriccNodeActivity` (the built instance): resolved `page: bool = False`.
- `TriccGroup` (`container_page`, YAML `groups`): `page: bool = False`, authored directly.
- `TriccNodeGoTo.instance`: update the comment (`models/tricc.py`) to
  `# -1: DEPRECATED, use as_group=False (feature/<date>-questionnaire-pages.md)`.

**Input**

- draw.io (`converters/drawio_type_map.py`): add `page` and `asGroup` to `activity_start`,
  `goto`; `page` to `block_start` and `block`. Parse `true`/`false`/`1`/`0` as bool in
  `xml_to_tricc` next to `priority` / `instance` / `repeat`. `asGroup` maps to `as_group`.
- YAML (`strategies/input/yaml.py` `NODE_TYPE_MAP`): the same attributes, `as_group` spelled
  `asGroup` in the file, as in draw.io.
- Groups: `page` on draw.io `container_page` (read in `xml_to_tricc` `get_groups` / `add_group`)
  and on YAML `groups[]` (`YamlGroup.page`).

**Deprecation of `instance = -1`**

- Every place that tests `instance == -1` (`DrawioStrategy.walkthrough_goto_node`,
  `xml_to_tricc.py` bridge skip, the YAML block path) goes through one helper,
  `resolve_as_group(goto, activity_start) -> bool` in `converters/xml_to_tricc.py`, with a
  `# DEPRECATED` comment on the `-1` branch.
- The `-1` branch logs `logger.warning` once per GoTo and emits
  `warnings.warn(..., DeprecationWarning, stacklevel=2)`, so test runs can turn it into an error
  (`-W error::DeprecationWarning`) when the alias is removed.
- `feature/goto-snippet-injection.md` gets Status `Superseded` with this spec under Related.

**Resolution at linking** (`DrawioStrategy.walkthrough_goto_node`, the YAML equivalent)

1. `as_group = goto.as_group if set, else activity_start.as_group if set, else True`.
2. `goto.instance == -1` with `as_group` unset: `as_group = False`, deprecation warning. With
   `as_group` set as well: `as_group` wins, warning.
3. `as_group is False` → today's snippet path (`clone_activity_for_snippet`,
   `inject_activity_as_snippet`), then the `instance` value is ignored (warn if it is not 1).
   The skip in `xml_to_tricc.py` (no bridge / wait for `instance == -1`) tests the resolved
   flag instead.
4. `as_group is True` → today's instance path (`make_instance`), unchanged.
5. `page = goto.page if set, else start.page if set, else False`, stored on the instance.
6. Shared instance (same `n`): the GoTo that sets `page` / `as_group` drives the instance;
   GoTos that leave it unset follow. Two GoTos setting different values: **error**, naming both
   GoTos and the instance, and the export stops. `as_group` cannot differ for one shared
   instance: an inlined call has no instance to share.
7. `page = True` on an inlined call or a block: the injected nodes are wrapped in a generated
   `TriccGroup` (`page = True`, name from the block or activity), because a page needs a group.

**FHIR export: flat sections** (`strategies/output/fhir_form.py`)

Per Questionnaire (segment), replace the nesting of activity groups (`_group_stack`, pushed on
`activity_start`, popped on `activity_end`) with a flat list of top-level **sections**. The walk
order stays the group-aware CHT order (`fix/20261118-fhir-group-aware-sections.md`).

1. **Paged** = at least one activity instance or `TriccGroup` of the segment has `page = True`.
2. **Section unit**: when paged, an activity or a `TriccGroup` with `page = True`; when not
   paged, every activity with `as_group = True`. Inlined calls and blocks are not units (their
   nodes belong to the caller), except a block or inlined call with `page = True` when paged
   (§ Resolution 7). A page `TriccGroup` is gated by its own relevance, ANDed with its
   activity's hidden item (rule 4).
3. Walk the items in order and keep a stack of open units:
   - entering unit C while section S is open: close S, open a section for C;
   - leaving C: if the enclosing unit P has more items, open a continuation section for P
     (same text as P);
   - an item outside every unit goes to a **default section**; consecutive such items share one
     (no text).
   - a section left with no item is dropped.
4. **Activity relevance is computed once.** The `activity_start` of every activity instance
   (unit or not) is exported as a hidden calculated item, linkId = its export name (today the
   group's linkId), `calculatedExpression` = the activity relevance. The relevance of an
   activity start is already the OR of its call sites, each ANDed with its caller's relevance
   (`get_prev_node_expression` in `visitors/tricc.py`), so a shared activity is shown when any
   caller reached it. Today the parent group's `enableWhen` masks that when nested.
   - A unit's sections (first and continuations) get `enableWhenExpression` = that item is true.
   - The items of a non-unit activity absorbed into another section get its gate the same way:
     their own expression AND that item is true. Item expressions already reference the
     activity root (`ISTRUE(activity.root)` in `get_prev_node_expression`); check that every
     absorbed item carries it, and add it where the nesting used to provide it.
   - Default sections have no `enableWhen`.
   - No relevance expression is copied into the items.
5. **linkIds.** Sections use a reserved suffix, in the style of `_Vv_` / `_Rr_` / `_Ii_`, so they
   can never collide with an export name: `<activity export name>_Ss_<n>` for a unit's sections
   (`n` = 1, 2… in order), `<segment>_Ss_d<n>` for default sections. The hidden activity item
   keeps the activity's export name, so references to the activity do not change. Item linkIds
   do not change; only their parent does.
6. When paged, every section gets `itemControl = page` (new `build_page_item_control_extension()`
   in `converters/fhir/`, next to the help/hint builders). Not paged: no extension.
   Reason for paging *every* section: in the Android SDC renderer every top-level item becomes a
   page once one is (`Questionnaire.isPaginated`, `QuestionnaireViewModel.getQuestionnairePages`).
7. Every `%resource.item…` path is resolved against the final flat tree
   (`_resource_item_path`, `_link_id_repeats`): build the sections before resolving expressions,
   or resolve after. Each item is at most two levels deep (section → item), plus help/hint
   children.
8. Activities with `repeat: x` need nothing special: the repeat slot is already in the export
   names and in the relevance. They are sections like any other; the suffixes of rule 5 keep
   their linkIds distinct.
9. A `TriccGroup` without `page` stays a nested group (a sub-heading) inside its section.

**XLSForm export** (`XLSFormStrategy`, inherited by `XLSFormCDSSStrategy` → `XLSFormCHTStrategy`
→ `XLSFormCHTHFStrategy`)

- A `begin_group` row built from an activity or `TriccGroup` with `page = True` gets
  `appearance = field-list` (one screen in ODK Collect, one page in CHT/Enketo). An existing
  appearance on the row is kept, `field-list` is added to it.
- A page nested in another page: close the outer group before the inner one and reopen it
  after, as in the FHIR export (rule 3), because ODK flattens a `field-list` inside another one.
  The reopened group keeps the outer relevance and gets a distinct name (`_Ss_<n>`, rule 5).
- No `page` anywhere: the XLSForm output is unchanged.

### 2. Validation and errors

- `page` / `asGroup` not a boolean: warning, attribute ignored.
- `asGroup` on a `block_start` or `block`: warning, ignored (a block is always inline).
- Conflicting values on GoTos sharing an instance: **error**, the export stops.
- `instance = -1`: deprecation warning (`logger.warning` + `DeprecationWarning`) pointing to
  `asGroup: false`; an error one release after DrawTRICC migrates projects on open.

### 3. Tests

- `tests/test_questionnaire_flat_sections.py` (YAML fixtures in `tests/data/yaml/`):
  - activity P calls C in the middle: sections `P_Ss_1`, `C_Ss_1`, `P_Ss_2`, in that order, no
    nesting, all gated by the hidden items `P` / `C`;
  - C called last in P: no empty `P_Ss_2`;
  - a non-page activity absorbed into a page: its items are gated by its hidden item; no
    relevance expression is duplicated;
  - a concept whose name ends like a section linkId: no linkId collision;
  - an activity with `repeat: 2` called twice: distinct sections and hidden items;
  - no `page` anywhere: same sections, no `itemControl`;
  - C called from P and from Q, only Q reached: C's section is enabled (its relevance is the OR
    of both call sites), P's is not;
  - expressions referencing an item moved out of a nested group still resolve (path check and
    an e2e run in `tests/uat/`).
- `tests/test_questionnaire_pages.py` (YAML fixtures in `tests/data/yaml/`):
  - two activities with `page: true` → two top-level sections with `itemControl = page`;
  - loose questions and non-page activities before and between them → default page sections,
    order kept;
  - page P calls page C: `P_Ss_1`, `C_Ss_1`, `P_Ss_2`, all pages;
  - GoTo `page: false` overrides activity `page: true`;
  - two GoTos to instance 2, one with `page: true` → the instance is a page, no warning;
    `page: true` vs `page: false` → error;
  - `asGroup: false` gives the same Questionnaire as today's `instance: -1`;
  - `instance: -1` still works, logs the deprecation and raises `DeprecationWarning`
    (`pytest.warns`);
  - a block call with `page: true` → wrapped in a page group;
  - a `container_page` with `page: true` → its own page; without → a nested group in its page;
  - no `page` anywhere → same as the flat-sections output, without `itemControl`.
- `tests/test_goto_snippet.py`: same cases with `asGroup: false`.
- `tests/test_xlsform_pages.py`: page activity → `appearance = field-list`; page inside page →
  outer group closed and reopened with a distinct name; no `page` → XLSForm unchanged.
- `tests/uat/` e2e: an Android-renderer check that the paginated form navigates (optional).

### 4. Phases

1. Model + both inputs + resolution, `asGroup` replacing `instance = -1` with the deprecation
   (no output change).
2. FHIR flat sections, no pagination (changes every FHIR export's structure, not its content;
   regenerate the regression baselines). Check LHC-Forms' support of `itemControl = page`.
3. FHIR pagination: `itemControl = page`, default sections, page groups.
4. XLSForm `field-list` pages.
5. DrawTRICC mirror: the `page` / `asGroup` settings (activity, GoTo, block, group), migration of
   `instance = -1`.

### 5. Implementation notes (phases 1–4)

Where the code made a rule above impossible or unclear:

- **Hidden activity items** are top-level items, placed before the activity's first section.
  One whose activity relevance is `true` and that nothing references is pruned with the other
  unused hidden calculates. A segment start gets one (and sections) only when it has a
  relevance; otherwise its items go to default sections.
- **Split** happens when an item of the caller follows the called activity's items: a called
  activity with no item leaves the caller's section whole.
- **Groups in FHIR**: `container_page` was not exported at all before. A group without `page`
  is now a sub-heading (its own relevance on it) in paginated and plain forms alike.
- A **section left with hidden items only** is marked `questionnaire-hidden`, so a paginated form
  shows no empty page. A section linkId already taken by an authored name gets `_<k>`.
- **XLSForm** groups were already one level deep, closed and reopened around other groups
  (`<name>_<n>`), and every `begin group` was already `field-list`. `page` therefore changes
  nothing in XLSForm; the reopened group keeps its existing `<name>_<n>` name (not `_Ss_<n>`)
  so a form without `page` is unchanged.
- **draw.io**: the bridge / wait skip of a goto runs before the called page is built; the
  `asGroup` of every `activity_start` is read up front (`TriccIntervention.start_as_group`).
- **YAML `groups`** (`id`, `name`, `label`, `parent`, `page`, node `group`) are read in the
  format of `feature/20261009-yaml-page-groups.md`, which this RFC needs for `YamlGroup.page`.
- Fixed on the way: `TriccNodeActivity.make_instance` dropped the `TriccGroup` of every node
  copy, so groups of called activities never reached an output; the XLSForm group of a
  `TriccGroup` now carries its activity's relevance (it crashed, or showed the questions
  outside the activity).

---

## Open questions

None.

## Decisions

- 2026-11-20: `asGroup: false` replaces GoTo `instance = -1`, which is abandoned; other
  `instance` values are out of scope (@delcroip)
- 2026-11-20: FHIR sections are always one level deep, split around nested activities as in
  XLSForm (`P_Ss_1`, `C_Ss_1`, `P_Ss_2`); paged when an activity or group of the segment has
  `page: true`, otherwise the same sections without pagination (@delcroip)
- 2026-11-20: in a paged form, an activity without `page` has no section of its own; its items
  join the enclosing page or a default section, gated by one generated calculate holding the
  activity relevance, not by duplicated expressions (@delcroip)
- 2026-11-20: `repeat: x` activities need no special section behaviour (the slot is in the names
  and the relevance); section linkIds must not collide with export names (@delcroip)
- 2026-11-20: `container_page` groups take `page` (default `false`); without it they stay a nested
  sub-group of their section (@delcroip)
- 2026-11-20: conflicting `page` / `asGroup` values on GoTos sharing an instance are an export
  error (@delcroip)
- 2026-11-20: XLSForm `field-list` pages are in this RFC (@delcroip)
- 2026-11-20: `instance = -1` is deprecated in code (comment + `DeprecationWarning`) and becomes
  an error one release after DrawTRICC migrates projects (@delcroip)
- 2026-11-20: LHC-Forms support of `itemControl = page` is checked during phase 2 (@delcroip)
- 2026-11-20: approved for implementation (@delcroip)
