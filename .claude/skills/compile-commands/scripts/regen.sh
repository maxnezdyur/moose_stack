#!/usr/bin/env bash
# Regenerate clangd's compile_commands.json for a moose_stack worktree.
#
# Usage: regen.sh [moose|moose-combined|blackbear|isopod ...]
#
# Default targets: moose blackbear isopod. For each target this runs
#   conda-run.sh -C <meta-root> -- make -C <build-dir> compile_commands.json
# then merges every per-submodule DB that exists (regenerated or not) into
# <meta-root>/compile_commands.json. Replaces the old merge.sh, whose merge
# logic lives in merge_dbs below.
#
# Exit codes: 0 = regenerated and merged; 1 = a make or merge failed;
# 2 = usage, or blocked (no jq, INL HPC host, conda env missing).
#
# Build dirs: moose -> moose/test (framework + test harness, fast),
# moose-combined -> moose/modules/combined (framework + all modules, slower).
# Picking both is harmless: the merge concatenates and clangd uses the first
# entry it finds for a file, but one usually suffices.
#
# The emitted DB embeds $CONDA_PREFIX include paths, so the make must run in
# the worktree's pinned env: conda-run.sh resolves it through moose-env.sh and
# fails clearly when that env does not exist. On INL HPC hostnames there is no
# conda (the env comes from container modules), so this script stops with a
# pointer instead of writing a DB against the wrong include paths.

set -uo pipefail

usage="usage: regen.sh [moose|moose-combined|blackbear|isopod ...]   (default: moose blackbear isopod)"

case "${1:-}" in
  -h|--help) echo "$usage"; exit 0 ;;
esac

# --- meta-root: $CLAUDE_PROJECT_DIR, else walk up to the first .clangd ------
root="${CLAUDE_PROJECT_DIR:-}"
if [[ -z "$root" ]]; then
  root="$PWD"
  while [[ "$root" != "/" && ! -f "$root/.clangd" ]]; do
    root="$(dirname "$root")"
  done
fi
if [[ ! -f "$root/.clangd" ]]; then
  echo "error: no .clangd found walking up from $PWD -- not inside a moose_stack worktree?" >&2
  exit 2
fi

# --- targets ----------------------------------------------------------------
# Name -> build dir. The compile_commands.json target must be the only make
# goal (framework/build.mk errors otherwise), so no other goal is passed.
build_dir() {
  case "$1" in
    moose)          echo "moose/test" ;;
    moose-combined) echo "moose/modules/combined" ;;
    blackbear)      echo "blackbear" ;;
    isopod)         echo "isopod" ;;
    *)              return 1 ;;
  esac
}

if [[ $# -eq 0 ]]; then
  targets=(moose blackbear isopod)
else
  targets=("$@")
fi
for t in "${targets[@]}"; do
  build_dir "$t" >/dev/null || { echo "$usage" >&2; exit 2; }
done

# --- blockers: jq, HPC host, conda env --------------------------------------
if ! command -v jq >/dev/null 2>&1; then
  echo "BLOCKED: jq not found on PATH (conda install jq, or brew install jq)" >&2
  exit 2
fi

pointer="see $root/docs/local.md for the conda flow (docs/hpc.md on INL HPC: regenerate inside the container shell by hand)"

case "$(hostname)" in
  sawtooth*|lemhi*|bitterroot*|hoodoo*|teton*)
    echo "BLOCKED: $(hostname) is an INL HPC host with no conda; $pointer" >&2
    exit 2 ;;
esac

# One probe activation up front so a missing conda or env is reported as
# BLOCKED (exit 2) instead of being mistaken for a make failure (exit 1).
conda_run="$root/scripts/conda-run.sh"
if ! bash "$conda_run" -C "$root" -- true; then
  echo "BLOCKED: conda env unavailable; $pointer" >&2
  exit 2
fi

# --- regenerate --------------------------------------------------------------
regenerated=()
for t in "${targets[@]}"; do
  dir="$(build_dir "$t")"
  echo "regen: $t (make -C $dir compile_commands.json)"
  if ! bash "$conda_run" -C "$root" -- make -C "$root/$dir" compile_commands.json; then
    echo "FAIL: make -C $dir compile_commands.json exited non-zero" >&2
    exit 1
  fi
  db="$root/$dir/compile_commands.json"
  if [[ ! -f "$db" ]]; then
    echo "FAIL: $dir/compile_commands.json not written" >&2
    exit 1
  fi
  echo "regen: $t -> $(jq 'length' "$db") entries"
  regenerated+=("$t")
done

# --- merge (the old merge.sh) -------------------------------------------------
# Every per-submodule DB that exists is merged, not only the ones just
# regenerated, so a stale-but-present blackbear DB still contributes when the
# user only refreshed moose. Missing DBs are skipped with a note.
merge_dbs() {
  local found=() f
  for f in moose/test/compile_commands.json \
           moose/modules/combined/compile_commands.json \
           blackbear/compile_commands.json \
           isopod/compile_commands.json; do
    if [[ -f "$root/$f" ]]; then
      found+=("$root/$f")
      echo "merge: $f ($(jq 'length' "$root/$f") entries)"
    else
      echo "merge: skip $f (not built)"
    fi
  done
  if [[ ${#found[@]} -eq 0 ]]; then
    echo "FAIL: no compile_commands.json found in any submodule" >&2
    return 1
  fi
  jq -s 'add' "${found[@]}" > "$root/compile_commands.json" || return 1
  echo "wrote $root/compile_commands.json ($(jq 'length' "$root/compile_commands.json") entries from ${#found[@]} DBs, $(du -h "$root/compile_commands.json" | cut -f1))"
}

merge_dbs || exit 1
echo "regenerated: ${regenerated[*]}"
