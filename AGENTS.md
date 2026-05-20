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

## Environment

Two parallel env-management flows. Pick by host:

- Local machine (conda) → [`docs/local.md`](docs/local.md)
- INL HPC (container modules; hostnames like `sawtooth*`, `lemhi*`, `bitterroot*`, `hoodoo*`) → [`docs/hpc.md`](docs/hpc.md)

Quick host check before running any moose commands:

```bash
case "$HOSTNAME" in
  sawtooth*|lemhi*|bitterroot*|hoodoo*) echo "HPC — see docs/hpc.md" ;;
  *) echo "local — see docs/local.md" ;;
esac
```
