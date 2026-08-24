#!/usr/bin/env bash
# Restore the Desktop Research workflow patch after a Hermes update removed it.
#
# `hermes update` autostashes local source changes, fast-forwards, and rebuilds
# the Desktop app from the clean tree, so every update silently ships a Hermes
# without these customizations. This reconciles the tree back, whatever caused
# the drift.
#
# Silent when the patch is already applied, so it can run on a schedule without
# producing a notification on every tick.
set -euo pipefail

hermes_root="${HERMES_HOME:-$HOME/.hermes}"
hermes_source="${HERMES_SOURCE_DIR:-$hermes_root/hermes-agent}"

# Prefer a checkout this script is running from; fall back to the usual clone
# location, then to the installed copy's sibling repository.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="${HERMES_CUSTOMIZATION_DIR:-}"
if [[ -z "$repo_dir" ]]; then
  if [[ -f "$script_dir/../patches/desktop-research-workflow.patch" ]]; then
    repo_dir="$(cd "$script_dir/.." && pwd)"
  else
    repo_dir="$HOME/Documents/projects/hermes-customization"
  fi
fi

patch_file="$repo_dir/patches/desktop-research-workflow.patch"
installer="$repo_dir/install-desktop-app.sh"

fail() {
  echo "reapply-desktop-patch: $*" >&2
  exit 1
}

[[ -f "$patch_file" ]] || fail "patch not found at $patch_file"
[[ -d "$hermes_source/.git" ]] || fail "Hermes source not found at $hermes_source"

cd "$hermes_source"

# Already applied: nothing to say. This is the common case on every tick.
if git apply --reverse --check "$patch_file" >/dev/null 2>&1; then
  exit 0
fi

# Only reconcile a tree we did not partially modify ourselves. A dirty tree
# means someone is mid-edit; reapplying on top would tangle their work.
if [[ -n "$(git status --porcelain)" ]]; then
  fail "Hermes source has uncommitted changes; reapply skipped. Inspect $hermes_source"
fi

if ! git apply --3way "$patch_file" >/dev/null 2>&1; then
  if [[ -n "$(git status --porcelain)" ]]; then
    # --3way leaves conflict markers in the tree on failure. Put the source
    # back the way we found it rather than leaving Hermes unbuildable.
    git checkout -- . >/dev/null 2>&1 || true
    git clean -fd >/dev/null 2>&1 || true
  fi
  fail "patch no longer applies to this Hermes version; resolve by hand against $patch_file"
fi

echo "Reapplied Desktop Research workflow patch after a Hermes update."

# The patch is only half the job — the installed app was packaged from the
# unpatched tree and still needs replacing.
if [[ -x "$installer" ]]; then
  if HERMES_HOME="$hermes_root" HERMES_SOURCE_DIR="$hermes_source" \
    "$installer" --no-open >/tmp/reapply-desktop-patch-build.log 2>&1; then
    echo "Rebuilt and reinstalled Hermes Desktop. Restart Hermes to load it."
  else
    echo "Patch restored, but the Desktop rebuild failed."
    echo "Log: /tmp/reapply-desktop-patch-build.log"
    exit 1
  fi
else
  echo "Run $installer to rebuild the Desktop app."
fi
