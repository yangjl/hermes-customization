#!/usr/bin/env bash
# Restore profile avatars from this repo into the live Hermes profiles.
#
# Why this exists: the avatar is a backend profile asset at
# <HERMES_HOME>/profiles/<name>/assets/avatar.png. Nothing version-controls it,
# so anything that writes that path (the desktop avatar picker, a profile
# reset, a bad clone) silently replaces the image with a generated default and
# the only copy is gone. On 2026-09-04 mimi's avatar was overwritten this way.
#
# Keep one canonical copy per profile in assets/profile-avatars/<profile>.png
# and re-stamp it with this script. Idempotent: skips when the bytes match.
#
# ponytail: a flat name->file mapping, no manifest, no metadata. If a profile
# ever needs more than one asset, add the asset kind then — not before.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO_DIR/assets/profile-avatars"
HERMES_HOME_ROOT="${HERMES_HOME:-$HOME/.hermes}"
PROFILES_DIR="$HERMES_HOME_ROOT/profiles"

if [ ! -d "$SRC_DIR" ]; then
  echo "no avatars to restore: $SRC_DIR is missing" >&2
  exit 1
fi

shopt -s nullglob
avatars=("$SRC_DIR"/*.png)
if [ ${#avatars[@]} -eq 0 ]; then
  echo "no avatars to restore: $SRC_DIR is empty" >&2
  exit 1
fi

restored=0
skipped=0
missing=0

for src in "${avatars[@]}"; do
  profile="$(basename "$src" .png)"
  dest_dir="$PROFILES_DIR/$profile/assets"
  dest="$dest_dir/avatar.png"

  if [ ! -d "$PROFILES_DIR/$profile" ]; then
    echo "  skip   $profile — no such profile under $PROFILES_DIR"
    missing=$((missing + 1))
    continue
  fi

  if [ -f "$dest" ] && cmp -s "$src" "$dest"; then
    echo "  ok     $profile — already current"
    skipped=$((skipped + 1))
    continue
  fi

  mkdir -p "$dest_dir"
  # Keep whatever is there now; a wrong-but-wanted image beats no undo.
  if [ -f "$dest" ]; then
    cp "$dest" "$dest.replaced-$(date +%Y%m%d-%H%M%S).bak"
  fi
  cp "$src" "$dest"
  echo "  wrote  $profile — $(basename "$src") -> $dest"
  restored=$((restored + 1))
done

echo
echo "restored $restored, unchanged $skipped, absent profiles $missing"
[ "$restored" -gt 0 ] && echo "Reload the desktop window to repaint the rail."
exit 0
