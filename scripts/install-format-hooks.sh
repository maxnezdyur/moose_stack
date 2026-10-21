#!/bin/bash
# Install the clang-format pre-commit hook into the moose, isopod and blackbear submodules.
# A submodule's hooks directory is shared by all of its worktrees. Run again to update the hooks.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for r in moose isopod blackbear; do
    hooks="$(git -C "$root/$r" rev-parse --path-format=absolute --git-common-dir)/hooks"
    install -m 755 "$root/scripts/git-hooks/$r-pre-commit" "$hooks/pre-commit"
    echo "$r: $hooks/pre-commit"
done
