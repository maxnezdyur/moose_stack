# moose_stack — operating guide

Meta-repo pinning three forks as submodules: `moose/`, `blackbear/`, `isopod/`. Each submodule is an independent repo; this stack tracks their tips together.

## Remotes (every submodule)

- `origin` → `maxnezdyur/<repo>` (push + fetch)
- `upstream` → `idaholab/<repo>` (fetch only — push URL is `DISABLED_UPSTREAM_PUSH`)
- Never add, re-enable, or push to idaholab upstream. Sync is manual via GitHub web UI.

## Starting a feature

Create a sibling workspace outside `moose_stack` so the baseline stays pristine. Apps find MOOSE via `../moose`, so pair a MOOSE worktree even if the feature is app-only.

```bash
mkdir -p ~/projects/<feature>
git -C ~/projects/moose_stack/<app>  worktree add ~/projects/<feature>/<app>  -b <feature>
git -C ~/projects/moose_stack/moose  worktree add ~/projects/<feature>/moose  --detach
git -C ~/projects/<feature>/moose submodule update --init --recursive
```

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

```bash
git -C ~/projects/moose_stack/<app>  worktree remove ~/projects/<feature>/<app>
git -C ~/projects/moose_stack/moose  worktree remove ~/projects/<feature>/moose
rmdir ~/projects/<feature>
```

## Default branches

- `moose` → `devel`
- `blackbear`, `isopod` → `devel`
- This meta-repo → `main`
