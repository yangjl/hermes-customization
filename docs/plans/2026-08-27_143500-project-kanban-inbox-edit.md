# PK-002: Office Inbox Independent Save/Edit — Implementation Plan

> **For Hermes:** Implement as one vertical slice with Ponytail `full`. Reuse
> the existing `project-kanban` route, backend router, and native `inbox`
> board. Do not commit, push, migrate shared vault data, or change the live
> cron job without explicit user approval.

**Goal:** An Office Inbox candidate can be edited (title/project/notes) and
explicitly **saved back into the Inbox** without being accepted or dismissed,
closing the PK-002 gap in
`/Users/jyang21/Documents/WikiHub/todo-list/Projects/Project Kanban Issue Log.md`.

**Approved visual evidence:** `sketches/project-kanban-inbox-edit/index.html`
(approved by Jinliang, 2026-08-27, "as designed").

**Branch:** none yet — work happens on the current tree; a branch/commit is a
separate authorization.

---

## 1. Product contract frozen by the approved sketch

- Each active Inbox candidate renders as a compact 1–2 row card (title +
  stage pill + source tag + one-line context), matching current density —
  no new list virtualization or pagination.
- Clicking the candidate's **title** opens an inline editor in the same card
  (no modal, no navigation away from the Inbox view). Clicking it again (or
  an explicit collapse affordance) closes the editor without discarding
  in-progress edits from view, matching sketch behavior.
- The editor has three fields: Title (text), Project (select, canonical
  projects only — same list as today's Accept form), Notes (textarea, maps to
  the existing `details` field).
- Three **distinct** actions, always visible together once editing:
  **Save**, **Accept**, **Dismiss**. No action is inferred from another.
  - **Save** — persists title/project/notes edits to the SAME Inbox
    candidate record. The candidate stays in the Inbox, unarchived,
    unaccepted. A brief inline confirmation (sketch: "Saved — kept in
    Inbox") appears and fades.
  - **Accept** — unchanged existing behavior (promotes to the `todos` board),
    but now also carries whatever title/project the editor currently holds
    (already true today — Accept already submits title+project_id).
  - **Dismiss** — unchanged existing behavior (archives the candidate).
- An **AI-assisted revision** affordance may propose a title/project
  revision with a stated reason. It is a suggestion only:
  - It never calls Save, Accept, Dismiss, or any mutating endpoint directly.
  - "Apply to fields" only copies the proposed values into the editor's own
    Title/Project inputs — nothing is persisted until the human presses Save
    or Accept.
  - "Discard suggestion" clears the proposal without touching the fields.
- **Achieved** (Office Inbox only, never Board): accepted and dismissed
  candidates move into a single folded-by-default "Achieved" group showing
  outcome (Accepted/Dismissed), title, and a relative timestamp. Folding
  preserves history — it must not delete or archive-out-of-reach anything
  beyond what Accept/Dismiss already do server-side. Un-folding is a plain
  disclosure toggle, no extra fetch required (client-visible history is
  scoped to the current session's accept/dismiss events — no new "Achieved
  log" persistence layer; see Non-goals).

---

## 2. Minimum data contract — one new backend route

### `PATCH /api/plugins/project-kanban/inbox/{task_id}`

New save-only route, sibling to the existing `POST /inbox/{task_id}/accept`
and `DELETE /inbox/{task_id}`, in
`plugins/project-kanban/dashboard/plugin_api.py`.

Request body (reuse the `InboxAccept` field shape, but title/project are
each optional so a partial save is possible; add `details` since the sketch
edits Notes too):

```python
class InboxEdit(BaseModel):
    title: str | None = None
    project_id: str | None = None
    details: str | None = None
```

Behavior, modeled directly on the existing `accept_inbox`/`dismiss_inbox`
pair (same board guard, same `_candidate_stage` eligibility check, same
optimistic `rowcount`-checked UPDATE under `kb.write_txn`):

1. 404 if the Inbox board does not exist (`_inbox_unavailable` contract).
2. Look up the candidate; 409 "Inbox candidate is no longer active" if
   `_candidate_stage(candidate) is None` (claimed, archived, or otherwise
   not currently a live candidate) — identical eligibility gate to
   `dismiss_inbox`, so a candidate that's mid-accept or already gone can't be
   silently edited out from under that operation.
3. If `title` provided: reject blank-after-strip with 422 (matches
   `capture_inbox`/`accept_inbox`'s existing title validation).
4. If `project_id` provided: validate it resolves via `_project_records()`
   the same way `accept_inbox` already does; 422 if unknown.
5. Merge provided fields into the candidate's existing JSON body
   (`_metadata`/`json.loads` pattern already used throughout this file) —
   do NOT touch `status`, `candidate_stage`, `review_candidate`, or any
   worker-lifecycle field. This is a body-only edit.
6. `UPDATE tasks SET body = ? WHERE id = ? AND claim_lock IS NULL AND
   worker_pid IS NULL` (no status predicate — a save must succeed regardless
   of the candidate's exact blocked/todo/ready stage, mirroring the PK-001
   fix's principle: human-facing metadata edits are independent of native
   worker-lifecycle state). 409 if `rowcount != 1` (raced by a worker claim
   or a concurrent accept/dismiss).
7. Append a `task_events` row, kind `edited`, payload
   `{"source": "project-kanban"}` — same audit pattern as every other mutator
   in this file (`accept`, `dismiss`, `move_task`).
8. Return `_task_view(updated_task)` — same response shape the Inbox list
   already emits, so the frontend can patch its query cache in place.

No new table, no new board, no new task. This reuses the exact task record
the Inbox already lists; only its `body` JSON gains fresher title/project
text ahead of a future Accept.

### Frontend: `desktop-plugins/project-kanban/plugin.js`

Rework `InboxCard` (currently: view mode ↔ one `editing` mode that only
serves Accept) into three states, matching the sketch:

- **Closed** — title (button) + stage pill + source tag + one-line
  reason/suggestion context. Unchanged from today except the title becomes
  the open-editor trigger (today's checkmark icon opens Accept editing;
  keep that icon working too, or fold it into the same open action — do not
  keep two separate ways to reach the same editor unless the sketch implies
  it, which it doesn't).
- **Open** — inline editor: Title input, Project select, Notes textarea,
  the AI-assisted-revision box (collapsed "Suggest revision" trigger →
  proposal panel with Apply/Discard), and the three-button row
  (Dismiss / Save / Accept).
- **Achieved** — after a successful Accept or Dismiss response, move the
  card client-side into a folded "Achieved" section (mirrors the sketch's
  `moveToAchieved`). This is a client-side view grouping of the *current
  session's* outcomes layered on top of the existing Board/Inbox data — see
  Non-goals for what it deliberately does not persist.

New mutation, alongside the existing `useKanbanMutation`-backed Accept/
Dismiss calls:

```js
const save = () => mutate.mutate({
  path: `/inbox/${task.id}`, method: 'PATCH',
  body: { title, project_id: projectId, details: notes }
})
```

The AI-suggestion affordance is **client-only for this slice** (see
Non-goals) — it renders a canned/local suggestion exactly like the sketch's
fixture data, wired so "Apply to fields" sets the same React state the
manual inputs use. No new backend endpoint, no model call, in this slice.

---

## 3. Non-goals

- No AI/model-backed suggestion generation. The sketch's AI box ships as a
  **static, clearly-fixture-derived UI affordance** in this slice — wiring
  an actual model call is separate scope requiring its own approval (a new
  external call is not "the smallest useful next action" for closing PK-002,
  and AGENTS.md's ponytail rule says do not speculatively build it now).
  Ship the interaction contract (propose → apply-to-fields-only → human
  confirms) so a real suggester can be dropped in later without a UI
  rework.
- No persistent "Achieved" log/table. Folding is a client-side grouping of
  outcomes the user causes *in the current session/page life*; a full
  Achieved history that survives reload/relaunch is a separate, larger
  change (would need a new persisted view or a `task_events` query) and is
  not required by the PK-002 issue-log text ("must not delete the candidate
  history" — satisfied because Accept/Dismiss already write `task_events`;
  survivable *display* of that history is future scope).
- No change to Accept/Dismiss's existing request/response contracts.
- No change to Board lane behavior (PK-001 is separate, already shipped).
- No new task schema, board, plugin, or dependency.
- No compact-Board-card or numeric-tab-badge work — those are separate
  recorded requirements in the issue log, not in this plan's scope.

---

## 4. Vertical slices

1. **Backend: `PATCH /inbox/{task_id}` route + regression tests.**
   - Add `InboxEdit` model and the route in `plugin_api.py`, following the
     exact eligibility/locking pattern above.
   - Tests in `tests/test_project_kanban_api.py`:
     - saving title/project on a `captured`-stage candidate returns 200 and
       the change is visible in a follow-up `_inbox_snapshot()`/GET;
     - saving on a `suggested`-stage candidate (native `todo`/`ready`
       status) also succeeds — proves the save is NOT gated on stage/status,
       mirroring the PK-001 regression test's shape;
     - a claimed candidate (`claim_lock` set) is rejected 409, unchanged;
     - an archived/dismissed candidate is rejected 409;
     - blank title after strip is rejected 422;
     - unknown `project_id` is rejected 422;
     - a save does not change `status`, `candidate_stage`, or
       `review_candidate` — only `title`/`project_id`/`details` in the body
       move.
   - Verify: `~/.hermes/hermes-agent/venv/bin/python -m unittest discover -s
     tests` green.

2. **Frontend: inline editor + Save button, wired to the new route.**
   - Rework `InboxCard` per §2. Keep Accept/Dismiss calling their existing
     unchanged endpoints.
   - Node test in `tests/*.test.mjs`: extend the existing Kanban v2 test
     file to assert the Inbox card source contains a save action wired to
     `PATCH /inbox/` (string/AST-level check, matching this repo's existing
     Node test style — no new test framework).
   - Verify: `node --test tests/*.test.mjs` green.

3. **Frontend: AI-suggestion affordance (static) + Achieved folding.**
   - Add the suggestion box and client-side Achieved grouping, matching the
     sketch's interaction contract exactly (propose → apply-to-fields-only →
     human Save/Accept required).
   - Visual self-check per AGENTS.md §4: reload desktop plugins, open
     `/project-kanban` → Office Inbox, `computer_use action='capture'`,
     compare against `sketches/project-kanban-inbox-edit/index.html` region
     by region (compact rows, editor layout, three-button row, AI box,
     folded Achieved) — note any divergence explicitly.
   - Check narrow-width layout (Project Kanban's existing responsive
     breakpoints) and the empty-Inbox / all-achieved state.

4. **Issue log update (Luna's follow-up, not this build step).** Once all
   slices are verified, PK-002 moves from "Sketch ready" to Resolved in
   `Project Kanban Issue Log.md` with the same evidence style used for
   PK-001 (files changed, test names, independently re-run output, git
   state).

---

## 5. Verification checklist (AGENTS.md §6, applied to this plan)

- [ ] Laziest rung taken: reused existing route family, existing
      `InboxCard`, no new schema/board/dependency — named above.
- [ ] Extension surface: existing backend plugin route + existing desktop
      plugin component (surface #6/#7 from AGENTS.md §2, already in use).
- [ ] Sketch approved (`sketches/project-kanban-inbox-edit/index.html`,
      2026-08-27) and this plan follows it.
- [ ] Both test suites green, output pasted not paraphrased.
- [ ] Screenshot taken and actually compared against the sketch region by
      region; divergences stated explicitly, not hidden.
- [ ] No secrets; nothing committed or pushed without an explicit request.
