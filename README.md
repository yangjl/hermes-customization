# Hermes Customizations

Personal dashboard customizations for Hermes that live outside the Hermes
source checkout and can be reinstalled after an update.

New here? `AGENTS.md` is the rulebook: how to choose an extension surface, when
a change needs a visual MVP first, and what must be verified before anything is
called done. Read it before adding a customization.

## Contents

- `AGENTS.md` — rules every agent follows when extending this repository.
- `dashboard-themes/hermes-focus.yaml` — the recommended agent-workbench theme.
- `dashboard-themes/light-lab.yaml` — the original VS Code-inspired light theme.
- `skins/vscode-light-lab.yaml` — the shared CLI, TUI, and Desktop Light Lab skin.
- `desktop-plugins/research-dashboard/plugin.js` — daily Research dashboard for Hermes Desktop.
- `desktop-plugins/project-kanban/plugin.js` — Project Kanban pane (opt-in).
- `plugins/project-kanban/` — scoped backend for the Project Kanban pane.
- `sketches/` — disposable visual MVPs; approved before a UI surface is built.
- `web-report/index.html` — content-rich Research portfolio report.
- `docs/hermes-focus-design.md` — audit, design rationale, and validation plan.
- `plugins/` — backend (web-dashboard) plugins.
- `scripts/refresh-todo-vault.py` — deterministic device-observation publisher for Project Kanban.
- `scripts/reapply-desktop-patch.sh` — restores the Desktop patch after a Hermes update.
- `scripts/harden-hermes-python-env.sh` — strips `__PYVENV_LAUNCHER__` from Hermes'
  Python entry points so Desktop boots and `hermes update` survive macOS
  framework-Python environment pollution (run by reapply-desktop-patch.sh).
- `hooks/telegram-idea-capture/` — turns a Telegram message into an inbox card.
- `patches/terminal-theme-fields.patch` — temporary compatibility patch for
  Hermes versions that omit custom terminal colors from dashboard theme data.
- `patches/desktop-research-workflow.patch` — portable Desktop source changes:
  five-project recent list, panel sizing, profile switching, and tests. The
  context meter and cross-surface skin support are native Hermes now and no
  longer patched; the skin's `desktop_*` color overrides are ignored by the
  native skin SDK. The three-line composer sizing was dropped as well.
- `install.sh` — installs and activates the theme.
- `install-desktop-app.sh` — packages, installs, pins, and opens a standalone
  macOS `Hermes.app`.

## Install

```bash
./install.sh
```

This installs the dashboard themes, Light Lab skin, Research Desktop plugin,
Research web report, and project-observation script under
`${HERMES_HOME:-$HOME/.hermes}/`. It activates `hermes-focus` for the browser
dashboard and `vscode-light-lab` for Hermes Desktop, CLI, and TUI.

The installed Research report is:

```text
${HERMES_HOME:-$HOME/.hermes}/research-report/index.html
```

To keep the original Light Lab theme active:

```bash
./install.sh --theme light-lab
```

Older Hermes versions need the optional compatibility patch before the light
terminal background can take effect:

```bash
./install.sh --with-terminal-patch
```

The patch is applied only when needed and when it applies cleanly. It is kept
separate because source-tree patches can conflict with future Hermes updates.
Once Hermes includes the fix upstream, use the normal `./install.sh` path.

To reproduce the complete customized Desktop workflow:

```bash
./install.sh --theme light-lab --with-desktop-patch --install-desktop-app
```

The Desktop patch already contains the terminal-theme fix, so do not combine
`--with-desktop-patch` with `--with-terminal-patch`. Source patches are tied to
the Hermes version they were created from; the installer checks compatibility
before applying anything. `--install-desktop-app` then builds a standalone
macOS application, installs it at `/Applications/Hermes.app`, replaces a stale
development Electron icon in the Dock, and opens Hermes.

The desktop application step can also be run independently after a Hermes
update or source change:

```bash
./install-desktop-app.sh
```

Use an existing package, choose another application location, or leave the
Dock and launch state unchanged when needed:

```bash
./install-desktop-app.sh --skip-build --target "$HOME/Applications/Hermes.app" \
  --no-dock --no-open
```

The packaged app is a local development build. It is not signed or notarized
for distribution.

Use the packaged `/Applications/Hermes.app` for daily work. The Vite/Electron
development window hot-reloads every intermediate source save and can briefly
remount or black out while core Desktop files are being edited.

`install-desktop-app.sh` also verifies the pinned `get-windows` native optional
dependency before packaging. On a Command Line Tools-only Mac whose compiler is
present but whose Apple installer receipt is missing, it uses a temporary
`xcodebuild -version` shim for that one native build. It does not modify system
receipts, package manifests, or the lockfile.

Override install locations when needed:

```bash
HERMES_HOME=/path/to/hermes-home \
HERMES_SOURCE_DIR=/path/to/hermes-agent \
HERMES_DESKTOP_APP_TARGET=/path/to/Applications/Hermes.app \
./install.sh --theme light-lab --with-desktop-patch --install-desktop-app
```

Refresh the dashboard after installation. If the compatibility patch was
newly applied, restart `hermes dashboard` as well.

## Surviving a Hermes update

`hermes update` autostashes local source changes, fast-forwards, and rebuilds
the Desktop app from the clean tree. The customizations are a source patch, so
every update silently ships a Hermes without them — the context meter, composer
sizing, and profile switching all revert, and the stashed copy is easy to miss.

`scripts/reapply-desktop-patch.sh` reconciles the tree back. It reapplies the
patch with a three-way merge, rebuilds the app, and reinstalls it. It exits
silently when the patch is already present, and it refuses to touch a source
tree with uncommitted changes rather than tangling work in progress.

Schedule it weekly, before the work week:

```bash
hermes cron create "0 6 * * 1" --no-agent \
  --script reapply-desktop-patch.sh \
  --name "Restore Desktop patch after Hermes update"
```

Weekly matches how often updates actually land. Checking more often does not
help: the reverted Hermes is only visible while using Desktop, seeing either
version takes a restart regardless, and a firing run means an unattended
multi-minute Electron build that swaps `/Applications/Hermes.app`. Monday at
6am puts that build before you sit down instead of in the middle of a session.
Run it by hand when an update lands mid-week:

```bash
./scripts/reapply-desktop-patch.sh
```

When Hermes changes the same lines the patch touches, the three-way merge fails
and the script restores the tree untouched rather than leaving conflict markers
in place. That is the signal to resolve the conflict by hand and regenerate:

```bash
cd "${HERMES_SOURCE_DIR:-$HOME/.hermes/hermes-agent}"
git apply --3way /path/to/patches/desktop-research-workflow.patch
# resolve the conflicted files, then:
git add -A && git reset apps/desktop/index.html
git diff --cached --binary > /path/to/patches/desktop-research-workflow.patch
git reset
```

Keep `apps/desktop/index.html` out of the patch. A packaged build rewrites it
with hashed asset paths, and capturing that makes the patch reinstall one
build's bundle names into the next build's source.

No model runs for this job — the script is the job, and it only speaks when it
did something. It fires only while the gateway is running
(`hermes gateway start`).

## Todo MVP

Hermes already ships a durable Kanban board, so the Todo MVP uses that instead
of maintaining a second task database or plugin. Enable **Kanban** under
**Settings → Plugins**, then open **Kanban** from the sidebar. This machine uses
the `todos` board, displayed as **Todo Dashboard**; add fields or integrations
only after the native board proves insufficient.

Create the board once per machine:

```bash
hermes kanban boards create todos --name "Todo Dashboard" --switch
```

Boards are SQLite and single-host, so they do not sync. Each machine keeps its
own; the office Desktop holds the main one.

## Project vault

Project knowledge lives in a separate private Obsidian vault
(`yangjl/todo-list`), cloned to `~/Documents/WikiHub/todo-list`. Notes and
inventories stay out of this repository.

Project Kanban v2 has four explicit authorities:

```text
Obsidian canonical project note = project status, goal, next action, blocker
Native Hermes `todos` board    = local action workflow
GitHub                         = development activity evidence
Device observation snapshot   = latest local Git evidence
Office Desktop `inbox` board  = capture and candidate review
```

A managed project is an active note under `Projects/` with unique frontmatter:

```yaml
project_id: stable-kebab-case-id
knowledge_status: active
project_category: main-research # or student-projects / systems-admin
github_repo: owner/repository   # optional
```

The note body uses `## Goal`, `## Next action`, and `## Blocker`. Obsidian is
authoritative: GitHub pushes and local Git state never overwrite these fields.
Notes without a valid `project_id` or any required heading are excluded with a
validation warning; they are not projects or action targets in this UI.
Heading matching is case-insensitive and tolerates any whitespace after `##`
(extra spaces or a tab).
A `project_id` claimed by more than one active note is ambiguous: **every**
claimant is excluded and warned, so an ambiguous ID can never be linked to an
action — even when only one of the claimants is otherwise valid.

`scripts/refresh-todo-vault.py` without arguments feeds the Office Desktop's
immediate project folders into canonical Obsidian notes under `Projects/Desktop/`:

- `~/Documents/projects` → `main-research`
- `~/Documents/coworkers` → `student-projects`
- `~/Documents/website` → `systems-admin`

Activity is the newer of the latest local Git commit anywhere inside the
immediate folder and the latest matching GitHub push. Only projects active in
the last 90 days are automatically marked `knowledge_status: active`; older or
undated projects remain `unreviewed` and therefore stay out of the Project
Kanban API. Refreshes update generated frontmatter while preserving each note's
human-authored Goal, Next action, Blocker, and other body content.

Run the project-note sync by hand:

```bash
"${HERMES_HOME:-$HOME/.hermes}/hermes-agent/venv/bin/python" \
"${HERMES_HOME:-$HOME/.hermes}/scripts/refresh-todo-vault.py"
```

The optional `--publish-observations` mode writes one allowlisted JSON record to
`Observations/devices/$TODO_MACHINE.json`. The snapshot contains only stable
project IDs, normalized GitHub repositories, commit/activity timestamps, short
checked-out HEAD IDs, and dirty/ahead/behind counts. It contains no local paths,
usernames, tokens, task bodies, or transcripts. The script stages and commits
only that one snapshot path, then pushes it. Before staging, it fetches and
aborts with an actionable error if the vault is behind upstream; it never pulls,
rebases, stashes, or merges unrelated vault work. Any local commits already
ahead must be observation-only commits for that same device path. The publisher
validates every pending and newly created snapshot blob against the exact
allowlisted schema, then pushes the validated commit ID explicitly, so unsafe
history or a concurrent local commit cannot ride along. It never creates Kanban
cards.

Run the observation publisher by hand:

```bash
"${HERMES_HOME:-$HOME/.hermes}/hermes-agent/venv/bin/python" \
"${HERMES_HOME:-$HOME/.hermes}/scripts/refresh-todo-vault.py" \
--publish-observations
```

The weekday project-note job runs the no-argument command at 8:00 AM Monday
through Friday. It is deterministic and no-agent. `TODO_MACHINE` is required
only for the optional observation publisher; `TODO_VAULT` changes the vault
location, and `TODO_PROJECT_MAP` optionally maps a machine-local non-Git folder
path to a canonical `project_id`. Reading private repository activity uses
tokens from `.env` when present and otherwise reuses the authenticated `gh` CLI
session. If an observation push loses a race, the scoped observation commit
stays local: reconcile the vault with `git pull --rebase`, then rerun the
publisher; an unchanged snapshot retries the pending push.

## Capturing ideas from Telegram

Not every idea is a repository. `hooks/telegram-idea-capture/` catches the ones
that arrive while you are away from a keyboard: message the bot `idea: …` and
the text becomes a card on a separate `inbox` board.

It is capture-only. No model runs, nothing is interpreted, and the card holds
what you typed verbatim — deciding what an idea means is something you do later,
against the board. Cards land in `todo` rather than `triage`, because a board
with `kanban.auto_decompose` enabled has a decomposer that would rewrite them.

The hook runs inside the gateway, so it only captures while the gateway is
running. That makes an always-on machine the right host.

Set up Telegram first (`hermes setup` walks through the BotFather token), then
add to `.env`:

```bash
TELEGRAM_CAPTURE_USERS=<your numeric Telegram user id>
```

Capture stays off until that line exists — a bot token is a public endpoint, so
the allowlist is the gate. Two optional settings: `TELEGRAM_CAPTURE_BOARD`
(default `inbox`) and `TELEGRAM_CAPTURE_PREFIX` (default `idea:,todo:,note:`,
or `*` to capture every message). The board is created on first use.

Review what you captured with:

```bash
hermes kanban --board inbox list
```

## Verification

Both suites must pass before any change is considered done:

```bash
~/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests
node --test tests/*.test.mjs
```

The Node glob matters — `node --test tests/` fails on the Python files.

UI changes also need a visual check against the approved `sketches/` MVP; see
`AGENTS.md`.

## Project Kanban pane

An opt-in, Board-first Desktop pane over native Kanban actions and canonical
Obsidian projects. It has three views:

- **Board** — the four native action lanes; human cards move locally.
- **Projects** — one global, read-only project list with GitHub and “Last
  observed on” evidence. Projects are never grouped by device.
- **Office Inbox** — the real review queue only where the local `inbox` board
  exists; other machines show the office-host boundary instead of copying it.

New human actions select a canonical project. Their existing task-body metadata
stores `project_id`, while category is derived from the project note. Existing
unlinked v1 cards remain usable in **Legacy / unlinked**. Cards whose project is
inactive, missing, invalid, or no longer agrees with the stored task category
also move to that non-destructive reconciliation bucket. Board badges count the
actions visible across its lanes; Projects badges count canonical Obsidian
projects. Local lane moves, archives, and Inbox decisions are never written back
to Git.

Inbox accept and dismiss are scoped to exactly what the Inbox lists: one shared
eligibility rule governs listing, accepting, and dismissing. A blocked task must
carry the `review_candidate` metadata this plugin writes on capture, and a task
claimed by a worker is never a candidate. A task that is not visible in the
Inbox therefore cannot be mutated through it, and dismissing archives a card
without ever clearing another worker's lock.

Install it with the flag:

```bash
./install.sh --theme light-lab --enable-project-kanban
```

That enables the backend half and creates this machine's board **only when it
does not already exist**. `hermes kanban boards create` is idempotent and
rewrites a board's display name, so the installer lists boards first and leaves
an existing `todos` or `inbox` board — and any name you gave it — untouched. If
the board list cannot be read, or the CLI exits non-zero, the installer stops
rather than risk a rename.
The **Desktop**
half ships disabled — plugins under `~/.hermes/plugins/` are inventoried but
inert until allowlisted, and that toggle lives in the app's local storage, not
`config.yaml`, so the installer cannot set it. Turn it on once per machine:

**Settings → Plugins → Project Kanban**, then click **Kanban** in the sidebar.

The underlying action board may retain its machine-local display name, but the
product hierarchy is always **Project Kanban**. Device names appear only as
observation provenance. The Inbox board is created only on the Office Desktop;
boards are SQLite and gateway-local, and the pane deliberately does not sync
another machine's board.

## Set up another computer

1. Install Hermes and configure that computer's credentials normally.
2. Clone this private repository.
3. Run `./install.sh --theme light-lab --with-desktop-patch --install-desktop-app`.
4. If needed, use **Reload desktop plugins** from the command palette.

To bring the todo workflow along as well:

5. Create the board: `hermes kanban boards create todos --name "Todo Dashboard" --switch`.
6. Clone the vault into `~/Documents/WikiHub/`.
7. Set `TODO_MACHINE` to a name for this computer and schedule the weekday
   observation publisher.
8. Schedule the patch restore job so Hermes updates do not revert the Desktop
   customizations (see "Surviving a Hermes update").
9. For the Kanban pane, rerun the installer with `--enable-project-kanban` and
   toggle it on under **Settings → Plugins**.

API keys, tokens, sessions, and machine-specific launchers are intentionally
not stored in this repository.
