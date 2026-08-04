---
name: new-feature
description: Scaffold a new moose_stack feature workspace — creates a meta-repo worktree with feature branches on all three submodules, a fresh conda env pinned to the checkout's moose-dev version, and a bootstrapped CodeGraph index. Manual-invoke only.
disable-model-invocation: true
allowed-tools:
  - Bash(git worktree *)
  - Bash(git branch *)
  - Bash(git -C *)
  - Bash(conda create *)
  - Bash(conda env list)
  - Bash(yq *)
  - Bash(ls *)
  - Bash(rmdir *)
  - Bash(mkdir *)
  - Bash(cp *)
  - Bash(sqlite3 *)
  - Bash(codegraph *)
---

# /new-feature

Scaffold a feature workspace: a meta-repo worktree with matching feature branches on the meta-repo and all three submodules (`moose`, `blackbear`, `isopod`), a fresh version-pinned conda env, and a bootstrapped CodeGraph index. Every submodule always gets a worktree — no pairing prompt; matching branch names on all four repos let the meta-repo bump pointers cleanly later. Use the app(s) you need, leave the rest untouched.

## Usage

/new-feature <feature-name>   # kebab-case (lowercase, hyphens); ask if missing

On failure at any step, stop and report — do not partially tear down; the user decides what to clean up.

## Steps

1. Validate:
   - Name is kebab-case.
   - `~/projects/<feature>/` does not exist; `conda env list` has no `moose-<feature>`.
   - Branch `<feature>` exists on none of the four repos:
     ```bash
     for r in moose_stack moose_stack/moose moose_stack/blackbear moose_stack/isopod; do
       git -C ~/projects/$r branch --list <feature>
     done
     ```
2. Meta-repo worktree + specs home:
   ```bash
   git -C ~/projects/moose_stack worktree add ~/projects/<feature> -b <feature>
   mkdir -p ~/projects/<feature>/specs   # home for blueprint.html (see /moose-blueprint)
   cp ~/projects/<feature>/moose_stack.code-workspace ~/projects/<feature>/<feature>.code-workspace
   ```
   The workspace copy gives each worktree a distinguishable VS Code window title. It is gitignored (`*.code-workspace` except the tracked original); never `mv` the tracked `moose_stack.code-workspace` — that dirties the feature branch.
   Submodule paths are left as empty directories (gitlinks only). Do NOT run `git submodule update --init` in this worktree — the submodule worktrees created next are the source of truth, and `update --init` would try to clone into those paths and conflict.
3. Submodule worktrees, for each of `moose`, `blackbear`, `isopod`:
   ```bash
   rmdir ~/projects/<feature>/<sub>   # empty dir left by step 2, if present
   git -C ~/projects/moose_stack/<sub> worktree add ~/projects/<feature>/<sub> -b <feature>
   ```
   Apps locate MOOSE via `../moose` (Makefile fallback) — the paired MOOSE worktree satisfies this.
4. CodeGraph index: always **copy + sync**, never `codegraph init` — the ~1 GB DB stores relative paths, so cloning the meta-repo's DB and syncing the branch diff takes ~50s vs a multi-minute full rebuild. Skip (and note it) if `~/projects/moose_stack/.codegraph/codegraph.db` is absent.
   ```bash
   # Flush main's WAL so a single-file copy is consistent, then APFS-clone the DB (instant, same volume)
   sqlite3 ~/projects/moose_stack/.codegraph/codegraph.db "PRAGMA wal_checkpoint(TRUNCATE);"
   mkdir -p ~/projects/<feature>/.codegraph
   cp -c ~/projects/moose_stack/.codegraph/codegraph.db ~/projects/<feature>/.codegraph/codegraph.db
   cp    ~/projects/moose_stack/.codegraph/.gitignore   ~/projects/<feature>/.codegraph/.gitignore
   ( cd ~/projects/<feature> && codegraph sync . )   # re-parses only changed files; prunes files absent from the worktree
   ```
   Copy only `codegraph.db` + `.gitignore` — never `daemon.sock`/`daemon.pid`/`*-wal`/`*-shm`; the new worktree spawns its own daemon on first `sync`. The DB stays gitignored and machine-local (it exceeds GitHub's 100 MB limit and goes stale immediately). This step is independent of the conda env — safe to run concurrently with it.
5. Conda env — fresh, pinned to the moose-dev version this checkout needs (never clone, never mutate the base `moose` env). Read the version from the feature worktree's own moose — the same source the MOOSE install docs' `!versioner!` shortcode substitutes into `conda create -n moose moose-dev=<version>`:
   ```bash
   yq -r '.packages."moose-dev".version' ~/projects/<feature>/moose/scripts/versioner.yaml   # e.g. 2026.05.08
   conda create -n moose-<feature> moose-dev=<version> -c https://conda.software.inl.gov/public -y
   ```
   MOOSE and its conda packages move in lockstep: if the branch later bumps `moose` to a commit whose `versioner.yaml` reports a different version, recreate the env with the new pin.
6. Report: workspace path, the `<feature>.code-workspace` file to open in VS Code, env name, the four branches created, CodeGraph status (or skipped), and remind the user to `conda activate moose-<feature>`.

## Notes

- Do NOT run `update_and_rebuild_libmesh.sh` / `update_and_rebuild_petsc.sh` / `update_and_rebuild_wasp.sh` here — those only run later, if the feature branch bumps those submodules.
- Branches are local-only at create time; the first `git push -u origin <feature>` happens with the user's first pushed commit.
