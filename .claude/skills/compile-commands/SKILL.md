---
name: compile-commands
description: Regenerate clangd's compile_commands.json for the moose_stack meta-repo. Asks which of moose (test), moose-combined (all modules), blackbear, isopod to rebuild the DB for, runs make in each, then merges them into a single compile_commands.json at the meta-repo root.
allowed-tools:
  - Bash(make *)
  - Bash(jq *)
  - Bash(bash *)
---

# Regenerate compile_commands.json for clangd

## Locate the meta-repo root

Walk up from `pwd` until a directory containing a `.clangd` file is found — that's the meta-repo root (or a feature worktree). Error out if not found; the skill only makes sense inside a moose_stack worktree.

## Pick build dirs

| Name | Build dir | Notes |
|---|---|---|
| `moose` | `moose/test` | framework + test harness (fast; good for stack work) |
| `moose-combined` | `moose/modules/combined` | framework + all modules (slower; for moose-only features touching modules) |
| `blackbear` | `blackbear` | |
| `isopod` | `isopod` | |

Picking both `moose` and `moose-combined` is harmless (the merge concatenates all entries; clangd uses the first entry it finds for a given file) but usually one suffices.

If `$ARGUMENTS` is non-empty, treat it as a space-separated selection; error on unknown names. Otherwise AskUserQuestion (multiSelect: true), defaulting to `moose`, `blackbear`, `isopod` selected.

## Regenerate

For each selected submodule, sequentially (~5–10s each); stop and surface any non-zero exit:

```bash
bash <root>/scripts/conda-run.sh -C <root> -- make -j compile_commands.json -C <path>
```

`conda-run.sh` resolves the worktree's version-pinned env (via `moose-env.sh`, e.g. `moose-8.23`), finds conda on whatever machine you are on, activates, and execs the command. Never hardcode a conda path here — the install prefix differs per machine, and in a non-interactive shell `conda` is often a lazy shell function rather than a binary on `PATH`.

The emitted DB embeds `$CONDA_PREFIX` include paths, so the wrong env writes a DB against the wrong moose-dev pin. Two failure modes worth recognizing:

| Error | Meaning | Fix |
|---|---|---|
| `no conda installation found` | conda lives somewhere unusual on this machine | set `MOOSE_CONDA_BASE` to the base prefix (the dir holding `etc/profile.d/conda.sh`) in that machine's shell profile |
| `conda env '<name>' not found` | this worktree's moose pin has no env yet | run the `conda create` line the error prints (see [`docs/local.md`](../../../docs/local.md)) |

This skill assumes the conda flow. On INL HPC (`sawtooth*`, `lemhi*`, `bitterroot*`, `hoodoo*`, `teton*`) the env comes from container modules instead — `conda-run.sh` will fail there; regenerate inside `moose-dev-shell` by hand, per [`docs/hpc.md`](../../../docs/hpc.md).

## Merge

From the meta-repo root:

```bash
bash <skill-dir>/merge.sh
```

where `<skill-dir>` is the directory containing this SKILL.md. The script picks up whatever per-submodule DBs exist (including ones not just regenerated) and writes the merged `compile_commands.json` at the root. It skips missing DBs with a warning — expected when the user doesn't care about a submodule.

## Report

Which submodules regenerated, merged entry count and file size, and any submodules the merge skipped.

## Notes

- The meta-repo's `.clangd` and `.gitignore` are already set up — don't modify them.
- `/new-feature` seeds a fresh worktree's DBs by copying the canonical stack's with the root path rewritten — this skill is the refresh path when entries go stale.
- clangd's index cache at `<root>/.cache/` may need clearing if entries go stale — mention only if the user reports clangd misbehaving.
