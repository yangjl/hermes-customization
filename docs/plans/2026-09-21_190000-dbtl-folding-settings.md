# DBTL folding and execution settings

Approved by the user on 2026-09-21: sketches/research-dbtl-cycle-folding/index.html.

Goal: keep active cycles visible, fold completed cycles, and let the human specify working folder, repository, skills and instructions per project agent or per task.
Non-goals: native archiving/status changes, automatic workers, cloning, research decisions, new database/schema, dependencies, commits or pushes.

Frozen interaction contract: Completed cycles starts closed; expand cycles and cards; source Build navigation expands its cycle. Any unfinished/stale task keeps its whole cycle active. Agent defaults are project-local. Task overrides are per field, including explicitly empty skills/instructions/repository. Folder must be an absolute local path. Save/Cancel and keyboard focus match the approved preview. Working runs retain their claimed settings; later edits configure future runs. Existing evidence keeps its original settings when known; older runs are labelled unrecorded. Human settings do not themselves approve a run.

## Slices and checks
- [x] Backend: add bounded settings validation and target-version conflict checks in scripts/dbtl.py. Store defaults in existing config and task overrides in native card JSON using edit_task. Resolve settings in status/claim; pin claimed context in the native card and submission. Use native workspace field at claim. Verify persistence, partial inheritance, explicit blanks, invalid atomic rejection, conflicts, cross-project rejection, frozen active context and preserved receipts with unittest fixtures.
- [x] UI: extend assets/index.html, app.js and style.css. Pure cycle grouping, project-scoped local folding preference, expandable cycles, back-to-active navigation, agent chooser and per-task form with effective settings/source labels. Verify all-complete/empty/stale/mixed cycles, source navigation, settings save/cancel/failure/inheritance, focus, mobile layout in isolated browser fixtures.
- [x] Docs/review: update README and bundled skill with paths/skills as task context, frozen claim instructions and preserved evidence root. Fresh code and Python review; fix findings. Run both required suites and full browser flow, inspect screenshots.
- [x] Install: existing install.sh --codex-dbtl-only, refresh cached package through codex plugin add; restart this panel with authenticated URL. Verify real board read-only retains 15 tasks and 7 historical Build + 7 Learn completions, same evidence, avatars and roles. No real approvals or settings changed by verification.

Review focus: stale browser writes, inheritance after reassignment, settings edited mid-run, historical results without execution metadata, hidden cards when source navigation occurs. Settings are data passed to the assigned human-started harness, not shell commands; no automatic filesystem/network access. Every task's evidence stays under the original research root.


## Verification and handoff

- Fresh UI reviewer: approved after startup dependency and folded-card return fixes.
- Python reviewer: Unicode HTTP byte-limit finding fixed, regression covers 7,000 CJK characters.
- Required Python output: `Ran 144 tests in 54.323s` / `OK`.
- Required Node output: `# tests 24` / `# pass 24` / `# fail 0`.
- Both real-browser fixture scripts pass. Existing review/avatars, new folding/settings, delayed script delivery, save failure/busy state, mobile focus and Unicode saving covered.
- Personally inspected desktop and mobile screenshots against approved sketch: hierarchy and controls match; production keeps existing role chips, approval controls and avatars, and explicitly separates next-run settings from recorded-run settings.
- Installed with existing opt-in installer; Codex cache bytes match source. No commits or pushes.
- Live board comparison: same 15 tasks, same evidence/completion receipts, statuses, owners, role defaults and avatar hashes. Live UI: one active Design, seven folded cycles with 14 historical results, functioning source-Build navigation. No real settings saved or research approvals invoked.
- The Codex open request queued the authenticated live panel; browser rendering was verified independently. The standalone preview remains at its existing URL.
