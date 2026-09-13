#!/usr/bin/env bash
# Keep non-interactive login shells cheap so Cortex XDR stops killing Hermes.
#
# Cortex XDR's Behavioral Threat Protection watches for burst process spawning.
# `nvm.sh` forks ~40 short-lived helpers (dirname/grep/sed/uname) every time it
# is sourced, and Hermes' terminal tool sources the rc files TWICE per session
# (once via `bash -l`, once via the snapshot prelude in
# tools/environments/base_session_env.py). A cron tick that wakes several
# profiles at the same minute turns that into a burst of hundreds of processes,
# BTP matches, and the response action is `Terminate Causality` — which kills
# the whole Hermes/gateway process tree, not just the shell.
#
# Observed on Desktop-new: 14 preventions between 2026-09-08 and 2026-09-13,
# all on the :00 minute of a cron schedule. Measured cost of one login shell
# before/after this script: 0.38s -> 0.04s, 882 -> 116 traced lines.
#
# The fix is the standard Debian-style guard: non-interactive shells only need
# PATH, so pin node's bin dir statically and return before the completions,
# hooks, and version managers that the interactive shell wants. `nvm` itself
# stays fully available in interactive shells.
#
# Idempotent. Verifies the toolchain still resolves afterwards and rolls back
# if it does not. Nothing here is Hermes-specific — it fixes the shell, which
# is where the actual problem lives.
set -euo pipefail

MARKER="# >>> hermes-customizations: xdr-btp-guard >>>"
MARKER_END="# <<< hermes-customizations: xdr-btp-guard <<<"
bashrc="${BASHRC_PATH:-$HOME/.bashrc}"
check_only=false
[[ "${1:-}" == "--check" ]] && check_only=true

log() { printf '%s\n' "$*"; }
die() { printf 'harden-shell-startup: %s\n' "$*" >&2; exit 1; }

# --- measurement -------------------------------------------------------------
# Wall time of one non-interactive login shell: what Hermes pays per terminal
# session, twice. Values are noisy on a busy machine; take the best of three.
measure_login_shell() {
  local best=99 r
  for _ in 1 2 3; do
    r=$( { /usr/bin/time -p bash -lc 'true'; } 2>&1 | awk '/real/{print $2}' )
    [[ -n "$r" ]] && best=$(awk -v a="$best" -v b="$r" 'BEGIN{print (b<a)?b:a}')
  done
  printf '%s' "$best"
}

if [[ ! -f "$bashrc" ]]; then
  log "No $bashrc on this machine — nothing to guard."
  exit 0
fi

if grep -qF "$MARKER" "$bashrc"; then
  if "$check_only"; then
    log "guard: PRESENT in $bashrc"
    log "login shell: $(measure_login_shell)s"
    exit 0
  fi
  log "Guard already present in $bashrc — nothing to do."
  log "login shell: $(measure_login_shell)s"
  exit 0
fi

if "$check_only"; then
  log "guard: ABSENT from $bashrc"
  log "login shell: $(measure_login_shell)s"
  exit 1
fi

before="$(measure_login_shell)"

# --- resolve the node bin dir the interactive shell would pick ---------------
# Ask nvm what it resolves to rather than guessing a version string, so the
# static PATH entry matches what `nvm use` already selected on this machine.
node_bin=""
if [[ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]]; then
  node_bin="$(
    set +u
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    # shellcheck disable=SC1091
    . "$NVM_DIR/nvm.sh" >/dev/null 2>&1 || true
    command -v node 2>/dev/null | xargs -r dirname 2>/dev/null || true
  )"
fi
# Fall back to whatever node is already reachable (non-nvm installs, brew node).
[[ -z "$node_bin" && -n "$(command -v node 2>/dev/null)" ]] &&
  node_bin="$(dirname "$(command -v node)")"

backup="$bashrc.bak-xdr-$(date +%Y%m%d%H%M%S)"
cp -p "$bashrc" "$backup"

# --- build the guard block ---------------------------------------------------
# Inserted at the TOP of the rc file: everything already in the file becomes
# interactive-only. Non-interactive shells (Hermes, cron, ssh commands) get
# PATH and stop. PATH additions that live in ~/.bash_profile are unaffected —
# it sources .bashrc first, then continues.
block="$MARKER
# Cortex XDR Behavioral Threat Protection terminates process trees that spawn
# processes in bursts. Sourcing nvm.sh forks ~40 helpers and Hermes' terminal
# tool sources this file twice per session. Non-interactive shells only need
# PATH, so pin it and return early; the interactive shell below still gets
# nvm, completions, and hooks. Re-run scripts/harden-shell-startup.sh after
# switching node versions, or edit the line below.
"
if [[ -n "$node_bin" ]]; then
  block+="export NVM_DIR=\"\${NVM_DIR:-\$HOME/.nvm}\"
export PATH=\"$node_bin:\$PATH\"
"
fi
block+="case \$- in
    *i*) ;;
      *) return 0;;
esac
$MARKER_END
"

printf '%s\n%s' "$block" "$(cat "$bashrc")" > "$bashrc.new"
mv "$bashrc.new" "$bashrc"

# --- verify, roll back on regression ----------------------------------------
# Source the file under test directly instead of relying on `bash -l` to find
# it: that keeps the check honest when BASHRC_PATH points somewhere else, and
# it mirrors what Hermes actually does (its snapshot prelude sources the rc
# file explicitly rather than trusting login-shell resolution).
#   non-interactive: no -i -> $- lacks 'i' -> guard returns early
#   interactive:        -i -> $- has 'i'   -> the whole rc runs
rc_noninteractive() {  # <rc-file> <command>
  bash --noprofile --norc -c ". '$1' >/dev/null 2>&1; $2"
}
rc_interactive() {     # <rc-file> <command>
  bash --noprofile --norc -ic ". '$1' >/dev/null 2>&1; $2"
}

# Compare the PATH a non-interactive shell ends up with, old rc vs new. Naming
# specific tools (node/npm/git) would miss the real hazard: this guard returns
# early, so ANY PATH export the rc file performs is now skipped — conda, pyenv,
# cargo, custom ~/bin dirs. A set difference catches all of them at once.
# Entries that are not existing directories are ignored: a stale path (e.g. an
# HPC conda dir carried over from another machine) contributes no commands, so
# losing it costs nothing and must not block the guard.
path_entries() {  # <rc-file> -> existing dirs on PATH, one per line, sorted
  rc_noninteractive "$1" 'printf "%s\n" "${PATH//:/$'"'"'\n'"'"'}"' 2>/dev/null |
    while IFS= read -r p; do [[ -n "$p" && -d "$p" ]] && printf '%s\n' "$p"; done |
    sort -u
}
lost="$(comm -23 <(path_entries "$backup") <(path_entries "$bashrc") || true)"

if [[ -n "$lost" ]]; then
  mv "$backup" "$bashrc"
  die "the guard would drop these PATH entries from non-interactive shells:
$(printf '  %s\n' $lost)
Reverted $bashrc (no changes kept). Move those PATH exports above the guard
block, or into ~/.bash_profile, then re-run."
fi

# The interactive shell must keep nvm as a function, or `nvm use` is gone.
if grep -q "nvm.sh" "$backup" 2>/dev/null; then
  if rc_interactive "$backup" '[[ "$(type -t nvm)" == function ]]' 2>/dev/null &&
     ! rc_interactive "$bashrc" '[[ "$(type -t nvm)" == function ]]' 2>/dev/null; then
    mv "$backup" "$bashrc"
    die "interactive shell lost nvm — reverted $bashrc (no changes kept)."
  fi
fi

after="$(measure_login_shell)"
log "Guarded $bashrc (backup: $backup)."
[[ -n "$node_bin" ]] && log "  node pinned at: $node_bin"
log "  login shell: ${before}s -> ${after}s"
log "  interactive shell keeps nvm / completions / hooks."
