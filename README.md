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
- `scripts/refresh-todo-vault.py` — weekly refresh for the Obsidian project vault.
- `scripts/reapply-desktop-patch.sh` — restores the Desktop patch after a Hermes update.
- `hooks/telegram-idea-capture/` — turns a Telegram message into an inbox card.
- `patches/terminal-theme-fields.patch` — temporary compatibility patch for
  Hermes versions that omit custom terminal colors from dashboard theme data.
- `patches/desktop-research-workflow.patch` — portable Desktop source changes:
  larger composer, context-usage indicator, five-project recent list, panel
  sizing, profile switching, Light Lab integration, and tests.
- `install.sh` — installs and activates the theme.
- `install-desktop-app.sh` — packages, installs, pins, and opens a standalone
  macOS `Hermes.app`.

## Install

```bash
./install.sh
```

This installs the dashboard themes, Light Lab skin, Research Desktop plugin,
Research web report, and vault refresh script under
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

`scripts/refresh-todo-vault.py` keeps that vault current. Each run reads
repository metadata from the GitHub API for the tracked accounts, scans this
machine's project folders, rewrites the inventory notes, then commits and pushes
the vault. It never clones a repository.

It raises a Kanban card when a repository whose note says
`knowledge_status: active` has been pushed since the previous run. Reviewing a
project is therefore what opts it into the board; unreviewed repositories stay
silent however often they are pushed. An idempotency key holds this to one card
per repository per calendar month, so a busy week cannot flood the board.

Run it by hand:

```bash
"${HERMES_HOME:-$HOME/.hermes}/hermes-agent/venv/bin/python" \
  "${HERMES_HOME:-$HOME/.hermes}/scripts/refresh-todo-vault.py"
```

Or schedule it weekly:

```bash
hermes cron create "0 15 * * 0" "Summarize the refresh output above." \
  --script refresh-todo-vault.py --name "Weekly todo vault refresh"
```

Four environment variables change its behavior. `TODO_MACHINE` names the vault
folder that receives this machine's local scans, so two machines never overwrite
each other. `TODO_VAULT` points at a vault somewhere other than the default
path. `TODO_BOARD` selects the Kanban board, and `TODO_CARDS=0` turns card
creation off for a run. Reading private repositories needs a `GITHUB_TOKEN` in
`.env` with metadata read access; the script also accepts `GITHUB_TOKEN_<NAME>`
for several accounts.

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

An opt-in Desktop pane over the native Kanban boards, with a review Inbox.
Install it with the flag:

```bash
./install.sh --theme light-lab --enable-project-kanban
```

That enables the backend half and creates this machine's board. The **Desktop**
half ships disabled — plugins under `~/.hermes/plugins/` are inventoried but
inert until allowlisted, and that toggle lives in the app's local storage, not
`config.yaml`, so the installer cannot set it. Turn it on once per machine:

**Settings → Plugins → Project Kanban**, then click **Kanban** in the sidebar.

The board is named after the machine: `Office Desktop` or `MacBook`. The
Inbox board is created only on the Office Desktop, so the Inbox tab elsewhere
reads "Inbox unavailable" — boards are SQLite and gateway-local, and the pane
deliberately does not sync another machine's board.

## Set up another computer

1. Install Hermes and configure that computer's credentials normally.
2. Clone this private repository.
3. Run `./install.sh --theme light-lab --with-desktop-patch --install-desktop-app`.
4. If needed, use **Reload desktop plugins** from the command palette.

To bring the todo workflow along as well:

5. Create the board: `hermes kanban boards create todos --name "Todo Dashboard" --switch`.
6. Clone the vault into `~/Documents/WikiHub/`.
7. Set `TODO_MACHINE` to a name for this computer and schedule the weekly refresh.
8. Schedule the patch restore job so Hermes updates do not revert the Desktop
   customizations (see "Surviving a Hermes update").
9. For the Kanban pane, rerun the installer with `--enable-project-kanban` and
   toggle it on under **Settings → Plugins**.

API keys, tokens, sessions, and machine-specific launchers are intentionally
not stored in this repository.
