---
name: new-feature
description: Scaffold a new moose_stack feature workspace — creates a meta-repo worktree with feature branches on all three submodules, a fresh build-locked conda env, a bootstrapped CodeGraph index, and a locally relinked combined-opt hydrated from the canonical MOOSE seed. Manual-invoke only.
disable-model-invocation: true
allowed-tools:
  - Bash(git worktree *)
  - Bash(git branch *)
  - Bash(git -C *)
  - Bash(conda env list)
  - Bash(conda run *)
  - Bash(python3 ~/projects/moose_stack/.claude/skills/new-feature/scripts/hydrate_moose_combined.py *)
  - Bash(hostname)
  - Bash(ls *)
  - Bash(rmdir *)
  - Bash(mkdir *)
  - Bash(cp *)
  - Bash(sqlite3 *)
  - Bash(codegraph *)
---

# /new-feature

Every submodule always gets a worktree — no pairing prompt; matching branch names on all four repos (the meta-repo plus `moose`, `blackbear`, `isopod`) let the meta-repo bump pointers cleanly later. Use the app(s) you need, leave the rest untouched.

## Usage

/new-feature <feature-name>   # kebab-case (lowercase, hyphens); ask if missing

On failure at any step, stop and report — do not partially tear down; the user decides what to clean up.

## Steps

1. Validate and lease the canonical combined seed before creating anything:
   - Run `hostname`; this workflow is for the local conda host, not an INL HPC host.
   - Name is kebab-case.
   - `~/projects/moose-worktrees/<feature>/` does not exist; `conda env list` has no `moose-<feature>`.
   - Branch `<feature>` exists on none of the four repos:
     ```bash
     for r in moose_stack moose_stack/moose moose_stack/blackbear moose_stack/isopod; do
       git -C ~/projects/$r branch --list <feature>
     done
     ```
   - The canonical checkouts are at their local base tips: `moose_stack` at `main`, and `moose`, `blackbear`, and `isopod` at `devel`. The three SHAs must also equal the submodule gitlinks recorded by `moose_stack/main`. Inspect and compare these outputs; stop before mutation if any pair differs, and never branch a new feature from an incidental topic `HEAD`.
     ```bash
     git -C ~/projects/moose_stack rev-parse HEAD main
     for r in moose blackbear isopod; do
       git -C ~/projects/moose_stack/$r rev-parse HEAD devel
     done
     git -C ~/projects/moose_stack ls-tree main moose blackbear isopod
     ```
   - The fixed donor `~/projects/moose_stack/moose` must pass the stamped-build preflight. This verifies its clean SHA, opt/unity profile, build environment, compiler, complete reusable inventory, hashes, binary provenance, and practical make no-op state. Missing, stale, or mixed seeds stop here rather than silently creating a cold workspace.
     ```bash
     python3 ~/projects/moose_stack/.claude/skills/new-feature/scripts/hydrate_moose_combined.py \
       preflight --donor ~/projects/moose_stack/moose
     ```
     Retain the reported SHA and lease. Pass that exact lease to both later helper commands; a concurrent restamp or donor change then stops safely.
2. Meta-repo worktree + specs home:
   ```bash
   mkdir -p ~/projects/moose-worktrees   # shared home for all feature worktrees
   git -C ~/projects/moose_stack worktree add ~/projects/moose-worktrees/<feature> -b <feature> main
   mkdir -p ~/projects/moose-worktrees/<feature>/specs   # home for blueprint.html (see /moose-blueprint)
   cp ~/projects/moose-worktrees/<feature>/moose_stack.code-workspace ~/projects/moose-worktrees/<feature>/<feature>.code-workspace
   ```
   The workspace copy gives each worktree a distinguishable VS Code window title. It is gitignored (`*.code-workspace` except the tracked original); never `mv` the tracked `moose_stack.code-workspace` — that dirties the feature branch.
   Submodule paths are left as empty directories (gitlinks only). Do NOT run `git submodule update --init` in this worktree — the submodule worktrees created next are the source of truth, and `update --init` would try to clone into those paths and conflict.
3. Submodule worktrees, for each of `moose`, `blackbear`, `isopod`:
   ```bash
   rmdir ~/projects/moose-worktrees/<feature>/<sub>   # empty dir left by step 2, if present
   git -C ~/projects/moose_stack/<sub> worktree add ~/projects/moose-worktrees/<feature>/<sub> -b <feature> devel
   ```
   Apps locate MOOSE via `../moose` (Makefile fallback) — the paired MOOSE worktree satisfies this.
4. CodeGraph index: always **copy + sync**, never `codegraph init` — the ~1 GB DB stores relative paths, so cloning the meta-repo's DB and syncing the branch diff takes ~50s vs a multi-minute full rebuild. Skip (and note it) if `~/projects/moose_stack/.codegraph/codegraph.db` is absent.
   ```bash
   # Flush main's WAL so a single-file copy is consistent, then APFS-clone the DB (instant, same volume)
   sqlite3 ~/projects/moose_stack/.codegraph/codegraph.db "PRAGMA wal_checkpoint(TRUNCATE);"
   mkdir -p ~/projects/moose-worktrees/<feature>/.codegraph
   cp -c ~/projects/moose_stack/.codegraph/codegraph.db ~/projects/moose-worktrees/<feature>/.codegraph/codegraph.db
   cp    ~/projects/moose_stack/.codegraph/.gitignore   ~/projects/moose-worktrees/<feature>/.codegraph/.gitignore
   ( cd ~/projects/moose-worktrees/<feature> && codegraph sync . )   # re-parses only changed files; prunes files absent from the worktree
   ```
   Copy only `codegraph.db` + `.gitignore` — never `daemon.sock`/`daemon.pid`/`*-wal`/`*-shm`; the new worktree spawns its own daemon on first `sync`. The DB stays gitignored and machine-local (it exceeds GitHub's 100 MB limit and goes stale immediately). This step is independent of the conda env — safe to run concurrently with it.
5. Conda env — fresh, never cloned and never mutating the donor. Recreate the donor manifest's exact conda package lock so copied C++ objects retain the same compiler and dependency ABI; the helper also requires the target MOOSE SHA/versioner file to match before creation:
   ```bash
   python3 ~/projects/moose_stack/.claude/skills/new-feature/scripts/hydrate_moose_combined.py \
     create-env \
     --donor ~/projects/moose_stack/moose \
     --target ~/projects/moose-worktrees/<feature>/moose \
     --name moose-<feature> \
     --lease <donor-lease>
   ```
6. Hydrate MOOSE combined only. Run this immediately, before feature edits. The helper rechecks the donor lease and target cleanliness, stages APFS clones outside the target, rebases text metadata and header symlinks, installs only reusable compile triplets/generated inputs, recompiles path-sensitive objects, and relinks every library/executable locally in the target env. It then requires a compile/link-clean second make, target-local Mach-O/data paths, two combined canaries, and clean tracked Git state.
   ```bash
   conda run -n moose-<feature> python \
     ~/projects/moose_stack/.claude/skills/new-feature/scripts/hydrate_moose_combined.py \
     hydrate \
     --donor ~/projects/moose_stack/moose \
     --target ~/projects/moose-worktrees/<feature>/moose \
     --lease <donor-lease>
   ```
   Any environment mismatch stops before copying. Any failure after installation/build begins stops and preserves the workspace for diagnosis; do not tear it down or fall back to a cold build.
7. Report: workspace path, the `<feature>.code-workspace` file to open in VS Code, env name, the four branches created, CodeGraph status (or skipped), donor SHA/lease, objects reused versus rebuilt locally, hydration timing/validation, and remind the user to `conda activate moose-<feature>`. State explicitly that BlackBear and Isopod were worktreed but not hydrated or built. Point to `docs/local.md` if the branch later bumps `moose`.

## Notes

- Do NOT run `update_and_rebuild_libmesh.sh` / `update_and_rebuild_petsc.sh` / `update_and_rebuild_wasp.sh` here — those only run later, if the feature branch bumps those submodules.
- Branches are local-only at create time; the first `git push -u origin <feature>` happens with the user's first pushed commit.
- The ignored donor manifest is `moose/framework/build/hydration/combined-opt-v1.json`. Create or refresh it only immediately after a clean, settled combined opt/unity/header-symlink build:
  ```bash
  python3 ~/projects/moose_stack/.claude/skills/new-feature/scripts/hydrate_moose_combined.py \
    stamp --donor ~/projects/moose_stack/moose
  ```
  `stamp` rejects source changes (including untracked files), mixed dependency metadata, and stale builds; it never repairs the seed. An individual object with a foreign embedded conda prefix is recorded as forced-local and omitted from hydration.
