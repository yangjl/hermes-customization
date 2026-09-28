#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hermes_root="${HERMES_HOME:-$HOME/.hermes}"
hermes_source="${HERMES_SOURCE_DIR:-$hermes_root/hermes-agent}"
theme_target_dir="$hermes_root/dashboard-themes"
skin_target_dir="$hermes_root/skins"
desktop_plugin_target_dir="$hermes_root/desktop-plugins/research-dashboard"
kanban_desktop_target_dir="$hermes_root/desktop-plugins/project-kanban"
kanban_backend_target_dir="$hermes_root/plugins/project-kanban"
web_report_target_dir="$hermes_root/research-report"
script_target_dir="$hermes_root/scripts"
hook_target_dir="$hermes_root/hooks/telegram-idea-capture"
patch_file="$repo_dir/patches/terminal-theme-fields.patch"
desktop_patch_file="$repo_dir/patches/desktop-research-workflow.patch"
theme_name="hermes-focus"

usage() {
  echo "Usage: ./install.sh [--theme NAME] [--enable-project-kanban] [--harden-shell] [--with-terminal-patch | --with-desktop-patch] [--install-desktop-app]"
  echo "Themes: hermes-focus (default), light-lab"
  echo "Codex only: ./install.sh --codex-dbtl-only (register Research DBTL; leave Hermes unchanged)"
}

plugin_enabled() {
  # Same pipeline caveat as board_exists: capture first, so a non-zero `hermes`
  # exit is not masked by python's status and misreported as "not enabled".
  local listing
  listing="$(hermes plugins list --enabled --json 2>/dev/null)" || return 2
  printf '%s' "$listing" | python3 -c '
import json, sys
name = sys.argv[1]
try:
    rows = json.load(sys.stdin)
except ValueError:
    sys.exit(2)
if not isinstance(rows, list):
    sys.exit(2)
sys.exit(0 if any(isinstance(r, dict) and r.get("name") == name for r in rows) else 1)
' "$1"
}

board_exists() {
  # Capture the listing FIRST. As a pipeline this would run under `pipefail`,
  # where a non-zero `hermes` exit masks python's status — an existing board
  # would read as "absent" and fall through to the renaming create.
  local listing
  listing="$(hermes kanban boards list --json 2>/dev/null)" || return 2
  printf '%s' "$listing" | python3 -c '
import json, sys
slug = sys.argv[1]
try:
    rows = json.load(sys.stdin)
except ValueError:
    raise SystemExit(2)
if not isinstance(rows, list):
    raise SystemExit(2)
found = False
for row in rows:
    if not isinstance(row, dict):
        raise SystemExit(2)
    if row.get("slug") == slug:
        found = True
raise SystemExit(0 if found else 1)
' "$1"
}

# `hermes kanban boards create` is idempotent and rewrites board.json's display
# name, so an unconditional create would silently rename an existing board.
# List first; create only when the board is genuinely absent.
ensure_board() {
  local slug="$1"
  local name="$2"
  local status=0
  board_exists "$slug" || status=$?
  case "$status" in
    0)
      echo "Board $slug already exists; preserved its metadata."
      return 0
      ;;
    1) ;;
    *)
      echo "Could not read the board list; refusing to touch board $slug." >&2
      return 1
      ;;
  esac
  if hermes kanban boards create "$slug" --name "$name"; then
    return 0
  fi
  echo "Could not create required board $slug." >&2
  return 1
}

apply_terminal_patch=false
apply_desktop_patch=false
install_desktop_app=false
enable_project_kanban=false
harden_shell=false
codex_dbtl_only=false
hermes_option_given=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --codex-dbtl-only|-h|--help) ;;
    *) hermes_option_given=true ;;
  esac
  case "$1" in
    --codex-dbtl-only)
      codex_dbtl_only=true
      shift
      ;;
    --theme)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      theme_name="$2"
      shift 2
      ;;
    --with-terminal-patch)
      apply_terminal_patch=true
      shift
      ;;
    --with-desktop-patch)
      apply_desktop_patch=true
      shift
      ;;
    --install-desktop-app)
      install_desktop_app=true
      shift
      ;;
    --enable-project-kanban)
      enable_project_kanban=true
      shift
      ;;
    --harden-shell)
      harden_shell=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if "$codex_dbtl_only"; then
  if "$hermes_option_given"; then
    echo "Use --codex-dbtl-only without Hermes installation flags." >&2
    exit 2
  fi
  python3 - "$repo_dir" <<'PY'
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

source = Path(sys.argv[1]) / "plugins/research-dbtl"
parent = Path(os.environ.get("CODEX_PLUGIN_PARENT", str(Path.home() / "plugins"))).expanduser().resolve()
marketplace = Path(os.environ.get("CODEX_MARKETPLACE_PATH", str(Path.home() / ".agents/plugins/marketplace.json"))).expanduser().resolve()
creator = Path(os.environ.get("CODEX_PLUGIN_CREATOR", str(Path.home() / ".codex/skills/.system/plugin-creator/scripts/create_basic_plugin.py"))).expanduser()
reader = creator.with_name("read_marketplace_name.py")
destination = parent / "research-dbtl"
if not creator.is_file() or not reader.is_file():
    sys.exit("Codex plugin-creator is required. Set CODEX_PLUGIN_CREATOR to its scripts/create_basic_plugin.py, then retry.")
# The scaffold records ./plugins/research-dbtl relative to the marketplace root.
if marketplace.parts[-3:] != (".agents", "plugins", "marketplace.json") or parent != marketplace.parents[2] / "plugins":
    sys.exit("Use matching destinations: CODEX_PLUGIN_PARENT=<root>/plugins and CODEX_MARKETPLACE_PATH=<root>/.agents/plugins/marketplace.json.")
if destination.is_symlink():
    sys.exit("Refusing to overwrite a symlinked Research DBTL installation.")
for current, directories, files in os.walk(destination, followlinks=False):
    if any((Path(current) / name).is_symlink() for name in directories + files):
        sys.exit("Refusing to update Research DBTL containing nested symlinks; no files were changed.")
if source.resolve() == destination.resolve():
    sys.exit("Choose a CODEX_PLUGIN_PARENT outside this repository's plugin source.")
registered = False
if marketplace.exists():
    subprocess.run([sys.executable, str(reader), "--marketplace-path", str(marketplace)], check=True)
    data = json.loads(marketplace.read_text())
    entries = data.get("plugins")
    if not isinstance(entries, list):
        sys.exit("Marketplace plugins must be an array; no files were changed.")
    matches = [entry for entry in entries if isinstance(entry, dict) and entry.get("name") == "research-dbtl"]
    if len(matches) > 1:
        sys.exit("Duplicate Research DBTL marketplace entries; resolve them before installation.")
    if matches:
        if matches[0].get("source") != {"source": "local", "path": "./plugins/research-dbtl"}:
            sys.exit("Research DBTL already points at a different source; no files were changed.")
        registered = True
if not registered:
    # --force intentionally replaces only this plugin's scaffold manifest.
    subprocess.run([sys.executable, str(creator), "research-dbtl", "--path", str(parent),
                    "--with-marketplace", "--marketplace-path", str(marketplace), "--force"], check=True)
# ponytail: merge this package's files; obsolete-file removal needs an ownership manifest.
shutil.copytree(source, destination, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
print(f"Installed Research DBTL to {destination}")
print(f"Registered in {marketplace}; enable Research DBTL in Codex and start a fresh task.")
PY
  exit 0
fi

if "$apply_terminal_patch" && "$apply_desktop_patch"; then
  echo "Choose only one patch; the Desktop patch already includes the terminal theme fix." >&2
  exit 2
fi

theme_source="$repo_dir/dashboard-themes/$theme_name.yaml"
if [[ ! -f "$theme_source" ]]; then
  echo "Unknown theme: $theme_name" >&2
  usage >&2
  exit 2
fi

install -d "$theme_target_dir"
for source in "$repo_dir"/dashboard-themes/*.yaml; do
  install -m 0644 "$source" "$theme_target_dir/$(basename "$source")"
done
echo "Installed dashboard themes to $theme_target_dir"

install -d "$skin_target_dir"
install -m 0644 "$repo_dir/skins/vscode-light-lab.yaml" \
  "$skin_target_dir/vscode-light-lab.yaml"
echo "Installed Light Lab skin to $skin_target_dir"

install -d "$desktop_plugin_target_dir"
install -m 0644 "$repo_dir/desktop-plugins/research-dashboard/plugin.js" \
  "$desktop_plugin_target_dir/plugin.js"
echo "Installed Research Desktop plugin to $desktop_plugin_target_dir"

install -d "$kanban_desktop_target_dir"
install -m 0644 "$repo_dir/desktop-plugins/project-kanban/plugin.js" \
  "$kanban_desktop_target_dir/plugin.js"
install -d "$kanban_backend_target_dir/dashboard/dist"
install -m 0644 "$repo_dir/plugins/project-kanban/plugin.yaml" \
  "$kanban_backend_target_dir/plugin.yaml"
install -m 0644 "$repo_dir/plugins/project-kanban/__init__.py" \
  "$kanban_backend_target_dir/__init__.py"
install -m 0644 "$repo_dir/plugins/project-kanban/dashboard/manifest.json" \
  "$kanban_backend_target_dir/dashboard/manifest.json"
install -m 0644 "$repo_dir/plugins/project-kanban/dashboard/plugin_api.py" \
  "$kanban_backend_target_dir/dashboard/plugin_api.py"
install -m 0644 "$repo_dir/plugins/project-kanban/dashboard/dist/index.js" \
  "$kanban_backend_target_dir/dashboard/dist/index.js"
echo "Installed Project Kanban Desktop and backend plugins"

install -d "$web_report_target_dir"
install -m 0644 "$repo_dir/web-report/index.html" \
  "$web_report_target_dir/index.html"
echo "Installed Research web report to $web_report_target_dir"

install -d "$script_target_dir"
install -m 0755 "$repo_dir/scripts/refresh-todo-vault.py" \
  "$script_target_dir/refresh-todo-vault.py"
legacy_runner="$script_target_dir/sync-todo-kanban.py"
if [[ -e "$legacy_runner" ]]; then
  # Only remove the artifact this installer itself once shipped, recognized by
  # its own docstring. Anything else at that path is the user's file.
  if [[ -f "$legacy_runner" ]] && grep -qF \
    "Pull shared todo records into this machine's local Kanban board." \
    "$legacy_runner"; then
    rm -f "$legacy_runner"
    echo "Removed the obsolete sync-todo-kanban.py runner."
  else
    echo "Preserved unrecognized file at $legacy_runner; remove it yourself if it is obsolete." >&2
  fi
fi
install -m 0755 "$repo_dir/scripts/reapply-desktop-patch.sh" \
  "$script_target_dir/reapply-desktop-patch.sh"
install -m 0755 "$repo_dir/scripts/harden-hermes-python-env.sh" \
  "$script_target_dir/harden-hermes-python-env.sh"
install -m 0755 "$repo_dir/scripts/harden-shell-startup.sh" \
  "$script_target_dir/harden-shell-startup.sh"
echo "Installed vault refresh script to $script_target_dir"
echo "Installed Desktop patch restore script to $script_target_dir"
echo "Installed Hermes Python environment hardener to $script_target_dir"
echo "Installed shell startup hardener to $script_target_dir"

# The shell guard edits ~/.bashrc, so it is opt-in rather than automatic: a
# machine without Cortex XDR does not need it, and an rc file that exports PATH
# late needs a human to reorder it first (the script refuses and explains).
if "$harden_shell"; then
  "$script_target_dir/harden-shell-startup.sh" ||
    echo "Shell hardening declined — see the message above; ~/.bashrc is unchanged." >&2
else
  if ! "$script_target_dir/harden-shell-startup.sh" --check >/dev/null 2>&1; then
    echo "Tip: this machine's login shell is unguarded. If Cortex XDR kills Hermes," \
         "re-run with --harden-shell."
  fi
fi

install -d "$hook_target_dir"
install -m 0644 "$repo_dir/hooks/telegram-idea-capture/HOOK.yaml" \
  "$hook_target_dir/HOOK.yaml"
install -m 0644 "$repo_dir/hooks/telegram-idea-capture/handler.py" \
  "$hook_target_dir/handler.py"
echo "Installed Telegram capture hook to $hook_target_dir"

if command -v hermes >/dev/null 2>&1; then
  hermes config set dashboard.theme "$theme_name"
  hermes config set display.skin vscode-light-lab
  # Curated Projects, not a scan of the disk. Desktop otherwise auto-discovers
  # every git repo under $HOME and lists all of them in the sidebar (41 on this
  # machine), which buries the handful of projects actually being worked on.
  # Off means the sidebar shows only Projects added deliberately; Hermes clears
  # the cached scan rows itself when this policy changes.
  hermes config set desktop.repo_scan_enabled false
  # Profiles deliberately do not inherit the default profile's config. During
  # a normal install, apply this user-wide preference explicitly to every
  # existing profile. Skip that home-anchored sweep for an isolated/test
  # HERMES_HOME so the installer never reaches unrelated real profiles.
  if [[ -z "${HERMES_HOME:-}" || "$HERMES_HOME" == "$HOME/.hermes" ]]; then
    for profile_dir in "$HOME/.hermes/profiles"/*; do
      [[ -d "$profile_dir" ]] || continue
      hermes -p "$(basename "$profile_dir")" config set desktop.repo_scan_enabled false
    done
  fi

  if "$enable_project_kanban"; then
    hermes plugins enable project-kanban --no-allow-tool-override

    computer_name="${TODO_MACHINE_NAME:-}"
    if [[ -z "$computer_name" ]] && command -v scutil >/dev/null 2>&1; then
      computer_name="$(scutil --get ComputerName 2>/dev/null || true)"
    fi
    case "$computer_name" in
      *[Dd]esktop*) board_name="Office Desktop" ;;
      *) board_name="MacBook" ;;
    esac
    ensure_board todos "$board_name"
    if [[ "$board_name" == "Office Desktop" ]] && \
       ! ensure_board inbox Inbox; then
      exit 1
    fi
    echo "Activated Project Kanban for $board_name"
  elif plugin_enabled project-kanban; then
    # An earlier run already opted in. Saying "disabled" here reads as a failed
    # install; only the board setup was skipped.
    echo "Project Kanban already enabled; boards left untouched (pass --enable-project-kanban to reconcile them)."
  else
    echo "Project Kanban installed but disabled; rerun with --enable-project-kanban to opt in."
  fi
  echo "Activated dashboard theme: $theme_name"
  echo "Activated Hermes skin: vscode-light-lab"
else
  echo "Hermes CLI not found; select $theme_name and vscode-light-lab manually."
fi

if "$apply_terminal_patch"; then
  if [[ ! -d "$hermes_source/.git" ]]; then
    echo "Hermes source repository not found at $hermes_source" >&2
    exit 1
  fi

  if git -C "$hermes_source" apply --reverse --check "$patch_file" >/dev/null 2>&1; then
    echo "Terminal theme compatibility patch is already present."
  elif git -C "$hermes_source" apply --check "$patch_file" >/dev/null 2>&1; then
    git -C "$hermes_source" apply "$patch_file"
    echo "Applied terminal theme compatibility patch."
    echo "Restart hermes dashboard to load the patched backend."
  else
    echo "Compatibility patch does not apply cleanly; Hermes may already include the fix." >&2
    echo "Inspect $patch_file before changing the Hermes source tree." >&2
    exit 1
  fi
fi

if "$apply_desktop_patch"; then
  if [[ ! -d "$hermes_source/.git" ]]; then
    echo "Hermes source repository not found at $hermes_source" >&2
    exit 1
  fi

  if git -C "$hermes_source" apply --reverse --check "$desktop_patch_file" >/dev/null 2>&1; then
    echo "Desktop Research workflow patch is already present."
  elif git -C "$hermes_source" apply --check "$desktop_patch_file" >/dev/null 2>&1; then
    git -C "$hermes_source" apply "$desktop_patch_file"
    echo "Applied Desktop Research workflow patch."
    echo "Restart Hermes Desktop to load the patched interface."
  else
    echo "Desktop patch does not apply cleanly; the Hermes source version may differ." >&2
    echo "Inspect $desktop_patch_file before changing the Hermes source tree." >&2
    exit 1
  fi
fi

if "$install_desktop_app"; then
  HERMES_HOME="$hermes_root" HERMES_SOURCE_DIR="$hermes_source" \
    "$repo_dir/install-desktop-app.sh"
fi
