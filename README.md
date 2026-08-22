# Hermes Customizations

Personal dashboard customizations for Hermes that live outside the Hermes
source checkout and can be reinstalled after an update.

## Contents

- `dashboard-themes/hermes-focus.yaml` — the recommended agent-workbench theme.
- `dashboard-themes/light-lab.yaml` — the original VS Code-inspired light theme.
- `skins/vscode-light-lab.yaml` — the shared CLI, TUI, and Desktop Light Lab skin.
- `desktop-plugins/research-dashboard/plugin.js` — daily Research dashboard for Hermes Desktop.
- `web-report/index.html` — content-rich Research portfolio report.
- `docs/hermes-focus-design.md` — audit, design rationale, and validation plan.
- `plugins/` — reserved for web-dashboard plugins.
- `scripts/refresh-todo-vault.py` — weekly refresh for the Obsidian project vault.
- `patches/terminal-theme-fields.patch` — temporary compatibility patch for
  Hermes versions that omit custom terminal colors from dashboard theme data.
- `patches/desktop-research-workflow.patch` — portable Desktop source changes:
  larger composer, context-usage indicator, panel sizing, profile switching,
  Light Lab integration, and tests.
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

Override install locations when needed:

```bash
HERMES_HOME=/path/to/hermes-home \
HERMES_SOURCE_DIR=/path/to/hermes-agent \
HERMES_DESKTOP_APP_TARGET=/path/to/Applications/Hermes.app \
./install.sh --theme light-lab --with-desktop-patch --install-desktop-app
```

Refresh the dashboard after installation. If the compatibility patch was
newly applied, restart `hermes dashboard` as well.

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

## Set up another computer

1. Install Hermes and configure that computer's credentials normally.
2. Clone this private repository.
3. Run `./install.sh --theme light-lab --with-desktop-patch --install-desktop-app`.
4. If needed, use **Reload desktop plugins** from the command palette.

To bring the todo workflow along as well:

5. Create the board: `hermes kanban boards create todos --name "Todo Dashboard" --switch`.
6. Clone the vault into `~/Documents/WikiHub/`.
7. Set `TODO_MACHINE` to a name for this computer and schedule the weekly refresh.

API keys, tokens, sessions, and machine-specific launchers are intentionally
not stored in this repository.
