---
name: moose-ship
description: Commits the finished MOOSE feature in its submodule, pushes the branch to origin, opens a draft PR against next, and bumps the meta-repo submodule pointer. The second human gate after /moose-build. Use for "/moose-ship [<submodule>]", "ship this feature", "open the PR", "commit and push the feature". Manual invoke only.
disable-model-invocation: true
argument-hint: "[<submodule>]"
effort: medium
allowed-tools:
  - Bash(git status *)
  - Bash(git diff *)
  - Bash(git log *)
  - Bash(git rev-list *)
  - Bash(gh pr view *)
  - Bash(gh pr list *)
---

# /moose-ship

Turns the tree `/moose-build` left green into one commit in the submodule, a pushed branch, a draft PR on `idaholab/<app>`, and a meta-repo pointer bump, then prints the PR URL. It runs only inside a `/new-feature` worktree: walk up from the cwd to the directory whose `.git` is a file beside `moose/`, `blackbear/`, and `isopod/`; anywhere else, refuse and say why. This skill does not mark the PR ready, does not push to `upstream`, does not push the meta-repo, and runs no formatter. Any failed command stops the run with its output, and the report says which steps completed.

## Submodule and files

The argument names the submodule. Without one, take the single submodule among `moose`, `blackbear`, `isopod` whose `git status --porcelain` is non-empty or whose branch is ahead of `devel`; with two or more candidates ask which one (AskUserQuestion); with none, refuse: nothing to ship. Show its `git status --short` in three groups: staged, unstaged, untracked. The commit takes what is staged (gold that `/moose-build` staged is already there) plus whatever the user adds in one AskUserQuestion listing the unstaged and untracked files: include all, staged only, or cancel. All three submodules have a pre-commit hook. In `moose` and `isopod` the hook runs `git clang-format` over staged C++ files and re-stages them, so the committed diff can differ from the shown one in formatting. In `blackbear` the hook rejects a commit whose staged C++ under `src`, `include`, `tests`, or `unit` is unformatted and prints the `git clang-format` fix; the user runs that command and re-stages, then the commit is retried (this skill runs no formatter).

## Commit message

Conventional subject under 72 characters (`feat(<area>): ...`, `fix(<area>): ...`). Body: from the `/moose-build` report when it is in the conversation (its suggested commit message, files, test counts, gold with observed values), otherwise a short body from the diff. The body ends with `refs #<issue>` or `closes #<issue>`; the number is the `issues` field of the new tests spec blocks. No `Co-Authored-By` or `Claude-Session` trailer, here or on the meta-repo commit (user rule in `~/.claude/CLAUDE.md`).

## Push, PR, pointer bump

```bash
git -C <worktree>/<sub> push -u origin <branch>
cd <worktree>/<sub> && gh pr create --repo idaholab/<app> --base next --head maxnezdyur:<branch> --draft \
  --title "<subject>" --body-file /tmp/moose-ship-<branch>-pr.md
git -C <worktree> add <sub>
git -C <worktree> commit -m "Bump <sub> to <short sha>"
```

`<branch>` is the submodule's current branch (the feature name); `<app>` is the submodule name. The PR body follows the app's `.github/PULL_REQUEST_TEMPLATE.md` (moose: Reason, Design, Impact) and carries the summary, the `refs #<issue>` line, the test counts, and the review counts (`required` and `suggested`, from the `/moose-build` report or `/tmp/moose-review-<label>.md`); no attribution trailer. The meta-repo commit stages only the gitlink; `specs/` and any other meta-repo change stay out. A rerun after a failure skips the steps that already happened: a clean tree with the branch ahead of `devel` means the commit exists; `git status -sb` up to date with `origin/<branch>` means the push happened; a hit from `gh pr list --repo idaholab/<app> --head <branch> --author @me` means the PR exists.

## Report

The PR URL, the submodule commit (short sha and subject), the meta-repo bump commit, the files committed, and any step skipped or failed with its output. The PR stays a draft; the user marks it ready in the GitHub UI.
