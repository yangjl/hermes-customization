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
  echo "Usage: ./install.sh [--theme NAME] [--enable-project-kanban] [--with-terminal-patch | --with-desktop-patch] [--install-desktop-app]"
  echo "Themes: hermes-focus (default), light-lab"
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
while [[ $# -gt 0 ]]; do
  case "$1" in
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
echo "Installed vault refresh script to $script_target_dir"
echo "Installed Desktop patch restore script to $script_target_dir"

install -d "$hook_target_dir"
install -m 0644 "$repo_dir/hooks/telegram-idea-capture/HOOK.yaml" \
  "$hook_target_dir/HOOK.yaml"
install -m 0644 "$repo_dir/hooks/telegram-idea-capture/handler.py" \
  "$hook_target_dir/handler.py"
echo "Installed Telegram capture hook to $hook_target_dir"

if command -v hermes >/dev/null 2>&1; then
  hermes config set dashboard.theme "$theme_name"
  hermes config set display.skin vscode-light-lab

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
