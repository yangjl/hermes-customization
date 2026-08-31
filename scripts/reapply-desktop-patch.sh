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
    repo_dir="$HOME/Documents/projects/hermes-customizations"
  fi
fi

# Every patch this repo overlays, in apply order. `terminal-theme-fields` is a
# strict subset of the desktop patch's web_server.py hunk, so on a normal tick
# it is already applied by the time we reach it and is skipped — listing it
# still matters for the day upstream decouples those files.
patch_names=(
  desktop-research-workflow
  terminal-theme-fields
)
installer="$repo_dir/install-desktop-app.sh"

fail() {
  echo "reapply-desktop-patch: $*" >&2
  exit 1
}

# The paths a patch touches, for scoping the dirty-tree guard. Reads the
# `diff --git a/<path> b/<path>` headers; the b-side is the post-image, which
# is what a reapplied patch writes.
patch_paths() {
  sed -n 's|^diff --git a/.* b/||p' "$1"
}

for name in "${patch_names[@]}"; do
  [[ -f "$repo_dir/patches/$name.patch" ]] || fail "patch not found at $repo_dir/patches/$name.patch"
done
[[ -d "$hermes_source/.git" ]] || fail "Hermes source not found at $hermes_source"

cd "$hermes_source"

# Updates regenerate venv/bin/hermes without the __PYVENV_LAUNCHER__ guard;
# restore it every tick (idempotent, silent when already applied).
"$script_dir/harden-hermes-python-env.sh"

applied=()
for name in "${patch_names[@]}"; do
  patch_file="$repo_dir/patches/$name.patch"

  # Already applied: nothing to say. This is the common case on every tick.
  if git apply --reverse --check "$patch_file" >/dev/null 2>&1; then
    continue
  fi

  # Only reconcile a tree we did not partially modify ourselves. A dirty tree
  # means someone is mid-edit; reapplying on top would tangle their work. Once
  # we have applied a patch ourselves the tree is legitimately dirty, so this
  # guard only speaks for changes that were there before we started.
  #
  # Scoped to the paths our patches touch. Upstream ships two contributor files
  # whose names differ only in case (agent@agents-Mac-mini.local and
  # agent@Agents-Mac-mini.local); on a case-insensitive macOS filesystem only
  # one can exist, so git reports the other as permanently modified and
  # restoring either dirties its twin. An unscoped guard would refuse forever
  # over a file no patch of ours goes near.
  if [[ ${#applied[@]} -eq 0 ]]; then
    conflicting="$(git status --porcelain -- $(patch_paths "$patch_file"))"
    if [[ -n "$conflicting" ]]; then
      fail "Hermes source has uncommitted changes to patched files; reapply skipped. Inspect $hermes_source"
    fi
  fi

  if ! git apply --3way "$patch_file" >/dev/null 2>&1; then
    # --3way leaves conflict markers in the tree on failure. Put the source
    # back the way we found it rather than leaving Hermes unbuildable. Scoped
    # to the paths this run touched, so an unrelated local edit survives; the
    # rollback covers every patch applied so far, making a run all-or-nothing.
    rollback_paths=()
    for prior in "${applied[@]}" "$name"; do
      while IFS= read -r p; do
        [[ -n "$p" ]] && rollback_paths+=("$p")
      done < <(patch_paths "$repo_dir/patches/$prior.patch")
    done
    if [[ ${#rollback_paths[@]} -gt 0 ]]; then
      git checkout -- "${rollback_paths[@]}" >/dev/null 2>&1 || true
      git clean -fd -- "${rollback_paths[@]}" >/dev/null 2>&1 || true
    fi
    fail "$name no longer applies to this Hermes version; resolve by hand against $patch_file"
  fi

  applied+=("$name")
done

# Nothing drifted: stay silent so a scheduled run produces no notification.
if [[ ${#applied[@]} -eq 0 ]]; then
  exit 0
fi

echo "Reapplied after a Hermes update: ${applied[*]}"

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
