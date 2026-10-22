---
name: feature-remove
description: Safely removes a moose_stack feature workspace under ~/projects/moose-worktrees/<feature>. Probes the meta-repo and the moose, blackbear, isopod worktrees for uncommitted changes, untracked files, commits on no remote, and a live session or held lease, refuses with a report on any hit, and otherwise hands off to `factory teardown`. Use for "/feature-remove [<feature>]", "remove this worktree", "delete the feature workspace". Manual invoke only.
disable-model-invocation: true
argument-hint: "[<feature>]"
effort: low
allowed-tools:
  - Bash(git -C *)
  - Bash(test *)
  - Bash(cat *)
  - Bash(ls *)
  - Bash(~/projects/moose_stack/factory/factory status *)
  - Bash(~/projects/moose_stack/factory/factory teardown *)
---

# /feature-remove

Proves that no work is lost, then hands off to `factory teardown`. This skill deletes nothing itself. It runs no `git worktree remove`, no `git branch -D`, no `rm`, and never passes `--force` to teardown. Teardown already enforces the teardown gate, open PRs, a live session, a held lease, dirty trees and never-pushed branches (`factory/tool/ext_teardown.py`); this skill adds the checks teardown does not make (untracked files by name, commits on no remote even when the branch tracks one) and stops before teardown ever sees `--force`.

## Feature and paths

The argument names the feature. Without one, walk up from the cwd to the directory whose `.git` is a file beside `moose/`, `blackbear/`, `isopod/`, under `~/projects/moose-worktrees/`; its basename is the feature. Otherwise ask. `W=~/projects/moose-worktrees/<feature>`. The four checkouts are `$W`, `$W/moose`, `$W/blackbear`, `$W/isopod`. A missing `$W` is not an error: report it and go to the hand-off, which removes the branches and says what remains.

## Probes

Run every probe on all four checkouts before you report anything.

1. Uncommitted changes: `git -C <c> status --porcelain --untracked-files=no`. Any line blocks.
2. Untracked files that are not ignored: `git -C <c> ls-files --others --exclude-standard`. Any path blocks. Ignored files (`specs/gallery/`, build outputs, `.factory-lease/`) do not; teardown copies the gallery into the vault before it removes anything.
3. Commits on no remote: `git -C <c> log --oneline HEAD --not --remotes`. Any commit blocks. This catches a branch that tracks `origin/<feature>` but has local commits past it, which teardown reports as pushed. Run it after `git -C <c> fetch --prune --all`, so a remote ref deleted after a merge does not hide a commit. A fetch that fails is a blocker: the count is unknown.
4. Live session or lease:
   ```bash
   ~/projects/moose_stack/factory/factory status <feature>
   test -d $W/.factory-lease && cat $W/.factory-lease/lease.json
   ```
   A `session:` value other than `none` blocks. A lease directory blocks; report its `bg_id`, `pid`, `host`, `acquired`.

## Decide

On any hit, report every finding grouped by checkout, then stop. Give the command that clears each one; never run it:

- uncommitted or untracked: commit it, or move it out of the worktree (`.gitignore` it only when it is a run artifact);
- commits on no remote: `git -C <c> push -u origin <feature>`;
- live session: `~/projects/moose_stack/factory/factory stop <feature>`;
- lease with no live owner: `~/projects/moose_stack/factory/factory release <feature>`.

Do not offer an override.

## Hand-off

When every probe passes, run teardown in print mode. It prints the recipe and its own blockers and changes nothing:

```bash
~/projects/moose_stack/factory/factory teardown <feature>
```

Relay its blockers verbatim (the `teardown` gate, an OPEN PR) with the commands it names. Teardown's `--yes` refuses without an interactive terminal, so this session cannot run it. When the recipe has no blockers, tell the user to run it in their own terminal:

```bash
~/projects/moose_stack/factory/factory teardown <feature> --yes
~/projects/moose_stack/factory/factory archive <feature>
```

## Report

Per checkout: branch, clean or not, untracked count, commits on no remote. Session and lease state. Teardown's blockers, its reclaimable size, and whether it removes the conda env (only when `specs/.factory-env` says `env_reused: false`). The two commands for the user's terminal, or the list of blocks.
