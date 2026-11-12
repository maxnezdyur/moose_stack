---
name: moose-ship
description: Commits the finished MOOSE feature in its submodule, pushes the branch to origin, opens a draft PR against next, and bumps the meta-repo submodule pointer. In an epic worktree (specs/epic.md) it ships one slice, which is the commit, the slice ref, and the draft PR when a place is free. The second human gate after /moose-build. Use for "/moose-ship [<submodule>]", "ship this feature", "open the PR", "commit and push the feature". Manual invoke only.
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

Turns the tree `/moose-build` left green into one commit in the submodule, a pushed branch, a draft PR on `idaholab/<app>`, and a meta-repo pointer bump, then prints the PR URL. It runs only inside a `/new-feature` worktree: walk up from the cwd to the directory whose `.git` is a file beside `moose/`, `blackbear/`, and `isopod/`; anywhere else, refuse and say why. This skill does not mark the PR ready, does not push to `upstream`, does not push the meta-repo, and runs no formatter. Any failed command stops the run with its output, and the report says which steps completed. In a worktree with `specs/epic.md`, read "In an epic worktree" below before the first step: it changes the order of the run, the commit message, the push, the PR body, the pointer bump, the rerun rules and the fix-ups.

## Submodule and files

The argument names the submodule. Without one, take the single submodule among `moose`, `blackbear`, `isopod` whose `git status --porcelain` is non-empty or whose branch is ahead of `devel`; with two or more candidates ask which one (AskUserQuestion); with none, refuse: nothing to ship. Show its `git status --short` in three groups: staged, unstaged, untracked, and list separately the paths that are run artifacts rather than the feature: test outputs (`*_out.e`, harness `*.json`, `*.csv` outside `gold/`), images outside `doc/content`, and a `largemedia` or other submodule pointer change. Those stay out unless the user names them; they have reached PRs before and had to be rebased out. A `.git/index.lock` left by a killed session, with no git process alive, is removed before staging. The commit takes what is staged (gold that `/moose-build` staged is already there) plus whatever the user adds in one AskUserQuestion listing the unstaged and untracked files: include all, staged only, or cancel. All three submodules have a pre-commit hook. In `moose` and `isopod` the hook runs `git clang-format` over staged C++ files and re-stages them, so the committed diff can differ from the shown one in formatting. In `blackbear` the hook rejects a commit whose staged C++ under `src`, `include`, `tests`, or `unit` is unformatted and prints the `git clang-format` fix; the user runs that command and re-stages, then the commit is retried (this skill runs no formatter).

## Commit message

Conventional subject under 72 characters (`feat(<area>): ...`, `fix(<area>): ...`). Body: from the `/moose-build` report when it is in the conversation (its suggested commit message, files, gold with observed values), otherwise a short body from the diff. The body says what the commit changes and why. Never put the local process in it. Put in no test count, no pass or skip tally, no test-run command, no gate result and no review count. Never reference the pull request from its own commits; reference the issue. The body ends with `refs #<issue>` or `closes #<issue>`; the number is the `issues` field of the new tests spec blocks, confirmed with `gh issue view <N> --repo idaholab/<app> --json title,state` before it is written anywhere: the title must describe this feature. A placeholder or unverifiable number stops the run with the question. The message ends with `Co-Authored-By: Claude <noreply@anthropic.com>`, here and on the meta-repo commit.

## Push, PR, pointer bump

```bash
git -C <worktree>/<sub> push -u origin <branch>
cd <worktree>/specs/gallery && gh pr create --repo idaholab/<app> --base next --head maxnezdyur:<branch> --draft \
  --title "<PR title>" --body-file /tmp/moose-ship-<branch>-pr.md \
  [--attach './<file>#<heading>' ...]
git -C <worktree> add <sub>
git -C <worktree> commit -m "Bump <sub> to <short sha>"
```

## PR title

The PR title is never the commit message. Write it as its own text, after the commit and before `gh pr create`. It is one plain sentence fragment that tells a reviewer what the change does, for example "Add arc-length continuation for tracing equilibrium paths past limit points". It starts with a capital letter. It has no conventional prefix (`feat(<area>):`, `fix:`), no issue number and no period at the end. It is 80 characters or fewer. Take the words from the blueprint title and the reason for the change (the issue, or the Reason of the PR body), not from the commit subject.

The title must always be better than the commit subject: a reviewer who reads only the title knows what changed and where. Name the object, system or module that changes, and say what it can do now or what was wrong before. A title such as "Fix bug", "Update kernel" or "Shell changes" is refused. When the first draft is the commit subject with other words, write it again from the user-visible effect of the change.

Check the title before `gh pr create` runs. Stop and rewrite it when it equals the commit subject, when it equals the commit subject without its prefix, or when it matches `^[a-z]+(\([^)]*\))?!?: `. Never pass `--fill`, `--fill-first` or `--fill-verbose` to `gh pr create`, and never omit `--title`: each of those makes `gh` take the title from the commit. These rules apply to `gh pr edit --title` too.

`<branch>` is the submodule's current branch (the feature name); `<app>` is the submodule name. The PR body takes its headings from the app's `.github/PULL_REQUEST_TEMPLATE.md` when it has one (moose: Reason, Design, Impact); isopod has none, so use those three. Read the issue first with `gh issue view <N> --repo idaholab/<app>`. When the issue gives the reason and the design, keep the body short and do not restate the issue. Fill a template heading only when the issue lacks that content, and leave out a heading that has nothing to add. Do not add boilerplate headings such as "Summary" or "Test plan". The body carries the summary and the `refs #<issue>` line; it ends with the Claude Code attribution line. Impact, when it is present, says what changes for a user or a downstream app: new or changed parameters, objects, API, defaults, gold files and doc pages. Make every claim in the body match the current code. State a downstream failure only after you observe it. State each known consequence that a reviewer must weigh. Use the term and the notation that MOOSE source and documentation already use, and replace a phrase that reads as machine-drafted with the plain MOOSE wording: write "recompute", not "refresh", and "results are unchanged", not "bit-for-bit". Never put the local process in the body. Put in no test count, no pass or skip tally, no test-run command, no gate result and no review count. Do not mention the local review, the findings it made or the pipeline that built the change. CI shows the test results. Those records stay in the `/moose-build` report and in `<worktree>/specs/review-<label>.md`. It is short, in plain ASCII punctuation with no em dashes. After the summary and any template headings it carries `## Proof` (below). Any further comment on the PR (more figures, tables, replies to reviewers) is drafted for the user and posted only when they say so. The meta-repo commit stages only the gitlink; `specs/` and any other meta-repo change stay out. A rerun after a failure skips the steps that already happened: a clean tree with the branch ahead of `devel` means the commit exists; `git status -sb` up to date with `origin/<branch>` means the push happened; a hit from `gh pr list --repo idaholab/<app> --head <branch> --author @me` means the PR exists.

## Proof

`## Proof` is what a reviewer can see without running the change, from `<worktree>/specs/proof/proof.md` and the blueprint's `## Proof`. One `### <title>` per proof from `proof.md`, in this order: the before, then the after. One sentence says what it shows and the precondition it met ("three uniform refinements, one rank"). An image is a `![<heading>](./<file>)` line, attached with `--attach './<file>#<heading>'` (`gh` 2.99 or later; `~/.claude/skills/playwright-cli/references/pr-attachments.md`), with the `Look at:` sentence of its `gallery.md` section. Attach only `.png`, `.jpg`, `.jpeg`, `.gif`, `.svg` and `.mp4` files under 10 MB, only the ones a proof names, and run `gh pr create` from `<worktree>/specs/gallery/` so that each `./<file>` matches its `--attach` argument (the `cd` above). A text proof (a convergence table, an iteration and timing comparison, a CSV or exodus excerpt, console lines) goes in inline: a fenced block of at most 20 lines, inside `<details><summary><title></summary>` when it is longer than 8 lines. Cut it to the lines that show the claim. The repository is public: never paste a home path, a host name, a token or an internal URL; replace them with `<redacted>` or a scope-relative path. Leave out every proof that `proof.md` or the build report marks `weak` or `skipped`, and name it in the report instead. Never put a test result, a gate result or a CIVET run here; CI shows those. With `Kind: none`, with no `proof.md` (a build from before `## Proof`), or with no proof that is `ok`, omit the section. When some uploads fail, `gh` still creates the PR; report each failed file with its error. To add a figure to a PR that exists, run `gh pr edit <N> --repo idaholab/<app> --attach './<file>#<alt>'` from the gallery.

## Fix-ups after the PR exists

This section is for an ordinary feature worktree; in an epic worktree, step 10 of "In an epic worktree" replaces it. A change to the PR (a CIVET failure, a review comment, a loosened tolerance) carries no code comment explaining the fix; the PR conversation is where that goes. The state of the PR decides the form:

- **Draft, and no reviewer has commented.** Amend the fix into the existing commit and push with `git push --force-with-lease`. Check both facts first: `gh pr view <N> --repo idaholab/<app> --json isDraft,reviews,comments`.
- **In review** (marked ready, or a reviewer has commented). Add the fix as a new commit and push with a plain `git push`, never with a force flag. The reviewers asked for no force-push during review, so that they can see what changed. The commit has a conventional subject under 72 characters, a body that ends with `refs #<issue>`, and the Claude trailer. Squash only when a maintainer asks, and then ask the user before the force-push.
- **Reply drafts.** Draft a reply for each review conversation, bot conversations included, before the user asks for another review. For a conversation that a fix answers, write one or two sentences: what changed, and the short SHA of the commit. For a question, answer it with the reasoning or the evidence. Print the drafts for the user. Post nothing; the user posts them.
- **Wording corrections.** When a reviewer corrects a wording, apply the correction at every place that states the same thing: the doc page, the code comment, the error message and the parameter doc string.
- **Stale text.** After the fix commit, read again every comment and doc sentence that describes what the commit changed, and correct each statement that the commit made false. Check every claim in the PR body the same way. When a claim is now false, draft the corrected body for the user.
- **Rebase.** Never rebase or force-push a PR in review without asking the user first. A conflict with `next` is the one reason to do it. When the user agrees, draft a PR comment that says the push is a rebase only.

Redo the meta-repo pointer bump after either form. A CIVET failure is triaged with the `civet-ci-failures` skill before any fix: a job that also fails on other authors' PRs is CIVET's environment, not the branch, and gets no code change and no push.

## In an epic worktree

`<worktree>/specs/epic.md` exists, so this run ships one slice of a chain (`/moose-epic`). The
sections above apply, with the changes below. `<epic>` is the worktree name and the branch of
`<moose>`, which is `<worktree>/moose`. The submodule is `moose`. The stack script owns the slice
refs and every push. Resolve it with these lines:

```bash
cfg="${MOOSE_FACTORY_CONFIG:-$HOME/.config/moose-factory/config.toml}"
meta_repo="$(sed -n -e 's/[[:space:]]*#.*$//' -e 's/^[[:space:]]*meta_repo[[:space:]]*=[[:space:]]*//p' "$cfg" 2>/dev/null | head -n 1 | tr -d '"')"
meta_repo="${meta_repo:-$HOME/projects/moose_stack}"; meta_repo="${meta_repo/#\~/$HOME}"
STACK="$meta_repo/scripts/stack"
```

Shell variables do not persist between Bash calls, so put these lines at the start of each call
that uses `$STACK`. Always call it as `"$STACK" -C <moose> <verb>`. Exit 1 is a refusal: print its
message and stop.

1. **Publish first.** Run `"$STACK" -C <moose> status`, and stop when it prints `chain: BROKEN` or
   a `problem:` line. `<pub>` is the lowest slice whose state is `sealed`: it has a ref and no
   pull request. When there is one and `"$STACK" -C <moose> slots` prints more than 0, publish
   `<pub>` (steps 6 and 7), report, and stop. Commit nothing and seal nothing in that run. When
   there is none, or `slots` prints 0, go on.
2. **The slice.** `<id>` is the `slice:` key of `specs/blueprint.md`. A blueprint with no `slice:`
   key was kept from before the epic; then `<id>` is the first row of `## Slices` with no ref.
   Before the commit, check that `<id>` is the id of the first row of `## Slices` in
   `specs/epic.md` that has no ref `epic/<epic>/<id>`
   (`git -C <moose> rev-parse --verify --quiet refs/heads/epic/<epic>/<id>` prints nothing). When it is
   not, stop and commit nothing. A blueprint whose slice has a ref is shipped: name
   `/moose-epic next`. When there is no blueprint and nothing to publish, refuse: nothing to ship.
   When parked `WIP` commits are at the top of the branch, run `"$STACK" -C <moose> unpark`
   before you show the files.
3. **Files.** A slice carries no newsletter entry while it is sealed or draft. When
   `git -C <moose> status --porcelain -- modules/doc/content/newsletter` prints a path, stop and
   tell the user to remove that change. `/moose-epic fix <id>` adds the entry before the user
   marks the pull request ready.
4. **Commit message.** The body ends with `refs #<N>`, where `<N>` is the `issue` of
   `specs/epic.md`, confirmed with `gh issue view` as above. `issue: pending` stops the run. Add
   `closes #<M>` only for an issue of this slice alone that the user named. Never write
   `closes #<N>` for the epic issue: the user closes it by hand. Each tests spec block of the
   slice carries the epic issue in `issues`.
5. **Commit and seal.** Make the one commit as above. Then run
   `"$STACK" -C <moose> seal --expect <id>`. It creates the ref `epic/<epic>/<id>` and prints the id.
   It refuses, and makes no ref, when the id that it would give is not `<id>`. Then decide: when
   `"$STACK" -C <moose> slots` prints 0, stop and say: "Slice <id> is sealed and not published:
   two pull requests are open. Run `/moose-ship` again when one merges." When it prints more
   than 0, `<pub>` is `<id>`: go on.
6. **Publish `<pub>`.** At most two pull requests of one epic are open.

   ```bash
   "$STACK" -C <moose> push <pub>
   cd <gallery of <pub>> && gh pr create --repo idaholab/moose --base next --head maxnezdyur:epic/<epic>/<pub> --draft \
     --title "<PR title of <pub>>" --body-file /tmp/moose-ship-<epic>-<pub>-pr.md \
     [--attach './<file>#<heading>' ...]
   ```

   Never run `git push` yourself here. The first push of a slice makes a new fork branch and
   rewrites nothing. Never pass `--yes` to a stack command in this skill: the script asks for it
   only before a force push to a pull request in review, and that is a decision for the user in
   `/moose-epic`. If `push` refuses for that reason, print the message and stop. The records of
   `<pub>` (`proof/`, the
   gallery) are in `<worktree>/specs/slices/<pub>/` when `/moose-epic next` archived them, and in
   `<worktree>/specs/` otherwise. Write the title by the rules of "PR title" above, from the
   title of the `<pub>` row of `## Slices`. It is never the subject of the commit at
   `epic/<epic>/<pub>`; read that subject with
   `git -C <moose> log -1 --format=%s epic/<epic>/<pub>` only to check that the title differs.
7. **PR body of `<pub>`.** Add two things after the summary. First, when the slice below `<pub>`
   is not merged, the line `Depends on #<P>. Review the commits after it.` `<P>` is the pull
   request of the slice below, from the `pr` column of the status table. Omit the line for the
   lowest slice and when the slice below is merged. Second, the line `Slice <k> of <N>.` and a
   numbered list of the titles of all rows of `## Slices`, with a mark on this slice. Put no
   pull request number of a slice above this one in the body: it goes stale, and nothing updates
   a PR body. Put no commit hash, no local path and no parked work in it.
8. **No pointer bump.** Skip the `Bump <sub>` commit. A restack rewrites the slice commits, and a
   recorded gitlink would point at a commit on no branch.
9. **Rerun.** The status table is the record of what happened. A slice with a ref has its commit
   and its seal. The `fork` column says `not pushed` until the push is done. The `pr` column
   holds the pull request when it exists. Step 1 picks up a slice that an earlier run sealed and
   did not publish.
10. **Fix-ups.** A fix to a slice that has a ref goes through `/moose-epic fix <id>`, never
    through an amend and never through `git push --force-with-lease`. A slice in review takes the
    fix as a new commit; reviewers asked for no force-push during review. Never run
    `gh pr ready`.
11. **Report and handoff.** Add the slice id, the ref, "published as <PR URL>" or "sealed, not
    published", and the next step: `/moose-epic next` starts the next slice. No meta-repo bump
    commit is listed. Write the handoff lines as below.

## Report

The PR URL, the submodule commit (short sha and subject), the meta-repo bump commit, the files committed, the proofs put in the body and the figures attached (and each weak, skipped or missing proof, with `/moose-build --verify-only` as the way to capture it again), and any step skipped or failed with its output. The PR stays a draft; the user marks it ready in the GitHub UI. Then run
`~/projects/moose_stack/factory/factory board` (absolute path; no `factory/` exists in this worktree) so the
board picks up the new PR, and say in one line that the card moved.
Finally append the PR URL to `## State` in `<worktree>/specs/handoff.md` (one sentence, after what is
already there) and one `## Sessions` line, `- <date> <time> <label> /moose-ship: opened <PR URL>`, and
bump `sessions`. Rewrite nothing else in that file: its other sections are append-only or belong to
`/moose-build`.
