---
name: compile-commands
description: Regenerates clangd's compile_commands.json for a moose_stack worktree through scripts/regen.sh and relays its per-target entry counts. Use for "regenerate compile commands", "refresh the clangd database", "clangd entries are stale", "rebuild compile_commands.json", or /compile-commands [targets].
argument-hint: "[moose|moose-combined|blackbear|isopod ...]"
allowed-tools: Bash(bash *)
effort: low
---

# compile-commands

One script does the work. Run it from the meta-repo root or the feature worktree root you are in:

    bash .claude/skills/compile-commands/scripts/regen.sh $ARGUMENTS

With no arguments it regenerates `moose` (the `moose/test` build), `blackbear`, and `isopod`,
then merges every per-submodule DB that exists into `<root>/compile_commands.json`. Pass
`moose-combined` when the work touches modules; it builds in `moose/modules/combined` and takes
longer. Each target takes about 5-10 s, so run the command in the foreground.

Only you see the command's output; put the `regen:` counts, the `wrote ...` line, any
`merge: skip` lines, and any `FAIL`/`BLOCKED` line in your reply. Exit 2 is BLOCKED (no jq, an
INL HPC host, or a missing conda env): relay the pointer the script prints and stop; this skill
does not create environments, edit `.clangd`, or run make by hand. `/new-feature` seeds a fresh
worktree's DBs by copying; this skill is the refresh path when entries go stale. If clangd still
misbehaves after a regen, clearing `<root>/.cache/` forces a re-index.
