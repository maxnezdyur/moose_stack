---
name: feature-sync
description: Refreshes a moose_stack feature workspace. Fetches every remote of the meta-repo and the moose, blackbear, isopod worktrees, reports ahead/behind per repo against upstream/devel (submodules) and origin/main (meta-repo), and offers a rebase only on a clean tree. Use for "/feature-sync [<feature>]", "sync the worktree", "how far behind devel am I", "rebase onto devel".
argument-hint: "[<feature>]"
effort: low
allowed-tools:
  - Bash(git -C *)
  - Bash(ls *)
---

# /feature-sync

Reports how far each repo of one feature workspace has drifted from its base. Changes history only after the user confirms. This skill never stashes, never uses `--autostash`, never force-pushes, never resolves a conflict, and never commits a pointer bump.

## Feature and paths

The argument names the feature. Without one, walk up from the cwd to the directory whose `.git` is a file beside `moose/`, `blackbear/`, `isopod/`, under `~/projects/moose-worktrees/`; its basename is the feature. Otherwise ask. `W=~/projects/moose-worktrees/<feature>`.

| checkout | remotes | base |
|---|---|---|
| `$W` (meta-repo) | `origin` = `maxnezdyur/moose_stack` | `origin/main` |
| `$W/moose` | `origin` = `maxnezdyur/moose`, `upstream` = `idaholab/moose` | `upstream/devel` |
| `$W/blackbear` | `origin` = `maxnezdyur/blackbear`, `upstream` = `idaholab/blackbear` | `upstream/devel` |
| `$W/isopod` | `origin` = `maxnezdyur/isopod`, `upstream` = `idaholab/isopod` | `upstream/devel` |

The fork's `origin/devel` is months stale. Never measure a submodule against it. Confirm the remotes with `git -C <c> remote -v`; a missing `upstream` stops the run with that finding.

## Step 1: fetch

```bash
git -C <c> fetch --prune --all
```

A failed fetch stops the run; the counts are unknown without it.

## Step 2: report drift

For each checkout:

- branch: `git -C <c> branch --show-current` (expect `<feature>`; anything else is a finding);
- behind and ahead of the base: `git -C <c> rev-list --left-right --count <base>...HEAD`;
- dirty: `git -C <c> status --porcelain`;
- pushed: test `git -C <c> rev-parse --verify --quiet origin/<feature>` first; only when it resolves, count `git -C <c> rev-list --count origin/<feature>..HEAD`. A missing remote branch is normal for a new feature.

For the meta-repo, also print the gitlinks: `git -C $W ls-tree HEAD moose blackbear isopod`, against each submodule's `HEAD`. A pointer that differs from the submodule `HEAD` is an unbumped or stale pointer.

## Step 3: offer a rebase

Offer it only for a checkout that is behind its base. Before the offer, check that checkout's tree. **A dirty tree refuses.** List its dirty files, tell the user to commit or stash them, and skip that checkout.

Ask with AskUserQuestion, one option per behind-and-clean checkout plus "none". On a confirmed checkout:

```bash
git -C <c> rebase <base>
```

On a conflict, stop at once. Report the conflicted files and the two commands: `git -C <c> rebase --continue` and `git -C <c> rebase --abort`.

## Submodule pointers

Say this whenever a submodule was rebased, or the meta-repo is behind `origin/main`:

- A submodule rebase rewrites its SHAs. Every `Bump <sub> to <sha>` commit on the meta-repo branch now points at a pre-rebase commit. Re-bump after the rebase: `git -C $W add <sub> && git -C $W commit -m "Bump <sub> to <short sha>"`.
- A submodule branch already on `origin` needs `git -C <c> push --force-with-lease origin <feature>`. An open PR on `idaholab/<sub>` then shows the rewritten history. The user runs that push.
- A meta-repo rebase onto `origin/main` can conflict on a gitlink when `main` bumped the same submodule. The feature's pointer is the one to keep (`git -C $W checkout --theirs <sub>`, then `git -C $W add <sub>`), checked against the submodule `HEAD`.
- A `moose` rebase onto a newer `devel` invalidates the hydrated combined build. Run `/moose-build` again before you trust a test result.
- `/new-feature` requires every gitlink on `main` to equal each submodule's `devel`; a stale `devel` in `~/projects/moose_stack/<sub>` is a separate fix and not this skill's job.

## Report

One block per checkout: branch, behind/ahead of its base, dirty count, pushed state, and the rebase result (rebased, skipped dirty, declined, conflict). Then the pointer block: each gitlink against the submodule `HEAD`, and the follow-up commands from the section above.
