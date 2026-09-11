---
name: moose-params
description: Looks up the registered parameters of exact MOOSE object type names (e.g. ADDirichletBC) by booting a built app binary, so the answer matches the current checkout. Use for "what params does X take", "params for X", "dump X", or /moose-params <Type>... [--param <name> | --full]. Needs a built app and takes 15-30 s. Does not choose objects; find candidates with codegraph_explore.
argument-hint: "<TypeName>... [--param <name> | --full]"
---

# moose-params

Answers "what does this app register for `<Type>`" by running a built binary, never a cache.
Arguments arrive as `$ARGUMENTS`: one or more exact type names, then optionally `--param <name>`
(one parameter) or `--full` (the whole JSON node). This skill does not ask for clarification; on
bad input it prints the script's usage line and stops.

## Binary

Pick by where the object lives. Paths are relative to the meta-repo root or the feature worktree
root you are in. Use the `-opt` build, or `-devel` when that is the one built.

| Object | Binary |
|---|---|
| framework or any moose module | `moose/modules/combined/combined-opt` |
| test-only | `moose/test/moose_test-opt` |
| blackbear | `blackbear/blackbear-opt` |
| isopod | `isopod/isopod-opt` |

## Command

    bash .claude/skills/moose-params/scripts/moose-params.sh <binary> <Type>... [--param <name> | --full]

The script boots the app once, extracts each type's node, and prints a lean summary per type
(name, class description, required parameters, optional parameters with defaults), the single
parameter with `--param`, or the full node with `--full`. It runs the binary through
`scripts/conda-run.sh` locally and bare on INL HPC hosts. One boot costs 15-30 s, so pass every
type for one question in a single call and do not kill the run early.

## Output

Print the script output verbatim in a fenced json block. No summary, no HIT block synthesis.
Exact match only: no substring retry and no near-miss suggestion, because a fuzzy hit would let a
caller "verify" a type that is not registered.

Two outcomes look alike and are not:

- `NO_NODE: <Type>`: the app started and does not register that type. Believe it, and name the
  binary asked; a blackbear or isopod object is not in `combined-opt`.
- `APP_FAILED` (exit 2): the app never started, usually a `dyld` mismatch after a `moose` bump or
  an unbuilt app. Surface the script's stderr. This says nothing about whether the type exists.

Building or repairing the app is out of scope, as is which method binary answered.
