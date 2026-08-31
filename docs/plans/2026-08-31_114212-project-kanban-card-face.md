# Project Kanban — Card-Face Bundle: Implementation Plan

> **For Hermes:** Implement as vertical slices with Ponytail `full`. Reuse
> the existing `project-kanban` route, backend router, `TaskCard`/`Dashboard`
> components, and native `todos`/`inbox` boards. Do not commit, push,
> migrate shared vault data, or change the live cron job without explicit
> user approval.

**Goal:** close four recorded enhancement requirements from
`/Users/jyang21/Documents/WikiHub/todo-list/Projects/Project Kanban Issue
Log.md` in one combined visual pass: numeric tab badges, a compact Board
card for the narrow side-view, a card-type label (quick action vs. tracked
project), and deadline visibility with an approaching/overdue warning.

**Approved visual evidence:**
`sketches/project-kanban-card-face/index.html` (approved by Jinliang,
2026-08-31, "looks good"). Two open questions in the sketch were resolved
by Jinliang in the same review:

- Deadline field: add `project_kanban.due_date` to the human-managed card's
  JSON metadata, populated manually on create/edit — same pattern as
  `lane` and `project_id`.
- Approaching-deadline threshold: **≤7 days**, as sketched.

**Branch:** none yet — work happens on the current tree (already carries the
committed-but-unpushed PK-003 fix, `8042cc9`); a branch/commit for this work
is a separate authorization.

---

## 1. Product contract frozen by the approved sketch

- **Numeric tab badges** (Board / Projects / Office Inbox): a small badge on
  each top-nav button showing that surface's current live count — open
  Board actions, canonical Projects, active Inbox captures. Counts come
  from data each surface already computes (`actionCounts`/`filterCounts`,
  `data.projects.total_active`, Inbox active count) — no new data source.
  **Zero-count is hidden entirely**, not shown as "0".
- **Card-type label**: a small pill on every Board card distinguishing
  **Tracked** (linked to a canonical project with GitHub/local Git evidence
  — `task.reconciliation === 'linked'` and the linked project carries a
  `github`/device evidence source) from **Quick** (human-managed card with
  no linked repository evidence). Reuses existing project-linkage data
  already computed for `TaskCard`/`TaskDetail` — no new backend field.
- **Deadline visibility**: when a card's `project_kanban.due_date` is set,
  render a small colored row on the card face (not only in the detail
  panel): neutral/quiet when the deadline is more than 7 days out, orange
  when ≤7 days out, red when overdue. No row renders when no due date is
  set (sketch's "No deadline set" / compact "No deadline" text is the
  no-date state, not a placeholder for a missing feature).
- **Compact Board card** (narrow side-view, i.e. the docked 640px panel /
  narrow window width already handled by `useWidth`/`columns` breakpoints):
  title + last-active date only; card body/description text is dropped.
  The type-label and deadline row from above render in compact form too
  (smaller padding/font, per the sketch). **The entire bottom row — link
  badges and lane-move chevrons — is preserved unchanged**, per the
  original PK-issue-log requirement ("preserve the entire existing bottom
  row, including its icons and lane arrows").
- All four apply only to the existing `TaskCard`/`Dashboard` surfaces
  already in `desktop-plugins/project-kanban/plugin.js`. No new view, no
  new route beyond the one additive PATCH field below.

---

## 2. Minimum data contract

### Backend: extend the existing lane-move field, don't add a new route

`project_kanban.due_date` is a new **optional** key inside the same
`project_kanban` JSON object `lane`/`project_id`/`human_managed` already
live in (`plugin_api.py`'s `_move_human_lane`/`_task_view`/`_metadata`
pattern). Two small additions, no new endpoint:

1. **`_task_view`** (`plugins/project-kanban/dashboard/plugin_api.py`,
   around the existing `workflow_lane`/`project_id` extraction): also pull
   `workflow.get("due_date")` (an ISO date string, e.g. `"2026-09-15"`) and
   return it in the view dict as `"due_date"`. `None` when absent or the
   value isn't a plausible `YYYY-MM-DD` string (defensive parse, matching
   this file's existing `if workflow_lane not in LANE_IDS: workflow_lane =
   ""` defensiveness) — a malformed date must never crash the snapshot
   endpoint.
2. **`PATCH /tasks/{task_id}`** (`move_task`/`_move_human_lane`): extend the
   existing `TaskMove` Pydantic model with an optional `due_date: str |
   None = None` field. When provided, merge it into `workflow["due_date"]`
   in the same write transaction that already sets `workflow["lane"]` —
   same human-managed-only gate already enforced by `_move_human_lane`'s
   guard (no new authorization logic needed; a non-human-managed task
   already 409s before this code runs). Setting `due_date: null` explicitly
   clears it (delete the key if present).

   This reuses the **already-existing** lane-move PATCH rather than adding
   a new route, because `due_date` is card metadata with the exact same
   ownership/authorization shape as `lane` (human-managed only, cleared
   on the same claim-race fix PK-003 just shipped). A future card-creation
   flow can also set it via `create_task`'s existing body-JSON convention
   with no backend change at all (this plan does not add a create-time UI
   for it — see Non-goals).

No new table, no new board, no schema migration — `due_date` lives entirely
inside the existing `body` TEXT column's JSON, exactly like `lane` and
`project_id` already do.

### Frontend: `desktop-plugins/project-kanban/plugin.js`

- **`countCategories`/`Dashboard` header buttons** (lines ~688-690): wrap
  each of the three view buttons (`Board`, `Projects`, `Office Inbox`) with
  a small badge showing `boardTasks.length`, `data.projects.total_active`,
  and the Inbox active-candidate count respectively — same three counts
  the header subtitle and filter row already compute this render, just
  surfaced on the tab itself. Render nothing (not a "0" badge) when the
  count is 0.
- **New `TaskTypePill` component** (or a small inline helper next to
  `priorityOf`/`categoryOf`): given `task`, return `'tracked'` when
  `task.reconciliation === 'linked' && task.project?.github` (or another
  already-present evidence flag on `task.project` — confirm exact field
  name against `_task_view`'s project payload during implementation) else
  `'quick'`. Render as a small pill matching the sketch's two-pill style,
  reusing the existing `tint`/`ink` theme-token helpers (no new hex color).
- **New `DeadlineRow` component**: given `task.due_date`, compute days-until
  (or overdue days) client-side, pick neutral/orange/red per the ≤7-day
  threshold, and render the small colored row. Returns `null` when
  `due_date` is absent — no row, no layout shift.
- **`TaskCard`**: add the type pill next to the existing category/project
  pill in the top row, add `DeadlineRow` below the body text, and add a
  `compact` prop (threaded from `Dashboard`'s existing `wide`/`columns`
  narrow-width detection — reuse `useWidth`, do not add a second width
  hook) that, when true: hides `task.body`, replaces it with a relative
  "Active <date>" line (reuse the existing `relativeTime` helper already
  defined for `AchievedRow`), and shrinks padding/font per the sketch.
  **Do not touch the bottom-row badges/chevron block** (lines ~130-152) —
  it is explicitly out of scope for the compact variant per the sketch and
  the original issue-log requirement.

No new file, no new dependency, no new route beyond the one additive
`due_date` field on the existing PATCH.

---

## 3. Non-goals

- **No due-date entry UI in this slice.** `due_date` is settable via the
  existing PATCH (so a future "set deadline" control, or Luna setting it
  via direct API/CLI calls as she already does for Kanban maintenance, both
  work), but this plan does not add a date-picker to `ActionForm` or
  `TaskDetail`. Card-face *display* is this bundle's scope; a creation/edit
  affordance is separate scope, not required to close the four recorded
  requests (which are all about visibility, not entry).
- **No change to `_move_human_lane`'s claim-race behavior** — PK-003 is
  separate, already fixed and committed (`8042cc9`), untouched by this plan
  beyond the one additive optional field on the same PATCH body.
- **No new "approaching" threshold configuration.** ≤7 days is a fixed
  constant per Jinliang's decision, not a per-card or global setting.
- **No change to `TaskDetail`** (the docked side-panel opened by clicking a
  card) beyond whatever falls out naturally from `due_date` being present
  in `_task_view` — if it's useful to also show the deadline there, that's
  a one-line addition worth doing in the same slice, but it is not the
  driving requirement (the issue log specifically asked for card-*face*
  visibility, "not only inside the detail panel").
- **No changes to Office Inbox** (`InboxCard`/`Achieved`) — that bundle is
  already resolved under PK-002, confirmed live and installed on
  2026-08-31; this plan is card-face/Board/tab-strip only.
- **No new dependency, schema, board, or plugin.**

---

## 4. Vertical slices

1. **Backend: `due_date` field on the existing lane-move PATCH + tests.**
   - Extend `TaskMove` with optional `due_date: str | None = None`;
     extend `_move_human_lane` to merge/clear it in the same transaction
     as `lane`; extend `_task_view` to surface it.
   - Tests in `tests/test_project_kanban_api.py`:
     - setting `due_date` on a human-managed card via PATCH returns 200 and
       a follow-up snapshot/GET shows the same value;
     - `due_date: null` clears a previously-set value;
     - a non-human-managed task's PATCH (with or without `due_date`) still
       409s unchanged — the existing guard is untouched;
     - a malformed `due_date` string is rejected 422 (matching this file's
       existing validation style) rather than silently stored or crashing
       `_task_view`;
     - `_task_view` returns `"due_date": null` when absent (backward
       compatible with every existing card/test that doesn't set it).
   - Verify: `~/.hermes/hermes-agent/venv/bin/python -m unittest discover -s
     tests` green — paste the exact pass count, not paraphrased.

2. **Frontend: tab badges + card-type pill + deadline row (regular width).**
   - Add the three tab badges to `Dashboard`'s header buttons.
   - Add `TaskTypePill` and `DeadlineRow` to `TaskCard`, regular (current)
     width only in this slice — compact-width work is slice 3.
   - Node test in `tests/*.test.mjs`: extend the existing Kanban source
     checks (matching this repo's existing string/AST-level Node test
     style) to assert the tab-badge markup, `TaskTypePill`, and
     `DeadlineRow` are present in the built source.
   - Verify: `node --test tests/*.test.mjs` green.
   - Visual self-check per AGENTS.md §4: reload desktop plugins, open
     `/project-kanban` → Board at normal width, `computer_use
     action='capture'`, compare against
     `sketches/project-kanban-card-face/index.html`'s "Regular width"
     column — pill placement, deadline row colors/thresholds, tab badges,
     zero-count hidden. State any divergence explicitly.

3. **Frontend: compact card variant for the narrow side-view.**
   - Add the `compact` prop to `TaskCard`, wired from `Dashboard`'s
     existing width detection (confirm exact breakpoint against the
     sketch's "narrow side-view" intent — likely the same `!wide` /
     narrow-window condition already driving `columns === 1`, not a new
     threshold invented for this slice).
   - Visual self-check: capture the docked/narrow panel width, compare
     against the sketch's "Compact" column — title + last-active only,
     body dropped, bottom-row icons/chevrons pixel-for-pixel unchanged
     from the regular card. Explicitly verify the lane-move chevrons still
     work (click one, confirm the PATCH fires) since PK-003 touches the
     exact same endpoint this slice's cards call.
   - Check the empty-lane and all-cards-compact-at-once states (many cards
     stacked narrow) for layout breakage.

4. **Issue log update (Luna's follow-up, not this build step).** Once all
   slices are verified, move the four requirements from "Recorded
   enhancement requirements" to a resolved/shipped state in `Project Kanban
   Issue Log.md`, same evidence style used for PK-001/PK-002/PK-003 (files
   changed, test names, independently re-run output, git state, screenshot
   comparison notes).

---

## 5. Verification checklist (AGENTS.md §6, applied to this plan)

- [ ] Laziest rung taken: reused the existing lane-move PATCH instead of a
      new route for `due_date`; reused existing `TaskCard`/`Dashboard`
      components and theme-token helpers; no new schema/board/dependency —
      named above.
- [ ] Extension surface: existing backend plugin route + existing desktop
      plugin component (surface #6/#7 from AGENTS.md §2, already in use).
- [ ] Sketch approved (`sketches/project-kanban-card-face/index.html`,
      2026-08-31) and this plan follows it, including the two decisions
      resolved in review (due_date field shape, ≤7-day threshold).
- [ ] Both test suites green, output pasted not paraphrased, for each
      slice that touches code.
- [ ] Screenshot taken at both regular and narrow width, actually compared
      against the sketch region by region; divergences stated explicitly.
- [ ] Bottom-row badges/lane-chevrons confirmed pixel-identical between
      regular and compact cards, and confirmed still functionally wired
      (a chevron click still PATCHes and moves the card).
- [ ] No secrets; nothing committed or pushed without an explicit request.
