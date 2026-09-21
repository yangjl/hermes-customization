# Agent avatars for Research DBTL

User approved `sketches/research-dbtl-avatars/index.html` on 2026-09-21 and
requested preserving the uploaded pictures in the installed sorghum project.

## Goal and frozen interaction contract

Agents opens a three-agent editor. Select Codex, Claude or Hermes; upload a PNG,
JPEG or WebP (5 MiB maximum), preview its centered square crop, remove to use
initials, cancel to discard, or save. Saved avatars appear on cards, role chips
and detail panels. Pictures belong to agent identity, independently of role.
The live version persists pictures across page reload and server restart.

## Non-goals and smallest extension

Reuse the existing Codex panel, local API and private project config. Native
Hermes profile avatars do not provide per-agent images in this Codex panel.
No dependencies, remote image fetching, shared task database, source patches,
role/task changes, scientific decisions, or background jobs.

## Isolation

Continue the current task's uncommitted DBTL files; their ownership and scope
are established by this conversation. Only edit `plugins/research-dbtl/`, DBTL
tests, this plan and the DBTL README section. Protect other dirty files,
including AGENTS, patches, reconciler scripts and their tests. Do not reload
the user's preview tab: uploads are in memory. Browser control currently fails
to initialize; original image paths have been requested as a recovery fallback.

## Slices and verification

1. Add project-config avatars, optional for existing projects. API action
   `{action: 'avatars', avatars: {codex: dataURL|null, ...}}` updates only provided
   actors. Accept bounded PNG data URLs; browser normalizes uploads to 256px.
   Snapshot includes `project.avatars`; reject invalid actors, type, malformed
   PNG and oversized requests before any write. Preserve tasks/roles and other
   avatars. Integration checks exercise persistence, removal and atomic rejection.
2. Reimplement approved controls in production assets, using snapshot avatars.
   Disable save during decode/save; cancel invalidates pending decode; maintain
   draft state on server failure. CSP allows only local/data/blob images.
   Browser verification covers all three actors, cards, reload, cancel, remove,
   failure, loading, keyboard, narrow layout and unchanged role behavior.
3. Review changes, run both mandatory suites and real-browser flow, inspect
   screenshots against approved preview. Reinstall with existing install.sh and
   plugin-creator cachebuster workflow. Restart local panel, restore the user's
   exact images if recovered, and verify the real project without decisions.

## Proof and delivery ledger

Completed on 2026-09-21:

- Red: new avatar-persistence integration test failed because the old action
  dispatcher treated avatar saves as task actions. Green: focused suite 12/12.
- Full mandatory Python suite: `Ran 126 tests in 49.398s` / `OK`.
- Mandatory Node suite: `# tests 19` / `# pass 19` / `# fail 0`.
- `node tests/research-dbtl-browser.cjs` with existing Chromium/Playwright passed
  both native workflow and production avatar checks. Wide/narrow editor and card
  screenshots were inspected against the approved sketch; hierarchy and actions
  match. Invalid files, save failure/retry, loading, removal/initials, keyboard,
  concurrent edits to different actors and reload persistence were checked.
- Backend Python reviewer and UI code reviewer approved. Review's malformed PNG
  finding was fixed by rejecting unknown critical/noncontiguous chunks and adding
  a valid-CRC regression. No remaining blockers.
- Plugin and skill validators, syntax checks and `git diff --check` passed.
- User's original files were recovered from their named Desktop/Downloads
  locations and reapplied through the production editor. Project snapshots before
  and after prove tasks and roles unchanged. All three stored images decode after
  reload; the real project's existing card displays its agent's picture.
- Existing `install.sh --codex-dbtl-only` and `codex plugin add` installed
  `0.1.0+codex.20260921180616`. Source, installed and cached six-file packages
  match. Existing local panel restarted and updated capability opened in Codex.

## Delivery checkpoint

Implementation → change-review → local installation completed. Authorized scope
comes from “keep them and reapply to the enhanced version of the DBTL workflow!”
and the earlier installation request. No commit, push, external publish or
research decision was performed. No remote CI/deploy applies to this local
installation. Package rollback can use the retained prior `0.1.0` cached package;
the optional avatars field is additive and ignored by the old panel. Pictures
remain in private project config, outside the plugin and its updates.

Browser-control initialization failed, so screenshots and interactions were
verified with existing local Chromium against the installed server. This proves
the local web surface, not native Codex rendering; the app-open action was queued.
Next / upcoming task: none — requested local delivery complete.
