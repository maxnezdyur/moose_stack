# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# moose_stack — operating guide

Meta-repo pinning three forks as submodules: `moose/`, `blackbear/`, `isopod/`. Each submodule is an independent repo; this stack tracks their tips together.

`moose` is the framework + physics modules. `blackbear` (structural degradation) and `isopod` (multiphysics constrained optimization) are MOOSE-based apps that link against it.

## Remotes (every submodule)

- `origin` → `maxnezdyur/<repo>` (push + fetch)
- `upstream` → `idaholab/<repo>` (fetch only — push URL is `DISABLED_UPSTREAM_PUSH`)
- Never add, re-enable, or push to idaholab upstream. Sync is manual via GitHub web UI.

## Starting a feature

Create a sibling worktree of the meta-repo outside `moose_stack` so the baseline stays pristine. Put a feature branch on the meta-repo and on every submodule — branch names all match `<feature>` so later the meta-repo can bump its submodule pointers cleanly. Clone the base `moose` conda env into a per-feature env so any `update_and_rebuild_*` runs stay isolated (never mutate the base env — it's shared across all worktrees).

```bash
# meta-repo worktree on a new feature branch (submodule paths are empty gitlinks)
git -C ~/projects/moose_stack worktree add ~/projects/<feature> -b <feature>

# for each submodule: remove the empty gitlink dir, then add a worktree on a matching branch
for sub in moose blackbear isopod; do
  rmdir ~/projects/<feature>/$sub
  git -C ~/projects/moose_stack/$sub worktree add ~/projects/<feature>/$sub -b <feature>
done

conda create -n moose-<feature> --clone moose
conda activate moose-<feature>
```

Do NOT run `git submodule update --init` inside the meta-repo worktree — the per-submodule worktrees above are the source of truth. All four branches are local-only at create time; push happens when you open a PR.

## Opening a PR

Target idaholab via `--head maxnezdyur:`:

```bash
cd ~/projects/<feature>/<app>
git push -u origin <feature>
gh pr create --repo idaholab/<app> --base devel --head maxnezdyur:<feature>
```

## Bumping submodule pointers in this stack

Only when you want the stack to track a new tip (usually after a merge lands upstream and your fork syncs):

```bash
git submodule update --remote <app>
git add <app> && git commit -m "bump <app> to $(git -C <app> rev-parse --short HEAD)"
git push
```

## Tearing down a feature workspace

Remove submodule worktrees first, then the meta-repo worktree, then the env. Delete feature branches only if nothing worth keeping lives on them.

```bash
for sub in moose blackbear isopod; do
  git -C ~/projects/moose_stack/$sub worktree remove ~/projects/<feature>/$sub
done
git -C ~/projects/moose_stack worktree remove ~/projects/<feature>
conda env remove -n moose-<feature>

# optional: drop the local branches if unused
for r in moose_stack moose_stack/moose moose_stack/blackbear moose_stack/isopod; do
  git -C ~/projects/$r branch -D <feature>
done
```

## Default branches

- `moose` → `devel`
- `blackbear`, `isopod` → `devel`
- This meta-repo → `main`
