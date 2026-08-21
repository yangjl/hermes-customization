#!/usr/bin/env bash
set -euo pipefail

hermes_root="${HERMES_HOME:-$HOME/.hermes}"
hermes_source="${HERMES_SOURCE_DIR:-$hermes_root/hermes-agent}"
install_target="${HERMES_DESKTOP_APP_TARGET:-/Applications/Hermes.app}"
build_app=true
update_dock=true
open_app=true

usage() {
  cat <<'EOF'
Usage: ./install-desktop-app.sh [OPTIONS]

Package and install Hermes Desktop as a standalone macOS application.

Options:
  --target PATH  Install at PATH (default: /Applications/Hermes.app)
  --skip-build   Install the existing packaged application
  --no-dock      Do not replace Hermes/Electron entries in the Dock
  --no-open      Do not open Hermes after installation
  -h, --help     Show this help

Environment overrides:
  HERMES_HOME
  HERMES_SOURCE_DIR
  HERMES_DESKTOP_APP_TARGET
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      install_target="$2"
      shift 2
      ;;
    --skip-build)
      build_app=false
      shift
      ;;
    --no-dock)
      update_dock=false
      shift
      ;;
    --no-open)
      open_app=false
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

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Hermes Desktop application installation is supported only on macOS." >&2
  exit 1
fi

if [[ ! -f "$hermes_source/apps/desktop/package.json" ]]; then
  echo "Hermes Desktop source not found at $hermes_source/apps/desktop" >&2
  exit 1
fi

if [[ "$install_target" != /* || "$install_target" != *.app ]]; then
  echo "Desktop install target must be an absolute .app path: $install_target" >&2
  exit 2
fi

if "$build_app"; then
  echo "Packaging Hermes Desktop from $hermes_source"
  npm --prefix "$hermes_source" run pack --workspace apps/desktop
fi

case "$(uname -m)" in
  arm64)
    package_dir="mac-arm64"
    ;;
  x86_64)
    package_dir="mac"
    if [[ ! -d "$hermes_source/apps/desktop/release/mac/Hermes.app" ]] && \
      [[ -d "$hermes_source/apps/desktop/release/mac-x64/Hermes.app" ]]; then
      package_dir="mac-x64"
    fi
    ;;
  *)
    echo "Unsupported macOS architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

packaged_app="$hermes_source/apps/desktop/release/$package_dir/Hermes.app"
if [[ ! -d "$packaged_app" ]]; then
  echo "Packaged Hermes application not found at $packaged_app" >&2
  echo "Run again without --skip-build, or inspect apps/desktop/release." >&2
  exit 1
fi

install_parent="$(dirname "$install_target")"
mkdir -p "$install_parent"
ditto "$packaged_app" "$install_target"

bundle_id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' \
  "$install_target/Contents/Info.plist")"
if [[ "$bundle_id" != "com.nousresearch.hermes" ]]; then
  echo "Installed application has unexpected bundle identifier: $bundle_id" >&2
  exit 1
fi
echo "Installed Hermes Desktop at $install_target"

repair_dock() {
  local dock_plist_tmp
  local bundle_identifier
  local file_url
  local i
  local j
  local next_index
  local app_url
  local -a remove_indexes=()

  dock_plist_tmp="$(mktemp "${TMPDIR:-/private/tmp}/hermes-dock.XXXXXX.plist")"
  if ! defaults export com.apple.dock "$dock_plist_tmp"; then
    echo "Could not read Dock preferences; leaving the Dock unchanged." >&2
    rm -f "$dock_plist_tmp"
    return 0
  fi

  i=0
  while /usr/libexec/PlistBuddy -c "Print :persistent-apps:$i" \
    "$dock_plist_tmp" >/dev/null 2>&1; do
    bundle_identifier="$(/usr/libexec/PlistBuddy \
      -c "Print :persistent-apps:$i:tile-data:bundle-identifier" \
      "$dock_plist_tmp" 2>/dev/null || true)"
    file_url="$(/usr/libexec/PlistBuddy \
      -c "Print :persistent-apps:$i:tile-data:file-data:_CFURLString" \
      "$dock_plist_tmp" 2>/dev/null || true)"

    if [[ "$bundle_identifier" == "com.nousresearch.hermes" ]] || \
      { [[ "$bundle_identifier" == "com.github.Electron" ]] && \
        [[ "$file_url" == *"/apps/desktop/node_modules/electron/dist/Electron.app/"* ]]; }; then
      remove_indexes+=("$i")
    fi
    i=$((i + 1))
  done

  for ((j=${#remove_indexes[@]} - 1; j >= 0; j--)); do
    /usr/libexec/PlistBuddy \
      -c "Delete :persistent-apps:${remove_indexes[$j]}" "$dock_plist_tmp"
  done

  next_index=0
  while /usr/libexec/PlistBuddy -c "Print :persistent-apps:$next_index" \
    "$dock_plist_tmp" >/dev/null 2>&1; do
    next_index=$((next_index + 1))
  done

  app_url="file://$install_target/"
  app_url="${app_url// /%20}"
  /usr/libexec/PlistBuddy -c "Add :persistent-apps:$next_index dict" "$dock_plist_tmp"
  /usr/libexec/PlistBuddy -c "Add :persistent-apps:$next_index:tile-data dict" "$dock_plist_tmp"
  /usr/libexec/PlistBuddy -c "Add :persistent-apps:$next_index:tile-data:bundle-identifier string com.nousresearch.hermes" "$dock_plist_tmp"
  /usr/libexec/PlistBuddy -c "Add :persistent-apps:$next_index:tile-data:file-data dict" "$dock_plist_tmp"
  /usr/libexec/PlistBuddy -c "Add :persistent-apps:$next_index:tile-data:file-data:_CFURLString string $app_url" "$dock_plist_tmp"
  /usr/libexec/PlistBuddy -c "Add :persistent-apps:$next_index:tile-data:file-data:_CFURLStringType integer 15" "$dock_plist_tmp"
  /usr/libexec/PlistBuddy -c "Add :persistent-apps:$next_index:tile-data:file-label string Hermes" "$dock_plist_tmp"
  /usr/libexec/PlistBuddy -c "Add :persistent-apps:$next_index:tile-type string file-tile" "$dock_plist_tmp"

  defaults import com.apple.dock "$dock_plist_tmp"
  rm -f "$dock_plist_tmp"
  killall Dock >/dev/null 2>&1 || true
  echo "Replaced stale Hermes/Electron Dock entries with $install_target"
}

if "$update_dock"; then
  repair_dock
fi

if "$open_app"; then
  open "$install_target"
  echo "Opened Hermes Desktop."
fi
