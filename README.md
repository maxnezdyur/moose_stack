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

## Feature worktrees

To work on a feature that touches multiple repos, create a sibling workspace that pairs worktrees from each baseline submodule:

```bash
mkdir -p ../creep-model
git -C moose     worktree add ../../creep-model/moose     -b creep-model
git -C blackbear worktree add ../../creep-model/blackbear -b creep-model
# (only include repos the feature actually touches)
```

Inside `../creep-model/blackbear`, `../moose` resolves to the paired MOOSE worktree — no `MOOSE_DIR` env juggling.

## Updating submodule pointers

When one of the app forks advances and you want this stack to track the new tip:

```bash
git submodule update --remote moose      # or blackbear / isopod
git add moose
git commit -m "bump moose to $(git -C moose rev-parse --short HEAD)"
git push
```
