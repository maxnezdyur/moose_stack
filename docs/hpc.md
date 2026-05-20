# INL HPC (container modules)

Per-feature env setup on an INL HPC login node (Sawtooth, Lemhi, Bitterroot, Hoodoo). Pairs with [`../README.md`](../README.md) for the worktree layout, and [`local.md`](local.md) for the local equivalent.

INL HPC uses containerized environment modules instead of conda. PETSc, libMesh, and WASP are pre-built inside the container — no `update_and_rebuild_*` scripts needed.

## Storage layout

- `/home/$USER` — Isilon NFS, shared site-wide, slow. Configs and small files.
- `/projects/...` — Isilon NFS, shared site-wide. Durable storage.
- `/scratch/$USER` — GPFS, shared site-wide, fast. Clone `moose_stack` here.

`/scratch` gives both fast parallel I/O and cross-cluster visibility. Confirm site purge policy before parking anything irreplaceable there.

## Per-feature setup

After creating the feature worktrees per `../README.md`, populate the moose submodules and load the matching container:

```bash
cd /scratch/$USER/projects/<feature>/moose
git submodule update --init --recursive     # libmesh, petsc, wasp, large_media
HASH=$(./scripts/versioner.py moose-dev)
module load use.moose moose-dev-openmpi/$HASH
```

The versioner hash is derived from the moose tree plus its submodules, so each worktree resolves to the correct module version automatically.

Always pin the version. Bare `module load moose-dev-openmpi` loads the latest build and will mismatch your source.

## Build

Enter the container shell, then build normally:

```bash
moose-dev-shell
cd /scratch/$USER/projects/<feature>/blackbear
make -j N
./run_tests -j N
exit
```

## Run

**Single host** (interactive node, debugging):

```bash
moose-dev-shell
mpiexec -n N ./blackbear-opt -i input.i
```

**Multi-host** (SLURM job):

```bash
#!/bin/bash
#SBATCH -N 2
#SBATCH -n 96
#SBATCH -t 4:00:00
module load use.moose moose-dev-openmpi/<HASH>
mpiexec -n $SLURM_NTASKS moose-dev-exec ./blackbear-opt -i input.i
```

`moose-dev-exec` runs a single command inside the container per rank — required when MPI spans multiple hosts. Always pass `-n` to `mpiexec` (OpenMPI quirk; the container requires it).

## Templates

Two reusable scripts live at the meta-repo root under [`../scripts/`](../scripts/):

- [`scripts/build-opt.sbatch`](../scripts/build-opt.sbatch) — `sbatch`-able dual-purpose script. Bakes in `#SBATCH` headers for the `short` partition with 32 ranks and bootstraps itself into the container. Builds `combined-opt` (moose/modules/combined), `blackbear-opt`, and `isopod-opt` in dependency order.
- [`scripts/moose-job.sbatch`](../scripts/moose-job.sbatch) — multi-node SLURM template for production runs using `moose-dev-exec`. Parametrized via `APP_PATH`, `INPUT`, and `MOOSE_DEV_VERSION`.

INL requires `--wckey=<project>` on every `salloc` and `sbatch`. The templates default to `neams`; override via `sbatch --wckey=<other>` as needed.

Compile (one-shot, asynchronous):

```bash
sbatch scripts/build-opt.sbatch        # defaults: short partition, 32 ranks, 2h walltime
squeue --me                        # watch for state R, then CD
tail -f moose-build.<jobid>.out    # follow the build log
```

To bump ranks/time without editing the script:

```bash
sbatch --ntasks=48 --time=04:00:00 scripts/build-opt.sbatch
```

Then submit a run with the production template:

```bash
HASH=$(./moose/scripts/versioner.py moose-dev)
MOOSE_DEV_VERSION=$HASH \
  sbatch --export=ALL,APP_PATH=$PWD/blackbear/blackbear-opt,INPUT=in.i \
  scripts/moose-job.sbatch
```

## Teardown

After removing worktrees per `../README.md`:

```bash
module purge
```

Modules are global, so there's no per-feature env to remove.
