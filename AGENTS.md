# AGENTS.md

Rules for any agent working in this repository. Read this before changing
anything. `README.md` documents what exists and how to install it; this file
documents how to add to it.

This repository is the source of truth for one person's Hermes customizations.
Everything here must survive a `hermes update`, reinstall on a second machine
from a clean clone, and be readable by the next agent six months from now.

## 1. Ponytail is the default

Minimum code that works. Climb this ladder and stop at the first rung that
holds:

1. **Does it need to exist?** Speculative need is not a requirement. Say so in
   one line and move on.
2. **Does Hermes already do it?** Check first — this is the most common miss.
   The Todo MVP was a whole plugin until the native Kanban board turned it into
   a `hermes kanban boards create` one-liner. Search the CLI (`hermes --help`,
   `hermes <area> --help`), the settings panes, and the docs at
   <https://claude-code.nousresearch.com/docs> before writing a line.
3. **Does this repo already do it?** Reuse `install.sh`, the existing skin, an
   existing plugin, an existing script. Do not add a second installer, a second
   theme system, or a second task database.
4. **Stdlib / native platform?** Python standard library, plain ESM, CSS. No new
   dependency for what twenty lines cover.
5. **One line?** One line.
6. **Only then:** the minimum new code.

Never build: a generic workflow engine, a second project database, a custom
OAuth client, auto-commit/auto-push, background notifications, or a config knob
for a value that never changes.

Mark a deliberate corner-cut with a `ponytail:` comment naming the ceiling and
the upgrade path.

## 2. Pick the extension surface in this order

Hermes-native first. Reach for the earliest surface that fits.

| Order | Surface | Use when | Lives in |
|---|---|---|---|
| 1 | **Built-in feature** | Hermes already ships it (Kanban, cron, Projects, sessions, themes) | config / CLI only |
| 2 | **Config + skin/theme** | Appearance or defaults | `dashboard-themes/`, `skins/` |
| 3 | **Skill** | A repeatable procedure *you* perform | `~/.hermes/skills/` (not this repo) |
| 4 | **Script + cron** | Scheduled, no reasoning needed | `scripts/` + `hermes cron create --no-agent` |
| 5 | **Hook** | React to an inbound event (message, tool call) | `hooks/<name>/` |
| 6 | **Desktop plugin** | New UI surface in Hermes Desktop | `desktop-plugins/<name>/plugin.js` |
| 7 | **Backend plugin** | The UI needs scoped server-side data | `plugins/<name>/` |
| 8 | **MCP server** | An external service with an existing maintained server | `setup_mcp` tool, pinned version |
| 9 | **Source patch** | Nothing above can reach it | `patches/*.patch` |

Rules that go with the table:

- A **skill** encodes a procedure; a **script** encodes a job. If a model must
  reason each run, it is a skill or an agent cron job. If the output is
  deterministic, it is `--no-agent`.
- **Never write an MCP server.** Use an existing maintained one, pinned to an
  exact version, read-only where possible, with an explicit tool allowlist. Get
  approval before installing or authenticating anything that touches an account.
- **A source patch is the last resort.** Every patch is debt: `hermes update`
  reverts it and `scripts/reapply-desktop-patch.sh` has to reconcile it back.
  Keep patches tiny and generic. Keep `apps/desktop/index.html` out of them.
  If a change can be a plugin, it is a plugin.
- **Patches are temporary; native always wins.** Every `patches/*.patch` is a
  stopgap until Hermes ships the feature natively. After an update, run the
  stock build first. When a patch conflicts with new upstream code, adapt the
  patch to the native implementation — never force our old version over it —
  and drop any hunk upstream has made redundant. Reapplying a patch after an
  update is a deliberate decision, not an automatic step.
- Anything installable goes through `install.sh`. One installer, idempotent,
  honouring `HERMES_HOME` / `HERMES_SOURCE_DIR`. New surfaces are **opt-in via a
  flag** (see `--enable-project-kanban`) unless the user asks for them on by
  default.

## 3. UI work: MVP → feedback → plan → build

Any change to a visible surface — a new pane, a dashboard, a layout, an
information hierarchy — follows this sequence. Do not skip to implementation.

1. **MVP.** One disposable standalone HTML file at
   `sketches/<name>/index.html`. Local CSS/JS, synthetic and visibly-labelled
   fixture data, no production imports, no network, no build step. It must open
   with a double-click.
2. **Human feedback.** Show it and ask for one decision: approve / correct /
   reject. Keep the review to 5–7 visible actions. Two interaction defects means
   stop, batch the findings, fix once, and replay the same script — never
   live-patch screenshot by screenshot.
3. **Plan.** Only after approval, write `docs/plans/<YYYY-MM-DD_HHMMSS>-<name>.md`
   with goal, non-goals, the frozen interaction contract, vertical slices, and
   per-slice verification. Planning proves nothing; it authorizes nothing on its
   own.
4. **Build.** One vertical slice at a time. Reimplement through real Hermes
   components — the sketch is evidence, not a codebase to harden.

Approval of a sketch approves *direction only*. It never authorizes schema,
auth, network access, a dependency, a runtime job, or a deploy.

## 4. Always self-check, including visually

Nothing is done because it was written. It is done because it was run.

**Every change:**

```bash
~/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests
node --test tests/*.test.mjs        # the glob matters; `tests/` alone fails
```

Both suites must be green before you report success. Non-trivial logic leaves
one runnable check behind — no fixtures or frameworks unless asked.

**Installer changes:** run `install.sh` against a temporary `HERMES_HOME`, then
run it twice to prove idempotence.

**UI changes — visual self-check is mandatory:**

1. Reload desktop plugins (command palette) or restart the packaged app.
2. Open the surface and capture it with `computer_use action='capture'`.
3. **Look at the screenshot yourself** and compare it against the approved
   `sketches/` MVP: same hierarchy, same regions, same labels, same primary
   actions. Note any divergence explicitly instead of hoping it is unnoticed.
4. Check the states that are easy to skip: empty, loading, failure, narrow
   layout, keyboard-only.

A passing test suite does not mean the surface renders. An embedded browser
does not mean the packaged app works. Say what each check *cannot* prove.

## 5. Repository conventions

- **Layout:** `dashboard-themes/` `skins/` `desktop-plugins/` `plugins/`
  `hooks/` `scripts/` `patches/` `sketches/` `docs/plans/` `tests/`
  `web-report/`. Put new work in an existing directory before inventing one.
- **Naming:** kebab-case directories; the plugin id, route, directory, and
  sidebar label all agree.
- **Commits:** lowercase `feat:` / `fix:` / `docs:` / `chore:` plus an
  imperative summary. **Never commit or push without an explicit request.**
- **Secrets:** no tokens, keys, sessions, raw message bodies, transcripts, or
  machine-specific launchers — ever. Machine-specific values are environment
  variables (`TODO_MACHINE`, `TELEGRAM_CAPTURE_USERS`, `GITHUB_TOKEN`) read from
  `.env`, documented in `README.md`, never committed.
- **Private data** lives in the separate Obsidian vault, not here.
- **Documentation:** anything a second machine needs to reproduce goes in
  `README.md` in the same change that adds it. An undocumented customization is
  a customization that dies at the next reinstall.

## 6. Before you report done

- [ ] The laziest rung that works was taken, and skipped alternatives are named
      in one line.
- [ ] The extension surface is the earliest one from §2 that fits.
- [ ] UI work has an approved `sketches/` MVP and a plan behind it.
- [ ] Both test suites ran and are green — output pasted, not paraphrased.
- [ ] UI work has a screenshot the agent actually looked at, compared against
      the MVP.
- [ ] `install.sh` covers anything installable, and is idempotent.
- [ ] `README.md` reflects the change.
- [ ] No secrets. Nothing committed or pushed unasked.

## 7. Patch status vs native Hermes

Last verified 2026-08-30 against Hermes `4f2254350`. Re-verify after any
Hermes update: from the Hermes checkout, `git apply --check <patch>` succeeding
means the tree is unpatched and the patch is still needed; `git apply --check
--reverse` succeeding means it is applied. When a feature lands natively,
delete its section from the patch and update this table.

`patches/terminal-theme-fields.patch` — **still needed.**
`_normalise_theme_definition` in `hermes_cli/web_server.py` still strips
`terminalBackground` / `terminalForeground` from dashboard theme data.

`patches/desktop-research-workflow.patch` — **still needed**, every remaining
section:

| Feature in patch | Native status |
|---|---|
| Five-project sidebar fold (`foldProjectOverview` + show-more footer) | Absent upstream |
| Project reorder keeps unlisted projects (`reorderProjects` append) | Absent — upstream still persists only the dragged ids |
| Profile avatar + nickname identity (`profile-identity.ts`, `profile-avatar.tsx`, rail, session rows, `global.d.ts`) | Absent — neither file exists upstream |
| Sidebar-wide fleet roster mount (`useFleetRoster(true)` in `sidebar/index.tsx`) | Absent — roster refresh is still fleet-conditional |
| Sidebar icon sizing tweak (`size-4` → `size-5`) | Absent |
| Profile-switch StrictMode fix (`use-on-profile-switch.ts` + test) | Absent — first-effect ref bug still upstream |
| Folded live tool runs (ticker removal in `fallback.tsx` + tests) | Absent — `run-ticker.tsx` still wired in |
| Narrower sash grab band (`tree-split.tsx`) | Absent — still 8px |
| Reasoning collapsed by default (`reasoning-disclosure.ts`) | Absent — default still `false` |
| Terminal theme fields in `web_server.py` (+ test) | Absent — duplicate of `terminal-theme-fields.patch` |

Removed from the patch because native Hermes covers the need:

| Former feature | Why removed |
|---|---|
| Context-usage ring, always visible | Native meter + panel exist; text-based, hidden by default — enable per machine via status-bar right-click |
| `desktop_*` skin color overrides (`skin.ts`) | Native cross-surface skin SDK loads Light Lab; the yaml's `desktop_*` keys are ignored, surfaces derive from base colors |
| Three-line composer min-height (`styles.css`) | Dropped by choice; native one-line composer grows as you type |
