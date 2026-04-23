---
name: compile-commands
description: Regenerate clangd's compile_commands.json for the moose_stack meta-repo. Asks which of moose (test), moose-combined (all modules), blackbear, isopod to rebuild the DB for, runs make in each, then merges them into a single compile_commands.json at the meta-repo root. Use when the user wants to refresh, rebuild, or regenerate the compile DB for clangd after a build or flag change. Accepts an optional space-separated list of names (e.g. /compile-commands moose-combined blackbear) to skip the prompt.
context: fork
agent: general-purpose
model: haiku
effort: low
allowed-tools:
  - Bash(make *)
  - Bash(jq *)
  - Bash(bash *)
  - Bash(source * && conda activate * && *)
---

# Regenerate compile_commands.json for clangd

Rebuild per-submodule compile_commands.json for the moose_stack meta-repo and merge into a single file at the root for clangd.

## Step 1: Locate the meta-repo root

Walk up from `pwd` until a directory with a `.clangd` file is found. That's the meta-repo root (or one of its feature worktrees). Error out if not found — the skill only makes sense inside a moose_stack worktree.

## Step 2: Pick build dirs

Valid names and their build dirs:
- `moose` → `moose/test` — framework + test harness (fast; good for stack work)
- `moose-combined` → `moose/modules/combined` — framework + all modules (slower; use for moose-only features that touch modules)
- `blackbear` → `blackbear`
- `isopod` → `isopod`

`moose` and `moose-combined` are not mutually exclusive — picking both is harmless (the merged DB deduplicates to first-match per file), but usually one or the other suffices.

If `$ARGUMENTS` is non-empty, treat it as a space-separated selection. Validate each token; error on unknown names.

Otherwise, use AskUserQuestion (multiSelect: true) to ask which to regenerate. Default to `moose`, `blackbear`, `isopod` selected (the stack-work default).

## Step 3: Regenerate

For each selected submodule, run sequentially (each takes ~5–10s):

```bash
source ~/miniforge3/etc/profile.d/conda.sh && conda activate moose && make -j compile_commands.json -C <path>
```

On non-zero exit, stop and surface the error.

## Step 4: Merge

From the meta-repo root, run the bundled script:

```bash
bash <skill-dir>/merge.sh
```

where `<skill-dir>` is the directory containing this SKILL.md. The script picks up whatever per-submodule DBs exist (including ones not just regenerated) and writes the merged `compile_commands.json` at the meta-repo root. Missing DBs are skipped with a warning — that's expected when the user doesn't care about a submodule.

## Step 5: Report

Report in a short message:
- Which submodules were regenerated
- The merged entry count and file size of `compile_commands.json`
- Any submodules skipped by the merge (not yet built)

## Notes

- The meta-repo's `.clangd` config and `.gitignore` are already set up. Do not modify them.
- clangd's index cache at `<root>/.cache/` may need clearing if entries go stale — mention only if the user reports clangd misbehaving.
