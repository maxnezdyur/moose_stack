---
name: moose-epic
description: Plans and runs an epic, which is a chain of dependent MOOSE pull requests built in one feature worktree with one commit and one PR per slice. Mode new grills the cut lines and writes specs/epic.md. Mode status shows the slice table and the single next move. Mode next archives the finished slice and starts the blueprint of the next one. Mode fix puts a review or CI fix into a shipped slice through the stack script. Use for "/moose-epic new <idea>", "/moose-epic status", "/moose-epic next", "/moose-epic fix s1", "split this into several PRs", "stack these PRs", "start the next slice", "fix the review comment on slice 1", "where is the stack".
argument-hint: "new <idea> | status | next | fix <id> [<what to fix>]"
effort: high
---

# /moose-epic

An epic is a chain of slices. Each slice needs code from the slice below it, and each slice is
one pull request. One worktree holds the whole chain:

- `<worktree-root>` is the `/new-feature` worktree. `<epic>` is its directory name.
- `<moose>` is `<worktree-root>/moose`. Its branch `<epic>` holds every slice in order. This
  branch is never pushed.
- Each finished slice has a local ref `epic/<epic>/<id>` (`<id>` is `s1`, `s2`, ...; the ref of
  slice `s2` of the epic `modal` is `epic/modal/s2`). The fork branch
  of the same name is the head of its pull request. No worktree ever checks out a slice ref.
- `specs/epic.md` is the plan of the chain. `specs/blueprint.md` is the blueprint of the slice
  that is built now. `specs/slices/<id>/` holds the records of each finished slice.

This skill writes `specs/epic.md`, moves files inside `specs/`, writes the handoff, and calls the
stack script. It builds nothing and it marks no PR ready.

## The stack script

`$STACK` owns every git write on the branch `<epic>`, except the one commit that `/moose-ship`
makes. Resolve it by absolute path, because a worktree has no `scripts/stack` of its own:

```bash
cfg="${MOOSE_FACTORY_CONFIG:-$HOME/.config/moose-factory/config.toml}"
meta_repo="$(sed -n -e 's/[[:space:]]*#.*$//' -e 's/^[[:space:]]*meta_repo[[:space:]]*=[[:space:]]*//p' "$cfg" 2>/dev/null | head -n 1 | tr -d '"')"
meta_repo="${meta_repo:-$HOME/projects/moose_stack}"; meta_repo="${meta_repo/#\~/$HOME}"
STACK="$meta_repo/scripts/stack"
```

Shell variables do not persist between Bash calls, so put these lines at the start of each call
that uses `$STACK`. Always call it as `"$STACK" -C <moose> <verb>`. These are the verbs:

| Verb | Does |
|---|---|
| `status` | Prints one row per sealed slice (`id`, `commit`, `n`, `state`, `pr`, `fork`), the work above the top slice, `chain: ok` or `chain: BROKEN`, and one `problem:` line per fault. The states are `sealed`, `draft`, `in review`, `merged`, `closed`, `unknown` (GitHub did not answer) and `merge-race`. `--no-gh` uses no network. |
| `base [<id>]` | Prints the diff base of a slice: the ref of the slice below, or the fork point. It is always an ancestor of HEAD. Without `<id>` it is the slice that is built now. `--sha` prints the commit. |
| `seal --expect <id>` | Makes the ref of a new slice from the one commit above the top slice and prints its id. `/moose-ship` runs it; this skill does not. |
| `slots` | Prints the number of free pull request places: 2 minus the open pull requests of the epic. |
| `park`, `unpark` | Saves and restores unfinished work as two `WIP` commits. Each prints a line and exits 0 when there is nothing to do. |
| `fix <id>` | Puts the staged index into slice `<id>` and moves every slice above it. It does not park: it refuses when a path is neither staged nor parked. `fix --continue` and `fix --abort` resume or cancel a restack that stopped, also one that `sync --rebase` started. |
| `push [<id>...]` | Publishes the slices that changed, all or none. `--dry-run` prints what it would push. |
| `sync` | Fetches `upstream/next`, reports each merged slice, and tests for a conflict with `next`. It rebases nothing. `sync --rebase` rebases the chain onto `upstream/next`. |
| `adopt <id>` | Takes the fork's version of a slice into the local chain. `--ours` keeps the local slice. |

Exit codes: 0 is success. 1 is a refusal: stderr starts with `stack: refused:` and names the
recovery. 2 is a usage error. 3 means the script stopped on a conflict.

On exit 1, show the message and stop. Do the recovery only when it is a `stack` command. Never
work around a refusal with a git command. When `$STACK` is not an executable file, stop and say
which path is missing; do not do its work with git.

## Rules for every mode

In an epic worktree, never run these by hand: `git rebase`, `git commit --amend`, `git stash`,
`git reset` on the branch `<epic>`, `git push` with any force flag, and `gh pr ready`.

- A rebase or an amend outside the script leaves the slice refs behind. The next fix then
  reports success and reaches no pull request.
- A stash is shared with every other worktree of the `moose` repository.
- The script pushes all refs or none, and it checks the fork first. A push by hand can
  overwrite a commit that a maintainer added.
- Only the user marks a pull request ready, in the GitHub user interface.

**The `--yes` flag.** `fix`, `push` and `sync --rebase` refuse to rewrite a slice whose pull
request is in review, closed, or in an unknown state, because the rewrite is a force push. A
fast-forward never needs the flag. Never pass `--yes` on your own. When the script refuses for
this reason, show the user the slices and pull requests that the message names and say why each
would be force-pushed. Remind the user that they promised a reviewer not to force-push during
review. Pass `--yes` only after the user says yes to that specific force-push, and only to the
one command that was refused.

## Modes

The first word of `$ARGUMENTS` picks the mode. With no argument, run `status`.

| `$ARGUMENTS` | Mode |
|---|---|
| `new <idea>` | Plan the chain and write `specs/epic.md`. |
| `status` | Show the stack and the next move. |
| `next` | Archive the finished slice. Start the blueprint of the next row. |
| `fix <id> [<what to fix>]` | Put a fix into a shipped slice. |

## Preconditions

Walk up from the cwd to the directory whose `.git` is a file beside `moose/`, `blackbear/` and
`isopod/`. Outside one, refuse: "Run /new-feature first; /moose-epic only runs inside a feature
worktree."

- `status`, `next` and `fix` need `specs/epic.md`. Without it, refuse: "No epic here. Run
  `/moose-epic new <idea>`."
- `next` and `fix` change files. Refuse them when `<worktree-root>/.factory-lease` names a live
  session that is not this one. Print that the workspace is held and stop.
- Refuse `fix` also while a `moose-feature-loop` that this session started for `/moose-build` is
  running. The loop and its children change the same tree. Wait for its terminal status.

## Mode `new`

Read `references/epic-format.md` first. It holds the format, the six cut tests and the checks.

1. Refuse when `specs/epic.md` exists: "An epic plan exists. Amend it as
   `references/epic-format.md` says." Refuse when `git -C <moose> branch --show-current` is not
   `<epic>`.
2. When `specs/blueprint.md` exists, ask one time with `AskUserQuestion`: keep it as the
   blueprint of the first slice, or cancel. If the user keeps it, the first row of the plan
   describes what that blueprint builds.
3. Take the idea from `$ARGUMENTS`. When it is empty, ask for it.
4. Ask for the epic issue number. Confirm it with
   `gh issue view <N> --repo idaholab/moose --json title,state`. With no issue yet, write
   `issue: pending` and tell the user that `/moose-ship` refuses until it is set.
5. Propose the slices. Spawn `moose-scout` only for a fact that decides a cut line: whether a
   class exists, which file two slices both change, which class a slice derives from. Spawn at
   most four, in one message, each with one angle.
6. Grill the cut lines and the order with `AskUserQuestion`. Ask these questions:
   - Which slice carries the most review risk?
   - Which slice can be dropped if upstream objects?
   - Which slice must land first to unblock the others?
   - Does each slice need the one below it?
7. Apply the six cut tests to each row. A slice that needs nothing from the slice below it goes
   to `## Related features`, not into the chain. Tell the user about each row that you moved or
   cut again, and why.
8. Write `specs/epic.md` in the shape of `references/example-epic.md`. Run the "Checks before you
   stop" list of the format document, and correct each failure.
9. Seed the handoff when `specs/handoff.md` is absent. Copy
   `<worktree-root>/.claude/skills/handoff/references/handoff-template.md` (fall back to
   `~/projects/moose_stack/.claude/skills/handoff/references/handoff-template.md`). Put the epic
   name in place of `<feature>`, set `updated` to today and `sessions: 1`. Write `## State` (the
   number of slices; no slice is built) and `## Next` (the first step is `/moose-epic next`).
10. Run `~/projects/moose_stack/factory/factory board`.

Tell the user: the path of `specs/epic.md`, the rows in one line each, each related feature, and
the next step. The next step is to read the plan and then run `/moose-epic next`, which starts
the blueprint of the first slice.

## Mode `status`

1. Run `"$STACK" -C <moose> status` and show its output as printed.
2. For each slice whose `pr` column holds a number `<P>`, read the review state:
   `gh pr view <P> --repo idaholab/moose --json isDraft,reviewDecision,mergeable`.
3. For the lowest open pull request, when it is a draft, read two more facts. Its checks:
   `gh pr checks <P> --repo idaholab/moose` exits 0 when each check passed. Its newsletter entry:
   `git -C <moose> diff --name-only "$("$STACK" -C <moose> base <id> --sha)" epic/<epic>/<id> -- modules/doc/content/newsletter`
   prints a path when the slice has one.
4. Add the rows of `## Slices` that have no ref, with the state `planned`.
5. Name one next move. Take the first row of this table that applies:

| What you see | Next move |
|---|---|
| The script refused, or it prints `chain: BROKEN` | The recovery command that the script printed |
| A `problem:` line says `restack-in-progress` | `"$STACK" -C <moose> fix --continue`, or `fix --abort` |
| A slice has the state `merge-race` | The slice merged at a commit that is not the local one. Stop and report both commits to the user. Never rebase and never move a ref to repair it. |
| A `note:` line says `merged on GitHub; run stack sync to fetch` | `"$STACK" -C <moose> sync`. It fetches `upstream/next` and rebases nothing. |
| The `fork` column says `DRIFT` (the `problem:` line says `stack-drift`) | Show the user what the fork holds, then `"$STACK" -C <moose> adopt <id>` (see "Sync and adopt") |
| A `problem:` line says `push-pending` | Show `"$STACK" -C <moose> push --dry-run`, ask the user, then `"$STACK" -C <moose> push`. The lowest open slice must be level with the fork before the user marks its pull request ready; after that the same push is a force-push in review. |
| A slice has the state `unknown`, or a `problem:` line says `fork unreachable` | Check the network and `gh auth status`, then run `status` again |
| A slice has the state `closed` | Tell the user that its pull request is closed and not merged. Do nothing more |
| A pull request merged since the last sync | `"$STACK" -C <moose> sync` |
| A pull request has requested changes or a red check that the change caused | `/moose-epic fix <id>` |
| The lowest open pull request is a draft, each check passed, and the slice has no newsletter entry | `/moose-epic fix <id>` to add the newsletter entry. Then tell the user that the pull request is ready for them to mark ready. |
| A slice has the state `sealed`, and `"$STACK" -C <moose> slots` prints more than 0 | `/moose-ship`, which publishes it |
| `specs/blueprint.md` has `status: draft` | Answer the review page, then approve the blueprint |
| `specs/blueprint.md` has `status: approved` | `/moose-build` |
| `specs/blueprint.md` has `status: built` and its slice has no ref | `/moose-ship` |
| The slice of `specs/blueprint.md` has a ref, or no blueprint exists, and a planned row remains | `/moose-epic next` |
| Each row is merged | Close the epic issue by hand. Run `~/projects/moose_stack/factory/factory board` before a teardown: each board run copies `specs/epic.md` and `specs/slices/` into `Artifacts/<epic>/`, and the teardown refuses when a file has no copy. |

## Mode `next`

1. Find the slice to archive. It is the `slice:` key of `specs/blueprint.md`. A blueprint with no
   `slice:` key belongs to the first row of `## Slices` that has no directory under
   `specs/slices/`. When `specs/blueprint.md` is absent, there is nothing to archive: go to
   step 5.
2. Refuse unless that slice is sealed:
   `git -C <moose> rev-parse --verify --quiet refs/heads/epic/<epic>/<id>` must print a commit. If it
   does not, say: "Slice <id> has no ref. Run `/moose-build`, then `/moose-ship`."
3. Refuse when `specs/slices/<id>/blueprint.md` exists: that archive is complete. Never write
   over an archive.
4. Move the records of the slice in one step. Run this from `<worktree-root>`. It runs under
   `bash`, because a pattern with no match stops `zsh`. `blueprint.md` moves last, so a run that
   stopped part way has no `blueprint.md` in the archive, and you run the step again. A second
   run after a complete one changes nothing:

   ```bash
   bash -s <<'ARCHIVE'
   set -e
   A=specs/slices/<id>; mkdir -p "$A/gallery" specs/gallery
   for f in specs/blueprint-page.html specs/blueprint.html specs/review-*.md specs/proof specs/verify \
            .claude/cache/moose-build-*.json; do
     [ -e "$f" ] || continue
     [ -e "$A/${f##*/}" ] && { echo "archive: $A/${f##*/} exists; not moved: $f" >&2; exit 1; }
     mv "$f" "$A/"
   done
   if [ ! -e "$A/gallery/gallery.md" ]; then
     find specs/gallery -mindepth 1 -maxdepth 1 -exec mv {} "$A/gallery/" \;
     [ -e "$A/gallery/gallery.md" ] || : > "$A/gallery/gallery.md"
     printf '# Gallery: %s\n' "<epic>" > specs/gallery/gallery.md
   fi
   for b in code test doc ad dry newobj; do
     rm -f "/tmp/moose-review-<epic>-$b.json" "/tmp/moose-review-<epic>-$b-retry.json"
   done
   if [ -e specs/blueprint.md ]; then mv specs/blueprint.md "$A/"; fi
   ARCHIVE
   ```

   Each path has a reason:

   | Path | Why it moves |
   |---|---|
   | `specs/blueprint.md`, `blueprint-page.html`, `blueprint.html` | The plan and the review page of the finished slice. The next slice needs the path. |
   | `specs/review-*.md` | The review file is named after the worktree, so the next build would write over it. `/moose-ship` reads its counts. |
   | `specs/proof/`, `specs/verify/` | `/moose-ship` puts the proofs in the PR body. The next slice has its own. |
   | `.claude/cache/moose-build-*.json` | The build record. A `GOAL_MET` record of the old slice would let `/moose-build --verify-only` pass for the new one. |
   | `specs/gallery/*` | The figures of the finished slice. `specs/gallery/gallery.md` is written again, empty, because the board reads it. |
   | `/tmp/moose-review-<epic>-<bucket>.json` and `-retry.json` (deleted) | The review label is the worktree name. `review-merge.sh` merges the findings of a reviewer file that an earlier run left under the same label. |

   `specs/epic.md` and `specs/handoff.md` stay. The handoff is one file for the whole epic.
5. Find the next row: the first row of `## Slices` with no ref `epic/<epic>/<id>` in `<moose>`. When
   no row remains, write the handoff (step 6), say that each slice is built, and stop. The work
   that remains is review fixes (`/moose-epic fix <id>`) and `"$STACK" -C <moose> sync`.
6. Write the handoff. Rewrite `## State`: the archived slice (when step 4 ran), its commit, its
   pull request or "sealed, no PR yet", and the next row. Rewrite `## Next`: the blueprint of the next row, then
   `/moose-build`, then `/moose-ship`. Append one `## Sessions` line, add 1 to `sessions`, and
   set `updated`. Do not change a line in an append-only section.
7. Start the blueprint: `Skill(moose-blueprint)`. The idea is the row and its joins: the title,
   the "a user can" sentence, the tests that prove it, each seam it uses (the contract and the
   owner), each seam it must add, and each cross-slice decision that applies. `/moose-blueprint`
   reads `specs/epic.md` itself and writes `epic:` and `slice:` into the blueprint front matter.
8. Run `~/projects/moose_stack/factory/factory board`.

## Mode `fix <id>`

Use this mode for a change to a slice that has a ref: a review comment, a CIVET failure, a
loosened tolerance. Triage a CIVET failure with the `civet-ci-failures` skill first. A job that
also fails on other authors' pull requests gets no fix and no push.

A change to the slice that is built now needs no fix mode: edit the working tree.

1. Run `"$STACK" -C <moose> status`. Stop on a refusal, on `chain: BROKEN`, and on a `problem:`
   line. If slice
   `<id>` has no ref, stop: it is not shipped. If slice `<id>` is merged, stop: put the change
   in the slice that is built now. If its state is `merge-race`, `closed` or `unknown`, stop and
   follow the `status` table. Note the state of slice `<id>` from the table; step 5 uses it.
2. Run `"$STACK" -C <moose> park`. It saves the unfinished work as `WIP` commits.
3. Make the change in `<moose>`. The tree holds every slice and the parked work. Change only
   what the comment asks for. Add no code comment that explains the fix; the PR conversation is
   the place for that. Run no build and no test before step 5: a run leaves files in the tree.
4. Stage each path of the fix by name: `git -C <moose> add <path> ...`. The script does not park
   for you, and it refuses when a path is neither staged nor parked. So
   `git -C <moose> status --porcelain` must show staged paths only.
5. Run the fix. The state of the slice decides the form:
   - Sealed or draft: `"$STACK" -C <moose> fix <id>`. The script squashes the fix into the
     slice commit.
   - In review (the user marked the PR ready): write the commit message to
     `/tmp/moose-epic-<epic>-<id>-fix.txt`, then run
     `"$STACK" -C <moose> fix <id> --append -F /tmp/moose-epic-<epic>-<id>-fix.txt`. The script
     adds a commit at the end of the slice, and the push is a fast-forward. The message is a
     conventional subject under 72 characters, a body that ends with `refs #<epic issue>`, and
     the line `Co-Authored-By: Claude <noreply@anthropic.com>`.
   - Pass `--squash` for a slice in review only when the user says that a maintainer asked for a
     squash. That squash is a rewrite, so the script refuses it without `--yes`.
   - A fix moves every slice above `<id>`. When one of those has a pull request in review, the
     script refuses and names it. Follow "The `--yes` flag" above.
6. On exit 3, the script stopped on a conflict in a slice above the fix. Resolve only the
   conflict hunks, keep the intent of both sides, stage the files, and run
   `"$STACK" -C <moose> fix --continue`. Repeat for each stop. When a resolution is not clear,
   run `"$STACK" -C <moose> fix --abort`, then `"$STACK" -C <moose> unpark`, and report the
   conflict.
7. Show the proof that the script prints: for each slice above the fix, whether its content
   changed. A slice whose content changed with no conflict that you resolved is a defect: stop
   and report it.
8. Record the amendment. Append one line to `## Amendments` of `specs/slices/<id>/blueprint.md`,
   or of `specs/blueprint.md` when slice `<id>` is not archived yet:
   `- <date>: review fix (<squashed|appended>): <what changed>; asked in #<PR> by <reviewer or CI job>`.
9. Verify at the top of the stack. Spawn one `moose-test-runner` with the scope of the slice
   (the `repo` of its blueprint), the build authorization, `--re=` with the test names of slice
   `<id>` (from the test plan of its blueprint) and of each test that the fix changed, and these
   gates:

   ```bash
   B="$("$STACK" -C <moose> base <id>)"
   bash <worktree-root>/.claude/skills/moose-build/scripts/gates.sh moose sqa --base "$B"
   bash <worktree-root>/.claude/skills/moose-build/scripts/gates.sh moose ascii --base "$B"
   ```

   Add `bash <worktree-root>/.claude/skills/moose-docs/scripts/docs.sh moose smoke --diff "$B"`
   when the fix changed a `.md` file. The local run tests slice `<id>` together with every slice
   above it and the parked work; CIVET tests the slice alone. When a failure comes only from
   parked work, say so, do not repair it here, and ask the user whether to push.
10. Ask before the push. Show `"$STACK" -C <moose> push --dry-run`, then ask with
    `AskUserQuestion`. On yes, run `"$STACK" -C <moose> push`. The script pushes only the slices
    whose own content changed. A draft above the fix that only moved waits for its own next
    push. Each push starts a full CIVET run on that pull request. The dry run prints
    `(REWRITE)` for a force push, and `(new)` or `(fast-forward)` otherwise. When the push refuses because a rewrite goes to a pull request in review,
    follow "The `--yes` flag" above.
11. Run `"$STACK" -C <moose> unpark`.
12. Append one `## Sessions` line to the handoff and run
    `~/projects/moose_stack/factory/factory board`.

Report: the slice, squashed or appended, the files, the proof lines, the test counts and the gate
results, the refs pushed (or "not pushed"), and each step that failed with its output.

**Newsletter entry.** A slice carries no newsletter entry while it is sealed or draft.
`/moose-blueprint` plans none, `/moose-build` writes none, and `/moose-ship` stops when a
newsletter file is changed. Before the user marks the lowest open pull request ready, run this
mode on that slice and add its entry to
`moose/modules/doc/content/newsletter/<year>/<year>_<month>.md` for the current month. The slice
is still a draft, so the script squashes the entry into its commit. The `status` mode prompts
this step.

## Sync and adopt

- `fix`, `push` and `sync` read the fork first. They refuse when the fork is not reachable.
  Offline, only `status --no-gh`, `base`, `park` and `unpark` are of use.
- `"$STACK" -C <moose> sync` fetches `upstream/next` and reports the slices that merged. Run it
  when a pull request of the epic merges. It rebases nothing. The local ref of a merged slice
  stays. It prints `CONFLICT with upstream/next in: <files>` when the chain conflicts with
  `next`.
- `"$STACK" -C <moose> sync --rebase` rebases the chain onto `upstream/next`. Run it only for a
  conflict with `next`, and only after the user says yes: it rewrites each open slice, and each
  push starts a CIVET run. It needs a clean tree, so run `park` first. On exit 3, resolve as
  step 6 of mode `fix` says. When it refuses because a slice is in review, follow "The `--yes`
  flag".
- **Merge race.** A slice that merged upstream at a commit that is not the local one has the
  state `merge-race` after a `sync`, and `fix` and `sync` refuse. This version does not repair
  it. Stop and report the two commits to the user. Never rebase, and never move a slice ref by
  hand.
- `"$STACK" -C <moose> adopt <id>` takes the fork's version of a slice. A maintainer can push to
  a pull request branch. Before you adopt, show the user what the fork holds: the `problem:`
  line of `status` gives the fork commit, so run `git -C <moose> fetch origin epic/<epic>/<id>`, then
  `git -C <moose> log --oneline epic/<epic>/<id>..FETCH_HEAD`. Adopt after the user says yes.
- **Update branch.** When a maintainer pressed "Update branch", the fork branch holds a merge
  commit and `adopt <id>` refuses it. The way out replaces the fork's branch with the local
  slice and rebases the chain, so ask the user first. On yes, run
  `"$STACK" -C <moose> adopt <id> --ours`, then `"$STACK" -C <moose> sync --rebase`, then the
  push of mode `fix` step 10. The yes to this plan is not a yes to `--yes`: when a step refuses
  for a pull request in review, follow "The `--yes` flag".

## The other skills in an epic worktree

Each of these skills reads `specs/epic.md` and changes its own steps. This table is a pointer;
the rule is in the skill.

| Skill | In an epic worktree |
|---|---|
| `/moose-blueprint` | Seeds the slice blueprint from the next row and its seams. |
| `/moose-build` | Takes the diff base from `stack base`, so each gate and the review read one slice. |
| `/moose-ship` | Makes the slice commit, seals it, and opens the draft PR when a place is free. |
| `/feature-sync` | Reports drift. Offers no rebase of `moose`. |
| `/moose-auto` | Does not run an epic. |
