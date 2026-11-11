# The test lab for `scripts/stack`

This directory holds the tests for `scripts/stack`, the tool that owns every git write on an epic
branch. The contract is `specs/epic-stack-plan.md`, section "The stack script".

## Run the tests

Run this command from the repository root:

```sh
python3 -m unittest discover -s scripts/tests -v
```

Run one test:

```sh
python3 -m unittest discover -s scripts/tests -k merge_race -v
```

The tests need git 2.38 or later and Python 3.9 or later. They need no network and no GitHub
account.

## What a test builds

Each test builds its own repositories in a temporary directory. The directory is removed when the
test ends.

| Path | Role |
|---|---|
| `upstream.git` | The stand-in for `idaholab/moose`. It has the branches `devel` and `next`. `next` is ahead of `devel`. |
| `origin.git` | The stand-in for the fork. Slice branches are pushed here. |
| `wt/moose` | The work checkout, on the epic branch `E`. `wt/` is the worktree root, and it holds `specs/epic.md`. |
| `maint` | A second clone. It plays the maintainer: it merges into `next` and pushes to PR heads. |
| `fake_gh.py` | The stand-in for `gh`. It reads PR states from `gh.json`. |
| `bin/git-clang-format` | The stand-in for the formatter. It is first on `PATH`, so no test runs the real one. |

No test reads or writes a real repository. Each git call runs with an empty global configuration.

## Slice branch names

The branch of slice `n` of epic `E` is `epic/E/s<n>`, locally and on the fork. The epic branch is
`E`. A slice id is `s<n>` in each command and in each table.

One constant in `scripts/stack` spells the branch name: `SLICE_BRANCH`. The functions
`slice_branch`, `parse_slice_branch` and `slice_namespace` are the only code that uses it. The
tests do not write a slice branch name as a literal. They use `sref(n)` and the constants `S1` to
`S4`, which call `slice_branch`. To rename the slice branches, change `SLICE_BRANCH` and the three
tests in the class `Names` that state the name on purpose.

## What each group proves

| Class | Proves |
|---|---|
| `SealAndStatus` | A slice id is never used again. `seal` refuses unfinished work. `status --json` has a stable shape. `base` prints a commit that is an ancestor of HEAD. |
| `Park` | `park` and `unpark` restore the staged set, the unstaged edits and the untracked files exactly. `unpark` with nothing parked changes nothing. |
| `Fix` | A squash fix and an append fix put the change in the right slice. A conflict moves no ref until the restack ends. An abort restores everything. No other branch moves. |
| `Push` | A push is all or nothing. A lease with an explicit SHA protects a foreign commit, also after a fetch. A slice that only moved is not pushed. |
| `MergeAndSync` | A merged slice keeps its SHA. The PR above it shows only its own slice with no rebase. `sync` rebases onto `upstream/next` only, and only on request. The merge race stops. |
| `Adopt`, `AdoptMessages` | Commits that a maintainer appended enter the local chain. A diverged fork branch is refused, and its commit is kept. A fork that is only behind is not an error. |
| `LinkedWorktree` | The tool works in a checkout that is a `git worktree`, as the factory makes them. |
| `Lease` | A live session that holds `.factory-lease` blocks every rewrite and every push. |
| `Names` | The slice branch name comes from one place and is parsed strictly. A branch with a similar name is not a slice. A branch that blocks the name is refused. |
| `NoSilentForcePush` | A rewrite of a PR head that is in review, or whose state is not known, needs `--yes`. A fast-forward does not. |
| `ContentIdentity` | A change of whitespace, of a file mode, of a binary file or of blank lines counts as a change. The user's git configuration cannot change a result. A failed commit leaves nothing behind. |
| `RaceAndRecovery` | The merge race shows with no answer from GitHub. A killed restack can always be undone or completed. A lost fix is never reported as done. A push sends the commit that was checked. |
| `NotAnEpic` | The tool never acts on the meta repository, on a plain feature branch or on a detached HEAD. |
| `AwkwardFiles` | Renames, deletes, mode changes, binary files, ignored files and names that are not ASCII survive `park`, a conflict and `unpark`. |

## The scenario behind each test

Each test name states its scenario. The scenarios come from the red-team run of 2026-11-10 and
from the adversarial review of the first version of the tool. The table at the end of
`specs/epic-stack-plan.md` maps each red-team finding to a rule.

## Add a test

1. Build the state with the `Lab` helpers: `chain`, `slice`, `edit_line`, `upstream_merge`,
   `maintainer_push`, `set_pr`. Name a slice branch with `sref(n)` or `S1` to `S4`.
2. Call the tool with `lab.ok(...)` when it must succeed. Call `self.refuse(...)` when it must
   refuse.
3. For a refusal, assert that no ref moved. Compare `self.refs()` before and after.
4. To test a kill, use `self.crash(argv, "<function>")`. It stops the tool when it reaches that
   function.
