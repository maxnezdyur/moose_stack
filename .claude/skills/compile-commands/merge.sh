#!/usr/bin/env bash
# Merge per-submodule compile_commands.json files into one at the meta-repo
# root. Invoked by the `/compile-commands` skill after regenerating per-app
# DBs. Walks up from cwd to find the meta-repo root via its .clangd marker,
# so it works from any worktree.

set -euo pipefail

root="$(pwd)"
while [[ "$root" != "/" && ! -f "$root/.clangd" ]]; do
  root="$(dirname "$root")"
done
if [[ ! -f "$root/.clangd" ]]; then
  echo "error: no .clangd found walking up from $(pwd) — not inside a moose_stack worktree?" >&2
  exit 1
fi
cd "$root"

candidates=(
  moose/test/compile_commands.json
  moose/modules/combined/compile_commands.json
  blackbear/compile_commands.json
  isopod/compile_commands.json
)

found=()
for f in "${candidates[@]}"; do
  if [[ -f "$f" ]]; then
    found+=("$f")
  else
    echo "skip: $f (not built yet)" >&2
  fi
done

if [[ ${#found[@]} -eq 0 ]]; then
  echo "error: no compile_commands.json found in any submodule" >&2
  exit 1
fi

jq -s 'add' "${found[@]}" > compile_commands.json
echo "wrote $root/compile_commands.json ($(jq 'length' compile_commands.json) entries from ${#found[@]} submodules)"
