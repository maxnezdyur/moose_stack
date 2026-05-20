# Local development (conda)

Per-feature env setup on a local machine. Pairs with [`../README.md`](../README.md) for the worktree layout, and [`hpc.md`](hpc.md) for the INL HPC equivalent.

## Base env (one-time)

```bash
conda create -n moose moose-dev -c https://conda.software.inl.gov/public
```

This is the shared base. Never modify it directly — clone it per feature.

## Per-feature env

After creating the feature worktrees per `../README.md`:

```bash
conda create -n moose-<feature> --clone moose
conda activate moose-<feature>
```

Cloning isolates any `update_and_rebuild_*` runs from the base.

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
