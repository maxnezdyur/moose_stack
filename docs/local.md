# Local development (conda)

Per-feature env setup on a local machine. Pairs with [`../README.md`](../README.md) for the worktree layout, and [`hpc.md`](hpc.md) for the INL HPC equivalent.

## Base env (one-time)

```bash
conda create -n moose moose-dev -c https://conda.software.inl.gov/public
```

This is the shared base for day-to-day work in the meta-repo. Never modify it directly.

## Per-feature env

After creating the feature worktrees per `../README.md`, create a fresh env pinned to the moose-dev version the checkout needs (read from the worktree's own moose — the same source MOOSE's install docs use):

```bash
yq -r '.packages."moose-dev".version' ~/projects/<feature>/moose/scripts/versioner.yaml
conda create -n moose-<feature> moose-dev=<version> -c https://conda.software.inl.gov/public
conda activate moose-<feature>
```

A fresh pinned env matches the checkout exactly and isolates any `update_and_rebuild_*` runs from the base. MOOSE and its conda packages move in lockstep — if the branch bumps `moose` to a commit whose `versioner.yaml` reports a different version, recreate the env with the new pin.

## Build

From your app's worktree with the env active:

```bash
cd ~/projects/<feature>/blackbear   # or isopod
make -j N
./run_tests -j N
```

If MOOSE deps change (petsc/libmesh/wasp), rebuild before `make`:

```bash
./moose/scripts/update_and_rebuild_petsc.sh
./moose/scripts/update_and_rebuild_libmesh.sh
./moose/scripts/update_and_rebuild_wasp.sh
```

## Run

```bash
mpiexec -n N ./blackbear-opt -i input.i
```

## Teardown

After removing worktrees per `../README.md`:

```bash
conda env remove -n moose-<feature>
```
