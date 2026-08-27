#!/usr/bin/env bash
# Run a command inside a moose_stack worktree's pinned conda env.
#
# Usage:
#   conda-run.sh [-C <path-inside-worktree>] -- <command> [args...]
#   conda-run.sh --print-env [-C <path>]      # print the resolved env name only
#
# The env name comes from scripts/moose-env.sh (the worktree's moose-dev pin).
# Conda itself is discovered at runtime, because a non-interactive shell often
# has no `conda` on PATH: a common local setup defers `conda shell.<sh> hook`
# behind a shell function that only exists in an interactive session. Search
# order, first hit wins:
#
#   1. $MOOSE_CONDA_BASE        - explicit override for unusual installs
#   2. $CONDA_EXE               - set by any activated conda
#   3. `conda` on PATH          - only if it is a real file, not a function
#   4. $CONDA_ROOT / $MAMBA_ROOT_PREFIX
#   5. the install roots in CONDA_SEARCH_ROOTS below
#
# To support a new machine whose conda lives somewhere unusual, set
# MOOSE_CONDA_BASE in that machine's shell profile — do not edit this list.

set -euo pipefail

CONDA_SEARCH_ROOTS="
$HOME/miniforge
$HOME/miniforge3
$HOME/miniconda3
$HOME/mambaforge
$HOME/anaconda3
$HOME/opt/miniforge3
$HOME/opt/miniconda3
/opt/miniforge3
/opt/miniconda3
/opt/homebrew/Caskroom/miniforge/base
/opt/homebrew/anaconda3
/usr/local/Caskroom/miniforge/base
"

die() { echo "error: $*" >&2; exit 1; }

where="$(pwd)"
print_env_only=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -C) [[ $# -ge 2 ]] || die "-C needs a path"; where="$2"; shift 2 ;;
    --print-env) print_env_only=1; shift ;;
    --) shift; break ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) die "unknown argument: $1 (did you forget --?)" ;;
  esac
done

env_name="$(bash "$(dirname "${BASH_SOURCE[0]}")/moose-env.sh" "$where")"

if [[ "$print_env_only" == 1 ]]; then
  echo "$env_name"
  exit 0
fi

[[ $# -gt 0 ]] || die "no command given; usage: conda-run.sh [-C <path>] -- <command> [args...]"

# --- locate a conda base ---------------------------------------------------
conda_base=""

try_base() {   # accepts a base prefix if it holds the activation hook
  [[ -n "${1:-}" && -f "$1/etc/profile.d/conda.sh" ]] || return 1
  conda_base="$1"
}
try_exe() {    # accepts a conda binary, deriving base as its ../..
  [[ -n "${1:-}" && -f "$1" ]] || return 1
  try_base "$(cd "$(dirname "$1")/.." && pwd)"
}

path_conda=""
if command -v conda >/dev/null 2>&1; then
  candidate="$(command -v conda)"
  [[ -f "$candidate" ]] && path_conda="$candidate"   # a shell function is not a file
fi

# An explicit override is a deliberate statement about this machine: if it is
# set but wrong, say so rather than quietly autodiscovering a different conda.
if [[ -n "${MOOSE_CONDA_BASE:-}" ]]; then
  try_base "$MOOSE_CONDA_BASE" \
    || die "MOOSE_CONDA_BASE=$MOOSE_CONDA_BASE is not a conda base prefix
(no etc/profile.d/conda.sh under it). Fix or unset it."
fi

try_base "$conda_base" \
  || try_exe "${CONDA_EXE:-}" \
  || try_exe "$path_conda" \
  || try_base "${CONDA_ROOT:-}" \
  || try_base "${MAMBA_ROOT_PREFIX:-}" \
  || {
    for root in $CONDA_SEARCH_ROOTS; do
      try_base "$root" && break
    done
  }

[[ -n "$conda_base" ]] || die "no conda installation found.
Set MOOSE_CONDA_BASE to your conda base prefix (the directory holding
etc/profile.d/conda.sh) and re-run. Searched: \$MOOSE_CONDA_BASE, \$CONDA_EXE,
conda on PATH, \$CONDA_ROOT, \$MAMBA_ROOT_PREFIX, and the usual install roots."

# conda.sh and the activate machinery reference unset vars; -u would abort here.
set +u
# shellcheck disable=SC1091
source "$conda_base/etc/profile.d/conda.sh"
if ! conda activate "$env_name" 2>/dev/null; then
  set -u
  die "conda env '$env_name' not found in $conda_base.
This worktree pins moose-dev to that env. Create it (see docs/local.md):
  conda create -n $env_name moose-dev=<version> -c https://conda.software.inl.gov/public"
fi
set -u

exec "$@"
