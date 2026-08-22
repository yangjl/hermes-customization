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
and Research web report under `${HERMES_HOME:-$HOME/.hermes}/`. It activates
`hermes-focus` for the browser dashboard and `vscode-light-lab` for Hermes
Desktop, CLI, and TUI.

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

Project knowledge lives in an Obsidian vault rather than in this repository, so
notes and inventories stay out of version control.

## Set up another computer

1. Install Hermes and configure that computer's credentials normally.
2. Clone this private repository.
3. Run `./install.sh --theme light-lab --with-desktop-patch --install-desktop-app`.
4. If needed, use **Reload desktop plugins** from the command palette.

API keys, tokens, sessions, and machine-specific launchers are intentionally
not stored in this repository.
