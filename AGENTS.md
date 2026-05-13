# AGENTS.md

# moose_stack — operating guide

Meta-repo pinning three forks as submodules: `moose/`, `blackbear/`, `isopod/`. Each submodule is an independent repo; this stack tracks their tips together.

`moose` is the framework + physics modules. `blackbear` (structural degradation) and `isopod` (multiphysics constrained optimization) are MOOSE-based apps that link against it.

## Remotes (every submodule)

- `origin` → `maxnezdyur/<repo>` (push + fetch)
- `upstream` → `idaholab/<repo>` (fetch only — push URL is `DISABLED_UPSTREAM_PUSH`)
- Never add, re-enable, or push to idaholab upstream. Sync is manual via GitHub web UI.

## Default branches

- `moose` → `devel`
- `blackbear`, `isopod` → `devel`
- This meta-repo → `main`

## Building

Always build via `.codex/scripts/build.sh` — never call `make` directly and never inline `CONDA_PREFIX=… PATH=… make`. The script discovers the meta-repo root, resolves the conda env, sets `CONDA_PREFIX`/`CONDA_DEFAULT_ENV`/`PATH`, and runs `make -jN METHOD=<method>` in the right dir.

```
.codex/scripts/build.sh <target> [opt|dbg] [--env <name>] [-j N] [-- <extra make args>]
```

Targets: `moose-test`, `moose-combined`, `blackbear`, `isopod`, any moose module name (e.g. `heat_transfer`), or any path containing a `Makefile`. Defaults: `opt`, `--env moose`, `-j` defaults to 4 if user has not overriden. Use `dbg` for debug builds.

## Testing
conda run -n moose env PATH=$(conda info --base)/envs/moose/bin:$PATH MOOSE_MPI_COMMAND=$(conda info --base)/envs/moose/bin/mpiexec.hydra python ./run_tests
