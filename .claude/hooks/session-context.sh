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
# stderr is discarded: a caller that closed fd 0 makes `cat` complain, and a
# hook that prints to stderr is reported as a warning for no reason.
[ -t 0 ] || cat >/dev/null 2>/dev/null

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

# Factory card: the head block of the note the board last generated for this
# worktree (lane, PR state, the one next move, the gates), capped at 16 lines.
# `--head` is load-bearing: the first 12 lines of the whole note are frontmatter,
# and the next move sits just below that cut. The cap is 16, not 12: a head block
# is 13 lines for every card, so 12 cut the last gate (`teardown`) off every
# injection. Fails open and silent: no projector, no vault, or no note for this
# feature prints nothing at all. The card is as of the last `factory board` run,
# never as of now.
#
# The projector is called by absolute path, because a worktree has no factory/ of
# its own, and that path is resolved, never a literal: the `meta_repo` key of this
# machine's ~/.config/moose-factory/config.toml ($MOOSE_FACTORY_CONFIG overrides
# the location), and $HOME/projects/moose_stack when the file or the key is
# absent. No user name appears here, so the same hook works on every machine. A
# checkout at any other path needs that key, because this hook cannot walk up to
# the checkout the way tool/config.py does; factory/install.sh writes it.
factory_config="${MOOSE_FACTORY_CONFIG:-$HOME/.config/moose-factory/config.toml}"
meta_repo=""
if [ -r "$factory_config" ]; then
  meta_repo="$(sed -n -e 's/[[:space:]]*#.*$//' \
                      -e 's/^[[:space:]]*meta_repo[[:space:]]*=[[:space:]]*//p' \
                      "$factory_config" 2>/dev/null | head -n 1 | tr -d '"')"
fi
meta_repo="${meta_repo:-$HOME/projects/moose_stack}"
meta_repo="${meta_repo/#\~/$HOME}"
factory_bin="$meta_repo/factory/factory"
if [ "$kind" = "feature worktree" ] && [ -x "$factory_bin" ]; then
  feature="$(basename "$root")"
  card="$("$factory_bin" status "$feature" --head 2>/dev/null | head -n 16)" || card=""
  if [ -n "$card" ]; then
    echo "factory card ($feature), as of the last \`factory board\` run:"
    printf '%s\n' "$card"
  fi
fi

# Handoff: the two rewrite sections of <worktree>/specs/handoff.md, which is
# where the previous session left what is green, what is red, and the ordered
# next steps. The append-only sections (Do not repeat, Decisions, Gotchas, Map,
# Sessions) stay out: the board projects the dead ends onto the card, and this
# injection is the start-of-session briefing, not the whole file. Fails open and
# silent: no worktree, no file, or an unreadable file prints nothing. awk selects
# by heading name, so a reordered file still works.
#
# The cap is per section, 18 lines each, and a truncated section says so. A
# single 40-line cap over the concatenation let a wordy State starve Next out of
# the injection entirely, which is the one part the new session must act on.
# Two headings plus 19 lines each is 40, so the overall budget is unchanged. A
# blank line counts, because the budget is about what the reader is handed.
#
# The heading pattern tolerates trailing whitespace, exactly like
# ext_handoff._HEADING: `## Next ` still renders on the board note, so a hook
# that demanded `## Next` dropped a section the other reader accepted, and the
# two readers disagreed with nothing reporting it.
handoff="$root/specs/handoff.md"
if [ "$kind" = "feature worktree" ] && [ -f "$handoff" ] && [ -r "$handoff" ]; then
  updated="$(sed -n '2,12s/^updated:[[:space:]]*//p' "$handoff" 2>/dev/null | head -n 1)"
  body="$(awk '
    /^##[[:space:]]+(State|Next)[[:space:]]*$/ { sec = $2; print; next }
    /^##[[:space:]]/                           { sec = ""; next }
    sec == ""                                  { next }
    { n[sec]++
      if (n[sec] <= 18) print
      else if (n[sec] == 19) print "... cut; the rest is in specs/handoff.md" }
  ' "$handoff" 2>/dev/null | head -n 40)"
  if [ -n "$body" ]; then
    echo "handoff (specs/handoff.md, updated ${updated:-unknown})"
    printf '%s\n' "$body"
  fi
fi
exit 0
