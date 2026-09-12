#!/bin/bash
# SessionStart hook (matcher: compact). Re-injects the workspace facts that a
# context compaction drops: where the meta-root is, which branches the
# meta-repo and moose/ are on, whether a blueprint exists, and the outcome of
# the last /moose-build run. Everything on stdout becomes session context.
#
# Takes no arguments; the hook payload arrives on stdin and is drained but not
# needed (the root is resolved from the environment, as every script here does).
# Fails open: a missing root or a bad cache file prints a note and exits 0,
# because a context injector that errors out only adds noise after compaction.
#
# Usage: session-context.sh   (stdin: hook JSON; stdout: ~15 lines of context)

set -u

usage() { echo "usage: session-context.sh   (no arguments; hook JSON on stdin)" >&2; exit 2; }
[ "$#" -eq 0 ] || usage

# Drain stdin so the harness never sees a broken pipe. The payload is unused.
[ -t 0 ] || cat >/dev/null

# Meta-root: $CLAUDE_PROJECT_DIR if set, else walk up from $PWD to the first
# directory holding `.clangd` (the marker scripts/moose-env.sh keys on). This
# makes the hook correct inside feature worktrees, not just the canonical repo.
root="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$root" ]; then
  root="$PWD"
  while [ "$root" != "/" ] && [ ! -f "$root/.clangd" ]; do
    root="$(dirname "$root")"
  done
fi
if [ ! -f "$root/.clangd" ]; then
  echo "moose_stack session context: no meta-root found (no .clangd above $PWD)"
  exit 0
fi

# Branch name, or `detached at <sha>` since submodule checkouts in worktrees
# are commonly detached and the sha is the only useful identity then.
branch_of() {
  local dir="$1" name sha
  [ -d "$dir" ] || { echo "missing"; return; }
  name="$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null)" || { echo "not a git repo"; return; }
  sha="$(git -C "$dir" rev-parse --short HEAD 2>/dev/null)"
  if [ "$name" = "HEAD" ]; then echo "detached at $sha"; else echo "$name ($sha)"; fi
}

# A feature worktree from /new-feature has `.git` as a file; the canonical
# checkout has a `.git` directory. Skills that refuse outside a worktree use
# the same test, so surface it here.
kind="canonical checkout"
[ -f "$root/.git" ] && kind="feature worktree"

echo "## moose_stack session context (re-injected after compaction)"
echo "meta-root: $root ($kind)"
echo "meta-repo branch: $(branch_of "$root")"
echo "moose/ branch: $(branch_of "$root/moose")"
if [ -f "$root/specs/blueprint.md" ]; then
  echo "blueprint: specs/blueprint.md present"
else
  echo "blueprint: specs/blueprint.md absent"
fi

# Last run record: /moose-build writes .claude/cache/moose-build-<label>.json
# as {runId, status, report}. Newest by mtime wins (ls -t); jq is optional
# and the file name alone is still worth printing when jq is absent.
last="$(ls -t "$root"/.claude/cache/moose-build-*.json 2>/dev/null | head -n 1)"
if [ -z "$last" ]; then
  echo "last moose-build run: none"
else
  summary=""
  if command -v jq >/dev/null 2>&1; then
    # `report` may be a string or an object; take its first line either way.
    # Kept on one line: jq 1.7 rejects a multi-line program that mixes string
    # interpolation with a following `+`.
    summary="$(jq -r '"status=" + ((.status // "?") | tostring) + " runId=" + ((.runId // "?") | tostring) + (if (.report | type) == "string" then " -- " + (.report | split("\n")[0]) elif (.report | type) == "object" then " -- " + ((.report.summary // "") | tostring | split("\n")[0]) else "" end)' "$last" 2>/dev/null)" || summary="unreadable JSON"
  fi
  # mtime: BSD stat first (macOS), GNU stat second, blank otherwise.
  when="$(stat -f '%Sm' -t '%Y-%m-%d %H:%M' "$last" 2>/dev/null || stat -c '%y' "$last" 2>/dev/null | cut -c1-16)"
  echo "last moose-build run: $(basename "$last")${when:+ ($when)}${summary:+ $summary}"
  echo "  record: $last"
fi
exit 0
