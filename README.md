# moose_stack

My MOOSE development stack. Pins my forks of [moose](https://github.com/maxnezdyur/moose), [blackbear](https://github.com/maxnezdyur/blackbear), and [isopod](https://github.com/maxnezdyur/isopod) as submodules so the three repos can be cloned, versioned, and updated together.

## Clone

```bash
git clone --recurse-submodules https://github.com/maxnezdyur/moose_stack.git
cd moose_stack
# moose has its own submodules (libmesh, petsc, wasp, large_media) — init them:
git -C moose submodule update --init --recursive
```

## Layout

```
moose_stack/
├── moose/       # maxnezdyur/moose (default branch: next)
├── blackbear/   # maxnezdyur/blackbear (default branch: devel)
└── isopod/      # maxnezdyur/isopod  (default branch: devel)
```

Each app's Makefile locates MOOSE via the relative path `../moose`, which resolves to the sibling submodule.

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

Inside `~/projects/<feature>/blackbear`, `../moose` resolves to the paired MOOSE worktree — no `MOOSE_DIR` env juggling.

## Opening a PR

Target idaholab via `--head maxnezdyur:`:

```bash
cd ~/projects/<feature>/<app>
git push -u origin <feature>
gh pr create --repo idaholab/<app> --base devel --head maxnezdyur:<feature>
```

## Updating submodule pointers

When one of the app forks advances and you want this stack to track the new tip:

```bash
git submodule update --remote moose      # or blackbear / isopod
git add moose
git commit -m "bump moose to $(git -C moose rev-parse --short HEAD)"
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
