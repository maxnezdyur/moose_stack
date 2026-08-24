#!/usr/bin/env bash
# Print the shared conda env name for a moose_stack worktree.
#
# Naming rule: moose-dev version YYYY.MM.DD -> moose-<M>.<DD>, with the
# month's leading zero stripped and the day kept verbatim.
#   2026.08.19 -> moose-8.19
#   2026.07.30 -> moose-7.30
#   2026.09.02 -> moose-9.02
# One env serves every worktree on the same pin. If two pins ever collide
# across years, name the newer one with the full version (moose-2027.08.19).
#
# Usage: moose-env.sh [path-inside-worktree]   (default: cwd)

set -euo pipefail

root="$(cd "${1:-$(pwd)}" && pwd)"
while [[ "$root" != "/" && ! -f "$root/.clangd" ]]; do
  root="$(dirname "$root")"
done
if [[ ! -f "$root/.clangd" ]]; then
  echo "error: no .clangd found walking up from ${1:-$(pwd)} — not inside a moose_stack worktree?" >&2
  exit 1
fi

meta="$root/moose/conda/moose-dev/meta.yaml"
if [[ ! -f "$meta" ]]; then
  echo "error: $meta not found — moose submodule not checked out?" >&2
  exit 1
fi

version="$(sed -n 's/.*set version = "\([0-9.]*\)".*/\1/p' "$meta")"
if [[ -z "$version" ]]; then
  echo "error: could not parse moose-dev version from $meta" >&2
  exit 1
fi

IFS=. read -r _year month day <<<"$version"
echo "moose-$((10#$month)).$day"
