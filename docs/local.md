# Local development (conda)

Shared version-pinned env setup on a local machine. Pairs with [`../README.md`](../README.md) for the worktree layout, and [`hpc.md`](hpc.md) for the INL HPC equivalent.

## Shared envs — one per moose-dev pin

Each env is named for its moose-dev pin: version `YYYY.MM.DD` → `moose-<M>.<DD>` (month's leading zero stripped, day verbatim). Example: `2026.08.19` → `moose-8.19`. Every worktree on the same pin uses the same env. Treat shared envs as read-only — never `conda install`/`update` into one.

To find the env name for any worktree:

```bash
bash ~/projects/moose_stack/scripts/moose-env.sh <path-inside-worktree>   # prints e.g. moose-8.19
```

The helper reads the pin from the worktree's own `moose/conda/moose-dev/meta.yaml`.

## Create an env for a pin (when it does not exist)

```bash
conda create -n moose-<M.DD> moose-dev=<version> -c https://conda.software.inl.gov/public
conda activate moose-<M.DD>
```

`/new-feature` does this automatically — it reuses the env when present (verified against the donor's exact package lock) and creates it from that lock otherwise.

MOOSE and its conda packages move in lockstep. If a branch bumps `moose` to a commit with a different moose-dev version, the helper prints a new env name — create that env with the new pin. The old env stays for worktrees still on the old pin.

## Run a command in a worktree's env

Scripts and skills should not hardcode a conda path — the install prefix differs per machine, and in a non-interactive shell `conda` is often a lazy shell function rather than a binary on `PATH`. Use the wrapper:

```bash
bash ~/projects/moose_stack/scripts/conda-run.sh -C <path-inside-worktree> -- <command> [args...]
bash ~/projects/moose_stack/scripts/conda-run.sh --print-env            # just the env name
```

It resolves the worktree's pinned env with `moose-env.sh`, discovers conda, activates, and execs the command. It searches `$MOOSE_CONDA_BASE`, `$CONDA_EXE`, `conda` on `PATH`, `$CONDA_ROOT`, `$MAMBA_ROOT_PREFIX`, then the usual install roots.

On a machine whose conda sits somewhere unusual, set `MOOSE_CONDA_BASE` to the base prefix (the directory that holds `etc/profile.d/conda.sh`) in that machine's shell profile. Do not add the path to the script.

## Build

From your app's worktree with the env active:

```bash
cd ~/projects/moose-worktrees/<feature>/blackbear   # or isopod
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

Shared envs outlive individual worktrees. Remove an env only when no remaining worktree resolves to it:

```bash
for w in ~/projects/moose_stack ~/projects/moose-worktrees/*/; do bash ~/projects/moose_stack/scripts/moose-env.sh "$w"; done | sort -u
conda env remove -n moose-<M.DD>   # only if absent from the list above
```
