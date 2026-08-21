# GreenAgent Morning Dashboard Implementation Plan

> **For Hermes:** Use subagent-driven-development to implement this plan task-by-task. Keep Ponytail `full` active: reuse built-ins first, add the minimum code, and do not commit or push without explicit user approval.

**Goal:** Add a separate Hermes Desktop GreenAgent Dashboard for morning briefing and task management that prioritizes todos, active projects, decisions, calendar events, attention-worthy Outlook mail, Hermes Slack/Telegram requests, cron health, and local Git project health.

**Architecture:** Preserve the existing `research-dashboard` unchanged and add a separate `greenagent-dashboard` Desktop plugin with its own route, pane, data, and scoped backend. Reuse Hermes Projects, sessions, cron, skills, and the existing 9:30 AM GreenAgent job. Store the canonical operational data and latest briefing snapshot in this private repository; expose it to the Desktop renderer through the smallest scoped plugin backend. Reuse an audited Microsoft 365 community connector rather than writing a Graph client.

**Tech stack:** Plain JavaScript ESM Desktop plugin (`@hermes/plugin-sdk`, React, `react/jsx-runtime`), Python standard library plus Hermes/FastAPI plugin APIs already installed, JSON data, Hermes cron, Microsoft Graph through a selected existing skill or MCP connector, Git CLI, and the existing `vscode-light-lab` skin.

---

## 1. Confirmed product decisions

### Surface and audience

- Private faculty command center in Hermes Desktop.
- Keep the existing Research Dashboard as the research-project interface.
- Add a separate GreenAgent Dashboard for morning briefing and task management.
- Restore as a pinned pane in the saved layout without stealing focus.
- Preserve the existing Research Dashboard plugin, `/research-dashboard` route, pane, sidebar entry, and status item unchanged.
- Give GreenAgent its own route, pane, sidebar entry, status item, storage keys, and persisted layout identity.
- Use the existing `vscode-light-lab` theme and native Hermes components/theme variables.

### Morning briefing hierarchy

1. **Handle first:** top 5 actions.
2. **More:** up to 10 lower-priority items behind a disclosure.
3. **Today:** detailed schedule plus a compact tomorrow preview.
4. **Detailed dashboard:** Todos, Active Projects, Needs My Input.
5. **Source health:** compact last-refresh/failure row; healthy details remain collapsed.

### Deterministic prioritization

Order items by:

1. timed events and explicit deadlines;
2. blockers and people waiting on the user;
3. direct requests/questions;
4. overdue todos;
5. stale projects;
6. routine items.

Every ranked item must show a short reason and its source. Do not use an opaque numeric AI score in v1.

### Todos

- Time buckets: Today / This week / Later.
- Due-date driven; overdue items remain in Today.
- Undated items are placed manually.
- States: Next / Doing / Waiting / Blocked / Done.
- Fields: title, owner, project, due date, time bucket, state, source links, timestamps.
- Quick actions: mark done, change state, reschedule, open details.

### Projects

- Separate My Projects and Student Projects; filter by owner.
- Card fields: owner, health, next milestone, blocker, next action, last updated.
- Health: On track / At risk / Blocked / Waiting.
- Flag projects stale after 14 days without an update.
- Hermes Projects is the explicit Git repository allowlist; users add repositories through Project settings.
- Git v1 signals: dirty files, ahead/behind, current branch, last commit, and stale activity.
- GitHub PR/issue/CI data is deferred until GitHub is connected.

### Decisions

- Fields: requester, deadline, options, recommendation, impact, related project, source.
- Sort by deadline, then impact; overdue first.
- Actions: Approve / Request changes / Defer, with an optional note.
- External messages, email, and calendar changes still require user approval.

### Briefing sources

- Canonical dashboard todos/projects/decisions from this private repository.
- Hermes Slack and Telegram conversations only in v1; broader workspace/channel history is deferred.
- Microsoft 365 Outlook mail and calendar through an audited existing connector.
- Hermes cron health, including the GreenAgent job.
- Hermes Projects and local Git status.
- Existing session history and source timestamps.

### Email/message triage

- Include direct questions/requests, deadlines, meeting preparation, and messages from Important People.
- Exclude newsletters and routine automated notifications.
- Read complete relevant email threads, not only snippets.
- Maintain an editable Important People list; seed suggestions from current students and frequent collaborators during guided import.
- Detect explicit requests/commitments, but require confirmation before creating a persistent todo.
- Merge likely duplicates into one item with source badges; allow manual split.

### Refresh and delivery

- Refresh when the pane opens if the snapshot is stale.
- Provide a manual Refresh action.
- Keep the existing weekday 9:30 AM America/Chicago schedule.
- Upgrade that job to refresh the dashboard and deliver a concise Top 5 summary to its current destination.
- Fetch email/messages since the last successful briefing, capped at seven days for weekends/outages.
- On source failure, retain the last good data with a Stale badge and timestamp.

### Handling and history

- Briefing actions: Handled / Snooze / Pin / Create todo / Ask Hermes.
- Remember Handled/Snooze decisions.
- Do not resurface unchanged source items; resurface after a material update or snooze expiry.
- Resolved items remain folded and visible for one month, then remain searchable in the archive.
- Visual urgency only in v1; no automatic desktop notifications.

### Data and Git policy

- Track live operational data in this private repository, excluding sensitive notes and message bodies not needed for action context.
- Dashboard writes leave the repository dirty.
- Never auto-commit or auto-push.
- Commit/push only after an explicit user request.

---

## 2. Reuse audit and implementation constraints

### Existing local assets to reuse

- Existing Research Dashboard to preserve unchanged: `desktop-plugins/research-dashboard/plugin.js`
- Standalone report: `web-report/index.html`
- Skin: `skins/vscode-light-lab.yaml`
- Installer: `install.sh`
- Documentation: `README.md`
- Portable Desktop source patch: `patches/desktop-research-workflow.patch`
- Existing GreenAgent cron job: `8d92c7208605`
- Hermes Projects RPC and model: `projects.list`
- Hermes session store/RPC: `session.list`
- Hermes cron RPC/tooling: `cron.manage` / `cronjob`

### Current limitations discovered

- The current Research Dashboard is a separate hard-coded fictional demo and is not a source of live GreenAgent records.
- Its component-only checkbox state and standalone report remain outside GreenAgent scope.
- No user/community plugin is currently installed.
- Slack and Telegram are configured, but v1 access is limited to messages that reached Hermes sessions.
- Microsoft 365 is not configured.
- Google Workspace is not authenticated and is not the user’s work provider.
- Himalaya is not installed and would not provide the Microsoft calendar requirement.
- Hermes’ official MCP catalog currently has no Microsoft 365 entry.

### Community-resource gate

Before installing a Microsoft connector, finish and record the assessment of:

- `ByteSide/hermes-skill-outlook`
- `Andrew-Girgis/microsoft-workspace-skill`
- `Softeria/ms-365-mcp-server`

Select the smallest connector that satisfies all of:

- Microsoft work/school account support;
- delegated read access to mail and calendar;
- local token storage;
- read-only or tightly filtered tool surface;
- active maintenance and compatible auth flow;
- no requirement to build a custom Graph client;
- acceptable UNL tenant consent/admin requirements.

Do not install any connector until the user reviews the recommendation and approves its scopes.

### Ponytail boundary

Do **not** build:

- a new generic workflow engine;
- a second project database;
- a custom Microsoft Graph OAuth/client implementation;
- automatic Git commits/pushes;
- background notifications;
- broad Slack/Telegram history ingestion;
- GitHub PR/CI integration before GitHub is connected;
- a numeric ranking model;
- a new model tool.

---

## 3. Proposed repository shape

Paths are relative to `/Users/jyang21/Documents/projects/hermes-customizations/`.

```text
docs/plans/2026-08-21_140027-greenagent-morning-dashboard.md
README.md
install.sh
data/
  greenagent-dashboard.json
  greenagent-dashboard.schema.json
  greenagent-briefing.json
  important-people.json
desktop-plugins/
  research-dashboard/
    plugin.js                 # preserve unchanged
  greenagent-dashboard/
    plugin.js
plugins/
  greenagent-dashboard/
    plugin.yaml
    __init__.py
    dashboard/
      manifest.json
      plugin_api.py
scripts/
  collect-greenagent-briefing.py
  validate-greenagent-data.py
tests/
  test_greenagent_data.py
  test_greenagent_plugin_api.py
patches/
  desktop-research-workflow.patch
```

Ponytail review before creating files:

- If one JSON file can safely hold dashboard data, briefing snapshot, and Important People without merge/confidentiality problems, collapse the four proposed data files into `data/greenagent-dashboard.json`.
- If the existing plugin backend loader does not require `plugin.yaml` or `__init__.py` for an API-only package, omit unnecessary files.
- If `host.request` can satisfy a read without a backend endpoint, use it and delete that endpoint.

---

## 4. Implementation tasks

### Task 0: Finish the Microsoft connector due-diligence gate

**Objective:** Choose an existing connector; do not write Microsoft Graph code.

**Files:**
- Modify plan only if the selected connector changes architecture.
- No implementation files yet.

**Steps:**

1. Record live GitHub metadata, assessed revision, release/activity, auth model, and permissions for each candidate.
2. Confirm support for Microsoft work/school accounts.
3. Confirm a read-only or filtered mode exposing only mail-read and calendar-read operations.
4. Confirm local token storage and no telemetry/hosted relay by default.
5. Identify whether UNL tenant admin consent is required.
6. Recommend one connector and one fallback.
7. Ask the user to approve the connector and scopes before installation.

**Verification:**

- Exact `owner/repo` and revision recorded.
- Required Graph scopes shown before consent.
- No connector installed during assessment.

**Commit:** None.

---

### Task 1: Define the minimum data contract with failing tests

**Objective:** Establish a validated, privacy-limited schema for todos, projects, decisions, briefing items, source health, handling state, and Important People.

**Files:**
- Create: `tests/test_greenagent_data.py`
- Create: `data/greenagent-dashboard.schema.json`
- Create: `scripts/validate-greenagent-data.py`
- Create: `data/greenagent-dashboard.json`

**Step 1: Write failing tests**

Cover these invariants:

- IDs are unique and stable.
- Every todo state/time bucket is valid.
- Every project health value is valid.
- Decision actions and statuses are valid.
- Source items carry source identity and source timestamp.
- Handled items carry a fingerprint/version so material updates can resurface.
- Resolved timestamps support the one-month folded window.
- Sensitive message bodies are absent; only action summaries and provider object IDs/links are stored.
- The initial live dataset contains only the two confirmed GreenAgent todos:
  - Review and evaluate the MemPalace GitHub repository.
  - Review and evaluate the Pi coding agent.
- No fictional `HEAT-MAIZE-01`, Maya/Leo/Alex, or Kansas-map records exist.

**Step 2: Run tests and verify failure**

Run:

```bash
/Users/jyang21/.hermes/hermes-agent/venv/bin/python -m unittest tests.test_greenagent_data -v
```

Expected: FAIL because the validator/data files do not exist.

**Step 3: Implement the smallest validator and initial data**

Prefer Python standard library JSON validation for required fields/enums if adding `jsonschema` would introduce a dependency. Keep the schema file as documentation and the validator as the executable contract.

**Step 4: Run tests and verify pass**

Expected: all data-contract tests pass.

**Step 5: Review checkpoint**

Show the initial JSON records before any commit. Do not commit without approval.

---

### Task 2: Add the minimum scoped GreenAgent backend API

**Objective:** Let the Desktop plugin read and update the repository data atomically without granting arbitrary filesystem access.

**Files:**
- Create only if required: `plugins/greenagent-dashboard/plugin.yaml`
- Create only if required: `plugins/greenagent-dashboard/__init__.py`
- Create: `plugins/greenagent-dashboard/dashboard/manifest.json`
- Create: `plugins/greenagent-dashboard/dashboard/plugin_api.py`
- Create: `tests/test_greenagent_plugin_api.py`

**Step 1: Inspect the real plugin loader contract**

Confirm the smallest file set required for an enabled API-only plugin. Reuse the established `dashboard/plugin_api.py` pattern.

**Step 2: Write failing API tests**

Test:

- `GET /snapshot` returns validated dashboard data.
- `POST /action` accepts only explicit actions: handled, snooze, pin, create-todo, todo state/reschedule, decision action.
- Invalid IDs/actions are rejected.
- Writes are atomic (`tempfile` + `os.replace`) and preserve the previous file on failure.
- Paths are fixed/configured by the installer; request payloads cannot choose filesystem paths.
- External provider mutations are not exposed.

**Step 3: Run tests and verify failure**

Run with the Hermes venv and the repo’s selected unittest/pytest path after confirming available dependencies.

**Step 4: Implement minimal routes**

Use existing FastAPI and standard library only. No database and no WebSocket in v1; polling/manual invalidation is sufficient.

**Step 5: Run tests and verify pass**

Expected: API behavior and atomic-write tests pass.

**Step 6: Review checkpoint**

Show endpoint list and capability boundary. Do not commit.

---

### Task 3: Implement the deterministic briefing collector

**Objective:** Produce one normalized briefing snapshot from built-in Hermes sources and the approved Microsoft connector.

**Files:**
- Create: `scripts/collect-greenagent-briefing.py`
- Modify: `tests/test_greenagent_data.py`
- Modify: `data/greenagent-briefing.json` or the collapsed canonical JSON file.

**Step 1: Write failing collector tests**

Use fixtures, not live accounts, for:

- deterministic priority ordering;
- top 5 plus up to 10 More;
- seven-day maximum lookback;
- duplicate merge with source badges;
- last-good stale fallback;
- handled/snoozed suppression and material-update resurfacing;
- project stale-after-14-days logic;
- cron failed/late/healthy states;
- local Git dirty/ahead/behind/branch/last-commit normalization.

**Step 2: Run tests and verify failure**

Expected: FAIL because collector functions are absent.

**Step 3: Implement only normalization and deterministic ranking**

Reuse:

- Hermes session APIs/store for Slack/Telegram sessions;
- Hermes Projects allowlist;
- Hermes cron job/execution data;
- Git CLI for each allowed project;
- approved Microsoft connector for Outlook mail/calendar.

Do not duplicate complete email bodies or chat transcripts into the dashboard data.

**Step 4: Run tests and verify pass**

Expected: collector fixture tests pass.

**Step 5: Live read-only smoke test**

Run collection against available sources. Missing Outlook auth must yield a stale/unconfigured source-health entry, not fail the whole briefing.

---

### Task 4: Add the separate GreenAgent Desktop plugin UI

**Objective:** Add the agreed morning briefing and daily work interface without changing the existing Research Dashboard.

**Files:**
- Create: `desktop-plugins/greenagent-dashboard/plugin.js`
- Preserve unchanged: `desktop-plugins/research-dashboard/plugin.js`

**Step 1: Establish independent plugin identity**

Use plugin id `greenagent-dashboard`, route `/greenagent`, pane id `greenagent-dashboard:dashboard`, and separate sidebar/status contributions. Do not import or mutate the Research Dashboard's fictional records.

**Step 2: Bind data through `ctx.rest` and React Query**

Use the app’s shared `useQuery`, `useMutation`, and query client. Do not hand-roll a polling loop.

**Step 3: Add the top briefing area**

Render:

- Handle first (5 maximum);
- More (10 maximum, collapsed);
- Today schedule;
- tomorrow preview;
- compact source-health row.

**Step 4: Add the detailed dashboard**

Render responsive Todos / Active Projects / Needs My Input columns.

- Wide: three columns.
- Narrow: count-labeled tabs.
- Compact cards expand in place.
- Search plus owner/status/project/time filters.

**Step 5: Add quick actions**

- Briefing: Handled, Snooze, Pin, Create todo, Ask Hermes.
- Todo: Done, state, reschedule, details.
- Decision: Approve, Request changes, Defer, optional note.

Actions must paint optimistically, roll back on failure, and refresh from backend truth.

**Step 6: Verify coexistence with Research Dashboard**

Confirm both dashboards can be open, closed, moved, and restored independently. GreenAgent must not reuse Research Dashboard contribution ids, route, pane state, storage keys, or status item.

**Step 7: Syntax check**

Run:

```bash
node --check desktop-plugins/greenagent-dashboard/plugin.js
```

Expected: exit 0.

---

### Task 5: Add the generic Ask Hermes composer bridge

**Objective:** Let a plugin submit item context through the real visible composer pipeline instead of bypassing renderer state.

**Hermes source files:**
- Modify: `/Users/jyang21/.hermes/hermes-agent/apps/desktop/src/sdk/index.ts`
- Test: `/Users/jyang21/.hermes/hermes-agent/apps/desktop/src/sdk/index.test.ts`
- Reuse unchanged: `/Users/jyang21/.hermes/hermes-agent/apps/desktop/src/app/chat/composer/focus.ts` (`requestComposerSubmit`)

**Portable repo file:**
- Regenerate: `patches/desktop-research-workflow.patch`

**Step 1: Write failing SDK test**

Assert that the public plugin host exposes a safe submit action which:

- routes through `requestComposerSubmit`;
- targets the visible composer;
- returns false when no visible composer exists;
- does not call gateway `prompt.submit` directly;
- supports visible user prompts for Ask Hermes.

**Step 2: Run the targeted test and verify failure**

Run the exact Vitest target after locating the package script.

**Step 3: Add the smallest generic host method**

Wrap the existing `requestComposerSubmit`; do not add another event bus or submission pipeline.

**Step 4: Run tests and typecheck**

From `apps/desktop`:

```bash
npx vitest run src/sdk/index.test.ts
npm run typecheck
```

Expected: pass.

**Step 5: Use feature detection in the disk plugin**

If an older Desktop lacks the method, prepare the prompt and show a clear fallback instead of failing.

**Step 6: Regenerate and verify the portable patch**

- Reverse-check against the live modified checkout.
- Forward-check/apply in a clean temporary worktree.
- Ensure the patch includes only intended Desktop changes.

**Step 7: Review checkpoint**

Show patch scope; do not commit.

---

### Task 6: Upgrade the existing GreenAgent cron job

**Objective:** Make job `8d92c7208605` refresh the snapshot and deliver the Top 5 briefing at 9:30 AM weekdays.

**Files:**
- Modify: `install.sh` to install/update the job idempotently.
- Modify: `README.md` with behavior and connector prerequisites.
- Runtime state: update the existing cron job only after user approval.

**Step 1: Define the self-contained job prompt/script**

The job must:

- collect available sources;
- retain last-good stale data for failed sources;
- write the validated snapshot atomically;
- deliver a concise Top 5 summary to the existing destination;
- report coverage/failures;
- never send email/messages or change calendar events;
- never commit/push Git data.

**Step 2: Update rather than duplicate**

List jobs, locate exact ID `8d92c7208605`, then update it. Do not create a second 9:30 AM job.

**Step 3: Run once in the background**

Use the cron run action. Do not poll; wait for completion delivery.

**Step 4: Verify runtime state**

Read back the job definition and inspect the written snapshot, execution status, and delivered Top 5 summary.

---

### Task 7: Make installation portable and idempotent

**Objective:** Install GreenAgent alongside the unchanged Research Dashboard, plus its backend, data path intent, and cron update safely on another computer.

**Files:**
- Modify: `install.sh`
- Modify: `README.md`

**Step 1: Write an installer smoke test**

Use a temporary `HERMES_HOME`. Verify:

- Existing Research Dashboard installation remains unchanged.
- GreenAgent Desktop plugin installs independently.
- Backend plugin installs disabled first, then is enabled only through the documented consent path.
- Repository data path is configured without copying secrets.
- Existing user data is not overwritten.
- Skin/report behavior remains unchanged.
- Re-running the installer is a no-op except for intentional source updates.

**Step 2: Implement minimum installer changes**

Use existing `install` commands and `hermes config set`; never hand-edit `config.yaml`.

**Step 3: Verify temporary-home install**

Compare source and installed artifacts byte-for-byte where applicable.

**Step 4: Secret/privacy scan**

Confirm no tokens, auth files, message bodies, session DBs, logs, or machine launchers are tracked.

---

### Task 8: Guided import for real projects, decisions, and Important People

**Objective:** Populate real data only after the working shell is visible.

**Files:**
- Modify: `data/greenagent-dashboard.json`
- Modify: `data/important-people.json` if not collapsed.

**Steps:**

1. Present current lab members and public research themes as suggestions only.
2. Ask which projects are actually active.
3. Capture owner, health, milestone, blocker, next action, and last-updated date.
4. Capture current decisions needing input.
5. Propose Important People from current students/frequent collaborators.
6. Show a full preview.
7. Write only after approval.
8. Validate the resulting data.

Do not infer that a public research theme or lab member equals an active project.

---

### Task 9: Automated and live Desktop verification

**Objective:** Prove the dashboard works in the actual app before handoff.

**Automated checks:**

```bash
node --check desktop-plugins/research-dashboard/plugin.js
node --check desktop-plugins/greenagent-dashboard/plugin.js
/Users/jyang21/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests -v
```

Run targeted Desktop SDK tests and `npm run typecheck` in the Hermes checkout.

**Live verification:**

- Reload Desktop plugins.
- Confirm no plugin error toast.
- Verify the active `vscode-light-lab` theme.
- Wide layout: three columns visible.
- Narrow layout: count-labeled tabs replace columns.
- Pane restores without stealing focus.
- Top 5 and More limits hold.
- Today/tomorrow calendar sections render.
- Source-health freshness/stale states render.
- Search and all four filters work.
- Handled/Snooze/Pin persist across reload.
- Unchanged handled source items remain hidden.
- Materially updated/snooze-expired items resurface.
- Todo state/reschedule persists.
- Decision actions persist.
- Ask Hermes appears as a normal visible chat submission and does not duplicate.
- Manual Refresh is bounded and cannot launch duplicate concurrent refreshes.
- One failed source leaves the rest usable.
- No background event navigates or steals focus.

Capture a live screenshot/crop for the user and inspect it before handoff.

---

## 5. Acceptance criteria

The feature is complete only when all are true:

- [ ] The existing Research Dashboard and its fictional demo remain unchanged and separate.
- [ ] No fictional Research Dashboard records appear in GreenAgent live data.
- [ ] The two confirmed GreenAgent todos are present.
- [ ] The morning view shows Top 5, More, today, tomorrow, and source health.
- [ ] Todos, projects, and decisions match the agreed fields/actions.
- [ ] Wide and narrow responsive states work.
- [ ] Outlook and calendar use an approved existing connector; no custom Graph client exists.
- [ ] Slack/Telegram v1 uses only Hermes session history.
- [ ] Cron and Git project health are visible.
- [ ] Priority ordering is deterministic and explainable.
- [ ] Duplicate-source items merge with visible source badges and can be split.
- [ ] Handled/snoozed items resurface only as specified.
- [ ] Last-good stale data is preserved on connector failures.
- [ ] External mutations require approval.
- [ ] The 9:30 AM job is updated in place and verified.
- [ ] Data writes are atomic and validated.
- [ ] No secrets or unnecessary message content are committed.
- [ ] Git remains uncommitted/unpushed until explicitly requested.
- [ ] Automated checks pass.
- [ ] Live Hermes Desktop visual and interaction verification passes.

---

## 6. Risks and mitigations

### Microsoft tenant consent

**Risk:** UNL may block user consent for Graph scopes.

**Mitigation:** Select a connector supporting delegated work/school accounts and document the exact admin-consent fallback. Keep Outlook source marked Unconfigured/Stale while the rest of the dashboard works.

### Third-party connector trust

**Risk:** A community skill/MCP can access sensitive mail/calendar data.

**Mitigation:** Inspect source and revision, use minimum read-only scopes/tool filters, pin the revision where possible, keep tokens local, and require explicit installation consent.

### Duplicate or noisy action extraction

**Risk:** Similar email/chat/project items may merge incorrectly or flood the queue.

**Mitigation:** deterministic caps, source badges, manual split, confirmation before todo creation, Important People list, and persistent handled fingerprints.

### Repository privacy

**Risk:** Tracked operational data could contain sensitive email/chat content.

**Mitigation:** store only action summaries, provider IDs/links, and minimal context; exclude full bodies/transcripts; keep the repo private; scan before commit.

### Desktop compatibility patch drift

**Risk:** the portable patch may stop applying after Hermes updates.

**Mitigation:** keep the composer bridge tiny and generic, forward/reverse-check it against live and clean worktrees, and feature-detect in the disk plugin.

### Refresh cost and duplicate runs

**Risk:** pane-open refreshes could spawn repeated agent runs.

**Mitigation:** refresh only when stale, keep one in-flight refresh guard, use a cooldown, and expose manual Refresh status.

---

## 7. Open questions requiring approval before implementation

1. Which audited Microsoft 365 connector and exact read scopes should be installed?
2. Does the UNL tenant allow delegated user consent, or will admin approval be required?
3. Should the collapsed data design use one JSON file or separate snapshot/people files after the data-contract test is written?
4. What exact refresh-staleness threshold should trigger a pane-open refresh? Proposed default: 15 minutes.
5. Should the new sidebar/pane label be **GreenAgent** or **Morning Briefing**? Proposed default: **GreenAgent**.

---

## 8. Execution and review policy

- This plan is the only file created in this planning turn.
- Do not implement until the user reviews and approves the plan.
- During implementation, complete one task at a time with a spec check and code-quality check.
- Show diffs and verification after each phase.
- Do not commit or push unless the user explicitly requests it.
