# CLAUDE.md

# moose_stack operating guide

Meta-repo that pins three forks as submodules: `moose/`, `blackbear/`, `isopod/`. Each submodule is an independent repo. This stack tracks their tips together. `moose` is the framework and the physics modules. `blackbear` (structural degradation) and `isopod` (multiphysics constrained optimization) are MOOSE-based apps that link against it.

## Remotes (every submodule)

- `origin` = `maxnezdyur/<repo>` (push and fetch).
- `upstream` = `idaholab/<repo>` (fetch only; the push URL is `DISABLED_UPSTREAM_PUSH`).
- Never add, re-enable, or push to the idaholab upstream. Sync is manual through the GitHub web UI.

## Branches and pull requests

- Default branches: `moose`, `blackbear`, and `isopod` use `devel`; this meta-repo uses `main`.
- Every PR to `idaholab/<app>` sets the base branch to `next`. CIVET's precheck rejects PRs against `devel`. `next` is only the PR target: branch from `devel` and diff against `devel`.
- Create PRs as drafts (`--draft`). I mark them ready in the GitHub UI. Never mark a PR ready.
- `gh pr create --repo idaholab/<app> --base next --head maxnezdyur:<feature> --draft`

## CIVET precheck facts

- Code files (`.C`, `.h`, `.py`, `.i`, `tests`) are 7-bit ASCII. `.md` and `.bib` are exempt.
- Every new `tests` spec block carries `requirement`, `design`, and `issues`. A parent block covers its children.

## Git context

A git-oriented skill (`branch-diff`, `commit`) targets the submodule I am working in, not the meta-repo root. Detect it from `cwd`. Ask which submodule only when it is ambiguous.

## Worktrees

Feature work happens in `~/projects/moose-worktrees/<feature>/`, a full copy of this layout that `/new-feature` creates. Skills and scripts run inside the worktree they are invoked from.

## Environment

Check `hostname` before any env, build, or test command:

- Local machine (conda): [`docs/local.md`](docs/local.md). Run commands through `scripts/conda-run.sh -C <path> -- <command>`.
- INL HPC (container modules; hostnames `sawtooth*`, `lemhi*`, `bitterroot*`, `hoodoo*`, `teton*`): [`docs/hpc.md`](docs/hpc.md). Run bare commands inside the container.

## Codex mirror

Codex reads this tree through the tracked symlink `.agents -> .claude`. A skill with `disable-model-invocation: true` has `agents/openai.yaml` beside it with `allow_implicit_invocation: false`. Codex ignores the `skills:` preload on agents, so each agent names its preloaded skills in its body.
