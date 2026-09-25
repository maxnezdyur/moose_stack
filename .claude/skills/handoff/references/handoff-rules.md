# Handoff writing rules

`<worktree>/specs/handoff.md` is the cross-session memory of one feature worktree, and
`campaigns/<id>/handoff.md` of one campaign, with the same seven sections. It sits beside
`specs/blueprint.md`, which holds the plan, and points at the build record, which holds the result.
It repeats neither.

## What goes where

| Section | Discipline | Holds |
|---|---|---|
| `## State` | rewrite | One paragraph: what is green, what is red, the exact command that shows it. |
| `## Next` | rewrite | Ordered `- [ ]` steps, each with its exact command or file. |
| `## Do not repeat` | append only | One line per dead end, dated. |
| `## Decisions` | append only | One line per decision, dated, with the rejected option. |
| `## Gotchas` | append only | Env, build and test quirks: wall-clock times, gold regeneration, flaky tests. |
| `## Map` | rewrite | Files touched and why, tests and gold, the review file, the build record path. |
| `## Sessions` | append only | One line per session: stamp, id or label, skill or mode, what it did. |

Rewrite means replace the section body and keep the heading. Append only means add lines at the end
of the section and never edit or delete a line that is already there, even one that now looks wrong:
a line that turned out to be wrong gets a second line saying so. Four sections are append only
because they are the only part of the file a later session cannot reconstruct.

Frontmatter: `feature` (`campaign` in a campaign), `updated` (a date, set by the writer when the content changes, never a
clock-driven rewrite of an otherwise unchanged file), and `sessions` (a count, bumped by one per
writing session).

## A good Do-not-repeat line

```
- 2026-09-12: tried `make -j 12` in moose; failed because the linker ran out of memory at
  libmoose.so; evidence specs/review-tri-remeshing.md; retry only if -j 6 also fails.
```

Four parts, in order: the date, what was tried verbatim, why it failed, where the evidence is, and
the condition under which it is worth trying again. A line with no evidence path and no retry
condition is a complaint, not a handoff. A line that says "tests failed" names nothing and saves
nobody any time.

## Budget

About 150 lines, whole file. `## State` is one paragraph. `## Next` is at most about eight steps.
The append-only sections grow, so when the file passes the budget, tighten `## Map` and `## Next`
first; never prune `## Do not repeat`, `## Decisions`, `## Gotchas` or `## Sessions`. Link to
evidence (a review file, a build record, a log path) and never paste it: the pasted copy goes stale
and the link does not.

## Who writes it

| Writer | When | Sections |
|---|---|---|
| `/moose-blueprint` | at write time | seeds the file from `references/handoff-template.md`, fills `## Map` from the blueprint's file list |
| `/moose-build` | in its final report | rewrites State, Next, Map; appends Do-not-repeat, Decisions, Sessions |
| `moose-feature-loop` | on STALLED or BLOCKED | hands `/moose-build` the State, Next and Do-not-repeat lines to write |
| `/moose-ship` | in its report | appends the PR URL to State and one Sessions line |
| `/handoff` | any time | seeds or updates the whole file from the conversation |
| `/campaign new` | after `campaign new` | seeds `campaigns/<id>/handoff.md` from the template with `campaign:` in place of `feature:`; appends one Sessions line |
| `/campaign learn` | after judging runs | rewrites State, Next, Map; appends Do-not-repeat per failed run, Decisions per hypothesis rewrite or withdrawn proposal, Sessions |
| `campaign-loop` | before it returns any status | the same sections as `/campaign learn`, plus one Sessions line per loop invocation |

Read back: the `session-context.sh` SessionStart hook prints State and Next at the start of every
session in the worktree, and `factory board` projects State, Next and the last three Do-not-repeat
lines onto the feature card, so the file is read even when nobody opens it.
