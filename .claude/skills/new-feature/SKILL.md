---
name: new-feature
description: Scaffolds a moose_stack feature workspace under ~/projects/moose-worktrees/<feature> with matching branches on the meta-repo and all three submodules, the shared pinned conda env, a cloned CodeGraph DB, remapped clangd DBs, and a combined-opt hydrated from the canonical MOOSE seed. Use for "/new-feature <name>", "new feature worktree", "start a feature". Manual invoke only.
disable-model-invocation: true
argument-hint: "<feature-name>"
effort: medium
allowed-tools:
  - Bash(git worktree *)
  - Bash(git branch *)
  - Bash(git -C *)
  - Bash(conda env list)
  - Bash(conda run *)
  - Bash(python3 ~/projects/moose_stack/.claude/skills/new-feature/scripts/hydrate_moose_combined.py *)
  - Bash(bash ~/projects/moose_stack/scripts/moose-env.sh *)
  - Bash(hostname)
  - Bash(ls *)
  - Bash(rmdir *)
  - Bash(mkdir *)
  - Bash(cp *)
  - Bash(sed *)
  - Bash(sqlite3 *)
  - Bash(codegraph *)
---

# /new-feature

Creates `~/projects/moose-worktrees/<feature>/` with branch `<feature>` on the meta-repo and on `moose`, `blackbear`, `isopod`, so the meta-repo can bump submodule pointers cleanly later. Local conda host only. The name is kebab-case; without one, ask. Any failed step stops the run with a report and leaves the workspace as it is.

Four facts:
- This skill does not run `git submodule update --init` in the worktree; the submodule worktrees are the source of truth.
- This skill does not `mv` the tracked `moose_stack.code-workspace`; it copies it (the copy is gitignored).
- This skill does not run `codegraph init` and does not copy `daemon.sock`, `daemon.pid`, `*-wal`, or `*-shm`; the worktree spawns its own daemon on first `sync`.
- This skill does not tear down a partial workspace; the user decides what to clean up.

## Commands, in order

1. Preflight. `env_name` is the shared env (one per moose-dev pin; existing is expected). `<feature>` must exist on none of the four repos. `moose_stack` must sit at `main` and each submodule at `devel`, with the three submodule SHAs equal to the gitlinks in `moose_stack/main`; stop before any mutation if a pair differs. Retain the SHA and lease that `preflight` prints; both later helper calls take that exact lease.
   ```bash
   env_name=$(bash ~/projects/moose_stack/scripts/moose-env.sh ~/projects/moose_stack)
   ```
   ```bash
   for r in moose_stack moose_stack/moose moose_stack/blackbear moose_stack/isopod; do
     git -C ~/projects/$r branch --list <feature>
   done
   ```
   ```bash
   git -C ~/projects/moose_stack rev-parse HEAD main
   for r in moose blackbear isopod; do
     git -C ~/projects/moose_stack/$r rev-parse HEAD devel
   done
   git -C ~/projects/moose_stack ls-tree main moose blackbear isopod
   ```
   ```bash
   python3 ~/projects/moose_stack/.claude/skills/new-feature/scripts/hydrate_moose_combined.py \
     preflight --donor ~/projects/moose_stack/moose
   ```
   A missing or stale donor manifest fails here; refresh it after a clean, settled combined opt build with `python3 ~/projects/moose_stack/.claude/skills/new-feature/scripts/hydrate_moose_combined.py stamp --donor ~/projects/moose_stack/moose`.

2. Meta-repo worktree and specs home.
   ```bash
   mkdir -p ~/projects/moose-worktrees   # shared home for all feature worktrees
   git -C ~/projects/moose_stack worktree add ~/projects/moose-worktrees/<feature> -b <feature> main
   mkdir -p ~/projects/moose-worktrees/<feature>/specs   # home for blueprint.html (see /moose-blueprint)
   cp ~/projects/moose-worktrees/<feature>/moose_stack.code-workspace ~/projects/moose-worktrees/<feature>/<feature>.code-workspace
   ```

3. Submodule worktrees, for each of `moose`, `blackbear`, `isopod`. Apps find MOOSE through `../moose`.
   ```bash
   rmdir ~/projects/moose-worktrees/<feature>/<sub>   # empty dir left by step 2, if present
   git -C ~/projects/moose_stack/<sub> worktree add ~/projects/moose-worktrees/<feature>/<sub> -b <feature> devel
   ```

4. CodeGraph DB: copy and sync (about 50 s; a full rebuild takes minutes). Skip and note it when `~/projects/moose_stack/.codegraph/codegraph.db` is absent. Independent of step 5.
   ```bash
   # Flush main's WAL so a single-file copy is consistent, then APFS-clone the DB (instant, same volume)
   sqlite3 ~/projects/moose_stack/.codegraph/codegraph.db "PRAGMA wal_checkpoint(TRUNCATE);"
   mkdir -p ~/projects/moose-worktrees/<feature>/.codegraph
   cp -c ~/projects/moose_stack/.codegraph/codegraph.db ~/projects/moose-worktrees/<feature>/.codegraph/codegraph.db
   cp    ~/projects/moose_stack/.codegraph/.gitignore   ~/projects/moose-worktrees/<feature>/.codegraph/.gitignore
   ( cd ~/projects/moose-worktrees/<feature> && codegraph sync . )   # re-parses only changed files; prunes files absent from the worktree
   ```

5. Conda env: reused when present (verified against the donor manifest), created from the manifest lock otherwise.
   ```bash
   python3 ~/projects/moose_stack/.claude/skills/new-feature/scripts/hydrate_moose_combined.py \
     create-env \
     --donor ~/projects/moose_stack/moose \
     --target ~/projects/moose-worktrees/<feature>/moose \
     --name "$env_name" \
     --lease <donor-lease>
   ```

6. Hydrate MOOSE combined, before any feature edit. A failure after installation begins leaves the workspace in place for diagnosis; no cold build fallback.
   ```bash
   conda run -n "$env_name" python \
     ~/projects/moose_stack/.claude/skills/new-feature/scripts/hydrate_moose_combined.py \
     hydrate \
     --donor ~/projects/moose_stack/moose \
     --target ~/projects/moose-worktrees/<feature>/moose \
     --lease <donor-lease>
   ```

7. clangd: remap the canonical compile DBs by repo-root path and clone `.cache/`. Skip and note it when the root `compile_commands.json` is absent. `/compile-commands` regenerates them later.
   ```bash
   src=~/projects/moose_stack
   dst=~/projects/moose-worktrees/<feature>
   for f in compile_commands.json moose/test/compile_commands.json moose/modules/combined/compile_commands.json blackbear/compile_commands.json isopod/compile_commands.json; do
     [ -f "$src/$f" ] && sed "s|$src|$dst|g" "$src/$f" > "$dst/$f"
   done
   [ -d "$src/.cache" ] && cp -c -R "$src/.cache" "$dst/.cache"
   ```

## Report

Workspace path; the `<feature>.code-workspace` file to open in VS Code; env name and whether it was reused or created; the four branches created; CodeGraph status (or skipped); clangd DB/index status (seeded or skipped); donor SHA/lease; objects reused versus rebuilt locally; hydration timing/validation; a reminder to `conda activate <env-name>`. State that BlackBear and Isopod were worktreed but not hydrated or built. Point to `docs/local.md` if the branch later bumps `moose`. Next steps: `/moose-blueprint` in the worktree, then `/moose-build`, then `/moose-ship`.

Host: !`hostname`
