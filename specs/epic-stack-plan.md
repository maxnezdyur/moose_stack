# Epics: a plan for a chain of dependent pull requests

Status: built 2026-11-10, uncommitted. Steps 1 to 6 of the build order are done. Step 7, the pilot
on a real epic, has not run. No skill has run in a real session, and no writing verb of the
script has run on the real `moose` repository. Commit the work to `main` before the pilot: a new
worktree takes its `.claude` from git.

A red-team run tested the design before the build: 36 findings, none refuted. Three independent
reviews tested the build: 21 defects in the script, 9 in the projector, and 6 blocker or major
defects in the skills. Each one is fixed, or is listed under "Known limits". Each script and
projector fix has a test.

## The problem

One feature is one worktree, one branch and one PR. A large change needs several PRs that merge in
order. The median time from open to merge is 24 days, so three PRs done one after the other take
two to three months. Work on PR 3 must start while PR 1 is in review.

The stack that exists today was made by hand and has drifted. #34249 and #34250 carry copies of the
commits of #33820 under different SHAs. #33820 gained commits later that the copies do not have.
`modal-participation` holds a hand copy of the `eigen-all-modes` commit. This plan removes the hand
copy: a slice exists once, and one tool moves everything above it.

## Constraints

Each row was verified against the repository or GitHub.

| Constraint | Consequence |
|---|---|
| PR heads live in the fork `maxnezdyur/moose`. The base must be `next` on `idaholab/moose`. | PR k shows slices 1 to k. The PR body says "Depends on #N". |
| `idaholab/moose` allows merge commits only. | A merged slice keeps its SHA. The PR above it needs no rebase. |
| Reviewers asked for no force-push during review (#33820, #33937). | A slice in review grows by appended commits. A rewrite of it needs your explicit yes. |
| Maintainers push to contributor branches (#30898, `reviewing.md:30`). | The fork ref can differ from the local ref. The tool checks before it writes. |
| Each push to a PR runs 58 CIVET jobs, changed or not. | Push a slice only when its own content changed. |
| Draft PRs get CI but no review. | One draft above the bottom PR is enough. |
| 37 branches share the moose object store through worktrees. | `git rebase --update-refs` is unsafe here. |
| `git stash` is shared across all worktrees of one repository. | Never stash. Park work as commits. |
| One issue can back several PRs. Precheck needs an issue in one commit per PR. | One epic issue serves the chain. |
| Nothing under `specs/` in a worktree is tracked. | The board copies the epic plan into the vault on each run. |

## The unit: an epic

An epic is a chain. Slice k+1 needs code from slice k. Work that needs nothing from the slice
below is not a slice: make it an ordinary feature and list it under `## Related features`. This
version supports a straight line only. A fan-out (two slices on one base) is the first follow-up.

```
upstream/next ── s1 ── s2 ── s3 ── WIP        branch <epic>, one worktree, one build
                 │     │     │
                 PR    PR    sealed           branches epic/<epic>/s1, epic/<epic>/s2, epic/<epic>/s3
               ready  draft  (local)
```

- One worktree at `~/projects/moose-worktrees/<epic>`, made by `/new-feature <epic>`.
- One linear branch `<epic>` in the `moose` checkout. This branch is never pushed.
- One local branch `epic/<epic>/s<n>` per sealed slice. No worktree ever checks out a slice
  branch. The fork branch of the same name is the PR head.
- The prefix `epic/` is the marker. A feature name cannot contain a slash, so a head that starts
  with `epic/` is a slice on every machine, with or without the worktree.
- A slice is the commit range from the slice branch below it to its own branch.
- A sealed slice keeps its id `s<n>` for ever. `specs/epic.md` numbers the unsealed rows in row
  order after the highest sealed id, and numbers them again when an unsealed row is added,
  dropped or moved.
- Unfinished work above the top slice is dirty files, or two parked commits named `WIP index` and
  `WIP tree`.

## The life of a slice

| State | Meaning | How the tool knows |
|---|---|---|
| planned | A row in `specs/epic.md` | No slice branch |
| building | `specs/blueprint.md` is for this slice | First row with no slice branch |
| sealed | One commit and a branch; no PR yet | Branch exists; no PR for that head |
| draft | PR open as draft | GitHub `isDraft` is true |
| in review | You marked the PR ready | GitHub `isDraft` is false |
| merged | The slice is in `next` | The slice commit is an ancestor of `upstream/next` |
| unknown | GitHub did not answer | Treated as in review for every rewrite |
| merge-race | The slice merged at a different SHA from the local one | The pushed SHA is in `upstream/next` and the local SHA is not |

Rules:

1. A slice is one commit while it is sealed or draft. A fix is squashed into that commit.
2. A slice in review takes a fix as a new commit at the end of its range. The push is a
   fast-forward. Squash only when a maintainer asks.
3. Only you mark a PR ready, in the GitHub user interface. No skill and no script runs
   `gh pr ready`.
4. Keep at most two PRs open per epic: the lowest unmerged slice and one draft above it. Slices
   above that stay sealed until a place opens.
5. Every slice commit says `refs #<epic issue>`. A slice can also close its own issue. No commit
   closes the epic issue; you close it by hand.
6. Each slice carries the documentation and the showcase that its own PR needs.
7. A sealed or draft slice carries no newsletter entry. Before you mark the lowest open PR ready,
   `/moose-epic fix <id>` adds the entry for the current month.
8. No skill and no script passes `--yes` by itself. `--yes` permits a force-push to a PR in
   review, and only you give it, for one named push.

## The stack script

`~/projects/moose_stack/scripts/stack` owns every git write on an epic branch, except the one
commit that `/moose-ship` makes. Skills call it by absolute path as `"$STACK" -C <moose> <verb>`,
with the path resolved from `config.toml`. A frozen `.claude` in a worktree then always reaches the
current script. The tests are in `scripts/tests/`: 95 tests, each in scratch repositories.

| Verb | Does |
|---|---|
| `status [--json] [--no-gh]` | Prints the slice table: id, commit, commit count, state, PR, drift. Then the parked and dirty work, `chain: ok` or `chain: BROKEN <reason>`, and each `problem:` line |
| `base [<id>] [--sha]` | Prints the diff base for a slice: the slice branch below it, or a fork-point SHA. The result is always an ancestor of HEAD |
| `seal [--expect <id>]` | Makes the slice branch for the one commit above the top slice. Prints the id. With `--expect`, refuses and makes nothing when the id differs |
| `slots` | Prints the free PR places: 2 minus the open PRs of the epic |
| `park`, `unpark` | Saves and restores unfinished work as two commits. Both do nothing and exit 0 when there is nothing to do |
| `fix <id> [--squash \| --append -m <msg> \| -F <file>]` | Puts the staged index into slice `<id>`, moves every slice above it, prints the proof |
| `fix --continue`, `fix --abort` | Resumes or cancels after a conflict |
| `push [<id>...] [--all] [--dry-run]` | Publishes the slices that changed, all or nothing. A first publish needs the id |
| `sync [--rebase] [--no-fetch]` | Records merged slices. Reports a conflict with `upstream/next`. Rebases only with `--rebase` |
| `adopt <id> [--ours]` | Takes the fork's version of a slice into the chain, or keeps the local one and saves the fork's commit |

Exit codes: 0 is success. 1 is a refusal: stderr starts with `stack: refused:` and names the
recovery. 2 is a usage error. 3 means that the script stopped on a conflict.

A fix is five steps: `park`, edit, `git add <paths>`, `fix <id>`, `unpark`. `fix` does not park
for you; it refuses when unparked work exists.

The rules of the script:

1. **Work on an epic only.** Refuse a checkout that is not an epic: the worktree has
   `specs/epic.md`, or the branch has a slice branch. Never act on the meta-repo.
2. **Check the chain first.** Before every writing verb, verify that each slice branch is an
   ancestor of the next and of `<epic>`. If not, refuse and name the offending ref.
3. **Check the fork first.** Before `fix`, `push` and `sync`, compare each fork ref with the SHA
   recorded at the last push. If they differ, refuse and name `stack adopt`. These three verbs
   refuse when the fork is unreachable.
4. **Check the lease.** Every writing verb refuses when another live session holds
   `<worktree>/.factory-lease`.
5. **Move the refs in the rebase.** Never use `--update-refs`. The script writes the rebase todo
   itself: `pick` and `fixup` lines by full SHA, and one `update-ref` line per slice branch. The
   refs do not move on a conflict stop or on an abort.
6. **Compute the base.** The base is the parent of the lowest unmerged slice. Refuse when the
   range from the base to `<epic>` holds a merge commit.
7. **Choose the fix by state.** Sealed or draft: squash. In review: append and fast-forward.
   Merged: refuse, and tell the session to put the change in the current slice.
8. **Ask before a rewrite of a PR in review.** `fix`, `push` and `sync --rebase` refuse to
   rewrite a slice that is in review, unknown or closed unless `--yes` is given. A fast-forward
   never needs it.
9. **Prove the result.** After a restack, verify that the fix is in the target slice. Compare
   the content of each slice above it, old against new, and print each slice that changed. The
   comparison counts whitespace, binary and mode changes.
10. **Push all or nothing.** Use `--atomic`, push `<sha>:<ref>`, and use
    `--force-with-lease=<ref>:<recorded SHA>` for each ref. Record the pushed SHA in
    `refs/stack/<epic>/pushed/s<n>` only after the push succeeds.
11. **Push only what changed.** Push a slice when its own content changed or when it gained a
    commit. A draft that was only moved waits for the next push of its own. Two slices never
    wait: the target of a fix, and the lowest open slice. `status` prints `push-pending` while
    the lowest open slice is behind, because a later push would be a force-push in review.
12. **Refuse an unsafe push.** Refuse when a `WIP`, `fixup!` or `squash!` commit is below a ref,
    or when a rebase is in progress.
13. **Park everything.** `park` makes two commits: `WIP index` from the index, then `WIP tree`
    after `git add -A`. If the second step fails, it removes the first. `unpark` removes exactly
    those two and restores the staged, unstaged and untracked sets.
14. **Sync onto `next`.** `upstream/devel` can be behind a merged slice. A rebase onto it makes a
    second copy of that slice.
15. **Stop on the merge race.** When a slice merged at a SHA that is not the local one, stop and
    print both SHAs. This version does not repair that case.
16. **Keep a way back.** The script writes its record before it changes anything. `fix --abort`
    restores the branch and every slice branch, also after the rebase finished.
17. **Guard the namespace.** `seal` and a first `push` refuse when a branch `epic` or
    `epic/<epic>` exists, because git cannot hold it beside `epic/<epic>/s1`.

## The blueprints

An epic has two levels of plan.

**`specs/epic.md`** is written once and is one or two pages. Its front matter uses the key
`epic:`, never `feature:`, so the board does not read it as a slice blueprint. The format is in
`.claude/skills/moose-epic/references/epic-format.md`.

| Section | Holds |
|---|---|
| Goal | What the chain delivers |
| Shared physics | Written once for all slices |
| `## Slices` | One row per slice, in order: id, title, what it needs, what a user can do when it merges alone, which tests prove that |
| `## Seams` | One sentence of contract per interface that one slice leaves for the next, and the slice that owns it. No signatures: the code at the slice branch is the signature. |
| Cross-slice decisions | Only the decisions that touch more than one slice |
| `## Related features` | The slugs of independent features that belong to the same theme |
| Out of scope | For the epic |
| `## Amendments` | Append only |

Two tests decide a cut. A row that cannot say what a user can do when it merges alone is a wrong
cut. A slice adds a seam only if its own tests exercise the seam; otherwise the seam moves to the
slice that first uses it.

**`specs/blueprint.md`** is the blueprint of the slice being built. Its format does not change; its
front matter gains `epic:` and `slice:`. Write it just in time: the current slice is approved, and
every later slice is only a row in `specs/epic.md`.

`/moose-epic next` moves the finished slice out of the way in one step that is safe to run twice.
It moves this set into `specs/slices/<id>/`, with `blueprint.md` last:

- `blueprint-page.html`, `blueprint.html`
- every `review-*.md`
- `proof/` and `verify/`
- `.claude/cache/moose-build-*.json`
- the files in `specs/gallery/`
- `blueprint.md`

It deletes the review files `/tmp/moose-review-<epic>-*.json`, because the next review would merge
their findings. It then rewrites the State and Next sections of the handoff. A later fix to a
shipped slice is recorded in `specs/slices/<id>/blueprint.md` under `## Amendments`.

## The skill `/moose-epic`

`/moose-epic` is the one entry point. It never runs a rebase itself; it calls the stack script.

| Mode | Does |
|---|---|
| `new` | Asks about the cut lines and the order, applies the cut tests, writes `specs/epic.md` |
| `status` | Shows `stack status` with the PR state from GitHub, and names one next move |
| `next` | Archives the finished slice, then starts `/moose-blueprint` for the next row with its seams |
| `fix <id>` | Makes a review fix to a shipped slice through `stack fix`, records the amendment, shows the proof, runs the gates, and pushes when you say yes |

In an epic worktree, no session runs these by hand: `git rebase`, `git commit --amend`,
`git stash`, `git reset` on the epic branch, `git push` with a force flag, and `gh pr ready`.

## Changes to the existing skills

| Skill | Change |
|---|---|
| `/moose-build` | Each gate, the docs smoke, the proof check, the review snapshot and the feature loop take the diff base from `stack base` in an epic worktree. `gates.sh`, `docs.sh` and `review-snapshot.sh` refuse a base that is not a mainline branch and not an ancestor of HEAD. |
| `/moose-ship` | In an epic worktree: publish an earlier sealed slice first when a place is free, and then stop. Otherwise make the commit, run `stack seal --expect <id>`, and open the draft PR only when `stack slots` is above 0. The PR body says "Depends on #N. Review the commits after it." and "slice k of N". No `Bump moose` commit. A later fix goes through `/moose-epic fix`. |
| `/moose-blueprint` | Takes the slice row and its seams from `specs/epic.md`. Plans no newsletter entry. Checks that the slice tests exercise each seam it adds. |
| `/feature-sync` | When `specs/epic.md` exists, offers no rebase of `moose` and prints the `stack sync` command. |
| `/feature-remove` | Judges an epic per slice, because the epic branch is never pushed. Deletes the slice branches and the `refs/stack/<epic>/` refs only when every slice is merged and you confirm. |
| `/new-feature` | Refuses the name `epic`, and a name that has slice branches left from an earlier epic. |
| `/moose-auto` | Does not run an epic. |
| `CLAUDE.md` | In an epic worktree, a PR fix goes through `stack fix`, never through an amend. |

## Changes to the factory

| Place | Change |
|---|---|
| `tool/probe.py` | A PR head `epic/<epic>/s<n>` is a slice and nothing else is. A slice joins the worktree card `<epic>` when that card has `specs/epic.md`. With no worktree, the slices of one epic form one PR-only card `<epic>`, merged slices included. A slice head never becomes a card id or a file name. `epic.md` and `handoff.md` are never the blueprint. |
| `tool/derive.py` | "Mark ready" is offered only for the lowest open slice while it is a draft. An epic card prints `scripts/stack sync` in place of a plain rebase. A flag on an epic card names the lowest slice that has the problem. An epic worktree is `merged` only when every slice in `## Slices` has merged. |
| `tool/ext_epic.py` (new) | Copies `specs/epic.md` and `specs/slices/` into `Artifacts/<epic>/` on each board run, up to `epic_rescue_max_mb` (20 by default). Adds the `## Epic` section to the note: the plan, the slices in order with their PR state, and the limits. Records a collision when a card `<epic>` exists and is not an epic; such a slice joins no card and writes no gate. |
| `tool/ext_teardown.py` | Blocks teardown when an epic file has no identical copy in `Artifacts/`. Judges unsaved work per slice when the checkout is on the epic branch, and lists the slice branches that teardown leaves behind. |
| `factory doctor` | Two new rows: `scripts/stack` runs for each epic worktree, and each slice PR is on the card of its epic. |
| `factory/tests/test_epic.py` (new) | 92 tests. The projector had no test before. |

With no epic present, the board output is byte-identical to the output before the change. This was
checked in a scratch vault with a frozen clock, and again on the real vault after the patch was
applied: only the "measured N min ago" lines moved.

## Known limits

- The `ship` grant and the `pr_ready` grant are per card. The grants of the first slice cover
  every later slice, so the board asks for neither again.
- The second machine shows one card for the epic with its slice PRs, and no slice table from
  `specs/epic.md`, because the plan is in the worktree on the first machine.
- `stack sync` does not repair a merge race. It stops and prints both SHAs.
- A fork branch that a maintainer rebased, or updated with "Update branch", cannot be adopted
  cleanly. The way out is `adopt <id> --ours`, then `sync --rebase`, each after your yes.
- An appended fix to a slice in review moves the drafts above it. Those drafts are not pushed
  until their own content changes or you run `push --all`.
- `fix`, `push` and `sync` need the fork reachable.
- A slice that is not the target of a fix, and whose lines only moved inside a file during a
  conflict resolution, reads as unchanged and waits for `push --all`.

## Not in this version

In the order to add them:

1. A second worktree forked off a slice (`/new-feature <x> --base epic/<epic>/s<n>`), with the
   fork point recorded in a ref.
2. The slice table on the card with the flags `needs-restack`, `stack-drift` and `fixup-pending`.
3. Gates per slice.
4. An `epic_approved` grant.
5. `/moose-epic recut`: split or drop a shipped slice.
6. The stack table in the session-start hook.
7. Repair of the merge race in `stack sync`.
8. An epic that spans two repositories.

## Build order

1. Done. The test lab for the stack script: `scripts/tests/test_stack.py`.
2. Done. `scripts/stack`.
3. Done. The `specs/epic.md` format and `/moose-epic new` and `status`.
4. Done. The changes to the existing skills and `CLAUDE.md`.
5. Done. The projector changes, applied to the live tree.
6. Done. `/moose-epic next` and `fix`.
7. Not done. Commit to `main`. Then run the upcoming epic as the pilot. Record each failure in
   this file.

## Not verified

- Whether the GitHub page of PR 2 shows only slice 2 after slice 1 merges. The git diff does.
- No skill has run in a real session.
- No writing verb of the script has run on the real `moose` repository. `status` ran there
  read-only in 0.9 s, wrote nothing, and `sync` refused the non-epic checkout.
- The real `git clang-format` step in `fix --continue`, and the real pre-commit hook during `park`.
- `factory teardown --yes` on an epic. Only the plan was tested.
- `Board.html` with several slice PRs on one card.
- Whether a branch pushed to the fork with no PR starts CIVET.

## Decisions taken

| Date | Decision |
|---|---|
| 2026-11-10 | One worktree per epic, not one per slice |
| 2026-11-10 | Plain git and one script; no stacking tool |
| 2026-11-10 | Slice blueprints are written just in time |
| 2026-11-10 | `/moose-epic` is the one entry point; there is no separate `/moose-stack` skill |
| 2026-11-10 | Each slice carries its own documentation and showcase |
| 2026-11-10 | One commit while a slice is draft; appended commits once it is in review |
| 2026-11-10 | This version handles a straight chain only |
| 2026-11-10 | Slice branches are named `epic/<epic>/s<n>`, so that the second machine can group them |
| 2026-11-10 | At most two open PRs per epic |
| 2026-11-10 | The board copies the epic plan into the vault, because `specs/` is not tracked |
| 2026-11-10 | Do not push slice branches to `idaholab/moose`; the fork-only convention stays |

## Where each rule came from

| Finding | Rule |
|---|---|
| `--update-refs` moves unrelated branches and skips a checked-out slice ref without an error | Script rule 5 |
| The push updates one ref and rejects the next; after a fetch it overwrites a foreign commit | Script rules 3 and 10 |
| A plain rebase makes the next fix a silent no-op | Script rule 2; `/feature-sync`; the board's sync command |
| `commit -am` parks no new file, and the unpark then removes a slice | Script rule 13 |
| No way to resume after a conflict | `fix --continue`, `fix --abort` |
| `--keep-base` can pick a base below the fork point | Script rule 6 |
| Two slices with the same subject: the fixup lands in the wrong one | Script rule 5 |
| A slice merges while the local copy is amended | Script rules 7 and 15 |
| A sync onto `devel` makes a second copy of a merged slice | Script rule 14 |
| PR k holds slices 1 to k, so draft state is the only merge guard | Slice rules 3 and 4; the mark-ready rule on the board |
| A restack orphans the `Bump moose` gitlink | `/moose-ship` skips the bump |
| Reviewers asked for no force-push during review | Slice rules 1, 2 and 8; script rules 7 and 8 |
| A plain push could force-push a PR in review (build review) | Script rule 8 |
| A whitespace-only fix read as "unchanged" (build review) | Script rule 9 |
| Maintainers push to PR heads | Script rule 3; `adopt` |
| Each push reruns 58 CIVET jobs | Script rule 11; slice rule 4 |
| Draft PRs get no review | Slice rule 4 |
| Each slice edits the same monthly newsletter file | Slice rule 7 |
| Code that only a later slice uses fails coverage | The seam test |
| The modal family is a graph, not a line | The chain rule; `## Related features` |
| Signatures in `## Seams` go stale in review | Seams are one sentence, no signature |
| "The last slice closes the issue" fails when the plan changes | Slice rule 5 |
| The plan and the script numbered slices differently (build review) | The numbering rule; `seal --expect` |
| A sealed slice could not be published later (build review) | `/moose-ship` publishes first |
| A head such as `plain-s3` joined an ordinary card (build review) | The `epic/` namespace |
| One lane per card: `merged` and teardown after slice 1 | The epic lane rule in `tool/derive.py` |
| Gates are per feature and never ungrant | Known limit; follow-up 3 |
| The probe can take `epic.md` as the blueprint | `epic:` front matter; the probe skips `epic.md` and `handoff.md` |
| Gates and reviews diff against `devel` | `stack base`; the `/moose-build` change |
| Build records and reviews are keyed by the worktree name | The archive set in `/moose-epic next` |
| Archive on ship breaks ship reruns and fix-ups | Archive at `next`, not on ship |
| The stack script does not reach a frozen `.claude` | Call it by absolute path |
| Nothing under `specs/` is tracked | `tool/ext_epic.py`; the teardown blocker |
