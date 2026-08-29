# Profile Avatar Identity Implementation Plan

> **For Hermes:** Implement as small TDD vertical slices. The durable deliverable lives in `hermes-customizations` as an update to `patches/desktop-research-workflow.patch`; use a temporary Hermes worktree to build and test the source changes. Do not commit, push, or install/restart the packaged Desktop without explicit approval.

**Goal:** Display each profile's configured avatar and nickname consistently in the Hermes Desktop profile rail and session rows, with a legible initial/color fallback when no avatar exists.

**Architecture:** Reuse the existing backend profile metadata and `profiles.get_asset` RPC—no new database, endpoint, plugin, or dependency. Add one renderer-side identity resolver and one shared avatar component, then consume them from the profile rail and session rows. Package the verified upstream changes into the customization repository's existing Desktop source patch.

**Tech stack:** React 19, TypeScript, Nanostores, TanStack Query, Hermes gateway RPC, Vitest/Testing Library, unified git patch.

**Approved visual evidence:** `sketches/profile-rail-avatars/index.html` (approved by Jinliang on 2026-08-28 after adding matching session-row avatars and nicknames).

**Branch:** none. The customization repository currently has unrelated uncommitted Project Kanban work; this feature must touch only the sketch, this plan, and the Desktop patch-related files listed below.

---

## 1. Product contract frozen by the approved MVP

- **One identity everywhere:** a profile uses the same avatar and nickname in the profile rail and all session rows owned by that profile.
- **Nickname source:** use backend `display_name` after trimming. Fall back to the existing `profileLabel(profile)` behavior; never show a blank label.
- **Avatar source:** use the backend `avatar` profile asset. This covers blob/geometric faces, uploaded images, generated portraits, and pixel pets because Bot Mode already backfills or stores them through `profiles.set_asset`.
- **Fallback:** if metadata is absent, the gateway is old/unreachable, the asset is missing, or loading fails, render the current deterministic initial + profile color. A broken image icon must never appear.
- **Profile rail:** named-profile squares become compact avatars without changing rail height, drag targets, ordering, horizontal scrolling, condensed-mode threshold, connection grouping, active ring, busy/pending state, tooltips, keyboard reordering, or the default Home control.
- **Session rows:** add a compact avatar at the row start and a muted nickname beneath the session title. Preserve timestamp, unread/running state, kebab actions, handoff badges, selection, drag behavior, and narrow-sidebar usability.
- **Accessibility:** avatar images have meaningful accessible names; decorative inner image content is hidden when the surrounding button/row already supplies the label. The active rail button remains identifiable as active.
- **Refresh:** identity data refreshes on mount, focus/visibility return, and connection-registry changes using the existing bounded fleet-roster refresh. Avatar assets may be cached, but must refetch after their bounded stale window so a newly edited avatar appears without relaunching Hermes.
- **Editing:** this slice does not add a second avatar editor. Users continue to edit avatars through Bot Mode's existing **Edit Profile** flow. Existing profile-rail context-menu actions remain unchanged. The MVP's `Edit avatar…` item demonstrated discoverability, not a new persistence contract.

---

## 2. Existing data contract to reuse

No backend change is required.

1. Electron's connection registry already enumerates each profile with credential-free `profileMetadata`:
   - `display_name?: string`
   - `title?: string`
   - `ui_meta?: Record<string, unknown>`
   - `has_avatar?: boolean`
2. `buildAgentRoster()` already attaches that metadata to each exact `(connectionId, profile)` row. The renderer declaration in `apps/desktop/src/global.d.ts` currently omits it; this plan makes the declaration match runtime truth.
3. Existing RPC `profiles.get_asset` accepts:

```ts
{
  name: profile,
  asset: 'avatar'
}
```

and returns a result containing `found` plus a data URL in `data` when present.
4. `requestGatewayForAgent(connectionId, profile, ...)` routes the request to the profile's owning gateway without switching the active workspace, so at-rest fleet avatars are safe.
5. `$fleetRoster` and `refreshFleetRoster()` already provide bounded, no-timer refresh and preserve the last known roster on transient errors. Mount this refresh for the sidebar even when only one connection exists so session identity is not conditional on fleet mode.

---

## 3. Proposed source organization

### New shared renderer files

- `apps/desktop/src/lib/profile-identity.ts`
  - Pure `ProfileIdentity` type.
  - Resolve `(connectionId, profile)` against `DesktopAgentRoster`.
  - Normalize nickname and `hasAvatar`.
  - Produce a stable key and fallback initial.
- `apps/desktop/src/components/ui/profile-avatar.tsx`
  - Shared `ProfileAvatar` component.
  - Fetch `profiles.get_asset` only when `hasAvatar` is true.
  - Cache by `(connectionId, profile)` with a bounded stale interval and focus refetch.
  - Render image or deterministic initial/color fallback at caller-supplied size.

### Existing renderer files to modify

- `apps/desktop/src/global.d.ts`
  - Add `RosterProfileMetadata` and `profileMetadata?: RosterProfileMetadata` to `DesktopRosterAgent`.
- `apps/desktop/src/app/chat/sidebar/index.tsx`
  - Mount the existing fleet-roster refresh once for the sidebar regardless of connection count.
- `apps/desktop/src/app/chat/sidebar/fleet-rail.ts`
  - Carry profile metadata through `FleetAgent` so at-rest rail entries use the exact source-qualified identity.
- `apps/desktop/src/app/chat/sidebar/profile-switcher.tsx`
  - Replace named-profile `ProfileGlyph` content with `ProfileAvatar` while preserving the existing square/button shell and all DnD/state logic.
  - Use nickname in tooltip/accessibility text; keep technical profile name available when nickname differs.
  - Leave the default Home pill and existing context menu unchanged.
- `apps/desktop/src/app/chat/sidebar/session-row.tsx`
  - Resolve identity from `session.connection_id` + `session.profile`.
  - Add the shared avatar and one-line nickname without disturbing row actions or status indicators.

### Tests in the Hermes source worktree

- Create: `apps/desktop/src/lib/profile-identity.test.ts`
- Create: `apps/desktop/src/components/ui/profile-avatar.test.tsx`
- Modify: `apps/desktop/src/app/chat/sidebar/profile-rail-fleet.test.tsx`
- Modify: `apps/desktop/src/app/chat/sidebar/session-row.test.tsx`

### Durable customization-repository files

- Modify: `patches/desktop-research-workflow.patch`
- Modify only if a regression guard is needed: `tests/test_install.py`
- Keep: `sketches/profile-rail-avatars/index.html`
- Keep: `docs/plans/2026-08-28_125009-profile-avatar-identity.md`

---

## 4. Vertical implementation slices

### Task 1: Build the pure identity resolver

**Objective:** Turn roster metadata into one stable, testable profile identity without UI or network behavior.

**Files:**
- Create: `apps/desktop/src/lib/profile-identity.ts`
- Create: `apps/desktop/src/lib/profile-identity.test.ts`
- Modify: `apps/desktop/src/global.d.ts`

**TDD steps:**

1. Add failing tests for:
   - matching by exact `(connectionId, profile)`, including duplicate profile names on two gateways;
   - trimmed `display_name` winning over profile label;
   - blank/missing `display_name` falling back;
   - `has_avatar` normalization;
   - missing roster/metadata returning a usable fallback identity.
2. Run:

```bash
npm --prefix apps/desktop run test:ui -- src/lib/profile-identity.test.ts
```

Expected: FAIL before the resolver exists.
3. Extend the renderer roster type to match Electron runtime metadata and implement the minimal pure resolver.
4. Re-run the targeted test; expected: PASS.
5. Run `npm --prefix apps/desktop run typecheck`; expected: zero new errors.

### Task 2: Build the shared avatar component

**Objective:** Render the stored profile asset with a reliable initial/color fallback.

**Files:**
- Create: `apps/desktop/src/components/ui/profile-avatar.tsx`
- Create: `apps/desktop/src/components/ui/profile-avatar.test.tsx`

**TDD steps:**

1. Add failing component tests with mocked `requestGatewayForAgent`:
   - `hasAvatar=false` does not call the RPC and renders the initial;
   - `found=true` renders the returned data URL;
   - `found=false`, rejected request, and image load error all retain/recover to fallback;
   - the request uses the exact source connection and profile;
   - repeated renders reuse the query cache rather than issuing one request per row.
2. Run:

```bash
npm --prefix apps/desktop run test:ui -- src/components/ui/profile-avatar.test.tsx
```

Expected: FAIL before implementation.
3. Implement the component with existing TanStack Query infrastructure and theme/profile-color utilities. Do not introduce a new cache, polling loop, image library, or backend route.
4. Re-run the targeted test; expected: PASS.
5. Run typecheck again.

### Task 3: Put avatars in the profile rail

**Objective:** Replace initials with avatars while preserving every existing profile/fleet interaction.

**Files:**
- Modify: `apps/desktop/src/app/chat/sidebar/index.tsx`
- Modify: `apps/desktop/src/app/chat/sidebar/fleet-rail.ts`
- Modify: `apps/desktop/src/app/chat/sidebar/profile-switcher.tsx`
- Modify: `apps/desktop/src/app/chat/sidebar/profile-rail-fleet.test.tsx`

**TDD steps:**

1. Extend the fleet-rail tests to prove:
   - active and at-rest named profiles receive source-qualified metadata;
   - duplicate names on different connections do not share avatars/nicknames;
   - default Home remains the Home glyph;
   - fallback initials still render when metadata is absent;
   - selecting and reordering profiles still call the existing handlers.
2. Run:

```bash
npm --prefix apps/desktop run test:ui -- src/app/chat/sidebar/profile-rail-fleet.test.tsx
```

Expected: new assertions FAIL.
3. Mount roster refresh once at the sidebar level, carry metadata through `FleetAgent`, and substitute `ProfileAvatar` inside the existing rail button shell. Do not rewrite DnD, condensed-menu, pending-route, or context-menu code.
4. Re-run the targeted test; expected: PASS.
5. Keyboard-check the rail in the development app: Tab focus, arrow-key reorder, Enter selection, tooltip label, and horizontal overflow.

### Task 4: Put the same identity in session rows

**Objective:** Show each session owner's matching avatar and nickname without losing existing row behavior.

**Files:**
- Modify: `apps/desktop/src/app/chat/sidebar/session-row.tsx`
- Modify: `apps/desktop/src/app/chat/sidebar/session-row.test.tsx`

**TDD steps:**

1. Add failing tests for:
   - avatar and nickname rendered from the session's exact connection/profile;
   - duplicate profile names resolved independently;
   - initial/profile-label fallback on old or missing metadata;
   - local default sessions still render;
   - running arc, selected state, timestamp, kebab menu, and cross-platform handoff avatar remain present.
2. Run:

```bash
npm --prefix apps/desktop run test:ui -- src/app/chat/sidebar/session-row.test.tsx
```

Expected: new identity assertions FAIL.
3. Add the avatar and muted nickname using the existing row layout; keep the row within the current sidebar width and truncate both title and nickname.
4. Re-run the targeted test; expected: PASS.
5. Re-run all four focused suites together:

```bash
npm --prefix apps/desktop run test:ui -- \
  src/lib/profile-identity.test.ts \
  src/components/ui/profile-avatar.test.tsx \
  src/app/chat/sidebar/profile-rail-fleet.test.tsx \
  src/app/chat/sidebar/session-row.test.tsx
```

Expected: all PASS.

### Task 5: Package the source change into the customization repo

**Objective:** Make the feature survive `hermes update` and a clean clone.

**Procedure:**

1. Create a temporary worktree from the exact clean Hermes commit recorded at implementation start.
2. Apply the current `patches/desktop-research-workflow.patch` there.
3. Implement and test Tasks 1–4 in that worktree.
4. Regenerate the full unified patch from the same clean commit, replacing—not appending to—`patches/desktop-research-workflow.patch`. Keep `apps/desktop/index.html` out of the patch.
5. In a second clean temporary worktree, run:

```bash
git apply --check /Users/jyang21/Documents/projects/hermes-customizations/patches/desktop-research-workflow.patch
git apply /Users/jyang21/Documents/projects/hermes-customizations/patches/desktop-research-workflow.patch
git diff --check
npm --prefix apps/desktop run typecheck
```

Expected: patch applies once, `git diff --check` is empty, and typecheck passes.
6. Run the customization repository's mandatory suites:

```bash
~/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests
node --test tests/*.test.mjs
```

Expected: both exit 0.
7. If necessary, add a narrow installer regression test proving the Desktop patch contains the new identity files and remains opt-in through `--with-desktop-patch`; do not add a new installer flag.

### Task 6: Build and visually verify the packaged Desktop

**Objective:** Prove the installed artifact—not just source/tests—matches the approved MVP.

**Precondition:** explicit approval to rebuild/install and restart Hermes Desktop.

1. Apply the patch through the repository-supported path and build/install with the existing installer; do not hand-copy files into the packaged app.
2. Restart Hermes Desktop and reload the same real profiles used by Bot Mode.
3. Capture the running app with `computer_use action='capture'` and compare against `sketches/profile-rail-avatars/index.html` region by region.
4. Verify these states with real data:
   - avatar present;
   - no avatar → initial fallback;
   - asset loading/failure → no broken image;
   - active profile and busy/pending profile;
   - session title + nickname at normal and narrow sidebar widths;
   - duplicate profile names from two gateways;
   - unreachable at-rest gateway;
   - more than 13 profiles → condensed selector;
   - keyboard-only selection and menu access.
5. Confirm profile selection, session opening, drag reorder, context menus, and Bot Mode avatar editing still work.
6. Record any visual divergence explicitly. Do not declare completion until the packaged app is visibly verified.

---

## 5. Non-goals

- No new avatar editor, upload flow, image generator, or profile-metadata schema.
- No change to Bot Mode avatar creation/storage or `profiles.set_asset`.
- No new backend route, database, file format, service, dependency, or polling daemon.
- No avatar data copied into session records; sessions reference profile identity by owner.
- No change to session sorting, grouping, pinning, archiving, deletion, or title generation.
- No change to profile creation, rename, delete, SOUL editing, color selection, or gateway switching.
- No attempt to make avatars visible in CLI/TUI/web dashboard in this slice.
- No commit, push, or packaged-app installation without separate explicit authorization.

---

## 6. Risks and mitigations

- **Renderer type/runtime drift:** Electron already sends `profileMetadata`, but renderer types omit it. Add a unit test and keep the change additive/optional for older builds.
- **Avatar asset fan-out:** many visible session rows may share one profile. TanStack Query must key/cache per `(connectionId, profile)`, so rows do not each fetch.
- **Stale avatar after edit:** use a bounded stale interval plus focus refetch; do not set infinite staleness. Bot Mode remains source of truth.
- **Cross-gateway ambiguity:** never key by profile name alone. All resolver and query keys include connection ID.
- **Unreachable gateways:** keep last known metadata and render fallback if an asset cannot be read; do not hide rows or switch gateways.
- **Session density regression:** keep the nickname one muted truncated line and verify the narrow sidebar live.
- **Patch fragility:** generate and verify against a clean temporary worktree, then test `git apply --check` separately. `profile-switcher.tsx` and `session-row.tsx` are active upstream files, so future Hermes updates may still require three-way reconciliation.
- **Unrelated dirty customization work:** constrain writes and diffs to the files named in this plan; never stage, revert, or rewrite current Project Kanban changes.

---

## 7. Definition of done

- [ ] Configured avatars render in named-profile rail squares.
- [ ] Each session row displays the owning profile's same avatar and nickname.
- [ ] Missing/failed avatars render a deterministic initial/color fallback.
- [ ] Duplicate names on separate gateways remain source-correct.
- [ ] Existing rail/session interactions and status indicators pass regression tests.
- [ ] Focused Hermes Desktop UI tests and typecheck pass.
- [ ] Updated source patch applies cleanly to a fresh worktree.
- [ ] Both customization-repository test suites pass.
- [ ] Packaged Desktop is rebuilt only after approval and visually verified against the approved sketch across normal, narrow, loading/failure, fleet, and keyboard states.
- [ ] No secrets, unrelated files, commits, or pushes.
