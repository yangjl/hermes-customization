#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hermes_root="${HERMES_HOME:-$HOME/.hermes}"
hermes_source="${HERMES_SOURCE_DIR:-$hermes_root/hermes-agent}"
theme_target_dir="$hermes_root/dashboard-themes"
skin_target_dir="$hermes_root/skins"
desktop_plugin_target_dir="$hermes_root/desktop-plugins/research-dashboard"
web_report_target_dir="$hermes_root/research-report"
script_target_dir="$hermes_root/scripts"
hook_target_dir="$hermes_root/hooks/telegram-idea-capture"
patch_file="$repo_dir/patches/terminal-theme-fields.patch"
desktop_patch_file="$repo_dir/patches/desktop-research-workflow.patch"
theme_name="hermes-focus"

usage() {
  echo "Usage: ./install.sh [--theme NAME] [--with-terminal-patch | --with-desktop-patch] [--install-desktop-app]"
  echo "Themes: hermes-focus (default), light-lab"
}

apply_terminal_patch=false
apply_desktop_patch=false
install_desktop_app=false
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

install -d "$web_report_target_dir"
install -m 0644 "$repo_dir/web-report/index.html" \
  "$web_report_target_dir/index.html"
echo "Installed Research web report to $web_report_target_dir"

install -d "$script_target_dir"
install -m 0755 "$repo_dir/scripts/refresh-todo-vault.py" \
  "$script_target_dir/refresh-todo-vault.py"
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
