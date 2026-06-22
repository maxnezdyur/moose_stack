---
name: new-feature
description: Scaffold a new moose_stack feature workspace — creates a meta-repo worktree with feature branches on all three submodules, a cloned conda env, and a bootstrapped CodeGraph index. Manual-invoke only.
disable-model-invocation: true
allowed-tools:
  - Bash(git worktree *)
  - Bash(git branch *)
  - Bash(git -C *)
  - Bash(conda create *)
  - Bash(conda env list)
  - Bash(ls *)
  - Bash(rmdir *)
  - Bash(mkdir *)
  - Bash(cp *)
  - Bash(sqlite3 *)
  - Bash(codegraph *)
---

# /new-feature

Scaffold a new feature workspace for moose_stack. Creates a worktree of the meta-repo with feature branches on the meta-repo and all three submodules (`moose`, `blackbear`, `isopod`), plus a cloned conda env.

## Usage

/new-feature <feature-name>

No pairing prompt — every submodule always gets a feature-branch worktree. Use the app(s) you need; leave the others untouched.

## Steps

1. Read the feature name from the argument. If missing, ask the user.
2. Validate (stop and report on any failure — do not clean up):
   - Name is kebab-case (lowercase, hyphens, no spaces).
   - `~/projects/<feature>/` does not already exist.
   - `conda env list` does not already contain `moose-<feature>`.
   - Branch `<feature>` does not exist on any of: `moose_stack`, `moose`, `blackbear`, `isopod`. Check with:
     ```bash
     for r in moose_stack moose_stack/moose moose_stack/blackbear moose_stack/isopod; do
       git -C ~/projects/$r branch --list <feature>
     done
     ```
3. Create the meta-repo worktree on a new feature branch:
   ```bash
   git -C ~/projects/moose_stack worktree add ~/projects/<feature> -b <feature>
   mkdir -p ~/projects/<feature>/specs   # home for spec.md + blueprint.html (see /moose-design-feature)
   ```
   This leaves submodule paths as empty directories (gitlinks only).
4. For each of `moose`, `blackbear`, `isopod`, create a submodule worktree on a matching feature branch:
   ```bash
   rmdir ~/projects/<feature>/<sub>   # remove empty dir left by step 3 if present
   git -C ~/projects/moose_stack/<sub> worktree add ~/projects/<feature>/<sub> -b <feature>
   ```
5. Bootstrap the CodeGraph index for the new worktree by cloning the meta-repo's existing index — do NOT rebuild from scratch. Skip this step (and note it) if `~/projects/moose_stack/.codegraph/codegraph.db` does not exist.
   ```bash
   # Flush main's WAL so a single-file copy is consistent, then APFS-clone the DB (instant, same volume)
   sqlite3 ~/projects/moose_stack/.codegraph/codegraph.db "PRAGMA wal_checkpoint(TRUNCATE);"
   mkdir -p ~/projects/<feature>/.codegraph
   cp -c ~/projects/moose_stack/.codegraph/codegraph.db ~/projects/<feature>/.codegraph/codegraph.db
   cp    ~/projects/moose_stack/.codegraph/.gitignore   ~/projects/<feature>/.codegraph/.gitignore
   # Re-index only the branch diff; also prunes vendored/build files absent from the worktree (~50s, not minutes)
   ( cd ~/projects/<feature> && codegraph sync . )
   ```
   The copied DB uses relative paths, so it is valid in the new worktree as-is; `sync` only re-parses changed files. Independent of the conda clone — safe to run concurrently with the next step.
6. Clone the conda env:
   ```bash
   conda create -n moose-<feature> --clone moose -y
   ```
7. Report: workspace path, env name, the four branches created, the CodeGraph index status (or that it was skipped), and tell the user to `conda activate moose-<feature>` to start working.

## Rules

- Never mutate the base `moose` conda env — always clone.
- Every submodule always gets a feature-branch worktree — no pairing prompt. This keeps all four repos on a matching branch name so the meta-repo can bump pointers cleanly later.
- Do NOT run `git submodule update --init` inside the meta-repo worktree. The submodule worktrees from step 4 are the source of truth; `update --init` would try to clone into those paths and conflict.
- Apps locate MOOSE via `../moose` (Makefile fallback). The paired MOOSE worktree from step 4 satisfies this.
- Do NOT run `update_and_rebuild_libmesh.sh` / `update_and_rebuild_petsc.sh` / `update_and_rebuild_wasp.sh` here. Those only run later if the feature branch bumps those submodules.
- CodeGraph: always **copy + sync**, never `codegraph init`. The 1 GB DB stores relative paths, so cloning the meta-repo's DB and syncing the diff is ~50s vs a multi-minute full rebuild. Copy only `codegraph.db` + `.gitignore` (never the `daemon.sock`/`daemon.pid`/`*-wal`/`*-shm`); the new worktree spawns its own daemon on first `sync`. The DB is gitignored and machine-local by design — do not commit it (it exceeds GitHub's 100 MB limit, bloats history, and goes stale immediately).
- Branches are local-only at create time. First `git push -u origin <feature>` happens when the user pushes their first commit (see CLAUDE.md §"Opening a PR").
- On failure at any step, stop and report — do not partially tear down. The user decides what to clean up.

## Canonical reference

See `CLAUDE.md` §"Starting a feature" for the sequence this skill automates.
